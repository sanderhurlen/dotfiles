"""PROTOTYPE — throwaway. Svarer på: hvordan skal tower se ut og oppføre seg?

Tre radikalt ulike hovedskjermer over samme modell, byttes med [ og ] (eller --variant A|B|C):
  A  Split      — mailklient: trådtabell venstre, tråd + utkast høyre, agenter i statuslinja
  B  Fokuskø    — én tråd om gangen, handling flytter deg videre, agentlogg i sidepanel
  C  Tavle      — kolonner etter tilstand (haster / venter / agent jobber / info / ute), detalj i modal

Data: ekte sonnet-triage og -utkast fra utkast-agent-prototypen. Agentene er falske (sover like lenge
som de ekte kallene tok). Ingenting lagres; send = toast. Etter ~45 s kommer en ny melding fra
Harbor for å vise utdatert-utkast + auto-regenerering. Første utkast til Ingrid feiler én gang.

Kjør: ./run  [--variant B] [--fart 3]
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll, Container
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Input, ListItem, ListView, OptionList, RichLog, Static
from textual.widgets.option_list import Option

HER = Path(__file__).parent
NÅ = datetime(2026, 10, 7, 13, 0)
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
KANAL_IKON = {"mail": "✉", "teams": "◆"}
MAKS_AGENTER = 3
FART = 1.0  # --fart 3 = tre ganger raskere agenter enn de ekte kallene


# ---------------------------------------------------------------- modell (i minnet)

@dataclass
class Utkast:
    status: str = "genererer"  # genererer | klart | feilet | utdatert | sendt | forkastet
    tekst: str = ""
    sjekk: list[str] = field(default_factory=list)
    feil: str = ""
    instruks: str = ""
    versjon: int = 0


@dataclass
class Tråd:
    id: str
    kanal: str
    emne: str
    meldinger: list[dict]
    fasit: dict
    status: str = "ny"  # ny | triagert | venter på meg | besvart | avvist | utsatt
    triage: dict | None = None
    utkast: Utkast | None = None
    utsatt_til: str = ""
    agent: str = ""  # "triage" | "utkast" | "" (kjører nå)
    i_kø: bool = False

    @property
    def fra(self) -> str:
        m = next((m for m in reversed(self.meldinger) if not m["fra_meg"]), self.meldinger[-1])
        return m["fra"].split(" <")[0]

    @property
    def sist(self) -> dict:
        return self.meldinger[-1]

    @property
    def alder(self) -> str:
        t = datetime.strptime(self.sist["tid"], "%Y-%m-%d %H:%M")
        min_ = int((NÅ - t).total_seconds() // 60)
        if min_ < 60:
            return f"{min_}m"
        if min_ < 24 * 60:
            return f"{min_ // 60}t"
        return f"{min_ // (24 * 60)}d"

    @property
    def haster(self) -> bool:
        return bool(self.triage and self.triage["haster"])

    @property
    def info(self) -> bool:
        return bool(self.triage and self.triage["kategori"] == "info")

    @property
    def aktiv(self) -> bool:
        return self.status not in ("besvart", "avvist", "utsatt")

    def sorteringsnøkkel(self):
        rang = 0 if self.haster else 1 if (self.triage and not self.info) else 2 if not self.triage else 3
        return (not self.aktiv, rang, self.sist["tid"][::-1])


def last_tråder() -> list[Tråd]:
    data = json.loads((HER / "data.json").read_text())
    return [Tråd(id=d["id"], kanal=d["kanal"], emne=d["emne"], meldinger=d["meldinger"], fasit=d) for d in data]


def triage_merke(t: Tråd) -> str:
    if t.agent == "triage":
        return "[dim]triagerer…[/]"
    if not t.triage:
        return "[dim]ny[/]"
    if t.haster:
        return "[b red]● haster[/]"
    if t.info:
        return "[dim]○ info[/]"
    return "[yellow]● svar[/]"


def utkast_merke(t: Tråd) -> str:
    if t.status == "utsatt":
        return f"[blue]⏾ {t.utsatt_til}[/]"
    if t.status in ("besvart", "avvist"):
        return f"[dim]{t.status}[/]"
    u = t.utkast
    if t.info:
        return "[dim]—[/]"
    if not u:
        return "[dim]i kø[/]" if t.i_kø else ""
    return {
        "genererer": "[magenta]✎ skriver…[/]",
        "klart": "[green]✔ klart[/]" + (f" [dim]v{u.versjon}[/]" if u.versjon > 1 else ""),
        "feilet": "[red]✗ feilet[/]",
        "utdatert": "[yellow]↻ utdatert[/]",
        "sendt": "[dim]sendt[/]",
        "forkastet": "[dim]forkastet[/]",
    }[u.status]


def tråd_markdown(t: Tråd, kompakt: bool = False) -> str:
    """Tråden som Rich-markup (Static), nyeste melding sist."""
    ut = []
    meldinger = t.meldinger[-1:] if kompakt else t.meldinger
    if kompakt and len(t.meldinger) > 1:
        ut.append(f"[dim]… {len(t.meldinger) - 1} tidligere melding(er)[/]\n")
    for m in meldinger:
        hvem = "[b cyan]meg[/]" if m["fra_meg"] else f"[b]{m['fra'].split(' <')[0]}[/]"
        ut.append(f"{hvem}  [dim]{m['tid'][5:]}[/]")
        ut.append(m["tekst"].replace("[", r"\["))
        ut.append("")
    return "\n".join(ut)


def utkast_markup(t: Tråd) -> str:
    u = t.utkast
    if t.info:
        return "[dim]Bare info — ingen utkast. [b]a[/b] kvitterer ut.[/]"
    if not u:
        return "[dim]Venter på triage…[/]" if not t.triage else "[dim]I kø for utkast…[/]"
    if u.status == "genererer":
        return f"[magenta]{SPINNER[App_ticks() % len(SPINNER)]} Agenten skriver utkast…[/]" + (
            f"\n[dim]instruks: {u.instruks}[/]" if u.instruks else "")
    if u.status == "feilet":
        return f"[red]✗ Utkast feilet:[/] {u.feil}\n[dim]r = prøv igjen[/]"
    tekst = u.tekst.replace("[", r"\[")
    tekst = tekst.replace(r"\[\[", "[b reverse yellow] ").replace("]]", " [/]")
    sjekk = "\n".join(f"[yellow]☐[/] {s}" for s in u.sjekk)
    pre = "[yellow]↻ Ny melding kom etter dette utkastet — regenererer…[/]\n\n" if u.status == "utdatert" else ""
    return pre + tekst + (f"\n\n[b]Sjekk før sending[/]\n{sjekk}" if sjekk else "")


_ticks = 0


def App_ticks() -> int:
    return _ticks


# ---------------------------------------------------------------- modaler

class UtsettSkjerm(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "dismiss(None)", "Avbryt")]
    DEFAULT_CSS = """
    UtsettSkjerm { align: center middle; }
    UtsettSkjerm OptionList { width: 36; height: auto; border: round $accent; }
    """

    def compose(self) -> ComposeResult:
        ol = OptionList(Option("1 time", "1t"), Option("i morgen 08:00", "i morgen"), Option("mandag 08:00", "mandag"))
        ol.border_title = "Utsett til"
        yield ol

    @on(OptionList.OptionSelected)
    def valgt(self, e: OptionList.OptionSelected) -> None:
        self.dismiss(e.option.id)


class InstruksSkjerm(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "dismiss(None)", "Avbryt")]
    DEFAULT_CSS = """
    InstruksSkjerm { align: center middle; }
    InstruksSkjerm Input { width: 70; border: round $accent; }
    """

    def compose(self) -> ComposeResult:
        i = Input(placeholder="f.eks. «kortere», «si nei høflig», «spør om budsjett» (tom = bare prøv igjen)")
        i.border_title = "Regenerer med instruks"
        yield i

    @on(Input.Submitted)
    def ferdig(self, e: Input.Submitted) -> None:
        self.dismiss(e.value)


class DetaljSkjerm(ModalScreen[None]):
    """Brukes av variant C: tråd + utkast i en modal, samme handlinger."""

    BINDINGS = [
        Binding("escape,q", "dismiss", "Lukk"),
        Binding("s", "app.send", "Send"),
        Binding("e", "app.rediger", "Rediger"),
        Binding("r", "app.regenerer", "Regenerer"),
        Binding("a", "app.avvis", "Avvis"),
        Binding("u", "app.utsett", "Utsett"),
    ]
    DEFAULT_CSS = """
    DetaljSkjerm { align: center middle; }
    DetaljSkjerm > Vertical { width: 90%; height: 90%; border: thick $accent; background: $surface; }
    DetaljSkjerm #hode { padding: 0 1; background: $boost; height: auto; }
    DetaljSkjerm VerticalScroll { padding: 0 1; }
    DetaljSkjerm #utkast { border: round $success; padding: 0 1; margin-top: 1; height: auto; }
    """

    def __init__(self, tråd_id: str) -> None:
        super().__init__()
        self.tråd_id = tråd_id

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(id="hode")
            with VerticalScroll():
                yield Static(id="trad")
                yield Static(id="utkast")
            yield Footer()

    def on_mount(self) -> None:
        self.oppdater()

    def oppdater(self) -> None:
        t = self.app.finn(self.tråd_id)
        tr = t.triage or {}
        self.query_one("#hode", Static).update(
            f"{KANAL_IKON[t.kanal]} [b]{t.emne}[/]  {triage_merke(t)}  {utkast_merke(t)}\n"
            f"[i]{tr.get('sammendrag', '')}[/]")
        self.query_one("#trad", Static).update(tråd_markdown(t))
        u = self.query_one("#utkast", Static)
        u.update(utkast_markup(t))
        u.border_title = "Utkast"

    def valgt_id(self) -> str | None:
        return self.tråd_id


# ---------------------------------------------------------------- variant A: split

class VariantA(Container):
    NAVN = "Split — mailklient"
    DEFAULT_CSS = """
    VariantA { layout: horizontal; }
    VariantA DataTable { width: 55%; height: 1fr; }
    VariantA #hoyre { width: 1fr; border-left: vkey $panel; }
    VariantA #hode { padding: 0 1; background: $boost; height: auto; }
    VariantA #scroll { padding: 0 1; }
    VariantA #utkast { border: round $success; padding: 0 1; height: auto; margin-top: 1; }
    VariantA #agentlinje { dock: bottom; height: 1; background: $panel; padding: 0 1; }
    """

    def compose(self) -> ComposeResult:
        yield DataTable(cursor_type="row", zebra_stripes=True)
        with Vertical(id="hoyre"):
            yield Static(id="hode")
            with VerticalScroll(id="scroll"):
                yield Static(id="trad")
                yield Static(id="utkast")
        yield Static(id="agentlinje")

    def on_mount(self) -> None:
        dt = self.query_one(DataTable)
        dt.add_column("", key="k", width=1)
        dt.add_column("Fra", key="fra", width=16)
        dt.add_column("Emne", key="emne", width=30)
        dt.add_column("Triage", key="tr", width=11)
        dt.add_column("Utkast", key="u", width=12)
        dt.add_column("", key="alder", width=3)
        self.oppdater()
        dt.focus()

    def oppdater(self) -> None:
        dt = self.query_one(DataTable)
        valgt = self.valgt_id()
        tråder = sorted(self.app.tråder, key=Tråd.sorteringsnøkkel)
        dt.clear()
        for t in tråder:
            dim = "" if t.aktiv else "[dim]"
            dt.add_row(KANAL_IKON[t.kanal], dim + t.fra, dim + emne_linje(t), triage_merke(t), utkast_merke(t), t.alder, key=t.id)
        if valgt:
            try:
                dt.move_cursor(row=dt.get_row_index(valgt))
            except Exception:
                pass
        self.vis_detalj()
        self.tikk()

    def tikk(self) -> None:
        kjører = [t for t in self.app.tråder if t.agent]
        kø = [t for t in self.app.tråder if t.i_kø and not t.agent]
        s = SPINNER[App_ticks() % len(SPINNER)]
        if kjører:
            deler = " · ".join(f"{t.agent} {t.fra.split()[0]}" for t in kjører)
            tekst = f"[magenta]{s}[/] {len(kjører)} agenter: {deler}" + (f"  [dim]+{len(kø)} i kø[/]" if kø else "")
        else:
            tekst = "[dim]agenter i ro[/]"
        venter = sum(1 for t in self.app.tråder if t.aktiv and t.utkast and t.utkast.status == "klart")
        self.query_one("#agentlinje", Static).update(
            f"{tekst}   [dim]│[/]  {venter} utkast klare  [dim]│[/]  ${self.app.kost:.3f} i dag  [dim]│ poll 2s[/]")
        t = self.app.finn(self.valgt_id()) if self.valgt_id() else None
        if t and t.utkast and t.utkast.status == "genererer":
            self.query_one("#utkast", Static).update(utkast_markup(t))

    def valgt_id(self) -> str | None:
        dt = self.query_one(DataTable)
        if dt.row_count == 0:
            return None
        return dt.coordinate_to_cell_key(dt.cursor_coordinate).row_key.value

    @on(DataTable.RowHighlighted)
    def vis_detalj(self, *_) -> None:
        vid = self.valgt_id()
        if not vid:
            return
        t = self.app.finn(vid)
        tr = t.triage or {}
        self.query_one("#hode", Static).update(
            f"{KANAL_IKON[t.kanal]} [b]{t.emne}[/]\n"
            f"{triage_merke(t)}  [i]{tr.get('sammendrag', '')}[/]\n"
            f"[dim]{tr.get('begrunnelse', '')}[/]")
        self.query_one("#trad", Static).update(tråd_markdown(t))
        u = self.query_one("#utkast", Static)
        u.update(utkast_markup(t))
        u.border_title = "Utkast " + utkast_merke(t)
        u.styles.border = ("round", "green" if t.utkast and t.utkast.status == "klart" else "grey")


# ---------------------------------------------------------------- variant B: fokuskø

class VariantB(Container):
    NAVN = "Fokuskø — én om gangen"
    DEFAULT_CSS = """
    VariantB { layout: horizontal; }
    VariantB #hoved { width: 1fr; }
    VariantB #fremdrift { height: 3; padding: 1 2 0 2; }
    VariantB #kort { margin: 1 4; padding: 1 2; border: tall $accent; height: 1fr; }
    VariantB #kort-hode { height: auto; }
    VariantB #kort-trad { height: auto; margin-top: 1; color: $text-muted; }
    VariantB #kort-utkast { height: auto; margin-top: 1; border-top: dashed $success; padding-top: 1; }
    VariantB #infostripe { height: 3; padding: 0 2; background: $boost; }
    VariantB RichLog { width: 44; border-left: vkey $panel; padding: 0 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.nåværende: str | None = None
        self.sett_logg = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="hoved"):
            yield Static(id="fremdrift")
            with VerticalScroll(id="kort", can_focus=True):
                yield Static(id="kort-hode")
                yield Static(id="kort-trad")
                yield Static(id="kort-utkast")
            yield Static(id="infostripe")
        logg = RichLog(markup=True, wrap=True)
        logg.border_title = "Agenter"
        yield logg

    def on_mount(self) -> None:
        self.query_one("#kort").focus()
        self.oppdater()

    def kø(self) -> list[Tråd]:
        return [t for t in sorted(self.app.tråder, key=Tråd.sorteringsnøkkel) if t.aktiv and t.triage and not t.info]

    def oppdater(self) -> None:
        kø = self.kø()
        ids = [t.id for t in kø]
        if self.nåværende not in ids:
            self.nåværende = ids[0] if ids else None
        klare = sum(1 for t in kø if t.utkast and t.utkast.status == "klart")
        ferdig = sum(1 for t in self.app.tråder if t.status in ("besvart", "avvist", "utsatt"))
        totalt = ferdig + len(kø)
        bar_b = 30
        fylt = int(bar_b * ferdig / totalt) if totalt else 0
        pos = ids.index(self.nåværende) + 1 if self.nåværende else 0
        self.query_one("#fremdrift", Static).update(
            f"[green]{'█' * fylt}[/][dim]{'░' * (bar_b - fylt)}[/]  {ferdig}/{totalt} unna   "
            f"[b]{pos}[/] av {len(kø)} i køen   [green]{klare} klare[/]   [dim]n/p = neste/forrige[/]")
        info = [t for t in self.app.tråder if t.aktiv and t.info]
        utriagert = [t for t in self.app.tråder if not t.triage]
        self.query_one("#infostripe", Static).update(
            f"[b]Bare info ({len(info)})[/]  " + "  ·  ".join(f"[dim]{t.emne}[/]" for t in info)
            + ("\n[dim]k = kvitter ut alle info[/]" if info else "")
            + (f"   [magenta]{len(utriagert)} triageres…[/]" if utriagert else ""))
        self.vis_kort()
        logg = self.query_one(RichLog)
        for linje in self.app.logg[self.sett_logg:]:
            logg.write(linje)
        self.sett_logg = len(self.app.logg)

    def vis_kort(self) -> None:
        hode = self.query_one("#kort-hode", Static)
        if not self.nåværende:
            hode.update("\n\n[b green]Innboks null.[/] Ingenting venter på deg." if all(t.triage for t in self.app.tråder)
                        else "\n\n[magenta]Agentene jobber…[/]")
            self.query_one("#kort-trad", Static).update("")
            self.query_one("#kort-utkast", Static).update("")
            return
        t = self.app.finn(self.nåværende)
        kort = self.query_one("#kort")
        kort.border_title = f"{KANAL_IKON[t.kanal]} {t.kanal}  ·  {t.fra}  ·  {t.alder} siden"
        kort.styles.border = ("tall", "red" if t.haster else "yellow")
        hode.update(f"[b]{t.emne}[/]   {triage_merke(t)}\n\n[b i]{t.triage['sammendrag']}[/]")
        self.query_one("#kort-trad", Static).update(tråd_markdown(t, kompakt=True))
        self.query_one("#kort-utkast", Static).update(utkast_markup(t))

    def tikk(self) -> None:
        if self.nåværende:
            t = self.app.finn(self.nåværende)
            if t.utkast and t.utkast.status == "genererer":
                self.query_one("#kort-utkast", Static).update(utkast_markup(t))

    def valgt_id(self) -> str | None:
        return self.nåværende

    def flytt(self, d: int) -> None:
        ids = [t.id for t in self.kø()]
        if not ids:
            return
        i = ids.index(self.nåværende) if self.nåværende in ids else 0
        self.nåværende = ids[(i + d) % len(ids)]
        self.oppdater()


