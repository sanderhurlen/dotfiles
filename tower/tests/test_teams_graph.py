"""Ekte Teams: personlige chatter fra Graph blir trådfiler, og svar kopieres fra tower i stedet for å sendes."""

from __future__ import annotations

import dataclasses
import json
import os
import urllib.parse
from datetime import datetime, timezone

import pytest
from textual.widgets import DataTable

from tower.app import tråd_markup
from tower.graph import Graph, GraphFeil
from tower.kanal.graph_fil import GraphFil
from tower.kanal.teams import TeamsKanal
from tower.kanal.teams_graph import TeamsGraph
from tower.tests.conftest import MEG, FalskRunner
from tower.tests.test_handlinger import App, klar

NÅ = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
OLA = "teams:19:u-ola_u-sander@unq.gbl.spaces"


def chat(id, type_="oneOnOne", sist="2026-10-22T08:00:00Z", forhånd="p1"):
    return {"id": id, "chatType": type_, "topic": None, "webUrl": f"https://teams/{id}",
            "lastMessagePreview": {"id": forhånd, "createdDateTime": sist}}


def melding(id, fra="u-ola", tid="2026-10-22T08:00:00Z", **ekstra):
    return {"id": id, "messageType": "message", "createdDateTime": tid, "deletedDateTime": None,
            "from": {"user": {"id": fra, "displayName": fra}}, "body": {"contentType": "text", "content": "hei"},
            **ekstra}


MEDLEMMER = [{"userId": "u-ola", "displayName": "Ola Berg", "email": "ola@visense.no"},
             {"userId": "u-meg", "displayName": MEG.navn, "email": MEG.adresse}]


class FalskGraph:
    def __init__(self, sider: list[list[dict]], meldinger: dict[str, list[dict]]) -> None:
        self.sider = sider
        self.meldinger = meldinger
        self.kall_logg: list[str] = []

    def kall(self, method, path, body=None, headers=None):
        assert method == "GET"
        self.kall_logg.append(path)
        if path.startswith("/me/chats?") or path.startswith("neste:"):
            i = int(path.removeprefix("neste:")) if path.startswith("neste:") else 0
            assert i or "$orderby=lastMessagePreview/createdDateTime%20desc" in path
            side = {"value": self.sider[i]}
            if i + 1 < len(self.sider):
                side["@odata.nextLink"] = f"neste:{i + 1}"
            return side
        chat_id = urllib.parse.unquote(path.split("/")[2])
        assert path.endswith("/messages?$top=50&$orderby=createdDateTime%20desc")
        return {"value": sorted(self.meldinger[chat_id], key=lambda m: m["createdDateTime"], reverse=True)}

    def alle(self, path, headers=None):
        self.kall_logg.append(path)
        assert path.endswith("/members")
        return MEDLEMMER


def les(sti):
    return json.loads(sti.read_text())


def test_synk_tar_personlige_chatter_innenfor_vinduet(tmp_path):
    graph = FalskGraph([
        [chat("19:a@unq"), chat("19:møte", type_="meeting")],
        [chat("19:g@thread.v2", type_="group", sist="2026-10-20T08:00:00Z"),
         chat("19:gammel", sist="2026-10-01T08:00:00Z"), chat("19:aldri-lest")],
    ], {"19:a@unq": [melding("2", tid="2026-10-22T08:00:00Z"), melding("1", fra="u-meg", tid="2026-10-21T08:00:00Z"),
                     melding("x", deletedDateTime="2026-10-21T09:00:00Z")],
        "19:g@thread.v2": [melding("g1")]})
    tg = TeamsGraph(graph, tmp_path)
    assert tg.synk(7, NÅ) == 2
    assert not any("aldri-lest" in p for p in graph.kall_logg)  # sidene stopper ved første gamle chat
    data = les(tmp_path / "19_a_unq.json")
    assert [m["id"] for m in data["value"]] == ["1", "2"]  # stigende, slettet melding borte
    assert data["chat"]["members"] == MEDLEMMER
    assert "/chats/19%3Aa%40unq/members" in graph.kall_logg
    assert sorted(p.name for p in tmp_path.iterdir()) == ["19_a_unq.json", "19_g_thread.v2.json"]

    graph.kall_logg.clear()
    assert tg.synk(7, NÅ) == 0  # samme siste melding: meldingene hentes ikke på nytt
    assert not any("/messages" in p for p in graph.kall_logg)

    graph.sider = [[chat("19:a@unq", forhånd="p2")]]
    assert tg.synk(7, NÅ) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["19_a_unq.json"]  # gruppa er for gammel nå


