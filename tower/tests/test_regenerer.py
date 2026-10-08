from __future__ import annotations

import json
from dataclasses import replace

import pytest

from tower.agent import AgentFeil, ClaudeRunner, Resultat, Verktøy, tolk
from tower.config import Config, last
from tower.db import Db
from tower.tests.conftest import NÅ, FalskRunner
from tower.tests.test_app import NORDLYS, tekst
from tower.tests.test_db import T, tråd
from tower.tests.test_handlinger import App, bare_nordlys, klar
from tower.utkast import INSTRUKS_VERKTØY, SCHEMA_RESEARCH, Research, kilde, skriv_utkast

# --- kilde-validering


@pytest.fixture
def røtter(tmp_path):
    kb, visense = tmp_path / "data" / "kunnskapsbase", tmp_path / "visense"
    (kb / "personer").mkdir(parents=True)
    (kb / "personer" / "kari.md").write_text("x")
    (visense / "docs").mkdir(parents=True)
    (visense / "docs" / "leveranse.md").write_text("x")
    (tmp_path / "hemmelig.txt").write_text("x")
    (visense / "lenke.md").symlink_to(tmp_path / "hemmelig.txt")
    return kb, visense


def test_kilde_normaliseres_under_tillatte_kataloger(røtter, tmp_path):
    kb, visense = røtter
    k = (kb, visense)
    assert kilde(f"{visense}/docs/leveranse.md:12", k) == "visense/docs/leveranse.md:12"
    assert kilde("visense/docs/leveranse.md:3-5", k) == "visense/docs/leveranse.md:3-5"
    assert kilde("docs/leveranse.md", k) == "visense/docs/leveranse.md"
    assert kilde("kunnskapsbase/personer/kari.md", k) == "kunnskapsbase/personer/kari.md"
    assert kilde(f"{kb}/personer/kari.md", k) == "kunnskapsbase/personer/kari.md"


def test_kilde_utenfor_eller_ukjent_avvises(røtter, tmp_path):
    k = røtter
    assert kilde(str(tmp_path / "hemmelig.txt"), k) is None
    assert kilde(f"{røtter[1]}/../hemmelig.txt", k) is None
    assert kilde(f"{røtter[1]}/lenke.md", k) is None  # symlenke ut
    assert kilde("visense/docs/finnes-ikke.md", k) is None
    assert kilde("visense/docs", k) is None  # katalog, ikke fil


# --- skriv_utkast med verktøy


async def test_skriv_utkast_med_verktøy_gir_research_og_ingen_nye_forsøk(røtter):
    kb, visense = røtter
    v = Verktøy((kb, visense))
    kall = []

    class R:
        async def kjør(self, instruks, schema, prompt, verktøy=None):
            kall.append((instruks, schema, prompt, verktøy))
            return Resultat({"tekst": "Hei", "sjekk": [], "research": [
                {"faktum": "Levering uke 46", "kilde": f"{visense}/docs/leveranse.md:4"},
                {"faktum": "Hemmelig", "kilde": "/etc/passwd"}]}, 0.05)

    s = await skriv_utkast(R(), tråd(False), "# kb", "kortere", "Forrige tekst", v)
    assert s.research == (Research("Levering uke 46", "visense/docs/leveranse.md:4"),) and s.forkastet == 1
    instruks, schema, prompt, verktøy = kall[0]
    assert instruks is INSTRUKS_VERKTØY and schema is SCHEMA_RESEARCH and verktøy is v
    assert f"<kataloger>\n{kb}\n{visense}\n</kataloger>" in prompt
    assert "<forrige_utkast>\nForrige tekst\n</forrige_utkast>" in prompt and "<instruks>\nkortere\n</instruks>" in prompt

    class Tak:
        async def kjør(self, *a, **kw):
            kall.append(a)
            raise AgentFeil("tak: budsjett brukt opp", 0.25)

    kall.clear()
    with pytest.raises(AgentFeil):
        await skriv_utkast(Tak(), tråd(False), "", "kortere", None, v)
    assert len(kall) == 1  # et tak som treffes, treffes igjen


# --- runner


def test_verktøy_argv(tmp_path):
    argv = ClaudeRunner("sonnet", tmp_path).argv("i", {}, Verktøy((tmp_path / "kb", tmp_path / "v")))
    assert argv[argv.index("--max-turns") + 1] == "12" and argv[argv.index("--max-budget-usd") + 1] == "0.25"
    assert [argv[i + 1] for i, a in enumerate(argv) if a == "--add-dir"] == [str(tmp_path / "kb"), str(tmp_path / "v")]
    assert argv[-2:] == ["--tools", "Read,Grep,Glob"]
    deny = json.loads(argv[argv.index("--settings") + 1])["permissions"]["deny"]
    # Relative mønstre gjelder bare under cwd (målt): alle må være absolutte.
    assert "Read(//**/.env*)" in deny and all(d.startswith("Read(//") for d in deny)
    assert "--setting-sources" in argv  # isolasjonen står


