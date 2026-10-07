from __future__ import annotations

import pytest

from tower.agent import AgentFeil, Resultat
from tower.kanal import Melding, Person, Tråd
from tower.prompt import tråd_tekst
from tower.tests.conftest import MEG, NÅ
from tower.triage import SCHEMA, Triage, triager

KARI = Person("Kari Nordmann", "kari@kunde.no")
TRÅD = Tråd("mail:x", "mail", "Tilbud", (
    Melding("m1", KARI, (MEG,), (), NÅ, "Har dere et tilbud?", fra_meg=False, haster=True),
    Melding("m2", MEG, (KARI,), (), NÅ, "Kommer i morgen.", fra_meg=True, haster=False),
))
SVAR = {"kategori": "info", "haster": False, "sammendrag": "s", "begrunnelse": "b"}


class Skriptet:
    def __init__(self, *utfall):
        self.utfall = list(utfall)
        self.prompts = []

    async def kjør(self, instruks, schema, prompt):
        assert schema is SCHEMA and "triagerer" in instruks
        self.prompts.append(prompt)
        u = self.utfall.pop(0)
        if isinstance(u, Exception):
            raise u
        return Resultat(u, 0.01)


def test_tråd_tekst_har_adresser_og_meg():
    tekst = tråd_tekst(TRÅD)
    assert "Kari Nordmann <kari@kunde.no>" in tekst
    assert "fra Sander (meg)" in tekst
    assert "[høy viktighet]" in tekst
    assert "<kunnskapsbase>" not in tekst
    assert tråd_tekst(TRÅD, "# stil").startswith("<kunnskapsbase>\n# stil")


async def test_triage_ok():
    r = Skriptet(SVAR)
    assert await triager(r, TRÅD) == (Triage("info", False, "s", "b"), 0.01)


async def test_ett_nytt_forsøk():
    r = Skriptet(AgentFeil("timeout", 0.002), SVAR)
    triage, usd = await triager(r, TRÅD)
    assert triage.kategori == "info" and usd == pytest.approx(0.012)
    assert len(r.prompts) == 2


async def test_to_feil_kaster_med_samlet_kost():
    r = Skriptet(AgentFeil("a", 0.002), AgentFeil("b", 0.003))
    with pytest.raises(AgentFeil, match="b") as e:
        await triager(r, TRÅD)
    assert e.value.usd == pytest.approx(0.005)