async def test_kanal_med_graph_gir_tråder_og_sender_aldri(tmp_path):
    graph = FalskGraph([[chat("19:a@unq")]], {"19:a@unq": [melding("1")]})
    (tmp_path / "teams").mkdir()
    kanal = TeamsKanal(GraphFil(tmp_path / "teams", tmp_path / "outbox"), MEG, TeamsGraph(graph, tmp_path / "teams"),
                       synk_sekunder=0)
    [tråd] = await kanal.hent()
    assert tråd.id == "teams:19:a@unq" and tråd.emne == "Ola Berg" and tråd.siste.fra.adresse == "ola@visense.no"
    assert kanal.lenke(tråd.id) == "https://teams/19:a@unq"
    with pytest.raises(RuntimeError, match="kopier"):
        await kanal.svar(tråd.id, "hei")

    graph.sider = [[]]
    assert await kanal.hent() == []
    assert kanal.fjernede() == [tråd.id]


async def test_historikken_har_nyeste_øverst(tmp_path):
    graph = FalskGraph([[chat("19:a@unq")]], {"19:a@unq": [
        melding("1", tid="2026-10-22T07:00:00Z", body={"content": "først"}),
        melding("2", tid="2026-10-22T08:00:00Z", body={"content": "sist"})]})
    (tmp_path / "teams").mkdir()
    kanal = TeamsKanal(GraphFil(tmp_path / "teams", tmp_path / "outbox"), MEG, TeamsGraph(graph, tmp_path / "teams"))
    [tråd] = await kanal.hent()
    tekst = tråd_markup(tråd)
    assert tekst.index("sist") < tekst.index("først")


def test_graph_nekter_å_sende_teams_og_krever_ny_innlogging_for_nye_scopes(tmp_path):
    (tmp_path / "config.json").write_text('{"tenantId": "t", "clientId": "c"}')
    g = Graph(tmp_path)
    with pytest.raises(GraphFeil, match="Teams"):
        g.kall("POST", "/chats/19:a/messages", {})
    (tmp_path / "token.json").write_text(json.dumps({"access_token": "a", "refresh_token": "r", "utløper": 9e12}))
    with pytest.raises(GraphFeil, match="tower login"):
        g.token()


def lag(config) -> App:
    config = dataclasses.replace(config, kanaler=("teams",), graph=("teams",))
    a = App(config, FalskRunner(), kanaler=[TeamsKanal(GraphFil(config.rot / "teams", config.outbox), MEG)])
    a.kopiert = []
    a.kopier = a.kopiert.append
    return a


async def test_teams_utkast_kopieres_og_chatten_åpnes(config):
    a = lag(config)
    async with a.run_test(size=(160, 40)) as pilot:
        await klar(a, pilot, OLA)
        await pilot.press("s")
        assert a.varsler[-1] == ("Sendes fra Teams: c kopierer utkastet, o åpner chatten", "warning")
        assert not config.outbox.exists() or not any(config.outbox.iterdir())

        await pilot.press("c")
        assert a.kopiert == ["Hei\n\nDet passer.\n\n--\nSander\nVisense"]
        assert a.varsler[-1] == ("Utkastet er kopiert, o åpner chatten", "information")
        await pilot.press("o")
        assert a.åpnet == ["https://teams.microsoft.com/l/chat/19:u-ola_u-sander@unq.gbl.spaces/0"]

        # Limt inn og sendt i Teams: svaret dukker opp i chatten
        sti = config.rot / "teams" / "ola-pr.json"
        data = les(sti)
        data["value"].append({**data["value"][-1], "id": "mitt-svar", "createdDateTime": "2026-10-07T10:59:00Z",
                              "from": {"user": {"id": "u-sander", "displayName": MEG.navn}}})
        sti.write_text(json.dumps(data))
        os.utime(sti, ns=(0, sti.stat().st_mtime_ns + 1_000_000))
        await a.poll()
        await pilot.pause()
        assert a.rader[OLA].status == "besvart"
        assert OLA not in [k.value for k in a.query_one(DataTable).rows]  # besvarte Teams-chatter vises ikke
