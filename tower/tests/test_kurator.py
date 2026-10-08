from __future__ import annotations

import json
import os

import pytest

from tower.agent import AgentFeil
from tower.db import Db
from tower.kanal import Melding, Person, Tråd
from tower.kurator import (KuratorJobb, commit_manuelt, git, gyldig_sti, kurater, prompt, siste_commit,
                           skriv_og_commit)
from tower.tests.conftest import MEG, NÅ, FalskRunner
from tower.tests.test_app import NORDLYS, tekst
from tower.tests.test_db import T, tråd
from tower.tests.test_handlinger import App, bare_nordlys, ferdig_sendt, klar
from tower.utkast import Research, Utkast

KARI = "---\nadresser: [kari.nordby@nordlys-energi.no]\nnavn: [Kari Nordby, Kari]\n---\n- Prosjektleder (2026-09-01)\n"


def logg(rot) -> list[str]:
    return [c.strip() for c in git(rot, "log", "--format=%an|%B%x1e").split("\x1e") if c.strip()]


# --- rene deler


def test_gyldig_sti():
    assert gyldig_sti("personer/kari-nordby.md") == "personer/kari-nordby.md"
    assert gyldig_sti("./kunnskapsbase/org/nordlys-energi.md") == "org/nordlys-energi.md"
    assert gyldig_sti("stil.md") == "stil.md"
    for ugyldig in ("../x.md", "personer/../../x.md", "/etc/passwd", "personer/Kari.md", "notater/x.md",
                    "personer/kari.txt", "personer/a/b.md", ".git/config", "personer/.md"):
        assert gyldig_sti(ugyldig) is None, ugyldig


def test_prompt_med_diff_research_og_filoversikt(tmp_path):
    rot = tmp_path / "kb"
    (rot / "personer").mkdir(parents=True)
    (rot / "personer" / "kari.md").write_text(KARI)
    (rot / "org").mkdir()
    (rot / "org" / "annen.md").write_text("---\ndomener: [annen.no]\n---\n- x\n")
    kari = Person("Kari Nordby", "kari.nordby@nordlys-energi.no")
    t = Tråd("mail:x", "mail", "Levering", (Melding("m0", kari, (MEG,), (), NÅ, "Når?", False, False),))
    vs = [Utkast(t.id, 1, "m0", "forkastet", "gammel", (), None, None, None),
          Utkast(t.id, 2, "m0", "forkastet", "Hei Kari\nUke 47.", (), None, None, "Hei Kari\nUke 46."),
          Utkast(t.id, 3, "m0", "sendt", "Hei\nUke 46.", (), None, "kortere", None,
                 (Research("Levering uke 46", "visense/docs/plan.md:4"),))]
    j = KuratorJobb(1, t.id, "m0", "Hei\nUke 46.", 3, 1, 3, "venter")
    p = prompt(t, j, vs, rot, MEG, NÅ)
    assert "I dag: 2026-10-07" in p
    assert "personer/kari.md  (adresser: kari.nordby@nordlys-energi.no; navn: Kari Nordby, Kari)" in p
    assert "org/annen.md" in p and "## personer/kari.md\n---" in p and "## org/annen.md" not in p  # berørt vs alle
    assert "gammel" not in p  # versjon 1 hører til en tidligere kjøring
    assert "<agentens_tekst>\nHei Kari\nUke 47.\n</agentens_tekst>\n<min_redigering>\nHei Kari\nUke 46." in p
    assert "<instruks>kortere</instruks>" in p and "- Levering uke 46 (visense/docs/plan.md:4)" in p
    assert '<sendt kilde="versjon 3">\nHei\nUke 46.\n</sendt>' in p

    utenfra = prompt(t, KuratorJobb(1, t.id, "m0", "Mitt svar", None, 0, 3, "venter"), vs, rot, MEG, NÅ)
    assert "<agentens_tekst>" not in utenfra and "Levering uke 46" in utenfra  # Research, ikke tekstene
    assert "ingen utkast-diff" in utenfra


async def test_kurater_forkaster_ugyldige_stier(tmp_path):
    svar = {"endringer": [{"fil": "personer/kari.md", "innhold": KARI}, {"fil": "../ut.md", "innhold": "x"},
                          {"fil": "stil.md", "innhold": "  "}]}
    r = FalskRunner(kurator=lambda p: svar)
    j = KuratorJobb(1, "mail:x", "m0", "s", None, 0, 0, "venter")
    endringer, forkastet, usd = await kurater(r, tråd(False), j, [], tmp_path, MEG, NÅ)
    assert endringer == [("personer/kari.md", KARI)] and forkastet == 2 and usd == 0.02


async def test_kurater_nytt_forsøk_ved_feil(tmp_path):
    n = []

    def kurator(p):
        n.append(1)
        if len(n) == 1:
            raise AgentFeil("timeout", 0.01)
        return {"endringer": []}

    j = KuratorJobb(1, "mail:x", "m0", "s", None, 0, 0, "venter")
    assert (await kurater(FalskRunner(kurator=kurator), tråd(False), j, [], tmp_path, MEG, NÅ))[2] == pytest.approx(0.03)
    assert len(n) == 2


