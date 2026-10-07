from __future__ import annotations

import json
import os

from textual.widgets import DataTable, Static

from tower.app import Tower
from tower.config import lag_kanaler
from tower.db import Db
from tower.tests.conftest import NÅ, FalskRunner


def app(config, runner=None, **kw) -> Tower:
    return Tower(config, lag_kanaler(config), Db(config.db), runner or FalskRunner(), nå=lambda: NÅ, poll=False, **kw)


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

    a = Tower(config, [Ødelagt()], Db(config.db), FalskRunner(), nå=lambda: NÅ, poll=False)
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


def triage_etter_emne(prompt: str) -> dict:
    from tower.agent import AgentFeil

    emne = prompt.split("Emne: ", 1)[1].split("\n", 1)[0]
    if "Harbor" in prompt and "BRANN" in prompt:
        raise AgentFeil("timeout etter 60 s", 0.001)
    haster = emne.startswith("URGENT")
    info = emne.startswith(("Azure", "Re: Møtereferat", "Re: Workshop"))
    return {"kategori": "info" if info else "svar", "haster": haster,
            "sammendrag": f"Om {emne}", "begrunnelse": "fordi"}


def ny_melding(config, tråd_id: str, id: str, tekst: str = "Ny melding") -> None:
    sti = config.rot / "mail" / f"{tråd_id.removeprefix('mail:')}.json"
    data = json.loads(sti.read_text())
    m = {**data["value"][-1], "id": id, "receivedDateTime": "2026-10-07T10:59:00Z"}
    m["body"] = {"contentType": "text", "content": tekst}
    m["from"] = data["value"][0]["from"]
    data["value"].append(m)
    sti.write_text(json.dumps(data))
    os.utime(sti, ns=(0, sti.stat().st_mtime_ns + 1_000_000))


def triagekolonne(a: Tower) -> list[str]:
    dt = a.query_one(DataTable)
    return [str(dt.get_row_at(i)[3]) for i in range(dt.row_count)]


