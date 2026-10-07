"""Tower-TUI: trådtabell venstre, Tråd i detalj høyre, statuslinje nederst."""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import datetime, timezone

from rich.markup import escape
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Footer, Static

from tower.config import Config
from tower.db import BESVART, GAMMEL, Db, Rad
from tower.kanal import Kanal, Tråd

KANAL_IKON = {"mail": "✉", "teams": "◆"}
FERDIG = {BESVART, GAMMEL}


def nå_utc() -> datetime:
    return datetime.now(timezone.utc)


def alder(tid: datetime, nå: datetime) -> str:
    min_ = max(0, int((nå - tid).total_seconds() // 60))
    if min_ < 60:
        return f"{min_}m"
    if min_ < 24 * 60:
        return f"{min_ // 60}t"
    return f"{min_ // (24 * 60)}d"


def motpart(t: Tråd) -> str:
    m = next((m for m in reversed(t.meldinger) if not m.fra_meg), t.siste)
    return m.fra.navn


def sorteringsnøkkel(t: Tråd, rad: Rad) -> tuple:
    return (rad.status in FERDIG, -t.siste.tid.timestamp())


def status_merke(rad: Rad) -> str:
    return {"ny": "[dim]ny[/]", GAMMEL: "[dim]gammel[/]", BESVART: "[dim]besvart[/]"}.get(rad.status, rad.status)


def tråd_markup(t: Tråd) -> str:
    ut = []
    for m in t.meldinger:
        hvem = "[b cyan]meg[/]" if m.fra_meg else f"[b]{escape(m.fra.navn)}[/]"
        tid = m.tid.astimezone().strftime("%d.%m %H:%M")
        til = ", ".join(p.navn for p in m.til)
        cc = f"  cc {', '.join(p.navn for p in m.cc)}" if m.cc else ""
        haster = " [b red]![/]" if m.haster else ""
        ut.append(f"{hvem}{haster}  [dim]{tid}  → {escape(til)}{escape(cc)}[/]")
        ut.append(escape(m.tekst))
        ut.append("")
    return "\n".join(ut)


class Tower(App):
    TITLE = "tower"
    CSS = """
    #hoved { height: 1fr; }
    #tabell { width: 55%; height: 1fr; }
    #hoyre { width: 1fr; border-left: vkey $panel; }
    #hode { padding: 0 1; background: $boost; height: auto; }
    #scroll { padding: 0 1; }
    #status { height: 1; background: $panel; padding: 0 1; }
    """
    BINDINGS = [Binding("q", "quit", "Avslutt")]

    def __init__(self, config: Config, kanaler: list[Kanal], db: Db,
                 nå: Callable[[], datetime] = nå_utc, poll: bool = True) -> None:
        super().__init__()
        self.config = config
        self.kanaler = kanaler
        self.db = db
        self.nå = nå
        self.auto_poll = poll
        self.tråder: dict[str, Tråd] = {}
        self.rader: dict[str, Rad] = {}
        self.hentfeil: dict[str, str] = {}
        self._poller = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="hoved"):
            yield DataTable(id="tabell", cursor_type="row", zebra_stripes=True)
            with Vertical(id="hoyre"):
                yield Static(id="hode")
                with VerticalScroll(id="scroll"):
                    yield Static(id="trad")
        yield Static(id="status")
        yield Footer()

    def on_mount(self) -> None:
        dt = self.query_one(DataTable)
        dt.add_column("", key="k", width=1)
        dt.add_column("Fra", key="fra", width=16)
        dt.add_column("Emne", key="emne", width=30)
        dt.add_column("Triage", key="tr", width=8)
        dt.add_column("Utkast", key="u", width=10)
        dt.add_column("", key="alder", width=3)
        dt.focus()
        self.oppdater_status()
        if self.auto_poll:
            self.utløs_poll()
            self.set_interval(self.config.poll_sekunder, self.utløs_poll)

    def utløs_poll(self) -> None:
        if not self._poller:
            self.run_worker(self.poll(), group="poll", exit_on_error=False)

    async def poll(self) -> None:
        """Henter fra alle kanaler, oppdaterer status i SQLite og tegner på nytt."""
        self._poller = True
        try:
            endret = False
            for kanal in self.kanaler:
                try:
                    tråder = await kanal.hent()
                except Exception as e:  # neste poll prøver igjen
                    self.hentfeil[kanal.navn] = str(e) or type(e).__name__
                    continue
                self.hentfeil.pop(kanal.navn, None)
                nå = self.nå()
                for t in tråder:
                    self.tråder[t.id] = t
                    self.rader[t.id] = self.db.registrer(t, nå, self.config.dager)
                    endret = True
            if endret:
                self.tegn_tabell()
            self.oppdater_status()
        finally:
            self._poller = False

    def sortert(self) -> list[Tråd]:
        return sorted(self.tråder.values(), key=lambda t: sorteringsnøkkel(t, self.rader[t.id]))

    def tegn_tabell(self) -> None:
        dt = self.query_one(DataTable)
        valgt = self.valgt_id()
        nå = self.nå()
        dt.clear()
        for t in self.sortert():
            rad = self.rader[t.id]
            dim = "[dim]" if rad.status in FERDIG else ""
            dt.add_row(KANAL_IKON.get(t.kanal, "?"), dim + escape(motpart(t)), dim + escape(t.emne),
                       status_merke(rad), "", alder(t.siste.tid, nå), key=t.id)
        if valgt in self.tråder:
            dt.move_cursor(row=dt.get_row_index(valgt), animate=False)
        self.vis_detalj()

    def valgt_id(self) -> str | None:
        dt = self.query_one(DataTable)
        if dt.row_count == 0:
            return None
        return dt.coordinate_to_cell_key(dt.cursor_coordinate).row_key.value

    @on(DataTable.RowHighlighted)
    def vis_detalj(self, *_) -> None:
        t = self.tråder.get(self.valgt_id() or "")
        if not t:
            return
        self.query_one("#hode", Static).update(
            f"{KANAL_IKON.get(t.kanal, '?')} [b]{escape(t.emne)}[/]\n{status_merke(self.rader[t.id])}")
        self.query_one("#trad", Static).update(tråd_markup(t))

    def oppdater_status(self) -> None:
        if self.hentfeil:
            tekst = "  ".join(f"[b red]✗ {k}:[/] {escape(v)}" for k, v in self.hentfeil.items())
        else:
            tekst = "[dim]agenter i ro[/]"
        aktive = sum(1 for r in self.rader.values() if r.status not in FERDIG)
        self.query_one("#status", Static).update(f"{tekst}   [dim]│[/]  {aktive} tråder venter")


def main(argv: list[str] | None = None) -> None:
    from tower import config as cfg

    argv = sys.argv[1:] if argv is None else argv
    if argv:
        sys.exit(f"bruk: tower\n(ukjent argument: {' '.join(argv)})")
    config = cfg.last()
    db = Db(config.db)
    try:
        Tower(config, cfg.lag_kanaler(config), db).run()
    finally:
        db.lukk()
