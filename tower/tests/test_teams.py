from __future__ import annotations

import json

import pytest

from tower.kanal.graph_fil import GraphFil
from tower.kanal.teams import TeamsKanal
from tower.tests.conftest import MEG

RELEASE = "teams:19:mock-release42@thread.v2"
OLA = "teams:19:u-ola_u-sander@unq.gbl.spaces"
REFERAT = "teams:19:mock-referat@thread.v2"


def kanal(config) -> TeamsKanal:
    return TeamsKanal(GraphFil(config.rot / "teams", config.outbox), MEG)


async def test_graph_til_domene(config):
    tråder = {t.id: t for t in await kanal(config).hent()}
    assert len(tråder) == 4

    release = tråder[RELEASE]
    assert release.kanal == "teams"
    assert release.emne == "Release 4.2" and not release.emne_utledet
    assert len(release.meldinger) == 3  # systemhendelsen er filtrert bort
    assert [m.fra_meg for m in release.meldinger] == [False, True, False]
    m = release.siste
    assert m.fra.navn == "Tom Hansen" and m.fra.adresse == "tom.hansen@visense.no"
    assert m.haster
    assert m.tekst.startswith("@Sander we need a go/no-go")  # HTML og mention strippet
    assert {p.navn for p in m.til} == {"Sander Hurlen", "Priya Nair"} and m.cc == ()
    assert m.tid.tzinfo is not None

    ola = tråder[OLA]
    assert ola.emne == "Ola Berg" and ola.emne_utledet
    assert not ola.siste.haster

    referat = tråder[REFERAT]
    assert referat.emne == "Marte Lie, Jonas Dahl" and referat.emne_utledet
    assert referat.siste.fra_meg


async def test_systemhendelse_alene_gir_ingen_tråd(config):
    sti = config.rot / "teams" / "release42.json"
    data = json.loads(sti.read_text())
    data["value"] = data["value"][:1]
    sti.write_text(json.dumps(data))
    assert RELEASE not in {t.id for t in await kanal(config).hent()}


async def test_svar_skriver_outbox_og_trådfil(config):
    k = kanal(config)
    await k.hent()
    await k.svar(OLA, "Ja, ser på den etter lunsj.")

    [ut] = list(config.outbox.iterdir())
    assert json.loads(ut.read_text()) == {
        "_towerChannel": "teams",
        "method": "POST",
        "path": "/chats/19:u-ola_u-sander@unq.gbl.spaces/messages",
        "body": {"body": {"contentType": "text", "content": "Ja, ser på den etter lunsj."}},
    }

    [t] = await k.hent()
    assert t.id == OLA
    assert t.siste.fra_meg and t.siste.tekst == "Ja, ser på den etter lunsj."
    assert t.siste.fra == MEG
    assert [p.navn for p in t.siste.til] == ["Ola Berg"]
    data = json.loads((config.rot / "teams" / "ola-pr.json").read_text())
    assert data["value"][-1]["from"]["user"]["id"] == "u-sander"


async def test_svar_på_ukjent_tråd_kaster(config):
    with pytest.raises(KeyError):
        await kanal(config).svar("teams:finnes-ikke", "hei")
