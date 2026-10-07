"""Deterministisk oppslag i Kunnskapsbasen for agentene. Ingen verktøy: tower velger filene.

Rekkefølge: `stil.md`, personer på adresse, så på eksakt navn, org fra domenet, prosjekter som lenker til
disse, prosjekter nevnt i emne eller tekst. Filer som ikke får plass under taket hoppes over.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tower.kanal import Person, Tråd

TAK = 20_000  # byte


@dataclass(frozen=True)
class Fil:
    sti: Path
    slug: str
    meta: dict[str, str | list[str]]

    def liste(self, nøkkel: str) -> list[str]:
        v = self.meta.get(nøkkel)
        return [] if v is None else [v] if isinstance(v, str) else v


def frontmatter(tekst: str) -> dict[str, str | list[str]]:
    """YAML-delmengden kuratoren skriver: `nøkkel: verdi`, `nøkkel: [a, b]` og blokklister."""
    if not tekst.startswith("---\n"):
        return {}
    meta: dict[str, str | list[str]] = {}
    nøkkel = None
    for linje in tekst[4:].splitlines():
        if linje.strip() == "---":
            break
        if nøkkel and linje.lstrip().startswith("- "):
            meta.setdefault(nøkkel, [])
            if isinstance(meta[nøkkel], list):
                meta[nøkkel].append(_ren(linje.lstrip()[2:]))
            continue
        k, sep, v = linje.partition(":")
        if not sep or linje[:1].isspace():
            continue
        nøkkel, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            meta[nøkkel] = [_ren(x) for x in v[1:-1].split(",") if x.strip()]
        elif v:
            meta[nøkkel] = _ren(v)
    return meta


def _ren(v: str) -> str:
    return v.strip().strip("\"'")


def _filer(rot: Path, katalog: str) -> list[Fil]:
    return [Fil(p, p.stem, frontmatter(p.read_text(errors="replace")))
            for p in sorted((rot / katalog).glob("*.md"))]


def _nevnt(ord_: str, tekst: str) -> bool:
    return bool(ord_) and re.search(rf"(?<!\w){re.escape(ord_)}(?!\w)", tekst, re.IGNORECASE) is not None


def utvalg(rot: Path, t: Tråd, meg: Person) -> list[Path]:
    """Filene som er relevante for Tråden, i prioritert rekkefølge."""
    if not rot.is_dir():
        return []
    meg_adr = meg.adresse.lower()
    deltakere = {p for m in t.meldinger for p in (m.fra, *m.til, *m.cc) if p.adresse.lower() != meg_adr}
    adresser = {p.adresse.lower() for p in deltakere if p.adresse}
    navn = {p.navn.lower() for p in deltakere}
    domener = {a.rsplit("@", 1)[1] for a in adresser if "@" in a}

    personer = _filer(rot, "personer")
    på_adresse = [f for f in personer if adresser & {a.lower() for a in f.liste("adresser")}]
    på_navn = [f for f in personer if f not in på_adresse and navn & {n.lower() for n in f.liste("navn")}]
    orger = [f for f in _filer(rot, "org") if domener & {d.lower() for d in f.liste("domener")}]

    p_slugs = {f.slug for f in på_adresse + på_navn}
    o_slugs = {f.slug for f in orger}
    prosjekter = _filer(rot, "prosjekter")
    lenket = [f for f in prosjekter if set(f.liste("org")) & o_slugs or set(f.liste("personer")) & p_slugs]
    tekst = "\n".join([t.emne, *(m.tekst for m in t.meldinger)])
    nevnt = [f for f in prosjekter if f not in lenket and any(
        _nevnt(o, tekst) for o in (f.slug, f.slug.replace("-", " "), *f.liste("navn")))]

    stil = [rot / "stil.md"] if (rot / "stil.md").is_file() else []
    return stil + [f.sti for f in på_adresse + på_navn + orger + lenket + nevnt]


def oppslag(rot: Path, t: Tråd, meg: Person, tak: int = TAK) -> str:
    """Utvalget som tekst til agenten, med sti over hver fil. Tom streng når basen er tom."""
    deler, brukt = [], 0
    for sti in utvalg(rot, t, meg):
        del_ = f"## {sti.relative_to(rot)}\n{sti.read_text(errors='replace').strip()}\n"
        n = len(del_.encode())
        if brukt + n > tak:
            continue
        deler.append(del_)
        brukt += n
    return "\n".join(deler)
