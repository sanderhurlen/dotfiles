"""Utkast-agenten: svar Sander kan sende nesten uendret. Manglende fakta blir `[[plassholder]]`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tower.agent import Runner, med_nytt_forsøk
from tower.kanal import Tråd
from tower.prompt import tråd_tekst

INSTRUKS = (Path(__file__).parent / "instrukser" / "utkast.md").read_text()
SCHEMA = {
    "type": "object",
    "properties": {
        "tekst": {"type": "string"},
        "sjekk": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tekst", "sjekk"],
    "additionalProperties": False,
}
PLASSHOLDER = re.compile(r"\[\[(.+?)\]\]", re.DOTALL)

# Utkast-tilstander. genererer → klart → sendt | forkastet | utdatert, pluss feilet.
GENERERER, KLART, SENDT, FORKASTET, UTDATERT, FEILET = "genererer", "klart", "sendt", "forkastet", "utdatert", "feilet"
ÅPNE = (GENERERER, KLART, FEILET)  # blir utdatert ved ny Melding


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

    @property
    def plassholdere(self) -> list[str]:
        return plassholdere(self.tekst)


def plassholdere(tekst: str) -> list[str]:
    return PLASSHOLDER.findall(tekst)


async def skriv_utkast(runner: Runner, t: Tråd, kunnskapsbase: str = "") -> tuple[str, tuple[str, ...], float]:
    """Tekst, sjekk og samlet kost. Kaster `AgentFeil` (med kost) når også det nye forsøket feiler."""
    r = await med_nytt_forsøk(runner, INSTRUKS, SCHEMA, tråd_tekst(t, kunnskapsbase))
    return r.svar["tekst"].strip(), tuple(r.svar["sjekk"]), r.usd
