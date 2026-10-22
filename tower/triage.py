"""Triage: svar eller info, haster, kan ryddes, sammendrag. Kjøres på nytt ved hver ny Melding."""

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
        "rydd": {"type": "boolean"},
        "sammendrag": {"type": "string", "maxLength": 80},
        "begrunnelse": {"type": "string"},
    },
    "required": ["kategori", "haster", "rydd", "sammendrag", "begrunnelse"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Triage:
    kategori: str  # "svar" | "info"
    haster: bool
    sammendrag: str
    begrunnelse: str
    rydd: bool = False  # kan arkiveres uten videre: forhåndsmerkes i tower


def historikk_tekst(ryddet: dict[str, int]) -> str:
    """Hvor mange tidligere Tråder jeg har arkivert fra hver avsender i Tråden."""
    if not ryddet:
        return ""
    linjer = [f"- {adresse}: {n} tråd{'er' if n > 1 else ''}" for adresse, n in sorted(ryddet.items())]
    return "<arkivert>\nSander har arkivert uten å svare tidligere tråder fra:\n" + "\n".join(linjer) + "\n</arkivert>\n\n"


async def triager(runner: Runner, t: Tråd, kunnskapsbase: str = "",
                  ryddet: dict[str, int] | None = None) -> tuple[Triage, float]:
    """Triage og samlet kost. Kaster `AgentFeil` (med kost) når også det nye forsøket feiler.

    `ryddet`: avsenderadresse → antall Tråder jeg har arkivert fra den før.
    """
    r = await med_nytt_forsøk(runner, INSTRUKS, SCHEMA, historikk_tekst(ryddet or {}) + tråd_tekst(t, kunnskapsbase))
    s = r.svar
    rydd = bool(s.get("rydd")) and s["kategori"] == "info"
    return Triage(s["kategori"], bool(s["haster"]), s["sammendrag"], s["begrunnelse"], rydd), r.usd
