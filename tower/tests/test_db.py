from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from tower.db import AVVIST, BESVART, GAMMEL, NY, TRIAGERT, UTSATT, Db, Rad, ny_status
from tower.kanal import Melding, Person, Tråd
from tower.tests.conftest import MEG, NÅ
from tower.triage import Triage

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


T = Triage("svar", True, "Svar Kari", "Hun spør direkte")


def test_lagre_triage_setter_triagert(tmp_path):
    db = Db(tmp_path / "tower.db")
    assert db.registrer(tråd(False), NÅ, 7).trenger_triage
    rad = db.lagre_triage("mail:x", "m0", T, NÅ)
    assert rad.status == TRIAGERT and rad.triage == T and not rad.trenger_triage


def test_ny_melding_beholder_gammel_triage_men_trenger_ny(tmp_path):
    db = Db(tmp_path / "tower.db")
    db.registrer(tråd(False), NÅ, 7)
    db.lagre_triage("mail:x", "m0", T, NÅ)
    rad = db.registrer(tråd(False, False), NÅ, 7)
    assert rad.status == NY and rad.triage == T and rad.trenger_triage


def test_triage_for_utdatert_melding_ignoreres(tmp_path):
    db = Db(tmp_path / "tower.db")
    db.registrer(tråd(False, False), NÅ, 7)
    assert db.lagre_triage("mail:x", "m0", T, NÅ) is None
    assert db.lagre_triage_feil("mail:x", "m0", "x", NÅ) is None
    assert db.rad("mail:x").triage is None


def test_triage_feil(tmp_path):
    db = Db(tmp_path / "tower.db")
    db.registrer(tråd(False), NÅ, 7)
    rad = db.lagre_triage_feil("mail:x", "m0", "timeout", NÅ)
    assert rad.triage_feilet and not rad.trenger_triage and rad.status == NY
    assert not db.registrer(tråd(False, False), NÅ, 7).triage_feilet


def test_kost_i_dag(tmp_path):
    db = Db(tmp_path / "tower.db")
    db.logg_kjøring("triage", "mail:x", 0.01, NÅ)
    db.logg_kjøring("triage", "mail:x", 0.02, NÅ, feil="timeout")
    db.logg_kjøring("triage", "mail:x", 0.5, NÅ - timedelta(days=1))
    assert db.kost(NÅ) == pytest.approx(0.03)


def test_migrerer_tracer_db(tmp_path):
    sti = tmp_path / "tower.db"
    con = sqlite3.connect(sti)
    con.execute("CREATE TABLE trad (id TEXT PRIMARY KEY, kanal TEXT NOT NULL, status TEXT NOT NULL, "
                "siste_melding_id TEXT NOT NULL, endret TEXT NOT NULL)")
    con.execute("INSERT INTO trad VALUES ('mail:x', 'mail', 'ny', 'm0', '')")
    con.commit()
    con.close()
    rad = Db(sti).rad("mail:x")
    assert rad == Rad("mail:x", "mail", NY, "m0") and rad.trenger_triage


def test_migrerer_utkast_uten_redigert(tmp_path):
    sti = tmp_path / "tower.db"
    con = sqlite3.connect(sti)
    con.execute("CREATE TABLE utkast (trad TEXT NOT NULL, versjon INTEGER NOT NULL, melding_id TEXT NOT NULL, "
                "status TEXT NOT NULL, tekst TEXT NOT NULL DEFAULT '', sjekk TEXT NOT NULL DEFAULT '[]', feil TEXT, "
                "instruks TEXT, opprettet TEXT NOT NULL, endret TEXT NOT NULL, PRIMARY KEY (trad, versjon))")
    con.execute("INSERT INTO utkast VALUES ('mail:x', 1, 'm0', 'klart', 'Hei', '[]', NULL, NULL, '', '')")
    con.commit()
    con.close()
    u = Db(sti).utkast("mail:x")
    assert u.redigert is None and u.gjeldende == "Hei"


def klart(db: Db, *fra_meg: bool, tekst="Hei [[dato]]"):
    t = tråd(*fra_meg)
    db.registrer(t, NÅ, 7)
    db.lagre_triage(t.id, t.siste.id, T, NÅ)
    return db.lagre_utkast(db.nytt_utkast(t.id, t.siste.id, NÅ), tekst, (), NÅ)


def test_redigert_beholder_agentens_tekst(tmp_path):
    db = Db(tmp_path / "tower.db")
    u = db.lagre_redigert(klart(db, False), "Hei 12. okt", NÅ)
    assert (u.tekst, u.redigert, u.gjeldende, u.plassholdere) == ("Hei [[dato]]", "Hei 12. okt", "Hei 12. okt", [])
    assert u.status == "klart"


def test_sendt_forkaster_andre_åpne_versjoner(tmp_path):
    db = Db(tmp_path / "tower.db")
    v1 = klart(db, False)
    db.registrer(tråd(False, False), NÅ, 7)  # v1 utdatert
    db.nytt_utkast("mail:x", "m1", NÅ)
    assert db.marker_sendt(v1, NÅ).status == "sendt"
    assert [v.status for v in db.versjoner("mail:x")] == ["sendt", "forkastet"]


def test_sendefeil_lar_utkastet_stå_klart(tmp_path):
    db = Db(tmp_path / "tower.db")
    u = db.lagre_sendefeil(klart(db, False), "nett nede", NÅ)
    assert (u.status, u.feil) == ("klart", "nett nede")
    assert db.marker_sendt(u, NÅ).feil is None


def test_avvis_forkaster_til_ny_melding(tmp_path):
    db = Db(tmp_path / "tower.db")
    klart(db, False)
    rad = db.avvis("mail:x", NÅ)
    assert rad.status == AVVIST and rad.utkast.status == "forkastet" and not rad.trenger_utkast
    rad = db.registrer(tråd(False, False), NÅ, 7)
    assert rad.status == NY and rad.trenger_triage


def test_utsett_vekkes_av_tid_med_utkastet_i_behold(tmp_path):
    db = Db(tmp_path / "tower.db")
    klart(db, False)
    rad = db.utsett("mail:x", NÅ + timedelta(hours=1), NÅ)
    assert rad.status == UTSATT and rad.utsatt_til == NÅ + timedelta(hours=1)
    assert db.vekk(NÅ + timedelta(minutes=59)) == []
    assert db.vekk(NÅ + timedelta(hours=1)) == ["mail:x"]
    rad = db.rad("mail:x")
    assert rad.status == TRIAGERT and rad.utsatt_til is None and rad.utkast.status == "klart"
    assert not rad.trenger_utkast  # gjenbrukes


def test_utsett_uten_triage_vekkes_som_ny_og_ny_melding_vekker_tidlig(tmp_path):
    db = Db(tmp_path / "tower.db")
    db.registrer(tråd(False), NÅ, 7)
    db.utsett("mail:x", NÅ + timedelta(days=1), NÅ)
    db.vekk(NÅ + timedelta(days=1))
    assert db.rad("mail:x").status == NY

    db.utsett("mail:x", NÅ + timedelta(days=1), NÅ)
    rad = db.registrer(tråd(False, False), NÅ, 7)
    assert rad.status == NY and rad.utsatt_til is None
    assert db.vekk(NÅ + timedelta(days=2)) == []
