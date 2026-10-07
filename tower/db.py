"""Tower-tilstand i SQLite. Kanalen eier Meldingene; her ligger bare status per Tråd."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from tower.kanal import Tråd

SKJEMA = """
CREATE TABLE IF NOT EXISTS trad (
    id TEXT PRIMARY KEY,
    kanal TEXT NOT NULL,
    status TEXT NOT NULL,
    siste_melding_id TEXT NOT NULL,
    endret TEXT NOT NULL
);
"""

# Trådstatus. Senere slices legger til triagert, venter på meg, avvist, utsatt.
NY, GAMMEL, BESVART = "ny", "gammel", "besvart"


@dataclass(frozen=True)
class Rad:
    id: str
    kanal: str
    status: str
    siste_melding_id: str


def ny_status(forrige: Rad | None, tråd: Tråd, nå: datetime, dager: int) -> str | None:
    """Status etter at `tråd` er hentet, eller None hvis ingen ny Melding.

    `besvart` utledes av siste avsender. `gammel` bare når Tråden sees første gang og er eldre enn `dager`.
    """
    siste = tråd.siste
    if forrige and forrige.siste_melding_id == siste.id:
        return None
    if siste.fra_meg:
        return BESVART
    if forrige is None and nå - siste.tid > timedelta(days=dager):
        return GAMMEL
    return NY


class Db:
    def __init__(self, sti: Path | str) -> None:
        self.con = sqlite3.connect(sti)
        self.con.executescript(SKJEMA)

    def rad(self, tråd_id: str) -> Rad | None:
        r = self.con.execute(
            "SELECT id, kanal, status, siste_melding_id FROM trad WHERE id = ?", (tråd_id,)).fetchone()
        return Rad(*r) if r else None

    def alle(self) -> dict[str, Rad]:
        return {r[0]: Rad(*r) for r in self.con.execute("SELECT id, kanal, status, siste_melding_id FROM trad")}

    def registrer(self, tråd: Tråd, nå: datetime, dager: int) -> Rad:
        """Oppdaterer status for en hentet Tråd og returnerer raden."""
        forrige = self.rad(tråd.id)
        status = ny_status(forrige, tråd, nå, dager)
        if status is None:
            return forrige
        with self.con:
            self.con.execute(
                "INSERT INTO trad (id, kanal, status, siste_melding_id, endret) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET status = excluded.status, "
                "siste_melding_id = excluded.siste_melding_id, endret = excluded.endret",
                (tråd.id, tråd.kanal, status, tråd.siste.id, nå.isoformat()))
        return Rad(tråd.id, tråd.kanal, status, tråd.siste.id)

    def lukk(self) -> None:
        self.con.close()
