"""Tower-tilstand i SQLite. Kanalen eier Meldingene; her ligger bare status per Tråd."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tower.kanal import Tråd
from tower.kurator import KuratorJobb
from tower.triage import Triage
from tower.utkast import ÅPNE, FEILET, FORKASTET, GENERERER, KLART, SENDT, Research, Utkast

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
-- Alle versjoner beholdes (Kurator-input). Siste versjon per Tråd er den som vises.
CREATE TABLE IF NOT EXISTS utkast (
    trad TEXT NOT NULL,
    versjon INTEGER NOT NULL,
    melding_id TEXT NOT NULL,  -- siste Melding da utkastet ble bestilt
    status TEXT NOT NULL,
    tekst TEXT NOT NULL DEFAULT '',
    sjekk TEXT NOT NULL DEFAULT '[]',  -- JSON-liste
    feil TEXT,
    instruks TEXT,
    opprettet TEXT NOT NULL,
    endret TEXT NOT NULL,
    PRIMARY KEY (trad, versjon)
);
-- Kurator-kø. Én jobb per Melding jeg svarte på: send i tower og `besvart` fra poll blir samme jobb.
CREATE TABLE IF NOT EXISTS kurator (
    id INTEGER PRIMARY KEY,
    trad TEXT NOT NULL,
    svar_pa TEXT NOT NULL,
    sendt TEXT NOT NULL,
    sendt_versjon INTEGER,  -- NULL: besvart utenfra, ingen diff
    fra_versjon INTEGER NOT NULL,
    til_versjon INTEGER NOT NULL,
    status TEXT NOT NULL,  -- venter | feilet | ferdig
    feil TEXT,
    opprettet TEXT NOT NULL,
    endret TEXT NOT NULL,
    UNIQUE (trad, svar_pa)
);
"""
# Lagt til etter tracer-sliken; eldre tower.db får dem ved åpning.
NYE_KOLONNER = {
    "kategori": "TEXT", "haster": "INTEGER", "sammendrag": "TEXT", "begrunnelse": "TEXT",
    "triage_melding_id": "TEXT",  # Meldingen triagen (eller feilen) gjelder
    "triage_feil": "TEXT",
    "utsatt_til": "TEXT",  # ISO UTC, bare i `utsatt`
}
NYE_U_KOLONNER = {"redigert": "TEXT", "research": "TEXT"}  # research: JSON-liste av {faktum, kilde}
U_KOLONNER = "trad, versjon, melding_id, status, tekst, sjekk, feil, instruks, redigert, research"
KOLONNER = ("id, kanal, status, siste_melding_id, kategori, haster, sammendrag, begrunnelse, triage_melding_id, "
            "triage_feil, utsatt_til")

# Trådstatus. `triagert` er «venter på meg». `avvist` og `utsatt` varer til ny Melding (utsatt også til tiden).
NY, GAMMEL, BESVART, TRIAGERT, AVVIST, UTSATT = "ny", "gammel", "besvart", "triagert", "avvist", "utsatt"
# Kurator-jobber
VENTER, FERDIG = "venter", "ferdig"
K_KOLONNER = "id, trad, svar_pa, sendt, sendt_versjon, fra_versjon, til_versjon, status, feil"


@dataclass(frozen=True)
class Rad:
    id: str
    kanal: str
    status: str
    siste_melding_id: str
    triage: Triage | None = None  # siste vellykkede, kan gjelde en eldre Melding
    triage_melding_id: str | None = None
    triage_feil: str | None = None
    utkast: Utkast | None = None  # synlig versjon, se `synlig`
    utsatt_til: datetime | None = None
    regenerering_feil: str | None = None  # siste versjon feilet; `utkast` er da versjonen før

    @property
    def trenger_triage(self) -> bool:
        return self.status == NY and self.triage_melding_id != self.siste_melding_id

    @property
    def triage_feilet(self) -> bool:
        return self.triage_feil is not None and self.triage_melding_id == self.siste_melding_id

    @property
    def trenger_utkast(self) -> bool:
        """Triagert som svar for siste Melding, og ingen ferdig eller feilet versjon for den ennå."""
        if (self.status != TRIAGERT or self.triage is None or self.triage.kategori != "svar"
                or self.triage_melding_id != self.siste_melding_id or self.triage_feilet):
            return False
        u = self.utkast
        return u is None or u.melding_id != self.siste_melding_id or u.status == GENERERER


