"""Tower-tilstand i SQLite. Kanalen eier Meldingene; her ligger bare status per Tråd."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from tower.kanal import Tråd
from tower.triage import Triage

SKJEMA = """
CREATE TABLE IF NOT EXISTS trad (
    id TEXT PRIMARY KEY,
    kanal TEXT NOT NULL,
    status TEXT NOT NULL,
    siste_melding_id TEXT NOT NULL,
    endret TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kjoring (
    tid TEXT NOT NULL,
    dato TEXT NOT NULL,  -- lokal dato, for "kost i dag"
    jobb TEXT NOT NULL,
    trad TEXT NOT NULL,
    usd REAL NOT NULL,
    feil TEXT
);
"""
# Lagt til etter tracer-sliken; eldre tower.db får dem ved åpning.
NYE_KOLONNER = {
    "kategori": "TEXT", "haster": "INTEGER", "sammendrag": "TEXT", "begrunnelse": "TEXT",
    "triage_melding_id": "TEXT",  # Meldingen triagen (eller feilen) gjelder
    "triage_feil": "TEXT",
}
KOLONNER = "id, kanal, status, siste_melding_id, kategori, haster, sammendrag, begrunnelse, triage_melding_id, triage_feil"

# Trådstatus. Senere slices legger til venter på meg, avvist, utsatt.
NY, GAMMEL, BESVART, TRIAGERT = "ny", "gammel", "besvart", "triagert"


@dataclass(frozen=True)
class Rad:
    id: str
    kanal: str
    status: str
    siste_melding_id: str
    triage: Triage | None = None  # siste vellykkede, kan gjelde en eldre Melding
    triage_melding_id: str | None = None
    triage_feil: str | None = None

    @property
    def trenger_triage(self) -> bool:
        return self.status == NY and self.triage_melding_id != self.siste_melding_id

    @property
    def triage_feilet(self) -> bool:
        return self.triage_feil is not None and self.triage_melding_id == self.siste_melding_id


def _rad(r: tuple) -> Rad:
    id, kanal, status, siste, kategori, haster, sammendrag, begrunnelse, tmid, tfeil = r
    triage = Triage(kategori, bool(haster), sammendrag, begrunnelse) if kategori else None
    return Rad(id, kanal, status, siste, triage, tmid, tfeil)


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
        finnes = {r[1] for r in self.con.execute("PRAGMA table_info(trad)")}
        with self.con:
            for navn, type_ in NYE_KOLONNER.items():
                if navn not in finnes:
                    self.con.execute(f"ALTER TABLE trad ADD COLUMN {navn} {type_}")

    def rad(self, tråd_id: str) -> Rad | None:
        r = self.con.execute(f"SELECT {KOLONNER} FROM trad WHERE id = ?", (tråd_id,)).fetchone()
        return _rad(r) if r else None

    def alle(self) -> dict[str, Rad]:
        return {r[0]: _rad(r) for r in self.con.execute(f"SELECT {KOLONNER} FROM trad")}

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
        return self.rad(tråd.id)

    def lagre_triage(self, tråd_id: str, melding_id: str, triage: Triage, nå: datetime) -> Rad | None:
        """Lagrer triage for `melding_id`. Ignoreres (None) hvis Tråden har fått en nyere Melding."""
        with self.con:
            n = self.con.execute(
                "UPDATE trad SET kategori = ?, haster = ?, sammendrag = ?, begrunnelse = ?, "
                "triage_melding_id = siste_melding_id, triage_feil = NULL, endret = ?, "
                "status = CASE status WHEN ? THEN ? ELSE status END "
                "WHERE id = ? AND siste_melding_id = ?",
                (triage.kategori, triage.haster, triage.sammendrag, triage.begrunnelse, nå.isoformat(),
                 NY, TRIAGERT, tråd_id, melding_id)).rowcount
        return self.rad(tråd_id) if n else None

    def lagre_triage_feil(self, tråd_id: str, melding_id: str, feil: str, nå: datetime) -> Rad | None:
        with self.con:
            n = self.con.execute(
                "UPDATE trad SET triage_melding_id = siste_melding_id, triage_feil = ?, endret = ? "
                "WHERE id = ? AND siste_melding_id = ?", (feil, nå.isoformat(), tråd_id, melding_id)).rowcount
        return self.rad(tråd_id) if n else None

    def logg_kjøring(self, jobb: str, tråd_id: str, usd: float, nå: datetime, feil: str | None = None) -> None:
        with self.con:
            self.con.execute("INSERT INTO kjoring (tid, dato, jobb, trad, usd, feil) VALUES (?, ?, ?, ?, ?, ?)",
                             (nå.isoformat(), nå.astimezone().date().isoformat(), jobb, tråd_id, usd, feil))

    def kost(self, nå: datetime) -> float:
        """Estimert agentkost i dag (lokal dato)."""
        r = self.con.execute("SELECT SUM(usd) FROM kjoring WHERE dato = ?",
                             (nå.astimezone().date().isoformat(),)).fetchone()
        return r[0] or 0.0

    def lukk(self) -> None:
        self.con.close()
