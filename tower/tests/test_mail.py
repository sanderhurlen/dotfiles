from __future__ import annotations

import json
import os

from tower.kanal.graph_fil import GraphFil
from tower.kanal.mail import MailKanal
from tower.kanal.tekst import html_til_tekst
from tower.tests.conftest import MEG


def kanal(config) -> MailKanal:
    return MailKanal(GraphFil(config.rot / "mail", config.outbox), MEG)


def test_html_til_tekst():
    html = "<html><head><style>p{}</style></head><body><p>Hei&nbsp;Sander,</p><p>linje 1<br>linje  2</p></body></html>"
    assert html_til_tekst(html) == "Hei\xa0Sander,\n\nlinje 1\nlinje 2"


async def test_graph_til_domene(config):
    tråder = {t.id: t for t in await kanal(config).hent()}
    assert len(tråder) == 7

    harbor = tråder["mail:AAQkADMock-harbor-outage"]
    assert harbor.kanal == "mail"
    assert harbor.emne.startswith("URGENT")
    m = harbor.siste
    assert m.fra.navn == "James Whitfield"
    assert [p.adresse for p in m.cc] == ["sander@visense.no"]
    assert m.haster and not m.fra_meg
    assert m.tid.tzinfo is not None
    assert "<p>" not in m.tekst and "\n\n" in m.tekst  # HTML-body strippet

    takk = tråder["mail:AAQkADMock-takk-passer"]
    assert [m.fra_meg for m in takk.meldinger] == [True, False]
    assert takk.meldinger[0].tid < takk.meldinger[1].tid


async def test_hent_gir_bare_endrede(config):
    k = kanal(config)
    assert len(await k.hent()) == 7
    assert await k.hent() == []

    sti = config.rot / "mail" / "AAQkADMock-nordlys-erp.json"
    os.utime(sti, ns=(0, sti.stat().st_mtime_ns + 1_000_000))
    assert [t.id for t in await k.hent()] == ["mail:AAQkADMock-nordlys-erp"]


async def test_halvskrevet_fil_prøves_igjen(config):
    k = kanal(config)
    await k.hent()
    sti = config.rot / "mail" / "ny.json"
    sti.write_text('{"value": [')
    assert await k.hent() == []
    data = json.loads((config.rot / "mail" / "AAQkADMock-nordlys-erp.json").read_text())
    data["conversationId"] = "ny"
    for m in data["value"]:
        m["conversationId"] = "ny"
    sti.write_text(json.dumps(data))
    os.utime(sti, ns=(0, sti.stat().st_mtime_ns + 1_000_000))
    assert [t.id for t in await k.hent()] == ["mail:ny"]


async def test_svar_skriver_outbox_og_trådfil(config):
    k = kanal(config)
    await k.hent()
    await k.svar("mail:AAQkADMock-fyi-cc", "Takk, Marte.")

    [ut] = list(config.outbox.iterdir())
    req = json.loads(ut.read_text())
    assert req == {
        "_towerChannel": "mail",
        "method": "POST",
        "path": "/me/messages/AAMkADMock-fyi-cc-1/replyAll",
        "body": {"comment": "Takk, Marte."},
    }

    [t] = await k.hent()
    assert t.siste.fra_meg and t.siste.tekst == "Takk, Marte."
    assert t.emne == "Re: Møtereferat oppstartsmøte"
    assert t.meldinger[-1].id.startswith("AAMkADMock-fyi-cc-1-svar-")
    assert {p.navn for p in t.siste.til} == {"Marte Lie", "Kari Nordby"}
    assert all(p.adresse != MEG.adresse for p in t.siste.til + t.siste.cc)