# ---------------------------------------------------------------- variant C: tavle

KOLONNER = [
    ("haster", "● Haster", "red"),
    ("venter", "Venter på meg", "yellow"),
    ("jobber", "Agenten jobber", "magenta"),
    ("info", "Bare info", "grey"),
    ("ute", "Ute av veien", "blue"),
]


def kolonne_for(t: Tråd) -> str:
    if not t.aktiv:
        return "ute"
    if t.agent or t.i_kø or not t.triage or (t.utkast and t.utkast.status in ("genererer", "utdatert")):
        return "jobber"
    if t.info:
        return "info"
    return "haster" if t.haster else "venter"


def emne_linje(t: Tråd) -> str:
    """Teams-chat har deltakernavn som emne; vis starten av siste melding i stedet."""
    if t.emne == t.fra:
        tekst = t.sist["tekst"].replace("\n", " ")
        return f"[i]«{tekst[:40]}{'…' if len(tekst) > 40 else ''}»[/]"
    return t.emne


class Kort(ListItem):
    def __init__(self, t: Tråd) -> None:
        super().__init__()
        self.tråd_id = t.id
        self.t = t

    def compose(self) -> ComposeResult:
        t = self.t
        linje3 = (t.triage or {}).get("sammendrag", "")
        if kolonne_for(t) == "jobber":
            linje3 = f"[magenta]{SPINNER[App_ticks() % len(SPINNER)]} {t.agent or 'i kø'}[/]"
        elif kolonne_for(t) == "ute":
            linje3 = utkast_merke(t)
        elif t.utkast and t.utkast.status == "feilet":
            linje3 = "[red]✗ utkast feilet[/]"
        yield Static(f"{KANAL_IKON[t.kanal]} [b]{t.fra}[/] [dim]{t.alder}[/]\n{emne_linje(t)}\n[dim]{linje3}[/]")


