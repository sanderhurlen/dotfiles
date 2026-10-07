from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from textual.widgets import DataTable, Static

from tower.app import Tower
from tower.config import lag_kanaler
from tower.db import Db
from tower.handlinger import editor_argv, første_plassholder, utsett_til
from tower.tests.conftest import NÅ, FalskRunner
from tower.tests.test_app import NORDLYS, ny_melding, tekst, triage_etter_emne, utkastkolonne, velg

# --- rene hjelpere


def test_utsett_til():
    lokal = NÅ.astimezone()  # onsdag
    assert utsett_til("1", NÅ) == NÅ + timedelta(hours=1)
    i_morgen = utsett_til("2", NÅ)
    assert (i_morgen.date() - lokal.date()).days == 1 and (i_morgen.hour, i_morgen.minute) == (8, 0)
    mandag = utsett_til("3", NÅ)
    assert mandag.weekday() == 0 and mandag.hour == 8 and 0 < (mandag.date() - lokal.date()).days <= 7
    man = datetime(2026, 10, 12, 9, tzinfo=lokal.tzinfo)  # mandag
    assert (utsett_til("3", man).date() - man.date()).days == 7


def test_første_plassholder():
    assert første_plassholder("Hei\n\nLevering [[dato]].") == (3, 10)
    assert første_plassholder("[[x]]") == (1, 1)
    assert første_plassholder("Ingen") == (1, 1)


def test_editor_argv():
    sti = Path("/tmp/u.txt")
    assert editor_argv(sti, 3, 10, "code --wait") == ["code", "--wait", "--goto", "/tmp/u.txt:3:10"]
    assert editor_argv(sti, 3, 10, "nvim") == ["nvim", "+call cursor(3, 10)", "/tmp/u.txt"]
    assert editor_argv(sti, 3, 10, "nano") == ["nano", "+3,10", "/tmp/u.txt"]
    assert editor_argv(sti, 3, 10, "ukjent -x") == ["ukjent", "-x", "/tmp/u.txt"]


# --- i appen

PLASS = "Hei Kari\n\nLevering [[dato]].\n\n--\nSander\nVisense"


def bare_nordlys(prompt: str) -> dict:
    kat = "svar" if "ERP" in prompt else "info"
    return {"kategori": kat, "haster": False, "sammendrag": "s", "begrunnelse": "b"}


class App(Tower):
    """Tower med fanget notify og styrbar klokke."""

    def __init__(self, config, runner=None, editor=None, kanaler=None):
        self.klokke = NÅ
        super().__init__(config, kanaler or lag_kanaler(config), Db(config.db), runner or FalskRunner(bare_nordlys),
                         nå=lambda: self.klokke, poll=False, editor=editor)
        self.varsler: list[tuple[str, str]] = []

    def notify(self, melding, *, severity="information", **kw):
        self.varsler.append((str(melding), severity))


async def klar(a, pilot, tråd_id=NORDLYS) -> None:
    await a.poll()
    await a.agenter.ferdig()
    await pilot.pause()
    velg(a, tråd_id)
    await pilot.pause()


def outbox(config) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(config.outbox.glob("*.json"))]


async def ferdig_sendt(a, pilot) -> None:
    await a.workers.wait_for_complete()
    await pilot.pause()


async def test_send_skriver_replyall_og_tråden_blir_besvart(config):
    a = App(config)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        indeks = a.query_one(DataTable).cursor_row
        await pilot.press("s")
        await ferdig_sendt(a, pilot)
        (req,) = outbox(config)
        assert req["path"] == "/me/messages/AAMkADMock-nordlys-erp-1/replyAll"
        assert req["body"]["comment"].startswith("Hei")
        rad = a.rader[NORDLYS]
        assert rad.status == "besvart" and rad.utkast.status == "sendt"
        assert "sendt" in utkastkolonne(a)[NORDLYS]
        assert a.query_one(DataTable).cursor_row == indeks and a.valgt_id() != NORDLYS  # markøren blir
        assert a.varsler == []


