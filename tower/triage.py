"""Triage: svar eller info, haster, sammendrag. Kjøres på nytt ved hver ny Melding."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tower.agent import Runner, med_nytt_forsøk
from tower.kanal import Tråd
from tower.prompt import tråd_tekst

INSTRUKS = (Path(__file__).parent / "instrukser" / "triage.md").read_text()
SCHEMA = {
    "type": "object",
    "properties": {
        "kategori": {"type": "string", "enum": ["svar", "info"]},
        "haster": {"type": "boolean"},
        "sammendrag": {"type": "string", "maxLength": 80},
        "begrunnelse": {"type": "string"},
    },
    "required": ["kategori", "haster", "sammendrag", "begrunnelse"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Triage:
    kategori: str  # "svar" | "info"
    haster: bool
    sammendrag: str
    begrunnelse: str


async def triager(runner: Runner, t: Tråd, kunnskapsbase: str = "") -> tuple[Triage, float]:
    """Triage og samlet kost. Kaster `AgentFeil` (med kost) når også det nye forsøket feiler."""
    r = await med_nytt_forsøk(runner, INSTRUKS, SCHEMA, tråd_tekst(t, kunnskapsbase))
    s = r.svar
    return Triage(s["kategori"], bool(s["haster"]), s["sammendrag"], s["begrunnelse"]), r.usd