async def test_triage_sorterer_og_vises(config):
    r = FalskRunner(triage_etter_emne)
    a = app(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await a.poll()
        await a.agenter.ferdig()
        await pilot.pause()
        assert len(r.kall) == 7
        emner = rader(a)
        assert emner[0] == "URGENT: API returning 500 errors since 07:00"
        assert "haster" in triagekolonne(a)[0]
        assert all("info" in x for x in triagekolonne(a)[-3:])
        assert {e.removeprefix("[dim]") for e in emner[-3:]} == {
            "Azure updates: October 2026", "Re: Møtereferat oppstartsmøte", "Re: Workshop 15. oktober"}
        assert {r.status for r in a.rader.values()} == {"triagert"}

        hode = tekst(a, "#hode")
        assert "Om URGENT: API returning 500 errors since 07:00" in hode and "fordi" in hode
        status = tekst(a, "#status")
        assert "agenter i ro" in status and "$0.110 i dag" in status  # 7 triage + 4 utkast


async def test_besvart_og_gammel_triageres_ikke(config):
    from dataclasses import replace

    sti = config.rot / "mail" / "AAQkADMock-takk-passer.json"
    data = json.loads(sti.read_text())
    data["value"] = data["value"][:1]
    sti.write_text(json.dumps(data))
    r = FalskRunner()
    a = app(config, r)
    async with a.run_test(size=(160, 40)):
        await a.poll()
        await a.agenter.ferdig()
        assert len(r.kall) == 6

    r = FalskRunner()
    config = replace(config, rot=config.rot / "annen", dager=0)
    import shutil
    shutil.copytree(config.rot.parent / "mail", config.rot / "mail")
    a = app(config, r)
    async with a.run_test(size=(160, 40)):
        await a.poll()
        await a.agenter.ferdig()
        assert r.kall == [] and {r.status for r in a.rader.values()} == {"gammel", "besvart"}


async def test_ny_melding_midt_i_triage_dreper_og_triagerer_på_nytt(config):
    r = FalskRunner(triage_etter_emne, porter=True)
    a = app(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await a.poll()
        await pilot.pause()
        assert len(a.agenter.kjørende) == 2
        a.tikk()
        status = tekst(a, "#status")
        assert "triage " in status and "+5 i kø" in status
        assert sum("triagerer…" in x for x in triagekolonne(a)) == 2
        assert sum("i kø" in x for x in triagekolonne(a)) == 5

        (_, tråd_id), = list(a.agenter.kjørende)[:1]
        ny_melding(config, tråd_id, "ny-1", "Glem det forrige, nytt spørsmål")
        await a.poll()
        await pilot.pause()
        assert r.avbrutt == 1
        r.slipp()
        await a.agenter.ferdig()
        await pilot.pause()
        assert len(r.kall) == 8
        assert "Glem det forrige" in r.kall[-1] or any("Glem det forrige" in k for k in r.kall)
        rad = a.rader[tråd_id]
        assert rad.triage_melding_id == "ny-1" and rad.status == "triagert"


async def test_svar_utenfra_avbryter_triage(config):
    r = FalskRunner(porter=True)
    a = app(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await a.poll()
        (_, tråd_id), = list(a.agenter.kjørende)[:1]
        sti = config.rot / "mail" / f"{tråd_id.removeprefix('mail:')}.json"
        data = json.loads(sti.read_text())
        meg = {**data["value"][-1], "id": "mitt-svar", "receivedDateTime": "2026-10-07T10:59:00Z",
               "from": {"emailAddress": {"name": "Sander Hurlen", "address": "sander@visense.no"}}}
        data["value"].append(meg)
        sti.write_text(json.dumps(data))
        os.utime(sti, ns=(0, sti.stat().st_mtime_ns + 1_000_000))
        await a.poll()
        await pilot.pause()
        assert r.avbrutt == 1 and not a.agenter.venter(("triage", tråd_id))
        r.slipp()
        await a.agenter.ferdig()
        assert a.rader[tråd_id].status == "besvart" and a.rader[tråd_id].triage is None
        assert len(r.kall) == 7


async def test_triage_feiler_og_omstart_tar_resten(config):
    ny_melding(config, "mail:AAQkADMock-harbor-outage", "brann", "BRANN")
    r = FalskRunner(triage_etter_emne, porter=True)
    a = app(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await a.poll()
        await pilot.pause()
    # avsluttet midt i: kjørende drept, ingen triage lagret
    assert r.avbrutt == 2 and r.aktive == 0

    r = FalskRunner(triage_etter_emne)
    a = app(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await a.poll()
        await a.agenter.ferdig()
        await pilot.pause()
        harbor = "mail:AAQkADMock-harbor-outage"
        assert sum("BRANN" in k for k in r.kall) == 2  # ett nytt forsøk
        assert a.rader[harbor].triage_feilet
        dt = a.query_one(DataTable)
        assert "feilet" in str(dt.get_row_at(dt.get_row_index(harbor))[3])
        dt.move_cursor(row=dt.get_row_index(harbor), animate=False)
        await pilot.pause()
        assert "timeout etter 60 s" in tekst(a, "#hode")
        assert "$0.092 i dag" in tekst(a, "#status")  # 6 triage × 0.01 + 2 × 0.001 + 3 utkast

    r = FalskRunner(triage_etter_emne)
    a = app(config, r)
    async with a.run_test(size=(160, 40)):
        await a.poll()
        await a.agenter.ferdig()
        assert r.kall == []  # alt triagert eller feilet for siste Melding


def utkastkolonne(a: Tower) -> dict[str, str]:
    dt = a.query_one(DataTable)
    return {k.value: str(dt.get_row_at(dt.get_row_index(k))[4]) for k in dt.rows}


def velg(a: Tower, tråd_id: str) -> None:
    dt = a.query_one(DataTable)
    dt.move_cursor(row=dt.get_row_index(tråd_id), animate=False)


NORDLYS = "mail:AAQkADMock-nordlys-erp"


async def test_utkast_for_svar_med_hint_og_plassholdere(config):
    kb = config.kunnskapsbase
    (kb / "personer").mkdir(parents=True)
    (kb / "stil.md").write_text("- Kort og direkte (2026-10-01)")
    (kb / "personer" / "kari.md").write_text("---\nadresser: [kari.nordby@nordlys-energi.no]\n---\n- Prosjektleder")

    def utkast(prompt):
        return {"tekst": "Hei Kari\n\nLevering [[dato]].\n\n--\nSander\nVisense", "sjekk": ["Bekreft dato"]}

    r = FalskRunner(triage_etter_emne, utkast=utkast)
    a = app(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await a.poll()
        await a.agenter.ferdig()
        await pilot.pause()
        assert len(r.utkast_kall) == 4  # bare svar, ikke info
        kol = utkastkolonne(a)
        assert "klart" in kol[NORDLYS] and "—" in kol["mail:AAQkADMock-azure-newsletter"]
        assert "4 utkast klare" in tekst(a, "#status")
        nordlys_prompt = next(p for p in r.utkast_kall if "ERP" in p)
        assert "## stil.md" in nordlys_prompt and "## personer/kari.md" in nordlys_prompt
        assert "## personer/kari.md" in next(p for p in r.kall if "ERP" in p)  # triage får også oppslaget
        assert "## personer/kari.md" not in next(p for p in r.utkast_kall if "Harbor" in p)

        velg(a, NORDLYS)
        await pilot.pause()
        w = a.query_one("#utkast", Static)
        innhold = tekst(a, "#utkast")
        assert w.display and w.has_class("klart") and w.border_title == "Utkast v1"
        assert innhold.index("Bekreft dato") < innhold.index("Hei Kari") and "[[dato]]" in innhold
        assert r"[b reverse yellow]\[\[dato]][/]" in w.content  # uthevet

        velg(a, "mail:AAQkADMock-azure-newsletter")
        await pilot.pause()
        assert not a.query_one("#utkast", Static).display  # info: ingen ramme


async def til(pilot, betingelse, n: int = 200) -> None:
    for _ in range(n):
        if betingelse():
            return
        await pilot.pause()
    raise AssertionError("betingelsen ble aldri sann")


def bare_nordlys_svar(prompt: str) -> dict:
    return {"kategori": "svar" if "ERP" in prompt else "info", "haster": False, "sammendrag": "s", "begrunnelse": "b"}


async def test_ny_melding_gjør_utkast_utdatert_og_lager_v2(config):
    r = FalskRunner()
    a = app(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await a.poll()
        await a.agenter.ferdig()
        velg(a, NORDLYS)
        ny_melding(config, NORDLYS, "ny-1", "Og en ting til")
        await a.poll()
        assert a.rader[NORDLYS].utkast.status == "utdatert"
        assert "utdatert" in utkastkolonne(a)[NORDLYS]
        assert "Ny melding kom etter dette utkastet" in tekst(a, "#utkast")
        await a.agenter.ferdig()
        await pilot.pause()
        assert [(v.versjon, v.melding_id, v.status) for v in a.db.versjoner(NORDLYS)] == [
            (1, "AAMkADMock-nordlys-erp-1", "utdatert"), (2, "ny-1", "klart")]
        assert "v2" in utkastkolonne(a)[NORDLYS] and a.query_one("#utkast", Static).border_title == "Utkast v2"
        assert "Og en ting til" in r.utkast_kall[-1]


async def test_ny_melding_midt_i_utkast_dreper_det(config):
    r = FalskRunner(bare_nordlys_svar, porter="utkast")
    a = app(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await a.poll()
        await til(pilot, lambda: ("utkast", NORDLYS) in a.agenter.kjørende)
        await pilot.pause()
        assert "skriver" in utkastkolonne(a)[NORDLYS] and "utkast Kari" in tekst(a, "#status")
        ny_melding(config, NORDLYS, "ny-1", "Glem det")
        await a.poll()
        await til(pilot, lambda: r.avbrutt == 1)
        r.slipp()
        await a.agenter.ferdig()
        assert [(v.melding_id, v.status) for v in a.db.versjoner(NORDLYS)] == [
            ("AAMkADMock-nordlys-erp-1", "utdatert"), ("ny-1", "klart")]
        assert len(r.utkast_kall) == 2


async def test_utkast_feiler_og_avbrutt_utkast_tas_opp_ved_omstart(config):
    def feiler(prompt):
        from tower.agent import AgentFeil
        raise AgentFeil("timeout etter 60 s", 0.001)

    r = FalskRunner(bare_nordlys_svar, utkast=feiler)
    a = app(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await a.poll()
        await a.agenter.ferdig()
        await pilot.pause()
        assert len(r.utkast_kall) == 2  # ett nytt forsøk
        assert a.rader[NORDLYS].utkast.status == "feilet" and "feilet" in utkastkolonne(a)[NORDLYS]
        velg(a, NORDLYS)
        await pilot.pause()
        assert "timeout etter 60 s" in tekst(a, "#utkast")

    # avsluttet midt i et utkast: versjonen står i genererer og kjøres ved neste oppstart
    ny_melding(config, NORDLYS, "ny-1", "Fortsatt?")
    r = FalskRunner(bare_nordlys_svar, porter="utkast")
    a = app(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await a.poll()
        await til(pilot, lambda: ("utkast", NORDLYS) in a.agenter.kjørende)
    assert r.avbrutt == 1 and a.db.utkast(NORDLYS).status == "genererer"

    r = FalskRunner(bare_nordlys_svar)
    a = app(config, r)
    async with a.run_test(size=(160, 40)):
        await a.poll()
        await a.agenter.ferdig()
        assert r.kall == [] and len(r.utkast_kall) == 1
        assert [(v.versjon, v.status) for v in a.db.versjoner(NORDLYS)] == [(1, "utdatert"), (2, "klart")]