# --- git


def test_commit_format_manuelt_først_og_ingen_tomme_commits(tmp_path):
    rot = tmp_path / "kb"
    assert commit_manuelt(rot, MEG) is False and (rot / ".git").is_dir()
    assert skriv_og_commit(rot, [], "Emne", "mail:x") == ([], None)
    assert siste_commit(rot) is None

    filer, sha = skriv_og_commit(rot, [("personer/kari.md", KARI), ("stil.md", "- Kort (2026-10-07)\n")],
                                 "Re:  Nordlys\nERP", "mail:x")
    assert filer == ["personer/kari.md", "stil.md"] and sha
    assert logg(rot) == ["tower kurator|kurator: Re: Nordlys ERP\n\nny: personer/kari.md\nny: stil.md\n\n"
                         "Tråd: mail:x"]
    assert skriv_og_commit(rot, [("personer/kari.md", KARI)], "Igjen", "mail:x") == ([], None)  # uendret

    (rot / "personer" / "kari.md").write_text(KARI + "- Min egen linje\n")
    (rot / "org").mkdir()
    (rot / "org" / "ny.md").write_text("x\n")
    assert commit_manuelt(rot, MEG) is True
    skriv_og_commit(rot, [("personer/kari.md", KARI + "- Min egen linje\n- Ny (2026-10-07)\n")], "Mer", "mail:y")
    første, andre, tredje = logg(rot)
    assert første.startswith("tower kurator|kurator: Mer\n\nendret: personer/kari.md\n")
    assert andre == "Sander Hurlen|manuelt: endringer"
    assert siste_commit(rot)[0] == "kurator: Mer"
    assert git(rot, "status", "--porcelain") == ""


def test_skriver_ikke_gjennom_symlenke_ut_av_basen(tmp_path):
    rot = tmp_path / "kb"
    (rot / "personer").mkdir(parents=True)
    (tmp_path / "ute.md").write_text("ute\n")
    (rot / "personer" / "lenke.md").symlink_to(tmp_path / "ute.md")
    assert skriv_og_commit(rot, [("personer/lenke.md", "inn\n")], "x", "mail:x") == ([], None)
    assert (tmp_path / "ute.md").read_text() == "ute\n"


# --- kø i db


def test_kø_dedupe_mellom_sending_og_besvart_utenfra(tmp_path):
    db = Db(tmp_path / "tower.db")
    db.registrer(tråd(False), NÅ, 7)
    db.lagre_triage("mail:x", "m0", T, NÅ)
    u = db.lagre_utkast(db.nytt_utkast("mail:x", "m0", NÅ), "v1", (), NÅ)
    db.lagre_redigert(u, "v1 min", NÅ)
    u = db.marker_sendt(u, NÅ)
    db.kurator_etter_sending(u, "m0", NÅ)
    db.registrer(tråd(False, True), NÅ, 7)  # mitt svar kommer inn via poll: samme jobb
    (j,) = db.kurator_jobber("venter")
    assert (j.tråd_id, j.svar_på, j.sendt, j.sendt_versjon, j.fra_versjon, j.til_versjon) == (
        "mail:x", "m0", "v1 min", 1, 0, 1)
    db.kurator_ferdig(j, NÅ)
    assert db.kurator_jobber("venter") == []


def test_besvart_utenfra_køer_jobb_uten_diff_men_ikke_første_gang(tmp_path):
    db = Db(tmp_path / "tower.db")
    db.registrer(tråd(False, True), NÅ, 7)  # første syn, alt besvart: ingenting å lære nå
    assert db.kurator_jobber("venter", "feilet") == []
    db.registrer(tråd(False, True, False), NÅ, 7)
    db.registrer(tråd(False, True, False, True), NÅ, 7)
    (j,) = db.kurator_jobber("venter")
    assert j.sendt_versjon is None and j.svar_på == "m2" and j.til_versjon == 0
    db.kurator_feil(j, "timeout", NÅ)
    db.lukk()
    (j,) = Db(tmp_path / "tower.db").kurator_jobber("feilet")  # overlever omstart
    assert j.feil == "timeout"


def test_avvis_køer_ingen_kurator(tmp_path):
    db = Db(tmp_path / "tower.db")
    db.registrer(tråd(False), NÅ, 7)
    db.avvis("mail:x", NÅ)
    assert db.kurator_jobber("venter", "feilet") == []


# --- i appen


def lærer_kari(prompt):
    return {"endringer": [{"fil": "personer/kari-nordby.md", "innhold": KARI},
                          {"fil": "../../hack.md", "innhold": "x"}]}


