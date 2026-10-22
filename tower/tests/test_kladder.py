"""Outlook-kladdene følger tower, og tower følger det jeg gjør med dem i Outlook."""

from __future__ import annotations

import dataclasses
import json
import os

from tower.config import lag_kanaler
from tower.kanal import Kladd, kladdtekst
from tower.tests.conftest import MEG, FalskRunner
from tower.tests.test_app import NORDLYS, ny_melding, utkastkolonne, velg
from tower.tests.test_handlinger import App, bare_nordlys, klar, outbox

TEKST = "Hei\n\nDet passer.\n\n--\nSander\nVisense"  # FalskRunner sitt utkast


class Outlook:
    """Mock-mailkanalen med kladder i minnet, slik MailKanal med ekte Graph oppfører seg."""

    def __init__(self, ekte) -> None:
        self.ekte, self.navn = ekte, ekte.navn
        self.mappe: dict[str, Kladd] = {}
        self.n = 0

    async def hent(self):
        return await self.ekte.hent()

    def fjernede(self):
        return self.ekte.fjernede()

    async def svar(self, tråd_id, tekst):
        raise AssertionError("ekte mail sendes aldri fra tower")

    def kladder(self):
        return dict(self.mappe)

    async def lag_kladd(self, tråd_id, tekst):
        self.n += 1
        k = Kladd(f"k{self.n}", f"https://owa/k{self.n}", kladdtekst(tekst))
        self.mappe[k.id] = k
        return k

    async def slett_kladd(self, kladd_id):
        self.mappe.pop(kladd_id, None)

    def tekster(self) -> list[str]:
        return [k.tekst for k in self.mappe.values()]


def lag(config, runner=None, editor=None) -> tuple[App, Outlook]:
    outlook = Outlook(lag_kanaler(config)[0])
    return App(dataclasses.replace(config, graph=("mail",)), runner, editor, kanaler=[outlook]), outlook


async def synket(a, pilot) -> None:
    for _ in range(3):  # en synk som endrer noe tegner tabellen, som utløser én synk til
        await a.agenter.ferdig()
        await a.workers.wait_for_complete()
        await pilot.pause()


async def poll(a, pilot) -> None:
    await a.poll()
    await synket(a, pilot)


def mitt_svar(config, tråd_id: str) -> None:
    """Kladden sendt fra Outlook: svaret dukker opp i Tråden."""
    sti = config.rot / "mail" / f"{tråd_id.removeprefix('mail:')}.json"
    data = json.loads(sti.read_text())
    data["value"].append({**data["value"][-1], "id": "mitt-svar", "receivedDateTime": "2026-10-07T10:59:00Z",
                          "from": {"emailAddress": {"name": MEG.navn, "address": MEG.adresse}},
                          "body": {"contentType": "text", "content": "Hei\n\nDet passer fint."}})
    sti.write_text(json.dumps(data))
    os.utime(sti, ns=(0, sti.stat().st_mtime_ns + 1_000_000))


async def test_klart_utkast_blir_kladd_og_o_åpner_den(config):
    a, outlook = lag(config)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await synket(a, pilot)
        assert outlook.tekster() == [TEKST]
        assert "i Outlook" in utkastkolonne(a)[NORDLYS]
        await pilot.press("o")
        assert a.åpnet == ["https://owa/k1"]
        await pilot.press("s")
        assert a.varsler[-1] == ("Mail sendes fra Outlook, o åpner kladden", "warning") and outbox(config) == []
        await poll(a, pilot)
        assert list(outlook.mappe) == ["k1"]  # uendret: ingen ny kladd


async def test_redigering_og_regenerering_erstatter_kladden(config):
    a, outlook = lag(config, editor=lambda tekst: tekst.replace("passer", "passer fint"))
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await synket(a, pilot)
        await pilot.press("e")
        await synket(a, pilot)
        assert list(outlook.mappe) == ["k2"] and "passer fint" in outlook.tekster()[0]

        a.regenerer(NORDLYS, "kortere")
        await synket(a, pilot)
        assert list(outlook.mappe) == ["k3"] and outlook.tekster() == [TEKST]


async def test_avvis_sletter_kladden(config):
    a, outlook = lag(config)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await synket(a, pilot)
        await pilot.press("a")
        await synket(a, pilot)
        assert outlook.mappe == {}


async def test_ny_melding_erstatter_kladden(config):
    a, outlook = lag(config)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await synket(a, pilot)
        ny_melding(config, NORDLYS, "ny", "ERP: og en ting til")
        await poll(a, pilot)
        assert list(outlook.mappe) == ["k2"]
        assert a.db.versjoner(NORDLYS)[-1].kladd == "k2"


async def test_redigert_i_outlook_blir_min_redigering(config):
    a, outlook = lag(config)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await synket(a, pilot)
        outlook.mappe["k1"] = dataclasses.replace(outlook.mappe["k1"], tekst="Hei\n\nTorsdag passer.")
        await poll(a, pilot)
        u = a.rader[NORDLYS].utkast
        assert (u.tekst, u.gjeldende) == (TEKST, "Hei\n\nTorsdag passer.")
        assert list(outlook.mappe) == ["k1"]  # ikke erstattet av tower


async def test_slettet_i_outlook_avviser_tråden(config):
    a, outlook = lag(config)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await synket(a, pilot)
        outlook.mappe.clear()
        await poll(a, pilot)
        assert a.rader[NORDLYS].status == "triagert"  # kan være sending på vei
        await poll(a, pilot)
        assert a.rader[NORDLYS].status == "avvist" and outlook.mappe == {}
        assert "slettet i Outlook" in a.varsler[-1][0]


async def test_sendt_fra_outlook_gir_kurator_diff(config):
    a, outlook = lag(config, FalskRunner(bare_nordlys))
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await synket(a, pilot)
        outlook.mappe["k1"] = dataclasses.replace(outlook.mappe["k1"], tekst="Hei\n\nDet passer fint.")
        await poll(a, pilot)
        outlook.mappe.clear()
        mitt_svar(config, NORDLYS)
        await poll(a, pilot)
        u = a.db.versjoner(NORDLYS)[0]
        assert (a.rader[NORDLYS].status, u.status, u.gjeldende) == ("besvart", "sendt", "Hei\n\nDet passer fint.")
        assert a.db.con.execute("SELECT sendt_versjon, sendt FROM kurator").fetchall() == [(1, "Hei\n\nDet passer fint.")]
        assert outlook.mappe == {}


async def test_kladder_røres_ikke_før_kanalen_er_hentet(config):
    a, outlook = lag(config)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await synket(a, pilot)
    a, outlook2 = lag(config)  # omstart: Trådene er ikke hentet ennå
    outlook2.mappe = outlook.mappe
    async with a.run_test(size=(160, 40)) as pilot:
        a.tegn_tabell()
        await synket(a, pilot)
        assert list(outlook2.mappe) == ["k1"]
        await poll(a, pilot)
        assert list(outlook2.mappe) == ["k1"] and a.rader[NORDLYS].utkast.kladd == "k1"