async def test_plassholdere_blokkerer_send(config):
    a = App(config, FalskRunner(bare_nordlys, utkast=lambda p: {"tekst": PLASS, "sjekk": []}))
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await pilot.press("s")
        await ferdig_sendt(a, pilot)
        assert outbox(config) == [] and a.rader[NORDLYS].utkast.status == "klart"
        assert a.varsler == [("1 plassholder igjen, fyll ut med e", "warning")]


async def test_send_feiler_lar_utkastet_stå_med_feil(config):
    class Nede:
        navn = "mail"

        def __init__(self, ekte):
            self.ekte, self.feil = ekte, True

        async def hent(self):
            return await self.ekte.hent()

        async def svar(self, tråd_id, tekst):
            if self.feil:
                raise OSError("Graph svarte 503")
            await self.ekte.svar(tråd_id, tekst)

    kanal = Nede(lag_kanaler(config)[0])
    a = App(config, kanaler=[kanal])
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await pilot.press("s")
        await ferdig_sendt(a, pilot)
        u = a.rader[NORDLYS].utkast
        assert (u.status, u.feil) == ("klart", "Graph svarte 503")
        assert a.varsler == [("Sending feilet: Graph svarte 503", "error")]
        assert "Sending feilet" in tekst(a, "#utkast") and "sending" in utkastkolonne(a)[NORDLYS]
        assert outbox(config) == []

        kanal.feil = False  # aldri auto-retry: først ny s sender
        await pilot.press("s")
        await ferdig_sendt(a, pilot)
        assert len(outbox(config)) == 1 and a.rader[NORDLYS].status == "besvart"


