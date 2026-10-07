"""Tower-TUI: trådtabell venstre, Tråd i detalj høyre, statuslinje nederst."""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import datetime, timezone

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import DataTable, Footer, Static

from tower.agent import AgentFeil, Agenter, ClaudeRunner, Jobb, Runner
from tower.config import Config
from tower.db import BESVART, GAMMEL, Db, Rad
from tower.kanal import Kanal, Tråd
from tower.kunnskapsbase import oppslag
from tower.triage import triager
from tower.utkast import FEILET, FORKASTET, GENERERER, KLART, PLASSHOLDER, SENDT, UTDATERT, Utkast, skriv_utkast

KANAL_IKON = {"mail": "✉", "teams": "◆"}
FERDIG = {BESVART, GAMMEL}
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
MAKS_AGENTER = 2


def escape(tekst: str) -> str:
    """Textual-markup: hver `[` escapes. `rich.markup.escape` lar `[[` vises som `[\\[`."""
    return tekst.replace("[", r"\[")


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


def emne_kort(t: Tråd) -> str:
    """Emne i tabellen. Chat uten topic: start av siste Melding (deltakerne står allerede i Fra)."""
    if t.emne_utledet:
        return " ".join(t.siste.tekst.split())[:60]
    return t.emne


def sorteringsnøkkel(t: Tråd, rad: Rad) -> tuple:
    """Ferdige nederst; ellers haster, svar, utriagert, info, nyeste først innen hver."""
    tr = rad.triage
    rang = 2 if tr is None else 0 if tr.haster else 3 if tr.kategori == "info" else 1
    return (rad.status in FERDIG, rang, -t.siste.tid.timestamp())


def status_merke(rad: Rad) -> str:
    return {"ny": "[dim]ny[/]", GAMMEL: "[dim]gammel[/]", BESVART: "[dim]besvart[/]",
            "triagert": "[dim]triagert[/]"}.get(rad.status, rad.status)


def triage_merke(rad: Rad, jobb: str | None = None) -> str:
    """`jobb` er "kjører" eller "kø" når en triage venter på Tråden."""
    if jobb == "kjører":
        return "[dim]triagerer…[/]"
    if jobb == "kø":
        return "[dim]i kø[/]"
    if rad.triage_feilet:
        return "[red]✗ feilet[/]"
    tr = rad.triage
    if tr is None:
        return ""
    if tr.haster:
        return "[b red]● haster[/]"
    if tr.kategori == "info":
        return "[dim]○ info[/]"
    return "[yellow]● svar[/]"


def utkast_merke(rad: Rad, jobb: str | None = None) -> str:
    """Utkaststatus i tabellen. `jobb` er "kjører" eller "kø" når et utkast-kall venter."""
    u = rad.utkast
    if rad.status in FERDIG:
        return "[dim]sendt[/]" if u and u.status == SENDT else ""
    if rad.triage and rad.triage.kategori == "info" and not rad.trenger_triage:
        return "[dim]—[/]"
    if u is None:
        return ""
    if u.status == GENERERER:
        return "[magenta]✎ skriver…[/]" if jobb == "kjører" else "[dim]i kø[/]"
    return {
        KLART: "[green]✔ klart[/]" + (f" [dim]v{u.versjon}[/]" if u.versjon > 1 else ""),
        FEILET: "[red]✗ feilet[/]",
        UTDATERT: "[yellow]↻ utdatert[/]",
        SENDT: "[dim]sendt[/]",
        FORKASTET: "[dim]forkastet[/]",
    }.get(u.status, u.status)


def utkast_tekst_markup(tekst: str) -> str:
    """Utkastteksten med plassholdere uthevet."""
    ut, start = [], 0
    for m in PLASSHOLDER.finditer(tekst):
        ut += [escape(tekst[start:m.start()]), f"[b reverse yellow]{escape(m.group(0))}[/]"]
        start = m.end()
    return "".join(ut) + escape(tekst[start:])


