from __future__ import annotations

import json
from datetime import timedelta

import pytest

from tower import mock
from tower.agent import AgentFeil, Resultat
from tower.kanal.graph_fil import GraphFil
from tower.kanal.mail import MailKanal
from tower.kanal.teams import TeamsKanal
from tower.tests.conftest import MEG, NÅ


class MockRunner:
    """Kannet svar per kall; husker schema og prompt."""

    def __init__(self, *svar) -> None:
        self.svar = list(svar)
        self.kall: list[tuple[dict, str]] = []

    async def kjør(self, instruks, schema, prompt):
        self.kall.append((schema, prompt))
        s = self.svar.pop(0)
        if isinstance(s, Exception):
            raise s
        return Resultat(s, 0.02)


def m(fra, tekst, alder, til=("meg",), cc=(), viktig=False):
    return {"fra": fra, "til": list(til), "cc": list(cc), "alder_minutter": alder, "viktig": viktig, "tekst": tekst}


NYE = {"trader": [
    {"kanal": "mail", "emne": "Faktura for oktober", "meldinger": [
        m("meg", "Hei Erik,\n\nVedlagt kommer fakturaen.\n\n--\nSander", 300, til=["erik"]),
        m("erik", "Hei Sander,\n\nHvorfor er timene høyere enn estimert?\n\nMvh Erik", 30, cc=["kari"], viktig=True),
    ]},
    {"kanal": "teams", "emne": "", "meldinger": [m("ola", "har du sett CI-feilen på main?", 5, til=[])]},
    {"kanal": "teams", "emne": "Harbor incident", "meldinger": [
        m("tom", "API is down again", 20, til=["priya"]),
        m("priya", "@Sander can you check the deploy log?", 10, til=[]),
    ]},
]}


def mail_kanal(config):
    return MailKanal(GraphFil(config.rot / "mail", config.outbox), MEG)


def teams_kanal(config):
    return TeamsKanal(GraphFil(config.rot / "teams", config.outbox), MEG)


@pytest.fixture
def tom(config, tmp_path):
    """Config uten fixtures: bare det mock lager."""
    for k in ("mail", "teams"):
        for f in (config.rot / k).iterdir():
            f.unlink()
    return config


async def test_nye_tråder_skrives_som_graph_og_leses_av_adapterne(tom):
    runner = MockRunner(NYE)
    skrevne, avvist, usd = await mock.lag_tråder(runner, tom, n=3, nå=NÅ)
    assert avvist == [] and len(skrevne) == 3 and usd == 0.02

    [faktura] = await mail_kanal(tom).hent()
    assert faktura.emne == "Faktura for oktober"
    første, siste = faktura.meldinger
    assert første.fra_meg and [p.adresse for p in første.til] == ["erik.haugen@nordlys-energi.no"]
    assert siste.fra.navn == "Erik Haugen" and not siste.fra_meg and siste.haster
    assert [p.adresse for p in siste.til] == ["sander@visense.no"]
    assert [p.adresse for p in siste.cc] == ["kari.nordby@nordlys-energi.no"]
    assert siste.tid == NÅ - timedelta(minutes=30) and første.tid < siste.tid
    data = json.loads(skrevne[0].read_text())
    assert data["value"][1]["subject"] == "RE: Faktura for oktober"
    assert data["value"][1]["isRead"] is False and data["value"][0]["isRead"] is True

    chatter = {t.emne: t for t in await teams_kanal(tom).hent()}
    ola = chatter["Ola Berg"]
    assert ola.emne_utledet and ola.siste.fra.adresse == "ola.berg@visense.no"
    hendelse = chatter["Harbor incident"]
    assert [x.fra.navn for x in hendelse.meldinger] == ["Tom Hansen", "Priya Nair"]
    assert {p.navn for p in hendelse.siste.til} == {"Sander Hurlen", "Tom Hansen"}


async def test_schema_og_prompt_følger_valgene(tom):
    runner = MockRunner({"trader": NYE["trader"][1:2]})
    await mock.lag_tråder(runner, tom, n=1, kanal="teams", nå=NÅ)
    schema, prompt = runner.kall[0]
    tråd = schema["properties"]["trader"]
    assert tråd["minItems"] == tråd["maxItems"] == 1
    assert tråd["items"]["properties"]["kanal"]["enum"] == ["teams"]
    assert "ola" in tråd["items"]["properties"]["meldinger"]["items"]["properties"]["fra"]["enum"]
    assert "<rollebesetning>" in prompt and "Lag 1 nye Tråder. Kanal: teams." in prompt


async def test_eksisterende_emner_er_med_i_prompten(config):
    runner = MockRunner({"trader": NYE["trader"][:1]})
    await mock.lag_tråder(runner, config, n=1, nå=NÅ)
    assert "- Status på ERP-integrasjonen" in runner.kall[0][1]


