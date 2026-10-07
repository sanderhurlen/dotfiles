from __future__ import annotations

from datetime import timedelta

from tower.db import BESVART, GAMMEL, NY, Db, Rad, ny_status
from tower.kanal import Melding, Person, Tråd
from tower.tests.conftest import MEG, NÅ

KARI = Person("Kari", "kari@kunde.no")


def tråd(*fra_meg: bool, alder=timedelta(hours=1)) -> Tråd:
    meldinger = tuple(
        Melding(id=f"m{i}", fra=MEG if meg else KARI, til=(), cc=(), tid=NÅ - alder + timedelta(minutes=i),
                tekst="", fra_meg=meg, haster=False)
        for i, meg in enumerate(fra_meg))
    return Tråd(id="mail:x", kanal="mail", emne="x", meldinger=meldinger)


def test_ny_tråd():
    assert ny_status(None, tråd(False), NÅ, 7) == NY


def test_siste_fra_meg_er_besvart():
    assert ny_status(None, tråd(False, True), NÅ, 7) == BESVART


def test_gammel_bare_ved_første_syn():
    gammel = tråd(False, alder=timedelta(days=8))
    assert ny_status(None, gammel, NÅ, 7) == GAMMEL
    forrige = Rad("mail:x", "mail", BESVART, "før")
    assert ny_status(forrige, gammel, NÅ, 7) == NY


def test_uendret_tråd_gir_ingen_endring():
    t = tråd(False)
    assert ny_status(Rad("mail:x", "mail", NY, t.siste.id), t, NÅ, 7) is None


def test_ny_melding_etter_besvart_gir_ny():
    t = tråd(False, True, False)
    assert ny_status(Rad("mail:x", "mail", BESVART, "m1"), t, NÅ, 7) == NY


def test_db_registrer_og_gjenåpne(tmp_path):
    sti = tmp_path / "tower.db"
    db = Db(sti)
    assert db.registrer(tråd(False), NÅ, 7).status == NY
    assert db.registrer(tråd(False, True), NÅ, 7).status == BESVART
    assert db.registrer(tråd(False, True), NÅ, 7).status == BESVART  # uendret
    db.lukk()
    assert Db(sti).alle() == {"mail:x": Rad("mail:x", "mail", BESVART, "m1")}
