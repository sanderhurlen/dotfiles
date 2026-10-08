from __future__ import annotations

import pytest

from tower.agent import AgentFeil, Resultat
from tower.db import Db
from tower.tests.test_db import T, tråd
from tower.tests.conftest import NÅ
from tower.utkast import SCHEMA, plassholdere, skriv_utkast


def test_plassholdere():
    assert plassholdere("Pris er [[pris per time]] fra [[dato]].") == ["pris per time", "dato"]
    assert plassholdere("Ingen [her].") == []


async def test_skriv_utkast_med_nytt_forsøk():
    kall = []

    class R:
        async def kjør(self, instruks, schema, prompt):
            assert schema is SCHEMA and "utkast til svar" in instruks
            kall.append(prompt)
            if len(kall) == 1:
                raise AgentFeil("timeout", 0.002)
            return Resultat({"tekst": " Hei [[x]]\n", "sjekk": ["x"]}, 0.01)

    assert tuple(await skriv_utkast(R(), tråd(False), "# stil")) == ("Hei [[x]]", ("x",), pytest.approx(0.012), (), 0)
    assert kall[0].startswith("<kunnskapsbase>\n# stil")


def triagert(db: Db, *fra_meg: bool):
    db.registrer(tråd(*fra_meg), NÅ, 7)
    return db.lagre_triage("mail:x", tråd(*fra_meg).siste.id, T, NÅ)


def test_trenger_utkast_bare_for_svar(tmp_path):
    db = Db(tmp_path / "tower.db")
    db.registrer(tråd(False), NÅ, 7)
    assert not db.rad("mail:x").trenger_utkast  # ikke triagert ennå
    assert triagert(db, False).trenger_utkast
    from tower.triage import Triage
    assert not db.lagre_triage("mail:x", "m0", Triage("info", False, "s", "b"), NÅ).trenger_utkast


def test_utkast_livssyklus_og_versjoner(tmp_path):
    db = Db(tmp_path / "tower.db")
    triagert(db, False)
    u = db.nytt_utkast("mail:x", "m0", NÅ)
    assert (u.versjon, u.status) == (1, "genererer") and db.rad("mail:x").trenger_utkast  # kjøres (igjen)
    u = db.lagre_utkast(u, "Hei [[x]]", ("x",), NÅ)
    assert (u.status, u.tekst, u.sjekk, u.plassholdere) == ("klart", "Hei [[x]]", ("x",), ["x"])
    assert not db.rad("mail:x").trenger_utkast

    # ny Melding: utdatert, ny triage og nytt utkast trengs
    rad = db.registrer(tråd(False, False), NÅ, 7)
    assert rad.utkast.status == "utdatert" and not rad.trenger_utkast and rad.trenger_triage
    assert db.lagre_triage("mail:x", "m1", T, NÅ).trenger_utkast
    v2 = db.nytt_utkast("mail:x", "m1", NÅ)
    assert v2.versjon == 2
    assert db.lagre_utkast_feil(v2, "timeout", NÅ).status == "feilet"
    assert not db.rad("mail:x").trenger_utkast  # feilet: ikke automatisk igjen
    assert [(v.versjon, v.status) for v in db.versjoner("mail:x")] == [(1, "utdatert"), (2, "feilet")]
    assert db.alle()["mail:x"].utkast.versjon == 2


def test_resultat_for_utdatert_utkast_ignoreres(tmp_path):
    db = Db(tmp_path / "tower.db")
    triagert(db, False)
    u = db.nytt_utkast("mail:x", "m0", NÅ)
    db.registrer(tråd(False, True), NÅ, 7)  # svar utenfra
    assert db.lagre_utkast(u, "x", (), NÅ) is None and db.lagre_utkast_feil(u, "x", NÅ) is None
    assert db.utkast("mail:x").status == "utdatert"


def test_utkast_overlever_gjenåpning(tmp_path):
    db = Db(tmp_path / "tower.db")
    triagert(db, False)
    db.lagre_utkast(db.nytt_utkast("mail:x", "m0", NÅ), "Hei", ("sjekk æ",), NÅ)
    db.lukk()
    assert Db(tmp_path / "tower.db").rad("mail:x").utkast.sjekk == ("sjekk æ",)