def _rad(r: tuple, versjoner: list[Utkast] = ()) -> Rad:
    id, kanal, status, siste, kategori, haster, sammendrag, begrunnelse, tmid, tfeil, utsatt_til = r
    triage = Triage(kategori, bool(haster), sammendrag, begrunnelse) if kategori else None
    til = datetime.fromisoformat(utsatt_til) if utsatt_til else None
    utkast, feil = synlig(versjoner)
    return Rad(id, kanal, status, siste, triage, tmid, tfeil, utkast, til, feil)


def synlig(versjoner: list[Utkast]) -> tuple[Utkast | None, str | None]:
    """Versjonen som vises, og feilen når en regenerering feilet.

    Siste versjon, unntatt når den feilet og versjonen før er klar for samme Melding: da står den
    (en mislykket regenerering tar aldri fra meg et utkast jeg kunne sendt).
    """
    if not versjoner:
        return None, None
    siste = versjoner[-1]
    if siste.status == FEILET and len(versjoner) > 1:
        forrige = versjoner[-2]
        if forrige.status == KLART and forrige.melding_id == siste.melding_id:
            return forrige, siste.feil
    return siste, None


def _utkast(r: tuple) -> Utkast:
    trad, versjon, melding_id, status, tekst, sjekk, feil, instruks, redigert, research = r
    funn = tuple(Research(f["faktum"], f["kilde"]) for f in json.loads(research or "[]"))
    return Utkast(trad, versjon, melding_id, status, tekst, tuple(json.loads(sjekk)), feil, instruks, redigert, funn)


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
        with self.con:
            for tabell, nye in (("trad", NYE_KOLONNER), ("utkast", NYE_U_KOLONNER)):
                finnes = {r[1] for r in self.con.execute(f"PRAGMA table_info({tabell})")}
                for navn, type_ in nye.items():
                    if navn not in finnes:
                        self.con.execute(f"ALTER TABLE {tabell} ADD COLUMN {navn} {type_}")

    def rad(self, tråd_id: str) -> Rad | None:
        r = self.con.execute(f"SELECT {KOLONNER} FROM trad WHERE id = ?", (tråd_id,)).fetchone()
        return _rad(r, self.versjoner(tråd_id)) if r else None

    def alle(self) -> dict[str, Rad]:
        versjoner: dict[str, list[Utkast]] = {}
        for u in map(_utkast, self.con.execute(f"SELECT {U_KOLONNER} FROM utkast ORDER BY trad, versjon")):
            versjoner.setdefault(u.tråd_id, []).append(u)
        return {r[0]: _rad(r, versjoner.get(r[0], [])) for r in self.con.execute(f"SELECT {KOLONNER} FROM trad")}

    def registrer(self, tråd: Tråd, nå: datetime, dager: int) -> Rad:
        """Oppdaterer status for en hentet Tråd og returnerer raden.

        Besvart utenfra (ikke første gang Tråden sees) køer en Kurator-jobb uten diff; sendte jeg fra tower,
        finnes jobben allerede.
        """
        forrige = self.rad(tråd.id)
        status = ny_status(forrige, tråd, nå, dager)
        if status is None:
            return forrige
        with self.con:
            if status == BESVART and forrige and forrige.status != BESVART:
                self._ny_kurator(tråd.id, forrige.siste_melding_id, tråd.siste.tekst, None, nå)
            self.con.execute(
                "INSERT INTO trad (id, kanal, status, siste_melding_id, endret) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET status = excluded.status, utsatt_til = NULL, "
                "siste_melding_id = excluded.siste_melding_id, endret = excluded.endret",
                (tråd.id, tråd.kanal, status, tråd.siste.id, nå.isoformat()))
            self.con.execute(
                f"UPDATE utkast SET status = 'utdatert', endret = ? WHERE trad = ? AND melding_id != ? "
                f"AND status IN ({', '.join('?' * len(ÅPNE))})", (nå.isoformat(), tråd.id, tråd.siste.id, *ÅPNE))
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

    def utkast(self, tråd_id: str) -> Utkast | None:
        """Siste versjon (ikke nødvendigvis den synlige, se `Rad.utkast`)."""
        r = self.con.execute(f"SELECT {U_KOLONNER} FROM utkast WHERE trad = ? ORDER BY versjon DESC LIMIT 1",
                             (tråd_id,)).fetchone()
        return _utkast(r) if r else None

    def versjoner(self, tråd_id: str) -> list[Utkast]:
        return [_utkast(r) for r in self.con.execute(
            f"SELECT {U_KOLONNER} FROM utkast WHERE trad = ? ORDER BY versjon", (tråd_id,))]

    def nytt_utkast(self, tråd_id: str, melding_id: str, nå: datetime, instruks: str | None = None) -> Utkast:
        """Ny versjon i `genererer` for `melding_id`."""
        with self.con:
            versjon = self.con.execute("SELECT COALESCE(MAX(versjon), 0) + 1 FROM utkast WHERE trad = ?",
                                       (tråd_id,)).fetchone()[0]
            self.con.execute(
                "INSERT INTO utkast (trad, versjon, melding_id, status, instruks, opprettet, endret) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", (tråd_id, versjon, melding_id, GENERERER, instruks, nå.isoformat(),
                                                 nå.isoformat()))
        return self.utkast(tråd_id)

    def _avslutt_utkast(self, u: Utkast, nå: datetime, status: str, **felt) -> Utkast | None:
        """Flytter en versjon ut av `genererer`. None hvis den er utdatert i mellomtiden."""
        sett = "".join(f", {k} = ?" for k in felt)
        with self.con:
            n = self.con.execute(
                f"UPDATE utkast SET status = ?, endret = ?{sett} WHERE trad = ? AND versjon = ? AND status = ?",
                (status, nå.isoformat(), *felt.values(), u.tråd_id, u.versjon, GENERERER)).rowcount
        return self.utkast(u.tråd_id) if n else None

    def lagre_utkast(self, u: Utkast, tekst: str, sjekk: tuple[str, ...], nå: datetime,
                     research: tuple[Research, ...] = ()) -> Utkast | None:
        """`u` → klart. Eldre åpne versjoner (en regenerering erstatter forrige) forkastes."""
        ny = self._avslutt_utkast(u, nå, KLART, tekst=tekst, sjekk=json.dumps(list(sjekk), ensure_ascii=False),
                                  feil=None, research=json.dumps([f.__dict__ for f in research], ensure_ascii=False))
        if ny:
            with self.con:
                self.con.execute(f"UPDATE utkast SET status = ?, endret = ? WHERE trad = ? AND versjon < ? "
                                 f"AND status IN ({', '.join('?' * len(ÅPNE))})",
                                 (FORKASTET, nå.isoformat(), u.tråd_id, u.versjon, *ÅPNE))
        return ny

    def lagre_utkast_feil(self, u: Utkast, feil: str, nå: datetime) -> Utkast | None:
        return self._avslutt_utkast(u, nå, FEILET, feil=feil)

    def lagre_redigert(self, u: Utkast, tekst: str, nå: datetime) -> Utkast:
        """Min redigering av en versjon, uansett status (ny Melding under redigering skal aldri overskrive den)."""
        with self.con:
            self.con.execute("UPDATE utkast SET redigert = ?, feil = NULL, endret = ? WHERE trad = ? AND versjon = ?",
                             (tekst, nå.isoformat(), u.tråd_id, u.versjon))
        return self._versjon(u)

    def marker_sendt(self, u: Utkast, nå: datetime) -> Utkast:
        """`u` → sendt; andre åpne versjoner av Tråden forkastes."""
        with self.con:
            self.con.execute("UPDATE utkast SET status = ?, feil = NULL, endret = ? WHERE trad = ? AND versjon = ?",
                             (SENDT, nå.isoformat(), u.tråd_id, u.versjon))
            self._forkast(u.tråd_id, nå)
        return self._versjon(u)

    def lagre_sendefeil(self, u: Utkast, feil: str, nå: datetime) -> Utkast:
        """Sending feilet: status står (klart), feilteksten vises. Aldri auto-retry."""
        with self.con:
            self.con.execute("UPDATE utkast SET feil = ?, endret = ? WHERE trad = ? AND versjon = ?",
                             (feil, nå.isoformat(), u.tråd_id, u.versjon))
        return self._versjon(u)

    def _versjon(self, u: Utkast) -> Utkast:
        return _utkast(self.con.execute(f"SELECT {U_KOLONNER} FROM utkast WHERE trad = ? AND versjon = ?",
                                        (u.tråd_id, u.versjon)).fetchone())

    def _forkast(self, tråd_id: str, nå: datetime) -> None:
        self.con.execute(f"UPDATE utkast SET status = ?, endret = ? WHERE trad = ? "
                         f"AND status IN ({', '.join('?' * len(ÅPNE))})", (FORKASTET, nå.isoformat(), tråd_id, *ÅPNE))

    def avvis(self, tråd_id: str, nå: datetime) -> Rad:
        """Trenger ikke svar fra meg (også kvittering av info). Åpne Utkast forkastes. Varer til ny Melding."""
        with self.con:
            self.con.execute("UPDATE trad SET status = ?, utsatt_til = NULL, endret = ? WHERE id = ?",
                             (AVVIST, nå.isoformat(), tråd_id))
            self._forkast(tråd_id, nå)
        return self.rad(tråd_id)

    def utsett(self, tråd_id: str, til: datetime, nå: datetime) -> Rad:
        """Skjul til `til` eller ny Melding. Utkastet står og gjenbrukes."""
        with self.con:
            self.con.execute("UPDATE trad SET status = ?, utsatt_til = ?, endret = ? WHERE id = ?",
                             (UTSATT, til.astimezone(timezone.utc).isoformat(), nå.isoformat(), tråd_id))
        return self.rad(tråd_id)

    def vekk(self, nå: datetime) -> list[str]:
        """Utsatte Tråder med tiden ute tilbake til `triagert` (gyldig triage for siste Melding) eller `ny`."""
        ids = [r[0] for r in self.con.execute("SELECT id, utsatt_til FROM trad WHERE status = ?", (UTSATT,))
               if datetime.fromisoformat(r[1]) <= nå]
        with self.con:
            for id in ids:
                self.con.execute(
                    "UPDATE trad SET utsatt_til = NULL, endret = ?, status = CASE WHEN kategori IS NOT NULL "
                    "AND triage_feil IS NULL AND triage_melding_id = siste_melding_id THEN ? ELSE ? END WHERE id = ?",
                    (nå.isoformat(), TRIAGERT, NY, id))
        return ids

    def logg_kjøring(self, jobb: str, tråd_id: str, usd: float, nå: datetime, feil: str | None = None) -> None:
        with self.con:
            self.con.execute("INSERT INTO kjoring (tid, dato, jobb, trad, usd, feil) VALUES (?, ?, ?, ?, ?, ?)",
                             (nå.isoformat(), nå.astimezone().date().isoformat(), jobb, tråd_id, usd, feil))

    def kost(self, nå: datetime) -> float:
        """Estimert agentkost i dag (lokal dato)."""
        r = self.con.execute("SELECT SUM(usd) FROM kjoring WHERE dato = ?",
                             (nå.astimezone().date().isoformat(),)).fetchone()
        return r[0] or 0.0

    # Kurator-kø

    def _ny_kurator(self, tråd_id: str, svar_på: str, sendt: str, versjon: int | None, nå: datetime) -> None:
        fra = self.con.execute("SELECT COALESCE(MAX(til_versjon), 0) FROM kurator WHERE trad = ?",
                               (tråd_id,)).fetchone()[0]
        til = self.con.execute("SELECT COALESCE(MAX(versjon), 0) FROM utkast WHERE trad = ?", (tråd_id,)).fetchone()[0]
        self.con.execute(
            "INSERT OR IGNORE INTO kurator (trad, svar_pa, sendt, sendt_versjon, fra_versjon, til_versjon, status, "
            "opprettet, endret) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tråd_id, svar_på, sendt, versjon, fra, max(til, fra), VENTER, nå.isoformat(), nå.isoformat()))

    def kurator_etter_sending(self, u: Utkast, svar_på: str, nå: datetime) -> None:
        """Køer Kuratoren for en sendt versjon. `svar_på` er siste Melding jeg hadde sett da jeg sendte."""
        with self.con:
            self._ny_kurator(u.tråd_id, svar_på, u.gjeldende, u.versjon, nå)

    def kurator_jobber(self, *status: str) -> list[KuratorJobb]:
        return [KuratorJobb(*r) for r in self.con.execute(
            f"SELECT {K_KOLONNER} FROM kurator WHERE status IN ({', '.join('?' * len(status))}) ORDER BY id",
            status)]

    def kurator_ferdig(self, jobb: KuratorJobb, nå: datetime) -> None:
        with self.con:
            self.con.execute("UPDATE kurator SET status = ?, feil = NULL, endret = ? WHERE id = ?",
                             (FERDIG, nå.isoformat(), jobb.id))

    def kurator_feil(self, jobb: KuratorJobb, feil: str, nå: datetime) -> None:
        with self.con:
            self.con.execute("UPDATE kurator SET status = ?, feil = ?, endret = ? WHERE id = ?",
                             (FEILET, feil, nå.isoformat(), jobb.id))

    def lukk(self) -> None:
        self.con.close()
