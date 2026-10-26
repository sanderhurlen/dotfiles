"""Tower-TUI: trådtabell venstre, Tråd i detalj høyre, statuslinje nederst."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
import webbrowser
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
from textual.widgets import DataTable, Footer, Input, Static

from tower import jobber
from tower.agent import AgentFeil, Agenter, ClaudeRunner, Jobb, Runner
from tower.config import Config
from tower.db import AVVIST, BESVART, FEILET as K_FEILET, GAMMEL, UTSATT, VENTER, Db, Rad
from tower.handlinger import UTSETT_VALG, editor_argv, første_plassholder, katalog_argv, utsett_til
from tower.kanal import Kanal, Kladd, Tråd, kladdtekst
from tower.kunnskapsbase import oppslag
from tower.kurator import KuratorJobb, commit_manuelt, kurater, sikre_repo, siste_commit, skriv_og_commit
from tower.triage import triager
from tower.utkast import (FEILET, FORKASTET, GENERERER, INNSPILL, KLART, PLASSHOLDER, SENDT, UTDATERT, Utkast,
                          skriv_utkast)

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


def macos_varsel(tittel: str, undertittel: str, tekst: str) -> None:
    """Notification Center via osascript, uten å vente på det."""
    subprocess.Popen(["osascript", "-e", "on run argv", "-e",
                      "display notification (item 3 of argv) with title (item 1 of argv) subtitle (item 2 of argv)",
                      "-e", "end run", tittel, undertittel, tekst],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
    if tr.rydd:
        return "[dim]○ rydd[/]"
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
    if rad.triage and rad.triage.kategori == "info" and not rad.trenger_triage and not (u and u.instruks):
        return "[dim]—[/]"
    if u is None:
        return ""
    if u.status == GENERERER:
        return "[magenta]✎ skriver…[/]" if jobb == "kjører" else "[dim]i kø[/]"
    return {
        KLART: ("[red]✗ sending[/]" if u.feil else "[green]✔ i Outlook[/]" if u.kladd else "[green]✔ klart[/]")
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
    if rad.status in FERDIG or (rad.triage and rad.triage.kategori == "info" and not rad.trenger_triage
                                and not (u and u.instruks)):
        return None
    if u is None:
        return None if rad.triage is None else "[dim]I kø for utkast…[/]" if rad.trenger_utkast else None
    instruks = f"[dim]↺ {escape(u.instruks)}[/]\n" if u.instruks else ""
    if u.status == GENERERER:
        if jobb != "kjører":
            return instruks + "[dim]I kø for utkast…[/]"
        return instruks + f"[magenta]{spinner} Agenten {'leter og ' if u.instruks else ''}skriver utkast…[/]"
    if u.status == FEILET:
        return instruks + f"[red]✗ Utkast feilet:[/] {escape(u.feil or '')}"
    hint = "".join(f"[yellow]›[/] {escape(s)}\n" for s in u.sjekk)
    kilder = "".join(f"[dim]·[/] {escape(f.faktum)} [dim]{escape(f.kilde)}[/]\n" for f in u.research)
    if kilder:
        hint += "[b dim]Kilder[/]\n" + kilder
    pre = "[yellow]↻ Ny melding kom etter dette utkastet[/]\n\n" if u.status == UTDATERT else ""
    if rad.regenerering_feil:
        pre += f"[red]✗ Regenerering feilet:[/] {escape(rad.regenerering_feil)}\n[dim]Forrige versjon står.[/]\n\n"
    if u.feil:
        pre += f"[red]✗ Sending feilet:[/] {escape(u.feil)}\n\n"
    return pre + instruks + (hint + "\n" if hint else "") + utkast_tekst_markup(u.gjeldende)


SAKS = "# ------------------------ >8 ------------------------"


def tråd_ren(t: Tråd) -> str:
    """Tråden som ren tekst under utkastet i editoren, nyeste først."""
    ut = ["# Alt fra saks-linja og ned fjernes. Tråden, nyeste først:", ""]
    for m in reversed(t.meldinger):
        hvem = "meg" if m.fra_meg else m.fra.navn
        til = ", ".join(p.navn for p in m.til)
        ut += [f"── {hvem}  {m.tid.astimezone().strftime('%d.%m %H:%M')}  → {til}", m.tekst, ""]
    return "\n".join(ut)


def tråd_markup(t: Tråd) -> str:
    """Nyeste Melding øverst, rett under Utkastet."""
    ut = []
    for m in reversed(t.meldinger):
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


class JobbValg(ModalScreen[str | None]):
    """`J`: launchd-jobbene mine — sist og neste kjøring, og hvordan det gikk. Jobbens tast velger den (navn ut)."""

    DEFAULT_CSS = """
    JobbValg { align: center middle; }
    JobbValg > Static { width: auto; max-width: 120; height: auto; border: round $accent; padding: 1 2;
                        background: $surface; }
    """
    BINDINGS = [Binding("escape", "esc", "Lukk")]

    def __init__(self, jobber: list[dict]) -> None:
        super().__init__()
        self.taster: dict[str, str] = {}
        linjer = ["[b]launchd-jobber[/]  [dim]tast = velg · esc lukker[/]", ""]
        for j in jobber:
            tast = next((c for c in j["name"].removeprefix("chores-") + "123456789"
                         if c.isalnum() and c not in self.taster), "?")
            self.taster[tast] = j["name"]
            linjer.append(f"[b]{tast}[/]  {j['merke']} {escape(j['name'])}  [dim]{escape(j['every'])}[/] · "
                          f"{escape(j['linje'])}")
        if not jobber:
            linjer.append("[dim]ingen com.sanderhurlen.*-jobber i launchd[/]")
        self.tekst = "\n".join(linjer)

    def compose(self) -> ComposeResult:
        yield Static(self.tekst)

    def on_key(self, e) -> None:
        if navn := self.taster.get(e.character or ""):
            e.stop()
            self.dismiss(navn)

    def action_esc(self) -> None:
        self.dismiss(None)


class JobbHandling(Valg):
    VALG = {"i": "hva den gjør · hva som feilet · hva du kan gjøre", "k": "kjør nå", "l": "loggen"}
    BINDINGS = [*(Binding(k, f"velg('{k}')", v) for k, v in VALG.items()), Binding("escape", "esc", "Tilbake")]

    def __init__(self, j: dict) -> None:
        super().__init__()
        self.TITTEL = f"[b]{j['merke']} {escape(j['name'])}[/]  [dim]{escape(j['every'])}[/]\n{escape(j['linje'])}"


class RadHandlinger(Valg):
    """`enter`: det jeg kan gjøre med raden. Tasten velger handlingen (navnet ut); tastene virker også rett i lista."""

    BINDINGS = [Binding("escape", "esc", "Lukk")]

    def __init__(self, tittel: str, handlinger: dict[str, tuple[str, str]]) -> None:
        super().__init__()
        self.TITTEL = f"[b]{escape(tittel)}[/]  [dim]tast = velg · esc lukker[/]"
        self.VALG = {k: v for k, (_, v) in handlinger.items()}
        self.handlinger = handlinger

    def on_key(self, e) -> None:
        if (h := self.handlinger.get(e.character or "")) is not None:
            e.stop()
            self.dismiss(h[0])


class InstruksPrompt(ModalScreen[str | None]):
    """Instruks til regenerering. Tom = prøv igjen uten verktøy; `escape` = avbryt (None)."""

    DEFAULT_CSS = """
    InstruksPrompt { align: center middle; }
    InstruksPrompt > Vertical { width: 80; height: auto; border: round $accent; padding: 1 2; background: $surface; }
    InstruksPrompt Input { margin-top: 1; }
    """
    BINDINGS = [Binding("escape", "avbryt", "Avbryt")]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[b]Regenerer utkast[/]\n[dim]Instruks til agenten, tom = prøv igjen. Med instruks kan den "
                         "lese Kunnskapsbasen og kildene dine.[/]")
            yield Input(placeholder="f.eks. kortere, og sjekk leveransedato i docs-repoet", id="instruks")

    @on(Input.Submitted)
    def send_inn(self, e: Input.Submitted) -> None:
        self.dismiss(e.value.strip())

    def action_avbryt(self) -> None:
        self.dismiss(None)


class Tower(App):
    TITLE = "tower"
    CSS = """
    #hoved { height: 1fr; }
    #tabell { width: 55%; height: 1fr; }
    #hoyre { width: 1fr; border-left: vkey $panel; }
    #hode { padding: 1 2; background: $boost; height: auto; }
    #scroll { padding: 0 1; }
    #utkast { border: round $panel-lighten-2; padding: 0 1; height: auto; margin-bottom: 1; }
    #utkast.klart { border: round $success; }
    #status { height: 1; background: $panel; padding: 0 1; }
    """
    # Radens handlinger ligger bak enter (RadHandlinger); tastene virker også direkte, uten å vises i footeren.
    BINDINGS = [
        Binding("enter", "handlinger", "Handlinger", key_display="↵"),
        Binding("s", "send", "Send", show=False),
        Binding("e", "rediger", "Rediger", show=False),
        Binding("r", "regenerer", "Regenerer", show=False),
        Binding("a", "avvis", "Avvis", show=False),
        Binding("u", "utsett", "Utsett", show=False),
        Binding("space", "merk", "Merk"),
        Binding("x", "arkiver", "Arkiver", show=False),
        Binding("c", "kopier", "Kopier", show=False),
        Binding("i", "innspill", "Innspill", show=False),
        Binding("o", "åpne", "Åpne"),
        Binding("k", "kunnskapsbase", "Kunnskapsbase"),
        Binding("J", "jobber", "Jobber"),
        Binding("q", "quit", "Avslutt"),
    ]

    def __init__(self, config: Config, kanaler: list[Kanal], db: Db, runner: Runner,
                 nå: Callable[[], datetime] = nå_utc, poll: bool = True,
                 editor: Callable[[str], str | None] | None = None,
                 åpne: Callable[[str], object] = webbrowser.open,
                 kopier: Callable[[str], object] | None = None,
                 varsle: Callable[[str, str, str], object] = lambda *_: None) -> None:
        super().__init__()
        # tekst inn, redigert tekst ut (None = avbrutt); min egen viser den valgte Tråden under utkastet
        self.editor = editor or (lambda tekst: self.rediger_i_editor(tekst, self.tråder.get(self.valgt_id() or "")))
        self.åpne = åpne  # lenke i nettleseren
        self.varsle = varsle  # (tittel, undertittel, tekst) når triagen sier haster
        self.kopier = kopier or (lambda tekst: subprocess.run(["pbcopy"], input=tekst.encode(), check=True))
        self._kladd_lås = asyncio.Lock()  # Outlook-kladdene: én synk av gangen, inn eller ut
        self._kladd_venter = False
        self._hentet: set[str] = set()  # kanaler hentet minst én gang: før det er ingen Kladd uønsket
        self._savnet: dict[str, int] = {}  # Kladd-id → synker på rad den har vært borte uten at Tråden er besvart
        self._hold: set[str] = set()  # Tråder med min redigering av et utdatert Utkast: ingen auto-utkast
        self._sender: set[str] = set()
        self.merket: set[str] = set()  # Tråder merket for arkivering
        self._foreslått: dict[str, str] = {}  # Tråd-id → Melding-id triagen forhåndsmerket: avmerking varer
        self._taster: tuple | None = None  # siste check_action for merk/arkiver
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
        self.kurator = Agenter(1, endret=self.agenter_endret)  # egen kø, én om gangen
        self.kurator_feilet: list[KuratorJobb] = db.kurator_jobber(K_FEILET)
        self._kurator_igjen = True  # feilede jobber får ett nytt forsøk per oppstart
        self.kb_siste: tuple[str, datetime] | None = None  # siste kurator-commit
        self._tikk = 0
        self.kost = db.kost(nå())

    def compose(self) -> ComposeResult:
        with Horizontal(id="hoved"):
            yield DataTable(id="tabell", cursor_type="row", zebra_stripes=True)
            with Vertical(id="hoyre"):
                yield Static(id="hode")
                with VerticalScroll(id="scroll"):
                    yield Static(id="utkast")
                    yield Static(id="trad")
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
        try:
            self.kb_siste = siste_commit(self.config.kunnskapsbase)
        except (OSError, subprocess.CalledProcessError):
            pass
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
                self._hentet.add(kanal.navn)
                for id in kanal.fjernede():  # slettet eller arkivert utenfor tower
                    endret |= self.glem(id)
                nå = self.nå()
                for t in tråder:
                    if (forrige := self.tråder.get(t.id)) and forrige.siste.id != t.siste.id:
                        self.merket.discard(t.id)  # ny Melding: merket gjaldt det jeg hadde sett
                    self.tråder[t.id] = t
                    self.rader[t.id] = self.db.registrer(t, nå, self.config.dager_for(t.kanal))
                    self.foreslå(t)
                    self.planlegg(t)
                    endret = True
                if self.har_kladder(kanal) and (kladder := kanal.kladder()) is not None:
                    endret |= await self.kladder_inn(kanal, kladder)
            for id in self.db.vekk(self.nå()):  # utsatt-tiden er ute
                self.rader[id] = self.db.rad(id)
                if id in self.tråder:
                    self.planlegg(self.tråder[id])
                endret = True
            if endret:
                self.tegn_tabell()
            self.planlegg_kurator()
            self.oppdater_status()
            self.utløs_kladder()  # også når ingenting er endret: en feilet synk prøves igjen
        finally:
            self._poller = False

    def glem(self, id: str) -> bool:
        """Tråden er borte fra innboksen: ut av tabellen, ventende agenter avbrytes."""
        self.merket.discard(id)
        if self.tråder.pop(id, None) is None:
            return False
        for nøkkel in (("triage", id), ("utkast", id)):
            if self.agenter.venter(nøkkel):
                self.agenter.avbryt(nøkkel)
        return True

    async def poll_nå(self) -> None:
        """Poll med en gang, etter en eventuell poll som allerede går."""
        while self._poller:
            await asyncio.sleep(0.01)
        await self.poll()

    # Outlook-kladdene (mail i `config.graph`): ett Utkast klart = én Kladd, begge veier

    def har_kladder(self, kanal: Kanal) -> bool:
        """Ekte Graph med kladder. Teams har ingen: der kopieres Utkastet."""
        return kanal.navn in self.config.graph and hasattr(kanal, "lag_kladd")

    def ønsket_kladd(self, tråd_id: str) -> Utkast | None:
        """Versjonen som skal ligge i Outlook: siste klare, så lenge Tråden er aktiv eller utsatt.

        Under regenerering står forrige versjon til den nye er klar; utdatert (ny Melding) slettes med en gang.
        """
        rad = self.rader.get(tråd_id)
        if tråd_id not in self.tråder or rad is None or rad.status in (BESVART, GAMMEL, AVVIST):
            return None
        return next((v for v in reversed(self.db.versjoner(tråd_id)) if v.status == KLART), None)

    async def kladder_inn(self, kanal: Kanal, kladder: dict[str, Kladd]) -> bool:
        """Det jeg har gjort i Outlook: redigert (blir min redigering), sendt eller slettet (Tråden avvises).

        Borte uten at svaret synes ennå kan være sending på vei: slettet først når den er borte to synker på rad.
        """
        endret = False
        async with self._kladd_lås:
            for u in self.db.med_kladd(kanal.navn):
                if (k := kladder.get(u.kladd)) is not None:
                    self._savnet.pop(u.kladd, None)
                    if k.tekst != u.kladd_tekst:
                        self.db.kladd_endret(u, k.tekst, self.nå())
                        self.rader[u.tråd_id] = self.db.rad(u.tråd_id)
                        endret = True
                    continue
                rad = self.rader.get(u.tråd_id)
                if rad and rad.status == BESVART:
                    self.db.kladd_sendt(u, self.nå())
                else:
                    self._savnet[u.kladd] = self._savnet.get(u.kladd, 0) + 1
                    if self._savnet[u.kladd] < 2:
                        continue
                    ønsket = self.ønsket_kladd(u.tråd_id)
                    self.db.fjern_kladd(u)
                    if ønsket and ønsket.versjon == u.versjon:
                        self._hold.discard(u.tråd_id)
                        self.db.avvis(u.tråd_id, self.nå())
                        if t := self.tråder.get(u.tråd_id):
                            self.rader[t.id] = self.db.rad(t.id)
                            self.planlegg(t)
                            self.notify(f"Kladden til {motpart(t)} ble slettet i Outlook, tråden er avvist")
                self._savnet.pop(u.kladd, None)
                self.rader[u.tråd_id] = self.db.rad(u.tråd_id)
                endret = True
        return endret

    def utløs_kladder(self) -> None:
        if not self._kladd_venter and any(map(self.har_kladder, self.kanaler)):
            self._kladd_venter = True
            self.run_worker(self.kladder_ut(), group="kladder", exit_on_error=False)

    async def kladder_ut(self) -> None:
        """Outlook følger tower: ønsket Kladd lages, alle andre slettes. Feil står i statuslinja til neste forsøk."""
        async with self._kladd_lås:
            self._kladd_venter = False
            endret = False
            for kanal in self.kanaler:
                if not self.har_kladder(kanal) or kanal.navn not in self._hentet:
                    continue
                feil_nøkkel = f"{kanal.navn} kladd"
                try:
                    for u in self.db.med_kladd(kanal.navn):
                        ønsket = self.ønsket_kladd(u.tråd_id)
                        if ønsket and ønsket.versjon == u.versjon and kladdtekst(ønsket.gjeldende) == u.kladd_tekst:
                            continue
                        await kanal.slett_kladd(u.kladd)
                        self.db.fjern_kladd(u)
                        self.rader[u.tråd_id] = self.db.rad(u.tråd_id)
                        endret = True
                    for tråd_id in [id for id, r in self.rader.items() if r.kanal == kanal.navn]:
                        if (ønsket := self.ønsket_kladd(tråd_id)) and ønsket.kladd is None:
                            self.db.lagre_kladd(ønsket, await kanal.lag_kladd(tråd_id, ønsket.gjeldende))
                            self.rader[tråd_id] = self.db.rad(tråd_id)
                            endret = True
                except Exception as e:
                    self.hentfeil[feil_nøkkel] = str(e) or type(e).__name__
                else:
                    self.hentfeil.pop(feil_nøkkel, None)
            if endret:
                self.tegn_tabell()
            self.oppdater_status()

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
        """Med instruks (regenerering): forrige versjon i prompten og lesetilgang via verktøy."""
        jobb = "regenerer" if u.instruks else "utkast"
        forrige = next((v.gjeldende for v in reversed(self.db.versjoner(t.id)) if v.versjon < u.versjon
                        and v.gjeldende), None) if u.instruks else None
        try:
            s = await skriv_utkast(self.runner, t, self.kunnskap(t), u.instruks, forrige,
                                   self.config.verktøy() if u.instruks else None)
        except AgentFeil as e:
            self.db.logg_kjøring(jobb, t.id, e.usd, self.nå(), feil=str(e))
            ny = self.db.lagre_utkast_feil(u, str(e), self.nå())
        else:
            self.db.logg_kjøring(jobb, t.id, s.usd, self.nå())
            sjekk = s.sjekk + ((f"{s.forkastet} kilde{'r' if s.forkastet > 1 else ''} utenfor tillatte kataloger "
                                "er fjernet fra Research",) if s.forkastet else ())
            ny = self.db.lagre_utkast(u, s.tekst, sjekk, self.nå(), s.research)
        self.kost = self.db.kost(self.nå())
        if ny:
            self.rader[t.id] = self.db.rad(t.id)
            if self.rader[t.id].regenerering_feil:
                self.notify(f"Regenerering feilet: {self.rader[t.id].regenerering_feil}", severity="error",
                            timeout=10)
        if self._utkast_for.get(t.id) == u.versjon:
            del self._utkast_for[t.id]
        self.tegn_tabell()

    async def kjør_triage(self, t: Tråd) -> None:
        try:
            triage, usd = await triager(self.runner, t, self.kunnskap(t),
                                        self.db.ryddet([m.fra.adresse for m in t.meldinger if not m.fra_meg]))
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
        if rad and rad.triage and rad.triage.haster and rad.status not in FERDIG:
            try:
                self.varsle("tower: haster", f"{motpart(t)} · {t.emne}", rad.triage.sammendrag)
            except Exception:  # varselet er pynt, triagen står uansett
                pass
        if rad:
            self.foreslå(self.tråder.get(t.id, t))
            self.planlegg(self.tråder.get(t.id, t))  # svar → utkast
        self.tegn_tabell()

    def planlegg_kurator(self) -> None:
        """Køer ventende Kurator-jobber for Tråder vi kjenner (etter omstart: når første poll har hentet dem)."""
        status = (VENTER, K_FEILET) if self._kurator_igjen else (VENTER,)
        jobber = [j for j in self.db.kurator_jobber(*status) if j.tråd_id in self.tråder]
        if self._kurator_igjen and self.tråder:
            self._kurator_igjen = False
        for j in jobber:
            nøkkel = ("kurator", str(j.id))
            if not self.kurator.venter(nøkkel):
                t = self.tråder[j.tråd_id]
                self.kurator.legg_i_kø(Jobb(nøkkel, f"kurator {motpart(t).split()[0]}",
                                            lambda j=j: self.kjør_kurator(j)))

    async def kjør_kurator(self, jobb: KuratorJobb) -> None:
        """Mine endringer committes først, så skriver Kuratoren og committer. Sending påvirkes aldri."""
        t = self.tråder[jobb.tråd_id]
        rot, meg = self.config.kunnskapsbase, self.config.meg
        usd = 0.0
        try:
            await asyncio.to_thread(commit_manuelt, rot, meg)
            endringer, forkastet, usd = await kurater(self.runner, t, jobb, self.db.versjoner(t.id), rot, meg,
                                                      self.nå())
            await asyncio.to_thread(skriv_og_commit, rot, endringer, emne_kort(t), t.id)
        except (AgentFeil, OSError, subprocess.CalledProcessError) as e:
            usd += getattr(e, "usd", 0.0)
            feil = (e.stderr or "").strip()[-200:] or str(e) if isinstance(e, subprocess.CalledProcessError) else str(e)
            self.db.logg_kjøring("kurator", t.id, usd, self.nå(), feil=feil)
            self.db.kurator_feil(jobb, feil, self.nå())
        else:
            self.db.logg_kjøring("kurator", t.id, usd, self.nå())
            self.db.kurator_ferdig(jobb, self.nå())
            if forkastet:
                self.notify(f"Kuratoren: {forkastet} endring{'er' if forkastet > 1 else ''} med ugyldig sti forkastet",
                            severity="warning")
            self.kb_siste = await asyncio.to_thread(siste_commit, rot)
        self.kost = self.db.kost(self.nå())
        self.kurator_feilet = self.db.kurator_jobber(K_FEILET)
        self.oppdater_status()

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
        if self.agenter.kjørende or self.kurator.kjørende:
            self.oppdater_status()
            if self.jobb_status(self.valgt_id() or "", "utkast") == "kjører":
                self.vis_utkast()

    async def on_unmount(self) -> None:
        self.agenter.endret = self.kurator.endret = lambda: None  # widgetene er borte
        await self.agenter.stopp()
        await self.kurator.stopp()

    def vises(self, t: Tråd) -> bool:
        """Besvarte Teams-chatter har ingenting å vise: de kommer tilbake med neste Melding."""
        return not (t.kanal == "teams" and self.rader[t.id].status == BESVART)

    def sortert(self) -> list[Tråd]:
        return sorted(filter(self.vises, self.tråder.values()), key=lambda t: sorteringsnøkkel(t, self.rader[t.id]))

    def tegn_tabell(self) -> None:
        dt = self.query_one(DataTable)
        valgt = self.valgt_id()
        nå = self.nå()
        dt.clear()
        tråder = self.sortert()
        for t in tråder:
            rad = self.rader[t.id]
            dim = "[dim]" if rad.status in FERDIG else ""
            dt.add_row(KANAL_IKON.get(t.kanal, "?"), self.fra_celle(t), dim + escape(emne_kort(t)),
                       triage_merke(rad, self.jobb_status(t.id)),
                       utkast_merke(rad, self.jobb_status(t.id, "utkast")), alder(t.siste.tid, nå), key=t.id)
        if any(t.id == valgt for t in tråder):
            dt.move_cursor(row=dt.get_row_index(valgt), animate=False)
        self.vis_detalj()
        self.utløs_kladder()  # tabellen tegnes etter hver endring i tower

    def fra_celle(self, t: Tråd) -> str:
        merke = "[b yellow]●[/] " if t.id in self.merket else ""
        return merke + ("[dim]" if self.rader[t.id].status in FERDIG else "") + escape(motpart(t))

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
        self.oppdater_taster()
        t = self.tråder.get(self.valgt_id() or "")
        if not t:
            return
        rad = self.rader[t.id]
        linjer = [f"{KANAL_IKON.get(t.kanal, '?')} [b]{escape(t.emne)}[/]"]
        merke = " ".join(m for m in (status_merke(rad), triage_merke(rad, self.jobb_status(t.id))) if m)
        if rad.triage_feilet:
            linjer += [merke, f"[red]{escape(rad.triage_feil or '')}[/]"]
        elif rad.triage:
            linjer += [merke, "", escape(rad.triage.sammendrag), "", f"[dim]{escape(rad.triage.begrunnelse)}[/]"]
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
            " · redigert" if u and u.redigert is not None else "") + (" · i Outlook" if u and u.kladd else "")
        w.set_class(bool(u and u.status == KLART), "klart")

    # Handlinger

    @on(DataTable.RowSelected)
    def rad_valgt(self, *_) -> None:
        self.action_handlinger()

    def action_handlinger(self) -> None:
        """Menyen over det som gir mening for raden nå; det som ikke kan gjøres er utelatt."""
        if not (valgt := self.valgt()):
            return
        t, rad = valgt
        h: dict[str, tuple[str, str]] = {}
        u = rad.utkast
        if not self.ikke_klart(t, rad):
            h |= {"s": ("send", "send utkastet"), "e": ("rediger", "rediger utkastet"),
                  "c": ("kopier", "kopier utkastet")}
        if rad.status not in FERDIG and u and u.status not in (GENERERER, SENDT, FORKASTET):
            h["r"] = ("regenerer", "regenerer utkastet, med instruks")
        elif self.kan_gi_innspill(rad):
            h["i"] = ("innspill", "kom med innspill — Claude skriver et utkast ut fra tråden")
        if rad.status != AVVIST:
            h["a"] = ("avvis", "avvis — trenger ikke svar")
        if rad.status not in (BESVART, GAMMEL, AVVIST):
            h["u"] = ("utsett", "utsett til …")
        if self.merket:
            h["x"] = ("arkiver", f"arkiver de {len(self.merket)} merkede")
        elif self.kan_arkiveres(t):
            h["x"] = ("arkiver", "arkiver tråden")
        if self.lenke(t):
            h["o"] = ("åpne", "åpne i Teams")
        elif any(v.kladd and v.lenke for v in self.db.versjoner(t.id)):
            h["o"] = ("åpne", "åpne kladden i Outlook")

        def kjør(navn: str | None) -> None:
            if navn:
                self.run_worker(self.run_action(navn), exit_on_error=False)

        self.push_screen(RadHandlinger(f"{motpart(t)} · {t.emne}"[:70], h), kjør)

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
        if t.kanal in self.config.graph:
            self.notify("Mail sendes fra Outlook, o åpner kladden" if t.kanal == "mail"
                        else "Sendes fra Teams: c kopierer utkastet, o åpner chatten", severity="warning")
            return
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
            self.db.kurator_etter_sending(u, self.rader[t.id].siste_melding_id, self.nå())
            self._hold.discard(t.id)
            self.rader[t.id] = self.db.rad(t.id)
            await self.poll_nå()  # mitt svar ligger i Tråden nå → besvart
            self.tegn_tabell()
            self.gå_til(indeks)
        finally:
            self._sender.discard(t.id)

    def action_kopier(self) -> None:
        """Utkastet til utklippstavla, for å lime inn selv (Teams)."""
        if not (valgt := self.valgt()):
            return
        t, rad = valgt
        if grunn := self.ikke_klart(t, rad):
            self.notify(grunn, severity="warning")
            return
        if n := len(rad.utkast.plassholdere):
            self.notify(f"{n} plassholder{'e' if n > 1 else ''} igjen, fyll ut med e", severity="warning")
            return
        try:
            self.kopier(rad.utkast.gjeldende)
        except Exception as e:
            self.notify(f"Kopiering feilet: {e}", severity="error")
            return
        self.notify("Utkastet er kopiert" + (", o åpner chatten" if self.lenke(t) else ""))

    def lenke(self, t: Tråd) -> str | None:
        """Tråden i kanalens egen app, for kanaler som har det (Teams)."""
        kanal = next((k for k in self.kanaler if k.navn == t.kanal), None)
        return kanal.lenke(t.id) if hasattr(kanal, "lenke") else None

    def action_åpne(self) -> None:
        """Chatten i Teams, ellers kladden i Outlook (under regenerering: forrige versjon sin)."""
        if not (valgt := self.valgt()):
            return
        if lenke := self.lenke(valgt[0]):
            self.åpne(lenke)
            return
        u = next((v for v in reversed(self.db.versjoner(valgt[0].id)) if v.kladd and v.lenke), None)
        if u is None:
            self.notify("Ingen kladd i Outlook for denne tråden", severity="warning")
            return
        self.åpne(u.lenke)

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

    def kan_arkiveres(self, t: Tråd) -> bool:
        """Bare kanaler med innboks (mail). Teams-chatter har ingenting å rydde."""
        return any(k.navn == t.kanal and hasattr(k, "arkiver") for k in self.kanaler)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        """Merk og arkiver er grået ut på rader som ikke kan arkiveres."""
        if action not in ("merk", "arkiver"):
            return True
        if action == "arkiver" and self.merket:
            return True
        valgt = self.valgt()
        return True if valgt and self.kan_arkiveres(valgt[0]) else None

    def oppdater_taster(self) -> None:
        """Footeren tegnes på nytt bare når merk/arkiver skifter mellom tilgjengelig og grået ut."""
        tilstand = tuple(self.check_action(a, ()) for a in ("merk", "arkiver"))
        if tilstand != self._taster and self.screen_stack:  # skjermen kan være revet ned
            self._taster = tilstand
            self.refresh_bindings()

    def foreslå(self, t: Tråd) -> None:
        """Triagen sier rydd for siste Melding: merket for arkivering, én gang per Melding."""
        rad = self.rader[t.id]
        if (rad.triage and rad.triage.rydd and rad.triage_melding_id == t.siste.id and rad.status not in FERDIG
                and self._foreslått.get(t.id) != t.siste.id and self.kan_arkiveres(t)):
            self._foreslått[t.id] = t.siste.id
            self.merket.add(t.id)

    def action_merk(self) -> None:
        """Merker raden for arkivering (eller fjerner merket) og går til neste."""
        if not (valgt := self.valgt()) or not self.kan_arkiveres(valgt[0]):
            return
        t = valgt[0]
        self.merket ^= {t.id}
        dt = self.query_one(DataTable)
        dt.update_cell(t.id, "fra", self.fra_celle(t))
        self.gå_til(dt.cursor_row + 1)
        self.oppdater_taster()
        self.oppdater_status()

    def action_arkiver(self) -> None:
        """Merkede Tråder, ellers den valgte, ut av lista (se `Arkiv`)."""
        ids = [t.id for t in self.sortert() if t.id in self.merket]
        if not ids and (valgt := self.valgt()) and self.kan_arkiveres(valgt[0]):
            ids = [valgt[0].id]
        if ids:
            self.run_worker(self.arkiver(ids), group="arkiver", exit_on_error=False)

    async def arkiver(self, ids: list[str]) -> None:
        kanaler = {k.navn: k for k in self.kanaler}
        indeks, valgt = self.query_one(DataTable).cursor_row, self.valgt_id()
        arkivert, feil = 0, []
        for id in ids:
            if (t := self.tråder.get(id)) is None:
                continue
            if not hasattr(kanal := kanaler.get(t.kanal), "arkiver"):
                feil.append(f"{motpart(t)}: {t.kanal} kan ikke arkiveres")
                continue
            try:
                await kanal.arkiver(id)
            except Exception as e:
                feil.append(f"{motpart(t)}: {str(e) or type(e).__name__}")
                continue
            avsender = next((m.fra.adresse for m in reversed(t.meldinger) if not m.fra_meg), "")
            self.db.arkivert(id, avsender, self._foreslått.get(id) == t.siste.id, self.nå())
            self.glem(id)
            arkivert += 1
        if arkivert:
            self.tegn_tabell()  # markøren blir på valgt rad, eller samme plass når den ble arkivert
            if valgt not in self.tråder:
                self.gå_til(indeks)
            self.notify(f"{arkivert} tråd{'er' if arkivert > 1 else ''} arkivert")
        if feil:
            self.notify("Arkivering feilet:\n" + "\n".join(escape(f) for f in feil), severity="error", timeout=10)
        self.oppdater_taster()
        self.oppdater_status()

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

    def action_regenerer(self) -> None:
        if not (valgt := self.valgt()):
            return
        t, rad = valgt
        u = rad.utkast
        if rad.status in FERDIG:
            grunn = "Tråden er ikke aktiv"
        elif u is None:
            grunn = "Ingen utkast å regenerere" if not rad.trenger_utkast else "Utkastet er ikke klart ennå"
        elif u.status == GENERERER:
            grunn = "Agenten skriver allerede"
        elif u.status in (SENDT, FORKASTET):
            grunn = "Ingen åpent utkast"
        else:
            grunn = None
        if grunn:
            self.notify(grunn, severity="warning")
            return
        self.push_screen(InstruksPrompt(), lambda instruks: self.regenerer(t.id, instruks))

    def kan_gi_innspill(self, rad: Rad) -> bool:
        """Aktiv Tråd uten åpent utkast for siste Melding, og ingen på vei av seg selv."""
        u = rad.utkast
        return (rad.status not in FERDIG and not rad.trenger_utkast
                and (u is None or u.melding_id != rad.siste_melding_id or u.status in (SENDT, FORKASTET, FEILET)))

    def action_innspill(self) -> None:
        """Et utkast for siste Melding selv om triagen ikke sa svar. Klart: ↵ → e redigerer."""
        if not (valgt := self.valgt()) or not self.kan_gi_innspill(valgt[1]):
            return
        t = valgt[0]
        self._hold.discard(t.id)
        self.db.nytt_utkast(t.id, t.siste.id, self.nå(), INNSPILL)
        self.rader[t.id] = self.db.rad(t.id)
        self.planlegg(t)
        self.tegn_tabell()
        self.vis_detalj()

    def regenerer(self, tråd_id: str, instruks: str | None) -> None:
        """Ny versjon for siste Melding. None = avbrutt; tom = prøv igjen uten verktøy.

        `planlegg` køer den når triagen for siste Melding sier svar (straks, eller når triagen er ferdig).
        """
        if instruks is None or self.rader[tråd_id].status in FERDIG:
            return
        t = self.tråder[tråd_id]
        self._hold.discard(tråd_id)
        self.db.nytt_utkast(tråd_id, t.siste.id, self.nå(), instruks or None)
        self.rader[tråd_id] = self.db.rad(tråd_id)
        self.planlegg(t)
        self.tegn_tabell()

    def etter_ny_melding(self, tråd_id: str, valg: str | None) -> None:
        if valg == "s":
            self.prøv_send(tråd_id)
        elif valg == "r":
            self.push_screen(InstruksPrompt(), lambda instruks: self.regenerer(tråd_id, instruks))
        else:  # se meldingen: slutten av Tråden nederst i visningen, redigeringen står under
            scroll = self.query_one("#scroll", VerticalScroll)
            scroll.scroll_to(y=max(0, self.query_one("#trad").outer_size.height - scroll.size.height // 2),
                             animate=False)

    def action_kunnskapsbase(self) -> None:
        """Kunnskapsbasen i $EDITOR. Det jeg endrer committes som `manuelt: endringer` etterpå."""
        rot = self.config.kunnskapsbase
        try:
            sikre_repo(rot)
        except (OSError, subprocess.CalledProcessError) as e:
            self.notify(f"Kunnskapsbasen: {e}", severity="error")
            return
        if (kode := self.i_terminal(katalog_argv(rot))) is None:
            return
        if kode != 0:
            self.notify(f"Editoren avsluttet med {kode}", severity="error")
        try:
            commit_manuelt(rot, self.config.meg)
        except (OSError, subprocess.CalledProcessError) as e:
            self.notify(f"Kunne ikke committe Kunnskapsbasen: {e}", severity="error")

    def action_jobber(self) -> None:
        """launchd-jobbene (`chores status`): har sync kjørt denne uka, når går den neste, hva feilet?"""
        try:
            liste = {j["name"]: j for j in jobber.jobber()}
        except Exception as e:  # bin/chores mangler eller feiler: si det, ikke krasj TUI-en
            self.notify(f"chores status: {e}", severity="error")
            return

        def handling(j: dict, valg: str | None) -> None:
            if valg is None:
                self.action_jobber()  # esc: tilbake til lista
            elif valg == "k":
                try:
                    jobber.kjør(j["label"])
                    self.notify(f"▶ {j['name']} startet")
                except RuntimeError as e:
                    self.notify(str(e), severity="error")
            elif valg == "i" or j.get("log"):
                self.i_terminal(jobber.detaljer_argv(j["name"]) if valg == "i"
                                else jobber.logg_argv(j["name"], j["log"]))

        def valgt(navn: str | None) -> None:
            if navn:
                self.push_screen(JobbHandling(liste[navn]), lambda v: handling(liste[navn], v))

        self.push_screen(JobbValg(list(liste.values())), valgt)

    def i_terminal(self, argv: list[str]) -> int | None:
        """Kjører `argv` med TUI-en suspendert. None hvis den ikke kunne startes."""
        try:
            with self.suspend():
                return subprocess.call(argv)
        except (OSError, SuspendNotSupported) as e:
            self.notify(f"Kunne ikke åpne editor: {e}", severity="error")
            return None

    def rediger_i_editor(self, tekst: str, tråd: Tråd | None = None) -> str | None:
        """$EDITOR via suspend, markøren på første plassholder. None hvis editoren feilet.
        Tråden står under en saks-linje, nyeste først; alt fra linja og ned fjernes."""
        linje, kol = første_plassholder(tekst)
        with tempfile.TemporaryDirectory(prefix="tower-") as d:
            sti = Path(d) / "utkast.txt"
            sti.write_text(tekst + "\n" + (f"\n{SAKS}\n{tråd_ren(tråd)}" if tråd else ""))
            try:
                with self.suspend():
                    kode = subprocess.call(editor_argv(sti, linje, kol))
            except (OSError, SuspendNotSupported) as e:
                self.notify(f"Kunne ikke åpne editor: {e}", severity="error")
                return None
            if kode != 0:
                self.notify(f"Editoren avsluttet med {kode}, utkastet er uendret", severity="error")
                return None
            return sti.read_text().split(f"\n{SAKS}\n")[0].rstrip("\n")

    def oppdater_status(self) -> None:
        deler = [f"[b red]✗ {k}:[/] {escape(v)}" for k, v in self.hentfeil.items()]
        if self.agenter.feil:
            deler.append(f"[b red]✗ {escape(self.agenter.feil)}[/]")
        if self.kurator_feilet:
            deler.append(f"[b red]✗ kurator:[/] {escape(self.kurator_feilet[-1].feil or '')}")
        kjører = [j.etikett for a in (self.agenter, self.kurator) for j, _ in a.kjørende.values()]
        if kjører:
            n = len(self.agenter.kø) + len(self.kurator.kø)
            kø = f"  [dim]+{n} i kø[/]" if n else ""
            deler.append(f"[magenta]{SPINNER[self._tikk % len(SPINNER)]}[/] {escape(' · '.join(kjører))}{kø}")
        elif not deler:
            deler.append("[dim]agenter i ro[/]")
        rader = [r for id, r in self.rader.items() if id in self.tråder]  # arkiverte har fortsatt rad i Db
        aktive = sum(1 for r in rader if r.status not in FERDIG)
        klare = sum(1 for r in rader if r.status not in FERDIG and r.utkast and r.utkast.status == KLART)
        merket = f"   [dim]│[/]  [b yellow]● {len(self.merket)} merket[/]" if self.merket else ""
        kb = ""
        if self.kb_siste:
            emne, tid = self.kb_siste
            kb = f"   [dim]│  kb: {escape(emne.removeprefix('kurator: ')[:30])} {alder(tid, self.nå())}[/]"
        self.query_one("#status", Static).update(
            f"{'  '.join(deler)}   [dim]│[/]  {aktive} tråder venter   [dim]│[/]  {klare} utkast klare"
            f"{merket}   [dim]│[/]  ${self.kost:.3f} i dag{kb}")


def main(argv: list[str] | None = None) -> None:
    from tower import config as cfg

    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["mock"]:
        from tower.mock import main as mock

        sys.exit(mock(argv[1:]))
    if argv[:1] == ["login"]:
        from tower.graph import Graph, GraphFeil

        graph = Graph()
        if argv[1:] == ["--ved-behov"]:  # start-workday: nettleser bare når refresh-tokenet ikke virker lenger
            try:
                graph.token()
                print("allerede logget inn")
                return
            except GraphFeil:
                pass
        graph.login()
        print("logget inn")
        return
    if argv:
        sys.exit(f"bruk: tower [login [--ved-behov] | mock …]\n(ukjent argument: {' '.join(argv)})")
    config = cfg.last()
    db = Db(config.db)
    try:
        Tower(config, cfg.lag_kanaler(config), db, ClaudeRunner(config.modell, config.agent_cwd),
              varsle=macos_varsel).run()
    finally:
        db.lukk()