class VariantC(Container):
    NAVN = "Tavle — kolonner etter tilstand"
    DEFAULT_CSS = """
    VariantC { layout: horizontal; }
    VariantC ListView { width: 1fr; border: round $panel; height: 1fr; }
    VariantC ListView:focus-within { border: round $accent; }
    VariantC ListItem { padding: 0 1; margin-bottom: 1; height: auto; background: $boost; }
    VariantC #ute ListItem { opacity: 60%; }
    VariantC #info, VariantC #ute { width: 22; }
    """

    def compose(self) -> ComposeResult:
        for kid, tittel, farge in KOLONNER:
            lv = ListView(id=kid)
            lv.border_title = f"[{farge}]{tittel}[/]"
            yield lv

    def on_mount(self) -> None:
        self.oppdater()
        self.query_one("#venter", ListView).focus()

    def oppdater(self) -> None:
        valgt = self.valgt_id()
        for kid, tittel, farge in KOLONNER:
            lv = self.query_one(f"#{kid}", ListView)
            tråder = [t for t in sorted(self.app.tråder, key=Tråd.sorteringsnøkkel) if kolonne_for(t) == kid]
            idx = lv.index
            lv.clear()
            for t in tråder:
                lv.append(Kort(t))
            lv.border_title = f"[{farge}]{tittel}[/] [dim]{len(tråder)}[/]"
            ids = [t.id for t in tråder]
            if valgt in ids:
                lv.index = ids.index(valgt)
                lv.focus()
            elif ids:
                lv.index = min(idx or 0, len(ids) - 1)
        if isinstance(self.app.screen, DetaljSkjerm):
            self.app.screen.oppdater()

    def tikk(self) -> None:
        if any(t.agent for t in self.app.tråder) and App_ticks() % 3 == 0:
            for item in self.query_one("#jobber", ListView).query(Kort):
                t = item.t
                for st in item.query(Static):
                    st.update(
                        f"{KANAL_IKON[t.kanal]} [b]{t.fra}[/] [dim]{t.alder}[/]\n{emne_linje(t)}\n"
                        f"[magenta]{SPINNER[App_ticks() % len(SPINNER)]} {t.agent or 'i kø'}[/]")
        if isinstance(self.app.screen, DetaljSkjerm):
            t = self.app.finn(self.app.screen.tråd_id)
            if t.utkast and t.utkast.status == "genererer":
                self.app.screen.oppdater()

    def valgt_id(self) -> str | None:
        f = self.app.focused
        lv = f if isinstance(f, ListView) else None
        if lv is None:
            return None
        item = lv.highlighted_child
        return item.tråd_id if isinstance(item, Kort) else None

    @on(ListView.Selected)
    def åpne(self, e: ListView.Selected) -> None:
        if isinstance(e.item, Kort):
            self.app.push_screen(DetaljSkjerm(e.item.tråd_id))


