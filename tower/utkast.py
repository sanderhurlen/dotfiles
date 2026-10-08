"""Utkast-agenten: svar Sander kan sende nesten uendret. Manglende fakta blir `[[plassholder]]`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from tower.agent import Runner, Verktøy, med_nytt_forsøk
from tower.kanal import Tråd
from tower.prompt import tråd_tekst

INSTRUKSER = Path(__file__).parent / "instrukser"
INSTRUKS = (INSTRUKSER / "utkast.md").read_text()
INSTRUKS_VERKTØY = INSTRUKS + "\n" + (INSTRUKSER / "utkast-verktøy.md").read_text()
SCHEMA = {
    "type": "object",
    "properties": {
        "tekst": {"type": "string"},
        "sjekk": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tekst", "sjekk"],
    "additionalProperties": False,
}
# Med verktøy: Research videre til Kuratoren.
SCHEMA_RESEARCH = {
    **SCHEMA,
    "properties": {**SCHEMA["properties"], "research": {"type": "array", "items": {
        "type": "object", "properties": {"faktum": {"type": "string"}, "kilde": {"type": "string"}},
        "required": ["faktum", "kilde"], "additionalProperties": False}}},
    "required": [*SCHEMA["required"], "research"],
}
PLASSHOLDER = re.compile(r"\[\[(.+?)\]\]", re.DOTALL)

# Utkast-tilstander. genererer → klart → sendt | forkastet | utdatert, pluss feilet.
GENERERER, KLART, SENDT, FORKASTET, UTDATERT, FEILET = "genererer", "klart", "sendt", "forkastet", "utdatert", "feilet"
ÅPNE = (GENERERER, KLART, FEILET)  # blir utdatert ved ny Melding


@dataclass(frozen=True)
class Research:
    faktum: str
    kilde: str  # `visense/repo/sti:linje` eller `kunnskapsbase/fil`: relativt til foreldren av en tillatt katalog


@dataclass(frozen=True)
class Utkast:
    tråd_id: str
    versjon: int
    melding_id: str  # siste Melding da utkastet ble bestilt
    status: str
    tekst: str = ""
    sjekk: tuple[str, ...] = ()
    feil: str | None = None
    instruks: str | None = None  # regenereringsinstruks
    redigert: str | None = None  # min redigering; `tekst` beholdes som agenten skrev den (Kurator-diff)
    research: tuple[Research, ...] = ()

    @property
    def gjeldende(self) -> str:
        """Teksten som vises og sendes."""
        return self.tekst if self.redigert is None else self.redigert

    @property
    def plassholdere(self) -> list[str]:
        return plassholdere(self.gjeldende)


def plassholdere(tekst: str) -> list[str]:
    return PLASSHOLDER.findall(tekst)


LINJE = re.compile(r"(:\d+(?:-\d+)?)$")


def kilde(rå: str, kataloger: tuple[Path, ...]) -> str | None:
    """Kilden normalisert, eller None når den ikke er en fil under en av `kataloger` (symlenker og `..` løses)."""
    m = LINJE.search(rå.strip())
    sti = Path(rå.strip()[:m.start()] if m else rå.strip()).expanduser()
    linje = m.group(1) if m else ""
    røtter = [k.resolve() for k in kataloger]
    kandidater = [sti] if sti.is_absolute() else [r / sti for k in røtter for r in (k, k.parent)]
    for k in kandidater:
        k = k.resolve()
        for r in røtter:
            if k.is_file() and k.is_relative_to(r):
                return f"{k.relative_to(r.parent)}{linje}"
    return None


class Skrevet(NamedTuple):
    tekst: str
    sjekk: tuple[str, ...]
    usd: float
    research: tuple[Research, ...] = ()
    forkastet: int = 0  # Research med kilde utenfor tillatte kataloger


def prompt(t: Tråd, kunnskapsbase: str, instruks: str | None, forrige: str | None,
           verktøy: Verktøy | None) -> str:
    ut = tråd_tekst(t, kunnskapsbase)
    if verktøy:
        ut += "\n\n<kataloger>\n" + "\n".join(map(str, verktøy.kataloger)) + "\n</kataloger>"
    if instruks:
        ut += f"\n\n<forrige_utkast>\n{forrige or ''}\n</forrige_utkast>\n\n<instruks>\n{instruks}\n</instruks>"
    return ut


async def skriv_utkast(runner: Runner, t: Tråd, kunnskapsbase: str = "", instruks: str | None = None,
                       forrige: str | None = None, verktøy: Verktøy | None = None) -> Skrevet:
    """Kaster `AgentFeil` (med kost) ved feil. Uten verktøy: ett automatisk nytt forsøk.

    Med verktøy ingen nye forsøk (et tak som treffes, treffes igjen), og Research med ugyldig kilde forkastes.
    """
    if verktøy:
        r = await runner.kjør(INSTRUKS_VERKTØY, SCHEMA_RESEARCH, prompt(t, kunnskapsbase, instruks, forrige, verktøy),
                              verktøy=verktøy)
    else:
        r = await med_nytt_forsøk(runner, INSTRUKS, SCHEMA, prompt(t, kunnskapsbase, instruks, forrige, None))
    research, forkastet = [], 0
    for f in r.svar.get("research", []) if verktøy else []:
        if (k := kilde(f["kilde"], verktøy.kataloger)) and f["faktum"].strip():
            research.append(Research(f["faktum"].strip(), k))
        else:
            forkastet += 1
    return Skrevet(r.svar["tekst"].strip(), tuple(r.svar["sjekk"]), r.usd, tuple(research), forkastet)