def test_tak_gir_lesbar_feil():
    ut = json.dumps({"subtype": "error_max_budget_usd", "is_error": True, "total_cost_usd": 0.26}).encode()
    with pytest.raises(AgentFeil, match="tak: budsjett") as e:
        tolk(ut, b"", 0)
    assert e.value.usd == 0.26
    with pytest.raises(AgentFeil, match="tak: for mange runder"):
        tolk(json.dumps({"subtype": "error_max_turns", "is_error": True}).encode(), b"", 0)


def test_config_kilder(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    c = last(tmp_path / "data")
    assert c.kilder == (tmp_path / "visense",)
    (tmp_path / "visense").mkdir()
    assert c.verktøy().kataloger == (c.kunnskapsbase, tmp_path / "visense") and c.kunnskapsbase.is_dir()
    assert replace(c, kilder=(tmp_path / "borte",)).verktøy().kataloger == (c.kunnskapsbase,)


# --- db


def test_research_lagres_og_regenerering_erstatter_forrige(tmp_path):
    db = Db(tmp_path / "tower.db")
    db.registrer(tråd(False), NÅ, 7)
    db.lagre_triage("mail:x", "m0", T, NÅ)
    v1 = db.lagre_utkast(db.nytt_utkast("mail:x", "m0", NÅ), "v1", (), NÅ)
    v2 = db.nytt_utkast("mail:x", "m0", NÅ, "kortere")
    assert db.rad("mail:x").utkast == v2 and db.rad("mail:x").trenger_utkast
    v2 = db.lagre_utkast(v2, "v2", (), NÅ, (Research("Uke 46", "visense/docs/a.md:1"),))
    assert v2.research == (Research("Uke 46", "visense/docs/a.md:1"),) and v2.instruks == "kortere"
    assert [v.status for v in db.versjoner("mail:x")] == ["forkastet", "klart"]
    db.lukk()
    assert Db(tmp_path / "tower.db").alle()["mail:x"].utkast.research == v2.research


def test_mislykket_regenerering_lar_forrige_versjon_stå(tmp_path):
    db = Db(tmp_path / "tower.db")
    db.registrer(tråd(False), NÅ, 7)
    db.lagre_triage("mail:x", "m0", T, NÅ)
    v1 = db.lagre_utkast(db.nytt_utkast("mail:x", "m0", NÅ), "v1", (), NÅ)
    db.lagre_utkast_feil(db.nytt_utkast("mail:x", "m0", NÅ, "x"), "tak: budsjett brukt opp", NÅ)
    rad = db.rad("mail:x")
    assert rad.utkast == v1 and rad.regenerering_feil == "tak: budsjett brukt opp" and not rad.trenger_utkast
    assert db.alle()["mail:x"] == rad
    rad = db.registrer(tråd(False, False), NÅ, 7)  # ny Melding: begge utdatert, siste vises
    assert rad.utkast.versjon == 2 and rad.utkast.status == "utdatert" and rad.regenerering_feil is None


# --- i appen


def svar_med_research(kilde_: str):
    def utkast(prompt):
        if "<instruks>" not in prompt:
            return {"tekst": "Hei Kari\n\nFørste.\n\n--\nSander\nVisense", "sjekk": []}
        return {"tekst": "Hei Kari\n\nLevering uke 46.\n\n--\nSander\nVisense", "sjekk": [],
                "research": [{"faktum": "Levering uke 46", "kilde": kilde_}, {"faktum": "x", "kilde": "/etc/hosts"}]}
    return utkast


@pytest.fixture
def med_kilder(config, tmp_path):
    visense = tmp_path / "visense"
    (visense / "docs").mkdir(parents=True)
    (visense / "docs" / "leveranse.md").write_text("Levering uke 46\n")
    return replace(config, kilder=(visense,))


async def regenerer(pilot, instruks: str) -> None:
    await pilot.press("r")
    await pilot.pause()
    if instruks:
        await pilot.press(*instruks)
    await pilot.press("enter")
    await pilot.pause()


async def test_regenerer_med_instruks_bruker_verktøy_og_viser_kilder(med_kilder):
    visense = med_kilder.kilder[0]
    r = FalskRunner(bare_nordlys, utkast=svar_med_research(f"{visense}/docs/leveranse.md:1"))
    a = App(med_kilder, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        a.db.lagre_redigert(a.rader[NORDLYS].utkast, "Hei Kari\n\nMin versjon.", NÅ)
        a.rader[NORDLYS] = a.db.rad(NORDLYS)
        await regenerer(pilot, "sjekk leveranse")
        await a.agenter.ferdig()
        await pilot.pause()

        assert r.verktøy[0] is None and r.verktøy[-1].kataloger == (med_kilder.kunnskapsbase, visense)
        assert r.instrukser[-1] == INSTRUKS_VERKTØY
        p = r.utkast_kall[-1]
        assert "<instruks>\nsjekk leveranse\n</instruks>" in p and "Min versjon." in p  # min redigering er forrige
        v1, v2 = a.db.versjoner(NORDLYS)
        assert (v1.status, v2.status, v2.instruks) == ("forkastet", "klart", "sjekk leveranse")
        assert v2.research == (Research("Levering uke 46", "visense/docs/leveranse.md:1"),)
        assert any("1 kilde utenfor" in s for s in v2.sjekk)
        innhold = tekst(a, "#utkast")
        assert "↺ sjekk leveranse" in innhold and "Kilder" in innhold and "visense/docs/leveranse.md:1" in innhold
        assert innhold.index("Kilder") < innhold.index("Levering uke 46.")
        assert a.db.con.execute("SELECT jobb FROM kjoring ORDER BY rowid DESC LIMIT 1").fetchone() == ("regenerer",)


async def test_regenerer_tom_instruks_prøver_igjen_uten_verktøy(config):
    r = FalskRunner(bare_nordlys)
    a = App(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await regenerer(pilot, "")
        await a.agenter.ferdig()
        await pilot.pause()
        assert r.verktøy == [None, None] and "<instruks>" not in r.utkast_kall[-1]
        assert [(v.status, v.instruks) for v in a.db.versjoner(NORDLYS)] == [("forkastet", None), ("klart", None)]


async def test_regenerer_avbrutt_med_escape(config):
    r = FalskRunner(bare_nordlys)
    a = App(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await pilot.press("r")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert len(a.db.versjoner(NORDLYS)) == 1 and len(a.screen_stack) == 1


async def test_regenerering_som_feiler_lar_forrige_stå_og_kan_sendes(config):
    def utkast(prompt):
        if "<instruks>" in prompt:
            raise AgentFeil("tak: budsjett brukt opp", 0.25)
        return {"tekst": "Hei\n\nFredag passer.", "sjekk": []}

    r = FalskRunner(bare_nordlys, utkast=utkast)
    a = App(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await regenerer(pilot, "lengre")
        await a.agenter.ferdig()
        await pilot.pause()
        assert len(r.utkast_kall) == 2  # ingen nye forsøk med verktøy
        rad = a.rader[NORDLYS]
        assert rad.utkast.versjon == 1 and rad.regenerering_feil == "tak: budsjett brukt opp"
        assert ("Regenerering feilet: tak: budsjett brukt opp", "error") in a.varsler
        innhold = tekst(a, "#utkast")
        assert "Regenerering feilet" in innhold and "Fredag passer." in innhold
        await pilot.press("s")
        await a.workers.wait_for_complete()
        await pilot.pause()
        assert [v.status for v in a.db.versjoner(NORDLYS)] == ["sendt", "forkastet"]


async def test_regenerer_feilet_utkast_og_nektes_der_det_ikke_gir_mening(config):
    feil = [True]

    def utkast(prompt):
        if feil[0]:
            raise AgentFeil("timeout")
        return {"tekst": "Hei", "sjekk": []}

    a = App(config, FalskRunner(bare_nordlys, utkast=utkast))
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        assert a.rader[NORDLYS].utkast.status == "feilet"
        feil[0] = False
        await regenerer(pilot, "")
        await a.agenter.ferdig()
        await pilot.pause()
        assert a.rader[NORDLYS].utkast.status == "klart" and a.rader[NORDLYS].regenerering_feil is None

        await pilot.press("a")  # avvist: ikke aktiv
        await pilot.pause()
        from tower.tests.test_app import velg
        velg(a, NORDLYS)
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        assert len(a.screen_stack) == 1 and a.varsler[-1] == ("Tråden er ikke aktiv", "warning")

        velg(a, "mail:AAQkADMock-azure-newsletter")  # info: ingen utkast
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        assert a.varsler[-1] == ("Ingen utkast å regenerere", "warning")