def utkast_markup(rad: Rad, jobb: str | None, spinner: str) -> str | None:
    """Innhold i utkastrammen, eller None når rammen skal skjules."""
    u = rad.utkast
    if rad.status in FERDIG or (rad.triage and rad.triage.kategori == "info" and not rad.trenger_triage):
        return None
    if u is None:
        return None if rad.triage is None else "[dim]I kø for utkast…[/]" if rad.trenger_utkast else None
    if u.status == GENERERER:
        return f"[magenta]{spinner} Agenten skriver utkast…[/]" if jobb == "kjører" else "[dim]I kø for utkast…[/]"
    if u.status == FEILET:
        return f"[red]✗ Utkast feilet:[/] {escape(u.feil or '')}"
    hint = "".join(f"[yellow]›[/] {escape(s)}\n" for s in u.sjekk)
    pre = "[yellow]↻ Ny melding kom etter dette utkastet[/]\n\n" if u.status == UTDATERT else ""
    return pre + (hint + "\n" if hint else "") + utkast_tekst_markup(u.tekst)


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
    #utkast { border: round $panel-lighten-2; padding: 0 1; height: auto; margin-top: 1; }
    #utkast.klart { border: round $success; }
    #status { height: 1; background: $panel; padding: 0 1; }
    """
    BINDINGS = [Binding("q", "quit", "Avslutt")]

    def __init__(self, config: Config, kanaler: list[Kanal], db: Db, runner: Runner,
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
        self.runner = runner
        self.agenter = Agenter(MAKS_AGENTER, endret=self.agenter_endret)
        self._triage_for: dict[str, str] = {}  # Tråd-id → Melding-id for køet/kjørende triage
        self._utkast_for: dict[str, int] = {}  # Tråd-id → versjon for køet/kjørende utkast
        self._tikk = 0
        self.kost = db.kost(nå())

    def compose(self) -> ComposeResult:
        with Horizontal(id="hoved"):
            yield DataTable(id="tabell", cursor_type="row", zebra_stripes=True)
            with Vertical(id="hoyre"):
                yield Static(id="hode")
                with VerticalScroll(id="scroll"):
                    yield Static(id="trad")
                    yield Static(id="utkast")
        yield Static(id="status")
        yield Footer()

    def on_mount(self) -> None:
        dt = self.query_one(DataTable)
        dt.add_column("", key="k", width=1)
        dt.add_column("Fra", key="fra", width=16)
        dt.add_column("Emne", key="emne", width=30)
        dt.add_column("Triage", key="tr", width=11)
        dt.add_column("Utkast", key="u", width=10)
        dt.add_column("", key="alder", width=3)
        dt.focus()
        self.oppdater_status()
        self.set_interval(0.12, self.tikk)
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
                    self.planlegg(t)
                    endret = True
            if endret:
                self.tegn_tabell()
            self.oppdater_status()
        finally:
            self._poller = False

    def kunnskap(self, t: Tråd) -> str:
        return oppslag(self.config.kunnskapsbase, t, self.config.meg)

    def planlegg(self, t: Tråd) -> None:
        """Køer triage når Tråden har en ny Melding fra andre, og utkast når triagen sier svar.

        Jobber som ikke lenger trengs (ny Melding, svar utenfra) avbrytes.
        """
        rad = self.rader[t.id]
        nøkkel = ("triage", t.id)
        if not rad.trenger_triage:
            if self.agenter.venter(nøkkel):
                self.agenter.avbryt(nøkkel)
        elif not (self.agenter.venter(nøkkel) and self._triage_for.get(t.id) == t.siste.id):
            self._triage_for[t.id] = t.siste.id
            self.agenter.legg_i_kø(Jobb(nøkkel, f"triage {motpart(t).split()[0]}", lambda: self.kjør_triage(t)))

        nøkkel = ("utkast", t.id)
        if not rad.trenger_utkast:
            if self.agenter.venter(nøkkel):
                self.agenter.avbryt(nøkkel)
            return
        u = rad.utkast
        if u is None or u.melding_id != t.siste.id:
            u = self.db.nytt_utkast(t.id, t.siste.id, self.nå())
            self.rader[t.id] = rad = self.db.rad(t.id)
        if self.agenter.venter(nøkkel) and self._utkast_for.get(t.id) == u.versjon:
            return
        self._utkast_for[t.id] = u.versjon
        self.agenter.legg_i_kø(Jobb(nøkkel, f"utkast {motpart(t).split()[0]}", lambda: self.kjør_utkast(t, u)))

    async def kjør_utkast(self, t: Tråd, u: Utkast) -> None:
        try:
            tekst, sjekk, usd = await skriv_utkast(self.runner, t, self.kunnskap(t))
        except AgentFeil as e:
            self.db.logg_kjøring("utkast", t.id, e.usd, self.nå(), feil=str(e))
            ny = self.db.lagre_utkast_feil(u, str(e), self.nå())
        else:
            self.db.logg_kjøring("utkast", t.id, usd, self.nå())
            ny = self.db.lagre_utkast(u, tekst, sjekk, self.nå())
        self.kost = self.db.kost(self.nå())
        if ny:
            self.rader[t.id] = self.db.rad(t.id)
        if self._utkast_for.get(t.id) == u.versjon:
            del self._utkast_for[t.id]
        self.tegn_tabell()

    async def kjør_triage(self, t: Tråd) -> None:
        try:
            triage, usd = await triager(self.runner, t, self.kunnskap(t))
        except AgentFeil as e:
            self.db.logg_kjøring("triage", t.id, e.usd, self.nå(), feil=str(e))
            rad = self.db.lagre_triage_feil(t.id, t.siste.id, str(e), self.nå())
        else:
            self.db.logg_kjøring("triage", t.id, usd, self.nå())
            rad = self.db.lagre_triage(t.id, t.siste.id, triage, self.nå())
        self.kost = self.db.kost(self.nå())
        if rad:
            self.rader[t.id] = rad
        if self._triage_for.get(t.id) == t.siste.id:
            del self._triage_for[t.id]
        if rad:
            self.planlegg(self.tråder.get(t.id, t))  # svar → utkast
        self.tegn_tabell()

    def jobb_status(self, tråd_id: str, type_: str = "triage") -> str | None:
        nøkkel = (type_, tråd_id)
        if nøkkel in self.agenter.kjørende:
            return "kjører"
        if nøkkel in self.agenter.kø:
            return "kø"
        return None

    def agenter_endret(self) -> None:
        if not self.is_mounted:
            return
        dt = self.query_one(DataTable)
        for tid, rad in self.rader.items():
            if tid in dt.rows:
                dt.update_cell(tid, "tr", triage_merke(rad, self.jobb_status(tid)))
                dt.update_cell(tid, "u", utkast_merke(rad, self.jobb_status(tid, "utkast")))
        self.vis_utkast()
        self.oppdater_status()

    def tikk(self) -> None:
        self._tikk += 1
        if self.agenter.kjørende:
            self.oppdater_status()
            if self.jobb_status(self.valgt_id() or "", "utkast") == "kjører":
                self.vis_utkast()

    async def on_unmount(self) -> None:
        self.agenter.endret = lambda: None  # widgetene er borte
        await self.agenter.stopp()

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
            dt.add_row(KANAL_IKON.get(t.kanal, "?"), dim + escape(motpart(t)), dim + escape(emne_kort(t)),
                       triage_merke(rad, self.jobb_status(t.id)),
                       utkast_merke(rad, self.jobb_status(t.id, "utkast")), alder(t.siste.tid, nå), key=t.id)
        if valgt in self.tråder:
            dt.move_cursor(row=dt.get_row_index(valgt), animate=False)
        self.vis_detalj()

    def valgt_id(self) -> str | None:
        try:
            dt = self.query_one(DataTable)
        except NoMatches:  # meldinger kan komme etter at skjermen er revet ned
            return None
        if dt.row_count == 0:
            return None
        return dt.coordinate_to_cell_key(dt.cursor_coordinate).row_key.value

    @on(DataTable.RowHighlighted)
    def vis_detalj(self, *_) -> None:
        t = self.tråder.get(self.valgt_id() or "")
        if not t:
            return
        rad = self.rader[t.id]
        linjer = [f"{KANAL_IKON.get(t.kanal, '?')} [b]{escape(t.emne)}[/]"]
        merke = " ".join(m for m in (status_merke(rad), triage_merke(rad, self.jobb_status(t.id))) if m)
        if rad.triage_feilet:
            linjer += [merke, f"[red]{escape(rad.triage_feil or '')}[/]"]
        elif rad.triage:
            linjer += [f"{merke}  [i]{escape(rad.triage.sammendrag)}[/]", f"[dim]{escape(rad.triage.begrunnelse)}[/]"]
        else:
            linjer.append(merke)
        self.query_one("#hode", Static).update("\n".join(linjer))
        self.query_one("#trad", Static).update(tråd_markup(t))
        self.vis_utkast()

    def vis_utkast(self) -> None:
        try:
            w = self.query_one("#utkast", Static)
        except NoMatches:
            return
        t = self.tråder.get(self.valgt_id() or "")
        innhold = None
        if t:
            rad = self.rader[t.id]
            innhold = utkast_markup(rad, self.jobb_status(t.id, "utkast"), SPINNER[self._tikk % len(SPINNER)])
        w.display = innhold is not None
        if innhold is None:
            return
        u = rad.utkast
        w.update(innhold)
        w.border_title = "Utkast" + (f" v{u.versjon}" if u and u.status != GENERERER else "")
        w.set_class(bool(u and u.status == KLART), "klart")

    def oppdater_status(self) -> None:
        deler = [f"[b red]✗ {k}:[/] {escape(v)}" for k, v in self.hentfeil.items()]
        if self.agenter.feil:
            deler.append(f"[b red]✗ {escape(self.agenter.feil)}[/]")
        kjører = [j.etikett for j, _ in self.agenter.kjørende.values()]
        if kjører:
            kø = f"  [dim]+{len(self.agenter.kø)} i kø[/]" if self.agenter.kø else ""
            deler.append(f"[magenta]{SPINNER[self._tikk % len(SPINNER)]}[/] {escape(' · '.join(kjører))}{kø}")
        elif not deler:
            deler.append("[dim]agenter i ro[/]")
        aktive = sum(1 for r in self.rader.values() if r.status not in FERDIG)
        klare = sum(1 for r in self.rader.values() if r.status not in FERDIG and r.utkast and r.utkast.status == KLART)
        self.query_one("#status", Static).update(
            f"{'  '.join(deler)}   [dim]│[/]  {aktive} tråder venter   [dim]│[/]  {klare} utkast klare"
            f"   [dim]│[/]  ${self.kost:.3f} i dag")


def main(argv: list[str] | None = None) -> None:
    from tower import config as cfg

    argv = sys.argv[1:] if argv is None else argv
    if argv:
        sys.exit(f"bruk: tower\n(ukjent argument: {' '.join(argv)})")
    config = cfg.last()
    db = Db(config.db)
    try:
        Tower(config, cfg.lag_kanaler(config), db, ClaudeRunner(config.modell, config.agent_cwd)).run()
    finally:
        db.lukk()
