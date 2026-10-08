"""Kuratoren: oppdaterer Kunnskapsbasen etter hvert svar, med fakta fra Tråden og stil fra mine endringer.

Agenten skriver hele filer via schema; tower validerer stiene, skriver og committer (eget git-repo i basen).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tower.agent import Runner, med_nytt_forsøk
from tower.kanal import Person, Tråd
from tower.kunnskapsbase import frontmatter, utvalg
from tower.prompt import tråd_tekst
from tower.utkast import Utkast

INSTRUKS = (Path(__file__).parent / "instrukser" / "kurator.md").read_text()
SCHEMA = {
    "type": "object",
    "properties": {
        "endringer": {"type": "array", "items": {
            "type": "object", "properties": {"fil": {"type": "string"}, "innhold": {"type": "string"}},
            "required": ["fil", "innhold"], "additionalProperties": False}},
    },
    "required": ["endringer"],
    "additionalProperties": False,
}
KATALOGER = ("personer", "org", "prosjekter")
SLUG = re.compile(r"[a-z0-9æøå]+(?:-[a-z0-9æøå]+)*")
TAK = 60_000  # byte berørte filer i prompten; kuratoren skriver hele filer, så de må med uavkortet


@dataclass(frozen=True)
class KuratorJobb:
    """Én Kurator-kjøring i køen. `svar_på` er Meldingen jeg svarte på (dedupe mellom send og poll)."""

    id: int
    tråd_id: str
    svar_på: str
    sendt: str  # teksten jeg sendte
    sendt_versjon: int | None  # None: besvart utenfra, ingen diff
    fra_versjon: int  # Utkast-versjoner i (fra_versjon, til_versjon] hører til denne kjøringen
    til_versjon: int
    status: str  # venter | feilet | ferdig
    feil: str | None = None


def gyldig_sti(fil: str) -> str | None:
    """Normalisert sti relativt til basen, eller None: `stil.md` eller `<katalog>/<slug>.md`."""
    fil = fil.strip().removeprefix("./").removeprefix("kunnskapsbase/")
    if fil == "stil.md":
        return fil
    deler = fil.split("/")
    if len(deler) == 2 and deler[0] in KATALOGER and deler[1].endswith(".md") and SLUG.fullmatch(deler[1][:-3]):
        return fil
    return None


def filoversikt(rot: Path) -> str:
    """Alle filer med frontmatter på én linje, mot duplikater."""
    linjer = []
    for k in KATALOGER:
        for p in sorted((rot / k).glob("*.md")):
            meta = frontmatter(p.read_text(errors="replace"))
            felt = "; ".join(f"{n}: {', '.join(v) if isinstance(v, list) else v}" for n, v in meta.items())
            linjer.append(f"{k}/{p.name}" + (f"  ({felt})" if felt else ""))
    return "\n".join(linjer)


def berørte(rot: Path, t: Tråd, meg: Person, tak: int = TAK) -> str:
    deler, brukt = [], 0
    for sti in utvalg(rot, t, meg):
        del_ = f"## {sti.relative_to(rot)}\n{sti.read_text(errors='replace').strip()}\n"
        if brukt + len(del_.encode()) > tak:
            continue
        deler.append(del_)
        brukt += len(del_.encode())
    return "\n".join(deler)


def versjon_tekst(v: Utkast, diff: bool) -> str:
    linjer = [f"<versjon nr=\"{v.versjon}\" status=\"{v.status}\">"]
    if v.instruks:
        linjer.append(f"<instruks>{v.instruks}</instruks>")
    if diff and v.tekst:
        linjer.append(f"<agentens_tekst>\n{v.tekst}\n</agentens_tekst>")
        if v.redigert is not None and v.redigert != v.tekst:
            linjer.append(f"<min_redigering>\n{v.redigert}\n</min_redigering>")
    if v.research:
        linjer.append("<research>\n" + "\n".join(f"- {f.faktum} ({f.kilde})" for f in v.research) + "\n</research>")
    return "\n".join(linjer + ["</versjon>"])


def prompt(t: Tråd, jobb: KuratorJobb, versjoner: list[Utkast], rot: Path, meg: Person, nå: datetime) -> str:
    """Utenfra (ingen sendt versjon): bare Research og instrukser fra versjonene, ikke tekstene."""
    diff = jobb.sendt_versjon is not None
    vs = [v for v in versjoner if jobb.fra_versjon < v.versjon <= jobb.til_versjon
          and (v.instruks or v.research or diff and v.tekst)]
    deler = [f"I dag: {nå.astimezone().date().isoformat()}",
             f"<alle_filer>\n{filoversikt(rot)}\n</alle_filer>",
             f"<berørte_filer>\n{berørte(rot, t, meg)}\n</berørte_filer>",
             tråd_tekst(t)]
    if vs:
        deler.append("<utkast_versjoner>\n" + "\n".join(versjon_tekst(v, diff) for v in vs) + "\n</utkast_versjoner>")
    kilde = f"versjon {jobb.sendt_versjon}" if diff else "skrevet utenfor tower, ingen utkast-diff"
    deler.append(f"<sendt kilde=\"{kilde}\">\n{jobb.sendt}\n</sendt>")
    return "\n\n".join(deler)


async def kurater(runner: Runner, t: Tråd, jobb: KuratorJobb, versjoner: list[Utkast], rot: Path, meg: Person,
                  nå: datetime) -> tuple[list[tuple[str, str]], int, float]:
    """Endringer (sti, innhold) med gyldig sti, antall forkastet og kost. Kaster `AgentFeil` etter nytt forsøk."""
    r = await med_nytt_forsøk(runner, INSTRUKS, SCHEMA, prompt(t, jobb, versjoner, rot, meg, nå))
    endringer, forkastet = {}, 0
    for e in r.svar["endringer"]:
        sti = gyldig_sti(e["fil"])
        if sti and e["innhold"].strip():
            endringer[sti] = e["innhold"].strip() + "\n"
        else:
            forkastet += 1
    return list(endringer.items()), forkastet, r.usd


# --- git i basen

KURATOR = Person("tower kurator", "kurator@tower.invalid")


def git(rot: Path, *args: str, hvem: Person | None = None, inn: str | None = None) -> str:
    """Isolert fra global config som kan forstyrre (hooks, signering)."""
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1"}
    if hvem:
        env |= {"GIT_AUTHOR_NAME": hvem.navn, "GIT_AUTHOR_EMAIL": hvem.adresse,
                "GIT_COMMITTER_NAME": hvem.navn, "GIT_COMMITTER_EMAIL": hvem.adresse}
    return subprocess.run(["git", "-C", str(rot), "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                           *args], env=env, input=inn, capture_output=True, text=True, check=True).stdout


def sikre_repo(rot: Path) -> None:
    rot.mkdir(parents=True, exist_ok=True)
    if not (rot / ".git").exists():
        git(rot, "init", "-q", "-b", "main")


def commit_manuelt(rot: Path, meg: Person) -> bool:
    """Mine ucommittede endringer først, som `manuelt: endringer`. True hvis noe ble committet."""
    sikre_repo(rot)
    if not git(rot, "status", "--porcelain"):
        return False
    git(rot, "add", "-A")
    git(rot, "commit", "-q", "-m", "manuelt: endringer", hvem=meg)
    return True


def skriv_og_commit(rot: Path, endringer: list[tuple[str, str]], emne: str, tråd_id: str) -> tuple[list[str], str | None]:
    """Skriver filer med nytt innhold og committer dem. (filer, commit-sha); ingen commit uten endringer."""
    sikre_repo(rot)
    skrevet = []
    for sti, innhold in endringer:
        p = rot / sti
        if not p.resolve().is_relative_to(rot.resolve()):  # symlenke ut av basen
            continue
        if p.is_file() and p.read_text(errors="replace") == innhold:
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        ny = not p.exists()
        p.write_text(innhold)
        skrevet.append((sti, ny))
    if not skrevet:
        return [], None
    filer = [s for s, _ in skrevet]
    git(rot, "add", "--", *filer)
    body = "\n".join(f"{'ny' if ny else 'endret'}: {s}" for s, ny in skrevet)
    melding = f"kurator: {' '.join(emne.split())[:60]}\n\n{body}\n\nTråd: {tråd_id}\n"
    git(rot, "commit", "-q", "-F", "-", "--", *filer, hvem=KURATOR, inn=melding)
    return filer, git(rot, "rev-parse", "--short", "HEAD").strip()


def siste_commit(rot: Path) -> tuple[str, datetime] | None:
    """Emne og tid for siste kurator-commit."""
    if not (rot / ".git").exists():
        return None
    try:
        ut = git(rot, "log", "-1", "--author=kurator@tower.invalid", "--format=%s%x00%cI").strip()
    except subprocess.CalledProcessError:  # ingen commits ennå
        return None
    if not ut:
        return None
    emne, tid = ut.split("\0")
    return emne, datetime.fromisoformat(tid)