async def test_avvis_forkaster_og_ny_melding_gjenåpner(config):
    r = FalskRunner(bare_nordlys)
    a = App(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await pilot.press("a")
        await pilot.pause()
        rad = a.rader[NORDLYS]
        assert rad.status == "avvist" and rad.utkast.status == "forkastet"
        dt = a.query_one(DataTable)
        assert "avvist" in utkastkolonne(a)[NORDLYS]
        assert str(dt.get_row_at(dt.get_row_index(NORDLYS))[2]).startswith("[dim]")
        assert a.valgt_id() != NORDLYS

        info = "mail:AAQkADMock-azure-newsletter"  # kvittering av info
        velg(a, info)
        await pilot.press("a")
        assert a.rader[info].status == "avvist"

        ny_melding(config, NORDLYS, "ny-1", "Hallo?")
        await a.poll()
        await a.agenter.ferdig()
        rad = a.rader[NORDLYS]
        assert rad.status == "triagert" and rad.utkast.versjon == 2 and rad.utkast.status == "klart"


async def test_utsett_skjuler_og_vekkes_med_samme_utkast(config):
    r = FalskRunner(bare_nordlys)
    a = App(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await pilot.press("u")
        await pilot.pause()
        await pilot.press("2")
        await pilot.pause()
        rad = a.rader[NORDLYS]
        assert rad.status == "utsatt" and rad.utsatt_til == utsett_til("2", NÅ)
        assert "⏾" in utkastkolonne(a)[NORDLYS]
        velg(a, NORDLYS)
        await pilot.pause()
        assert "utsatt til" in tekst(a, "#hode") and not a.query_one("#utkast", Static).display

        a.klokke = rad.utsatt_til
        await a.poll()
        await a.agenter.ferdig()
        rad = a.rader[NORDLYS]
        assert rad.status == "triagert" and rad.utkast.versjon == 1 and rad.utkast.status == "klart"
        assert len(r.utkast_kall) == 1  # gjenbrukt


async def test_utsett_escape_avbryter_og_ny_melding_vekker_tidlig(config):
    a = App(config)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await pilot.press("u", "escape")
        await pilot.pause()
        assert a.rader[NORDLYS].status == "triagert"
        await pilot.press("u", "3")
        await pilot.pause()
        assert a.rader[NORDLYS].status == "utsatt"
        ny_melding(config, NORDLYS, "ny-1", "Hallo?")
        await a.poll()
        await a.agenter.ferdig()
        assert a.rader[NORDLYS].status == "triagert" and a.rader[NORDLYS].utkast.versjon == 2


async def test_rediger_lagrer_ved_siden_av_agentens_tekst_og_sender_den(config):
    sett: list[str] = []

    def editor(t):
        sett.append(t)
        return t.replace("[[dato]]", "uke 46")

    a = App(config, FalskRunner(bare_nordlys, utkast=lambda p: {"tekst": PLASS, "sjekk": []}), editor=editor)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await pilot.press("e")
        await pilot.pause()
        assert sett == [PLASS]
        u = a.rader[NORDLYS].utkast
        assert u.tekst == PLASS and "uke 46" in u.redigert and u.status == "klart"
        assert "uke 46" in tekst(a, "#utkast") and "redigert" in a.query_one("#utkast", Static).border_title
        await pilot.press("s")
        await ferdig_sendt(a, pilot)
        assert "Levering uke 46." in outbox(config)[0]["body"]["comment"]


async def test_rediger_avbrutt_endrer_ingenting(config):
    a = App(config, editor=lambda t: None)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await pilot.press("e")
        await pilot.pause()
        assert a.rader[NORDLYS].utkast.redigert is None and not a._hold


def redigerer_mens_ny_melding_kommer(config):
    def editor(t):
        ny_melding(config, NORDLYS, "ny-1", "Rekker dere fredag?")
        return t.replace("Det passer", "Fredag passer")
    return editor


async def test_ny_melding_under_redigering_send_likevel(config):
    r = FalskRunner(bare_nordlys)
    a = App(config, r, editor=redigerer_mens_ny_melding_kommer(config))
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await pilot.press("e")
        await pilot.pause()
        assert "Ny melding kom mens du redigerte" in str(a.screen.query_one(Static).render())
        await a.agenter.ferdig()
        assert [v.status for v in a.db.versjoner(NORDLYS)] == ["utdatert"]  # ingen v2 mens jeg velger
        await pilot.press("s")
        await ferdig_sendt(a, pilot)
        assert len(a.screen_stack) == 1  # dialogen tok tasten
        assert "Fredag passer" in outbox(config)[0]["body"]["comment"]
        assert [v.status for v in a.db.versjoner(NORDLYS)] == ["sendt"]
        assert a.rader[NORDLYS].status == "besvart" and len(r.utkast_kall) == 1


async def test_ny_melding_under_redigering_se_meldingen_så_regenerer(config):
    r = FalskRunner(bare_nordlys)
    a = App(config, r, editor=redigerer_mens_ny_melding_kommer(config))
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await pilot.press("e")
        await pilot.pause()
        await pilot.press("m")
        await a.agenter.ferdig()
        await pilot.pause()
        innhold = tekst(a, "#utkast")
        assert "Ny melding kom etter dette utkastet" in innhold and "Fredag passer" in innhold
        assert "Rekker dere fredag?" in tekst(a, "#trad")
        assert len(r.utkast_kall) == 1

        a.editor = lambda t: t + "\nPS"  # redigere videre uten ny Melding: ingen ny advarsel
        await pilot.press("e")
        await pilot.pause()
        assert len(a.screen_stack) == 1
        assert a.rader[NORDLYS].utkast.redigert.endswith("PS")


async def test_ny_melding_under_redigering_regenerer(config):
    r = FalskRunner(bare_nordlys)
    a = App(config, r, editor=redigerer_mens_ny_melding_kommer(config))
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await pilot.press("e")
        await pilot.pause()
        await pilot.press("r")
        await a.agenter.ferdig()
        await pilot.pause()
        assert [(v.status, v.redigert is not None) for v in a.db.versjoner(NORDLYS)] == [
            ("utdatert", True), ("klart", False)]  # redigeringen overskrives aldri
        assert "Rekker dere fredag?" in r.utkast_kall[-1]
