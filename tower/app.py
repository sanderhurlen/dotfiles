"""Tower-TUI: trådtabell venstre, Tråd i detalj høyre, statuslinje nederst."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.app import SuspendNotSupported
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Static

from tower.agent import AgentFeil, Agenter, ClaudeRunner, Jobb, Runner
from tower.config import Config
from tower.db import AVVIST, BESVART, GAMMEL, UTSATT, Db, Rad
from tower.handlinger import UTSETT_VALG, editor_argv, første_plassholder, utsett_til
from tower.kanal import Kanal, Tråd
from tower.kunnskapsbase import oppslag
from tower.triage import triager
from tower.utkast import FEILET, FORKASTET, GENERERER, KLART, PLASSHOLDER, SENDT, UTDATERT, Utkast, skriv_utkast

KANAL_IKON = {"mail": "✉", "teams": "◆"}
FERDIG = {BESVART, GAMMEL, AVVIST, UTSATT}  # dimmet nederst, ingen agenter
UKEDAG = ["ma", "ti", "on", "to", "fr", "lø", "sø"]
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


def kort_tid(t: datetime) -> str:
    lokal = t.astimezone()
    return f"{UKEDAG[lokal.weekday()]} {lokal:%H:%M}"


def status_merke(rad: Rad) -> str:
    if rad.status == UTSATT and rad.utsatt_til:
        return f"[dim]utsatt til {kort_tid(rad.utsatt_til)}[/]"
    return {"ny": "[dim]ny[/]", GAMMEL: "[dim]gammel[/]", BESVART: "[dim]besvart[/]",
            "triagert": "[dim]triagert[/]", AVVIST: "[dim]avvist[/]"}.get(rad.status, rad.status)


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
    if rad.status == UTSATT and rad.utsatt_til:
        return f"[dim]⏾ {kort_tid(rad.utsatt_til)}[/]"
    if rad.status == AVVIST:
        return "[dim]avvist[/]"
    if rad.status in FERDIG:
        return "[dim]sendt[/]" if u and u.status == SENDT else ""
    if rad.triage and rad.triage.kategori == "info" and not rad.trenger_triage:
        return "[dim]—[/]"
    if u is None:
        return ""
    if u.status == GENERERER:
        return "[magenta]✎ skriver…[/]" if jobb == "kjører" else "[dim]i kø[/]"
    return {
        KLART: ("[red]✗ sending[/]" if u.feil else "[green]✔ klart[/]")
        + (f" [dim]v{u.versjon}[/]" if u.versjon > 1 else ""),
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
    if u.feil:
        pre += f"[red]✗ Sending feilet:[/] {escape(u.feil)}\n\n"
    return pre + (hint + "\n" if hint else "") + utkast_tekst_markup(u.gjeldende)


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


class Valg(ModalScreen[str | None]):
    """Dialog med én tast per valg. `esc` er verdien escape gir."""

    DEFAULT_CSS = """
    Valg { align: center middle; }
    Valg > Static { width: auto; max-width: 72; height: auto; border: round $accent; padding: 1 2;
                    background: $surface; }
    """
    TITTEL = ""
    VALG: dict[str, str] = {}
    ESC: str | None = None

    def compose(self) -> ComposeResult:
        linjer = [self.TITTEL, ""] + [f"[b]{k}[/]  {escape(v)}" for k, v in self.VALG.items()]
        yield Static("\n".join(linjer))

    def action_velg(self, verdi: str) -> None:
        self.dismiss(verdi)

    def action_esc(self) -> None:
        self.dismiss(self.ESC)


class UtsettValg(Valg):
    TITTEL = "[b]Utsett til[/]"
    VALG = UTSETT_VALG
    BINDINGS = [*(Binding(k, f"velg('{k}')", v) for k, v in UTSETT_VALG.items()),
                Binding("escape", "esc", "Avbryt")]


class NyMeldingValg(Valg):
    """Ny Melding kom mens jeg redigerte. Redigeringen er lagret og overskrives aldri."""

    TITTEL = "[b yellow]↻ Ny melding kom mens du redigerte[/]\n[dim]Redigeringen din er lagret.[/]"
    VALG = {"s": "send likevel", "m": "se meldingen", "r": "regenerer"}
    ESC = "m"
    BINDINGS = [Binding("s", "velg('s')", "Send likevel"), Binding("m", "velg('m')", "Se meldingen"),
                Binding("r", "velg('r')", "Regenerer"), Binding("escape", "esc", "Se meldingen")]


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
    BINDINGS = [
        Binding("s", "send", "Send"),
        Binding("e", "rediger", "Rediger"),
        Binding("a", "avvis", "Avvis"),
        Binding("u", "utsett", "Utsett"),
        Binding("q", "quit", "Avslutt"),
    ]

    def __init__(self, config: Config, kanaler: list[Kanal], db: Db, runner: Runner,
                 nå: Callable[[], datetime] = nå_utc, poll: bool = True,
                 editor: Callable[[str], str | None] | None = None) -> None:
        super().__init__()
        self.editor = editor or self.rediger_i_editor  # tekst inn, redigert tekst ut (None = avbrutt)
        self._hold: set[str] = set()  # Tråder med min redigering av et utdatert Utkast: ingen auto-utkast
        self._sender: set[str] = set()
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
            for id in self.db.vekk(self.nå()):  # utsatt-tiden er ute
                self.rader[id] = self.db.rad(id)
                if id in self.tråder:
                    self.planlegg(self.tråder[id])
                endret = True
            if endret:
                self.tegn_tabell()
            self.oppdater_status()
        finally:
            self._poller = False

    async def poll_nå(self) -> None:
        """Poll med en gang, etter en eventuell poll som allerede går."""
        while self._poller:
            await asyncio.sleep(0.01)
        await self.poll()

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
        if not rad.trenger_utkast or t.id in self._hold:
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
        w.border_title = "Utkast" + (f" v{u.versjon}" if u and u.status != GENERERER else "") + (
            " · redigert" if u and u.redigert is not None else "")
        w.set_class(bool(u and u.status == KLART), "klart")

    # Handlinger

    def valgt(self) -> tuple[Tråd, Rad] | None:
        t = self.tråder.get(self.valgt_id() or "")
        return (t, self.rader[t.id]) if t else None

    def gå_til(self, indeks: int) -> None:
        """Markøren til samme plass etter at raden flyttet seg (ferdige havner nederst)."""
        dt = self.query_one(DataTable)
        if dt.row_count:
            dt.move_cursor(row=min(indeks, dt.row_count - 1), animate=False)

    def ikke_klart(self, t: Tråd, rad: Rad) -> str | None:
        """Hvorfor Utkastet ikke kan sendes eller redigeres, eller None."""
        u = rad.utkast
        if rad.status in FERDIG:
            return "Tråden er ikke aktiv"
        if u is None or u.status == GENERERER:
            return "Utkastet er ikke klart ennå"
        if u.status == FEILET:
            return "Utkastet feilet, ingen tekst"
        if u.status == UTDATERT and t.id not in self._hold:
            return "Utkastet er utdatert, nytt er på vei"
        if u.status in (SENDT, FORKASTET):
            return "Ingen åpent utkast"
        return None

    def action_send(self) -> None:
        if valgt := self.valgt():
            self.prøv_send(valgt[0].id)

    def prøv_send(self, tråd_id: str) -> None:
        t, rad = self.tråder[tråd_id], self.rader[tråd_id]
        if grunn := self.ikke_klart(t, rad):
            self.notify(grunn, severity="warning")
            return
        if n := len(rad.utkast.plassholdere):
            self.notify(f"{n} plassholder{'e' if n > 1 else ''} igjen, fyll ut med e", severity="warning")
            return
        if t.id not in self._sender:
            self._sender.add(t.id)
            self.run_worker(self.send(t, rad.utkast, self.query_one(DataTable).cursor_row), group="send",
                            exit_on_error=False)

    async def send(self, t: Tråd, u: Utkast, indeks: int) -> None:
        """Sender via kanalen. Feil: Utkastet står som klart med feiltekst, aldri auto-retry."""
        try:
            kanal = next(k for k in self.kanaler if k.navn == t.kanal)
            try:
                await kanal.svar(t.id, u.gjeldende)
            except Exception as e:
                feil = str(e) or type(e).__name__
                self.db.lagre_sendefeil(u, feil, self.nå())
                self.rader[t.id] = self.db.rad(t.id)
                self.notify(f"Sending feilet: {feil}", severity="error", timeout=10)
                self.tegn_tabell()
                return
            self.db.marker_sendt(u, self.nå())
            self._hold.discard(t.id)
            self.rader[t.id] = self.db.rad(t.id)
            await self.poll_nå()  # mitt svar ligger i Tråden nå → besvart
            self.tegn_tabell()
            self.gå_til(indeks)
        finally:
            self._sender.discard(t.id)

    def action_avvis(self) -> None:
        if not (valgt := self.valgt()) or valgt[1].status == AVVIST:
            return
        t, _ = valgt
        indeks = self.query_one(DataTable).cursor_row
        self._hold.discard(t.id)
        self.rader[t.id] = self.db.avvis(t.id, self.nå())
        self.planlegg(t)
        self.tegn_tabell()
        self.gå_til(indeks)

    def action_utsett(self) -> None:
        if not (valgt := self.valgt()) or valgt[1].status in (BESVART, GAMMEL, AVVIST):
            return
        t, _ = valgt
        indeks = self.query_one(DataTable).cursor_row

        def valgt_tid(valg: str | None) -> None:
            if valg is None:
                return
            self._hold.discard(t.id)
            self.rader[t.id] = self.db.utsett(t.id, utsett_til(valg, self.nå()), self.nå())
            self.planlegg(t)
            self.tegn_tabell()
            self.gå_til(indeks)

        self.push_screen(UtsettValg(), valgt_tid)

    async def action_rediger(self) -> None:
        if not (valgt := self.valgt()):
            return
        t, rad = valgt
        if grunn := self.ikke_klart(t, rad):
            self.notify(grunn, severity="warning")
            return
        u = rad.utkast
        # Sist sette Melding: for et holdt (utdatert) Utkast har jeg alt sett meldingene fram til nå.
        sett = rad.siste_melding_id if u.status == UTDATERT else u.melding_id
        ny = self.editor(u.gjeldende)
        if ny is not None and ny != u.gjeldende:
            u = self.db.lagre_redigert(u, ny, self.nå())
        # Ny Melding mens editoren var åpen? Hold igjen auto-utkast til jeg har valgt.
        self._hold.add(t.id)
        await self.poll_nå()
        rad = self.rader[t.id] = self.db.rad(t.id)
        if rad.status in FERDIG or rad.siste_melding_id == sett:
            if rad.status in FERDIG or u.status != UTDATERT:
                self._hold.discard(t.id)
            self.tegn_tabell()
            return
        self.tegn_tabell()
        self.push_screen(NyMeldingValg(), lambda valg: self.etter_ny_melding(t.id, valg))

    def etter_ny_melding(self, tråd_id: str, valg: str | None) -> None:
        if valg == "s":
            self.prøv_send(tråd_id)
        elif valg == "r":
            self._hold.discard(tråd_id)
            self.planlegg(self.tråder[tråd_id])
            self.tegn_tabell()
        else:  # se meldingen: slutten av Tråden nederst i visningen, redigeringen står under
            scroll = self.query_one("#scroll", VerticalScroll)
            scroll.scroll_to(y=max(0, self.query_one("#trad").outer_size.height - scroll.size.height // 2),
                             animate=False)

    def rediger_i_editor(self, tekst: str) -> str | None:
        """$EDITOR via suspend, markøren på første plassholder. None hvis editoren feilet."""
        linje, kol = første_plassholder(tekst)
        with tempfile.TemporaryDirectory(prefix="tower-") as d:
            sti = Path(d) / "utkast.txt"
            sti.write_text(tekst + "\n")
            try:
                with self.suspend():
                    kode = subprocess.call(editor_argv(sti, linje, kol))
            except (OSError, SuspendNotSupported) as e:
                self.notify(f"Kunne ikke åpne editor: {e}", severity="error")
                return None
            if kode != 0:
                self.notify(f"Editoren avsluttet med {kode}, utkastet er uendret", severity="error")
                return None
            return sti.read_text().rstrip("\n")

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
    if argv[:1] == ["mock"]:
        from tower.mock import main as mock

        sys.exit(mock(argv[1:]))
    if argv:
        sys.exit(f"bruk: tower [mock …]\n(ukjent argument: {' '.join(argv)})")
    config = cfg.last()
    db = Db(config.db)
    try:
        Tower(config, cfg.lag_kanaler(config), db, ClaudeRunner(config.modell, config.agent_cwd)).run()
    finally:
        db.lukk()