async def test_send_kjører_kurator_som_committer_og_vises_i_statuslinja(config):
    kb = config.kunnskapsbase
    (kb / "personer").mkdir(parents=True)
    (kb / "stil.md").write_text("- Min egen regel\n")  # ucommittet: blir `manuelt: endringer` først
    r = FalskRunner(bare_nordlys, kurator=lærer_kari)
    a = App(config, r)
    async with a.run_test(size=(200, 40)) as pilot:
        await klar(a, pilot)
        a.db.lagre_redigert(a.rader[NORDLYS].utkast, "Hei Kari\n\nMin tekst.\n\n--\nSander\nVisense", NÅ)
        a.rader[NORDLYS] = a.db.rad(NORDLYS)
        await pilot.press("s")
        await ferdig_sendt(a, pilot)
        await a.kurator.ferdig()
        await pilot.pause()

        (p,) = r.kurator_kall
        assert "<min_redigering>\nHei Kari\n\nMin tekst." in p and '<sendt kilde="versjon 1">' in p
        assert (kb / "personer" / "kari-nordby.md").read_text() == KARI
        assert not (config.rot / "hack.md").exists()
        kurator, manuelt = logg(kb)
        assert kurator.startswith("tower kurator|kurator: Status på ERP") and f"Tråd: {NORDLYS}" in kurator
        assert manuelt.startswith("Sander Hurlen|manuelt: endringer")
        assert ("Kuratoren: 1 endring med ugyldig sti forkastet", "warning") in a.varsler
        assert "kb: Status på ERP" in tekst(a, "#status")
        assert a.db.kurator_jobber("venter", "feilet") == []
        assert a.db.con.execute("SELECT jobb FROM kjoring ORDER BY rowid DESC LIMIT 1").fetchone() == ("kurator",)


async def test_besvart_utenfra_kjører_kurator_uten_diff(config):
    r = FalskRunner(bare_nordlys)
    a = App(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        sti = config.rot / "mail" / "AAQkADMock-nordlys-erp.json"
        data = json.loads(sti.read_text())
        m = {**data["value"][-1], "id": "mitt-svar", "receivedDateTime": "2026-10-07T10:59:00Z",
             "from": {"emailAddress": {"name": "Sander Hurlen", "address": "sander@visense.no"}},
             "body": {"contentType": "text", "content": "Svarte fra Outlook"}}
        data["value"].append(m)
        sti.write_text(json.dumps(data))
        os.utime(sti, ns=(0, sti.stat().st_mtime_ns + 1_000_000))
        await a.poll()
        await a.kurator.ferdig()
        assert a.rader[NORDLYS].status == "besvart"
        (p,) = r.kurator_kall
        assert "ingen utkast-diff" in p and "Svarte fra Outlook" in p and "<agentens_tekst>" not in p


async def test_avvis_kjører_ikke_kurator(config):
    r = FalskRunner(bare_nordlys)
    a = App(config, r)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot)
        await pilot.press("a")
        await a.poll()
        await a.kurator.ferdig()
        assert r.kurator_kall == []


async def test_kurator_feil_i_statuslinja_og_nytt_forsøk_ved_omstart(config):
    def feiler(p):
        raise AgentFeil("timeout etter 60 s", 0.01)

    r = FalskRunner(bare_nordlys, kurator=feiler)
    a = App(config, r)
    async with a.run_test(size=(200, 40)) as pilot:
        await klar(a, pilot)
        await pilot.press("s")
        await ferdig_sendt(a, pilot)
        await a.kurator.ferdig()
        await pilot.pause()
        assert len(r.kurator_kall) == 2  # ett nytt forsøk
        assert "✗ kurator: timeout etter 60 s" in tekst(a, "#status")
        assert a.rader[NORDLYS].utkast.status == "sendt"  # sending påvirkes aldri
        await a.poll()
        await a.kurator.ferdig()
        assert len(r.kurator_kall) == 2  # feilet blir liggende til neste oppstart

    r2 = FalskRunner(bare_nordlys)
    a = App(config, r2)
    async with a.run_test(size=(200, 40)) as pilot:
        assert "✗ kurator" in tekst(a, "#status")
        await a.poll()
        await a.kurator.ferdig()
        await pilot.pause()
        assert len(r2.kurator_kall) == 1 and "✗ kurator" not in tekst(a, "#status")
        assert a.db.kurator_jobber("feilet") == []


async def test_k_åpner_kunnskapsbasen_og_committer_endringene(config):
    kjørt = []

    class K(App):
        def i_terminal(self, argv):
            kjørt.append(argv)
            (self.config.kunnskapsbase / "stil.md").write_text("- Fra editoren\n")
            return 0

    a = K(config)
    async with a.run_test(size=(160, 40)) as pilot:
        await pilot.press("k")
        await pilot.pause()
        assert kjørt[0][-1] == str(config.kunnskapsbase)
        assert logg(config.kunnskapsbase) == ["Sander Hurlen|manuelt: endringer"]