VARIANTER = {"A": VariantA, "B": VariantB, "C": VariantC}


# ---------------------------------------------------------------- app

class Tower(App):
    TITLE = "tower"
    CSS = """
    #variant { height: 1fr; }
    #bytter { dock: top; height: 1; background: $warning; color: $background; text-align: center; text-style: bold; }
    """
    BINDINGS = [
        Binding("s", "send", "Send"),
        Binding("e", "rediger", "Rediger"),
        Binding("r", "regenerer", "Regenerer"),
        Binding("a", "avvis", "Avvis"),
        Binding("u", "utsett", "Utsett"),
        Binding("n", "neste", "Neste", show=False),
        Binding("p", "forrige", "Forrige", show=False),
        Binding("k", "kvitter_info", "Kvitter info", show=False),
        Binding("left_square_bracket", "variant(-1)", "◀ variant", show=False),
        Binding("right_square_bracket", "variant(1)", "variant ▶", show=False),
        Binding("q", "quit", "Avslutt"),
    ]

    def __init__(self, variant: str = "A") -> None:
        super().__init__()
        self.tråder = last_tråder()
        self.variant = variant
        self.kost = 0.0
        self.logg: list[str] = []
        self.sem = asyncio.Semaphore(MAKS_AGENTER)
        self.feilet_en_gang: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Container(id="variant")
        yield Static(id="bytter")
        yield Footer()

    async def on_mount(self) -> None:
        await self.bytt_variant(self.variant)
        self.set_interval(0.1, self.tikk)
        for t in self.tråder:
            self.kjør_triage(t)
        self.set_timer(45 / FART, self.ny_melding)

    # -- variantbytte
    async def bytt_variant(self, key: str) -> None:
        self.variant = key
        c = self.query_one("#variant")
        await c.remove_children()
        await c.mount(VARIANTER[key]())
        keys = list(VARIANTER)
        self.query_one("#bytter", Static).update(
            f"PROTOTYPE   ◀ [   {key} — {VARIANTER[key].NAVN}   ] ▶   ([ og ] bytter, {keys.index(key) + 1}/{len(keys)})")

    async def action_variant(self, d: int) -> None:
        keys = list(VARIANTER)
        await self.bytt_variant(keys[(keys.index(self.variant) + d) % len(keys)])

    @property
    def v(self):
        return self.query_one("#variant").children[0]

    def finn(self, tid: str) -> Tråd:
        return next(t for t in self.tråder if t.id == tid)

    def endret(self) -> None:
        try:
            self.v.oppdater()
        except (NoMatches, IndexError):
            pass  # variant byttes akkurat nå

    def tikk(self) -> None:
        global _ticks
        _ticks += 1
        try:
            self.v.tikk()
        except (NoMatches, IndexError):
            pass

    def logg_linje(self, tekst: str) -> None:
        self.logg.append(f"[dim]{datetime.now():%H:%M:%S}[/] {tekst}")

    # -- falske agenter
    @work(group="agenter", exit_on_error=False)
    async def kjør_triage(self, t: Tråd) -> None:
        t.i_kø = True
        self.endret()
        async with self.sem:
            t.agent, t.i_kø = "triage", False
            self.endret()
            await asyncio.sleep(t.fasit["triage_sek"] / FART)
            t.triage = t.fasit["triage"]
            t.agent = ""
            t.status = "triagert" if t.info else "venter på meg"
            self.kost += t.fasit["triage_usd"]
            self.logg_linje(f"[b]triage[/] {t.fra}: {triage_merke(t)} [dim]{t.fasit['triage_sek']}s ${t.fasit['triage_usd']}[/]")
        self.endret()
        if not t.info:
            self.kjør_utkast(t)

    @work(group="agenter", exit_on_error=False)
    async def kjør_utkast(self, t: Tråd, instruks: str = "") -> None:
        forrige = t.utkast
        t.utkast = Utkast(status="genererer", instruks=instruks, versjon=(forrige.versjon if forrige else 0) + 1)
        t.i_kø = True
        self.endret()
        async with self.sem:
            t.agent, t.i_kø = "utkast", False
            self.endret()
            await asyncio.sleep(t.fasit["utkast_sek"] / FART)
            t.agent = ""
            self.kost += t.fasit["utkast_usd"]
            if t.id == "teams:ingrid-ring" and t.id not in self.feilet_en_gang:
                self.feilet_en_gang.add(t.id)
                t.utkast.status, t.utkast.feil = "feilet", "claude -p timeout etter 60s"
                self.logg_linje(f"[red]✗ utkast {t.fra} feilet[/] — prøver én gang til")
                self.endret()
                await asyncio.sleep(1)
                self.kjør_utkast(t, instruks)
                return
            tekst = t.fasit["utkast"]["tekst"]
            if instruks:
                tekst = f"[PROTOTYPE: regenerert med «{instruks}»]\n\n" + tekst
            if t.id == "mail:harbor-outage" and len(t.meldinger) > 1:
                tekst = tekst.replace("Hi James,", "Hi James,\n\nSorry for the silence — still on it.")
            t.utkast.tekst, t.utkast.sjekk, t.utkast.status = tekst, t.fasit["utkast"]["sjekk"], "klart"
            self.logg_linje(f"[b]utkast[/] {t.fra} [green]klart[/] v{t.utkast.versjon} [dim]{t.fasit['utkast_sek']}s ${t.fasit['utkast_usd']}[/]")
        self.endret()
        if t.haster:
            self.notify(f"{t.emne}", title="Haster-utkast klart", severity="warning")

    def ny_melding(self) -> None:
        t = self.finn("mail:harbor-outage")
        t.meldinger = t.meldinger + [{
            "fra": "James Whitfield <j.whitfield@harborlogistics.com>", "til": "support@visense.no",
            "cc": "sander@visense.no", "tid": "2026-10-07 12:58", "fra_meg": False,
            "tekst": "Any update? Still failing. Our CEO is asking.\n\nJames"}]
        if t.status in ("avvist", "besvart", "utsatt"):
            t.status = "venter på meg"
        if t.utkast and t.utkast.status in ("klart", "genererer"):
            t.utkast.status = "utdatert"
        self.logg_linje("[yellow]↻ ny melding[/] Harbor — utkast utdatert, triagerer på nytt")
        self.notify("Ny melding fra James Whitfield — utkast utdatert", title="Harbor", severity="warning")
        self.endret()
        t.triage = None
        self.kjør_triage(t)

    # -- handlinger
    def _valgt(self, trenger_utkast: bool = True) -> Tråd | None:
        skjerm = self.screen
        vid = skjerm.valgt_id() if isinstance(skjerm, DetaljSkjerm) else self.v.valgt_id()
        if not vid:
            return None
        t = self.finn(vid)
        if trenger_utkast and not (t.utkast and t.utkast.status == "klart"):
            self.notify("Ingen klart utkast på denne tråden", severity="warning")
            return None
        return t

    def _etter_handling(self) -> None:
        if isinstance(self.screen, DetaljSkjerm):
            self.screen.dismiss()
        self.endret()

    def action_send(self) -> None:
        t = self._valgt()
        if not t:
            return
        t.utkast.status, t.status = "sendt", "besvart"
        t.meldinger = t.meldinger + [{"fra": "Sander Hurlen", "til": "", "cc": "", "tid": "2026-10-07 13:00",
                                      "fra_meg": True, "tekst": t.utkast.tekst}]
        mottaker = "replyAll" if t.kanal == "mail" else "chat"
        self.notify(f"→ outbox ({mottaker}): {t.emne}", title="Sendt")
        self.logg_linje(f"[green]→ sendt[/] {t.emne}  [dim]kurator lærer…[/]")
        self._etter_handling()

    def action_rediger(self) -> None:
        t = self._valgt()
        if not t:
            return
        with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
            f.write(t.utkast.tekst)
            sti = f.name
        with self.suspend():
            subprocess.run([os.environ.get("EDITOR", "vi"), sti])
        t.utkast.tekst = Path(sti).read_text()
        self.notify("Utkast oppdatert (s for å sende)")
        self.endret()

    def action_regenerer(self) -> None:
        t = self._valgt(trenger_utkast=False)
        if not t or t.info:
            return

        def ferdig(instruks: str | None) -> None:
            if instruks is not None:
                self.logg_linje(f"[magenta]↻ regenererer[/] {t.fra}" + (f" «{instruks}»" if instruks else ""))
                self.kjør_utkast(t, instruks)

        self.push_screen(InstruksSkjerm(), ferdig)

    def action_avvis(self) -> None:
        t = self._valgt(trenger_utkast=False)
        if not t:
            return
        t.status = "avvist"
        if t.utkast and t.utkast.status == "klart":
            t.utkast.status = "forkastet"
        self.notify(f"Avvist: {t.emne}")
        self._etter_handling()

    def action_utsett(self) -> None:
        t = self._valgt(trenger_utkast=False)
        if not t:
            return

        def ferdig(når: str | None) -> None:
            if når:
                t.status, t.utsatt_til = "utsatt", når
                self.notify(f"Utsatt til {når}: {t.emne}")
                self._etter_handling()

        self.push_screen(UtsettSkjerm(), ferdig)

    def action_neste(self) -> None:
        if isinstance(self.v, VariantB):
            self.v.flytt(1)

    def action_forrige(self) -> None:
        if isinstance(self.v, VariantB):
            self.v.flytt(-1)

    def action_kvitter_info(self) -> None:
        n = 0
        for t in self.tråder:
            if t.aktiv and t.info:
                t.status = "avvist"
                n += 1
        self.notify(f"Kvitterte ut {n} info-tråder")
        self.endret()


if __name__ == "__main__":
    v = sys.argv[sys.argv.index("--variant") + 1].upper() if "--variant" in sys.argv else "A"
    if "--fart" in sys.argv:
        FART = float(sys.argv[sys.argv.index("--fart") + 1])
    Tower(v).run()