async def test_ugyldige_tråder_avvises_resten_skrives(tom):
    svar = {"trader": [
        {"kanal": "teams", "emne": "", "meldinger": [m("github", "PR merged", 3)]},  # bare_mail
        {"kanal": "mail", "emne": "Tom", "meldinger": [m("kari", "   ", 3)]},
        {"kanal": "fax", "emne": "Feil kanal", "meldinger": [m("kari", "x", 3)]},
        NYE["trader"][0],
    ]}
    skrevne, avvist, _ = await mock.lag_tråder(MockRunner(svar), tom, n=4, kanal=None, nå=NÅ)
    assert len(skrevne) == 1 and len(avvist) == 3
    assert "github finnes ikke i Teams" in avvist[0] and "tom melding" in avvist[1] and "fax" in avvist[2]
    assert [f.name for f in (tom.rot / "teams").iterdir()] == []


async def test_ikke_idempotent(tom):
    runner = MockRunner(NYE, NYE)
    a, _, _ = await mock.lag_tråder(runner, tom, n=3, nå=NÅ)
    b, _, _ = await mock.lag_tråder(runner, tom, n=3, nå=NÅ)
    assert not set(a) & set(b)
    assert len(await mail_kanal(tom).hent()) == 2


async def test_svar_legger_ny_melding_i_mail_tråd(config):
    k = mail_kanal(config)
    await k.hent()
    runner = MockRunner({"fra": "per.aas@fjellbygg.no", "viktig": False, "tekst": "Glemte å si: gjerne fra 1. desember."})
    sti, t, _ = await mock.ny_melding(runner, config, "pris-kontrakt", nå=NÅ)
    assert sti.name == "AAQkADMock-pris-kontrakt.json"
    schema, prompt = runner.kall[0]
    assert schema["properties"]["fra"]["enum"] == ["per.aas@fjellbygg.no"]
    assert "Spørsmål om pris for utvidet support" in prompt

    [endret] = await k.hent()  # adapteren ser én endret Tråd med ny siste Melding fra Per
    assert len(endret.meldinger) == 2 and endret.siste.fra.navn == "Per Aas"
    assert endret.siste.tid == NÅ and [p.adresse for p in endret.siste.til] == ["sander@visense.no"]
    assert json.loads(sti.read_text())["value"][-1]["subject"] == "RE: Spørsmål om pris for utvidet support"


async def test_svar_i_teams_bruker_medlemmets_bruker_id(config):
    runner = MockRunner({"fra": "priya.nair@visense.no", "viktig": True, "tekst": "Tests are green now."})
    _, t, _ = await mock.ny_melding(runner, config, "release42", nå=NÅ)
    assert t.siste.fra.adresse == "priya.nair@visense.no" and t.siste.haster
    assert t.siste.tid > t.meldinger[-2].tid
    assert sorted(runner.kall[0][0]["properties"]["fra"]["enum"]) == ["priya.nair@visense.no", "tom.hansen@visense.no"]


async def test_svar_uten_tråd_velger_en_som_venter_på_meg(config):
    valgt = []

    def velg(xs):
        valgt.extend(xs)
        return next(x for x in xs if x[0].stem == "AAQkADMock-nordlys-erp")

    await mock.ny_melding(MockRunner({"fra": "kari.nordby@nordlys-energi.no", "viktig": False, "tekst": "x"}),
                          config, None, nå=NÅ, velg=velg)
    assert valgt and not any(x[2].siste.fra_meg for x in valgt)


def test_finn_er_tydelig_på_tvetydige_og_ukjente(config):
    with pytest.raises(mock.MockFeil, match="treffer 0"):
        mock.finn(config, "finnes-ikke")
    with pytest.raises(mock.MockFeil, match="treffer [2-9]"):
        mock.finn(config, "AAQkADMock")


def test_cli(tom, capsys):
    runner = MockRunner({"trader": NYE["trader"][1:]})
    assert mock.main(["-n", "2", "--kanal", "teams"], runner=runner, config=tom) == 0
    ut = capsys.readouterr()
    assert ut.out.count("teams: ") == 2 and "kost $0.020" in ut.err

    assert mock.main(["--svar", "finnes-ikke"], runner=MockRunner(), config=tom) == 1
    assert "treffer 0" in capsys.readouterr().err

    feilende = MockRunner(AgentFeil("timeout"), AgentFeil("timeout"))
    assert mock.main([], runner=feilende, config=tom) == 1
    assert "timeout" in capsys.readouterr().err


def test_rollebesetningen_henger_sammen():
    ps = mock.personer()
    assert ps["meg"]["adresse"] == MEG.adresse
    org = {o["id"] for o in mock.ROLLEBESETNING["org"]}
    assert all(p["org"] in org | {"ekstern"} for p in ps.values())
    assert len({p["adresse"] for p in ps.values()}) == len(ps)
    assert {p["relasjon"] for p in ps.values()} >= {"kunde", "kollega", "ledelse", "info"}
