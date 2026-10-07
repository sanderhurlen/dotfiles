from __future__ import annotations

import json
import os

from textual.widgets import DataTable, Static

from tower.app import Tower
from tower.config import lag_kanaler
from tower.db import Db
from tower.tests.conftest import NÅ


def app(config, **kw) -> Tower:
    return Tower(config, lag_kanaler(config), Db(config.db), nå=lambda: NÅ, poll=False, **kw)


def rader(a: Tower) -> list[str]:
    dt = a.query_one(DataTable)
    return [str(dt.get_row_at(i)[2]) for i in range(dt.row_count)]


def tekst(a: Tower, id: str) -> str:
    return str(a.query_one(id, Static).render())


async def test_tabell_sortert_og_ferdige_nederst(config):
    # takk-passer: lag en Tråd der siste Melding er min
    sti = config.rot / "mail" / "AAQkADMock-takk-passer.json"
    data = json.loads(sti.read_text())
    data["value"] = data["value"][:1]
    sti.write_text(json.dumps(data))

    a = app(config)
    async with a.run_test(size=(160, 40)) as pilot:
        await a.poll()
        await pilot.pause()
        emner = rader(a)
        assert len(emner) == 7
        assert emner[0] == "URGENT: API returning 500 errors since 07:00"  # nyeste aktive først
        assert emner[-1] == "[dim]Re: Workshop 15. oktober"
        assert a.rader["mail:AAQkADMock-takk-passer"].status == "besvart"
        assert "6 tråder venter" in tekst(a, "#status")


async def test_detalj_følger_markøren(config):
    a = app(config)
    async with a.run_test(size=(160, 40)) as pilot:
        await a.poll()
        await pilot.pause()
        assert "URGENT" in tekst(a, "#hode")
        assert "James Whitfield" in tekst(a, "#trad")
        await pilot.press("down")
        andre = a.sortert()[1]
        assert andre.emne in tekst(a, "#hode")
        assert andre.siste.fra.navn in tekst(a, "#trad")


async def test_poll_plukker_opp_ny_melding_og_beholder_markør(config):
    a = app(config)
    async with a.run_test(size=(160, 40)) as pilot:
        await a.poll()
        await pilot.press("down", "down")
        valgt = a.valgt_id()

        sti = config.rot / "mail" / "AAQkADMock-azure-newsletter.json"
        data = json.loads(sti.read_text())
        ny = {**data["value"][0], "id": "ny-melding", "receivedDateTime": "2026-10-07T10:59:00Z"}
        data["value"].append(ny)
        sti.write_text(json.dumps(data))
        os.utime(sti, ns=(0, sti.stat().st_mtime_ns + 1_000_000))

        await a.poll()
        await pilot.pause()
        assert a.sortert()[0].id == "mail:AAQkADMock-azure-newsletter"
        assert a.valgt_id() == valgt


async def test_hentfeil_vises_i_statuslinja(config):
    class Ødelagt:
        navn = "mail"

        async def hent(self):
            raise OSError("disk borte")

    a = Tower(config, [Ødelagt()], Db(config.db), nå=lambda: NÅ, poll=False)
    async with a.run_test() as pilot:
        await a.poll()
        await pilot.pause()
        assert "disk borte" in tekst(a, "#status")


async def test_q_avslutter(config):
    a = app(config)
    async with a.run_test() as pilot:
        await pilot.press("q")
        await pilot.pause()
    assert a.return_code == 0


async def test_teams_i_tabellen(config):
    from dataclasses import replace

    a = app(replace(config, kanaler=("mail", "teams")))
    async with a.run_test(size=(160, 40)) as pilot:
        await a.poll()
        await pilot.pause()
        emner = rader(a)
        assert len(emner) == 11
        assert "Release 4.2" in emner
        assert "Ring meg når du har et øyeblikk" in emner  # chat uten topic: start av siste Melding
        assert "Ola Berg" not in emner
        assert a.rader["teams:19:mock-referat@thread.v2"].status == "besvart"

        dt = a.query_one(DataTable)
        dt.move_cursor(row=dt.get_row_index("teams:19:u-ingrid_u-sander@unq.gbl.spaces"), animate=False)
        await pilot.pause()
        assert "Ingrid Solheim" in tekst(a, "#hode")
