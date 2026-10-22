from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone

import pytest

from tower.graph import Graph, GraphFeil
from tower.kanal import Kladd
from tower.kanal.graph_fil import GraphFil
from tower.kanal.mail import MailKanal
from tower.kanal.mail_graph import MailGraph
from tower.tests.conftest import MEG

NÅ = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
MAPPER = {"inbox": "INN", "drafts": "KLADD", "deleteditems": "SLETTET", "junkemail": "SØPPEL", "outbox": "UT"}


def melding(id, samtale, mappe, fra="ola@kunde.no", tid="2026-10-22T08:00:00Z", **ekstra):
    return {"id": id, "conversationId": samtale, "subject": f"Emne {samtale}", "parentFolderId": mappe,
            "from": {"emailAddress": {"name": fra, "address": fra}}, "toRecipients": [], "ccRecipients": [],
            "receivedDateTime": tid, "sentDateTime": tid, "body": {"contentType": "text", "content": "hei"},
            "isDraft": False, **ekstra}


class FalskGraph:
    def __init__(self, meldinger: list[dict], kladder: list[dict] = ()) -> None:
        self.meldinger = meldinger
        self.kladder = list(kladder)
        self.kall_logg: list[tuple] = []

    def kall(self, method, path, body=None, headers=None):
        self.kall_logg.append((method, path, body))
        if path.startswith("/me/mailFolders/"):
            return {"id": MAPPER[path.split("/")[3].split("?")[0]]}
        if path.endswith("/createReplyAll"):
            return {"id": "kladd", "isDraft": True, "webLink": "https://outlook.office365.com/owa/?ItemID=kladd"}
        if method == "DELETE" and path.endswith("/borte"):
            raise GraphFeil("Graph 404: The specified object was not found in the store.")
        return {}

    def alle(self, path, headers=None):
        if path.startswith("/me/mailFolders/drafts/messages"):
            assert "uniqueBody" in path and "text" in headers["Prefer"]
            return self.kladder
        if path.startswith("/me/mailFolders/inbox/messages?$filter="):
            samtale = urllib.parse.unquote(path.split("=", 1)[1].split("&")[0]).split("'")[1]
            return [{"id": m["id"], "isRead": m.get("isRead", False)} for m in self.meldinger
                    if m["parentFolderId"] == "INN" and m["conversationId"] == samtale]
        if path.startswith("/me/mailFolders/inbox/messages"):
            return [{"conversationId": m["conversationId"]} for m in self.meldinger if m["parentFolderId"] == "INN"]
        assert "$filter=receivedDateTime%20ge%20" in path
        return self.meldinger


def les(sti):
    return json.loads(sti.read_text())


def test_synk_grupperer_samtaler_med_innboks(tmp_path):
    graph = FalskGraph([
        melding("a1", "A", "INN"),
        melding("a2", "A", "SENDT", fra=MEG.adresse, tid="2026-10-22T09:00:00Z"),
        melding("b1", "B", "SENDT", fra=MEG.adresse),  # bare sendt: ikke en Tråd
        melding("c1", "C", "INN", isDraft=True),
        melding("d1", "D", "SØPPEL"),
    ])
    mg = MailGraph(graph, tmp_path)
    assert mg.synk(7, NÅ) == 1
    data = les(tmp_path / "A.json")
    assert data["conversationId"] == "A"
    assert [m["id"] for m in data["value"]] == ["a1", "a2"]
    assert mg.synk(7, NÅ) == 0  # uendret: fila røres ikke


async def test_kladd_lages_hentes_og_slettes_aldri_sendt(tmp_path):
    graph = FalskGraph([melding("a1", "A", "INN")], kladder=[
        {"id": "k1", "webLink": "https://owa/k1", "uniqueBody": {"content": "Hei \r\nDet passer.\r\n"}}])
    (tmp_path / "mail").mkdir()
    kanal = MailKanal(GraphFil(tmp_path / "mail", tmp_path / "outbox"), MEG, MailGraph(graph, tmp_path / "mail"))
    [tråd] = await kanal.hent()
    assert kanal.kladder() == {"k1": Kladd("k1", "https://owa/k1", "Hei\nDet passer.")}
    assert kanal.kladder() is None  # ikke hentet på nytt

    k = await kanal.lag_kladd(tråd.id, "Hei <Ola>\nDet passer.\n")
    assert k == Kladd("kladd", "https://outlook.office365.com/owa/?ItemID=kladd", "Hei <Ola>\nDet passer.")
    assert graph.kall_logg[-1] == ("POST", "/me/messages/a1/createReplyAll",
                                   {"comment": "Hei &lt;Ola&gt;<br>Det passer.<br>"})
    await kanal.slett_kladd("k1")
    await kanal.slett_kladd("borte")  # slettet allerede er ok
    assert graph.kall_logg[-2][:2] == ("DELETE", "/me/messages/k1")
    with pytest.raises(RuntimeError):
        await kanal.svar(tråd.id, "hei")
    assert not any("/send" in p or p.endswith("/replyAll") for _, p, _ in graph.kall_logg)


def test_graph_nekter_å_sende(tmp_path):
    (tmp_path / "config.json").write_text('{"tenantId": "t", "clientId": "c"}')
    g = Graph(tmp_path)
    for path in ("/me/sendMail", "/me/messages/a1/send", "/me/messages/a1/replyAll", "/me/messages/a1/reply",
                 "/me/messages/a1/forward"):
        with pytest.raises(GraphFeil, match="sender aldri"):
            g.kall("POST", path, {})


async def test_tråd_slettet_i_outlook_forsvinner(tmp_path):
    graph = FalskGraph([melding("a1", "A", "INN"), melding("b1", "B", "INN")])
    (tmp_path / "mail").mkdir()
    kanal = MailKanal(GraphFil(tmp_path / "mail", tmp_path / "outbox"), MEG, MailGraph(graph, tmp_path / "mail"),
                      synk_sekunder=0)
    assert {t.id for t in await kanal.hent()} == {"mail:A", "mail:B"}
    assert kanal.fjernede() == []

    graph.meldinger[0]["parentFolderId"] = "SLETTET"
    assert await kanal.hent() == []
    assert kanal.fjernede() == ["mail:A"]
    assert sorted(p.name for p in (tmp_path / "mail").iterdir()) == ["B.json"]


def test_eldre_tråd_i_innboksen_beholdes(tmp_path):
    graph = FalskGraph([melding("a1", "A", "INN")])
    mg = MailGraph(graph, tmp_path)
    mg.synk(7, NÅ)
    graph.alle = lambda path, headers=None: (
        [{"conversationId": "A"}] if "inbox/messages" in path else [])  # utenfor vinduet, men fortsatt i innboksen
    mg.synk(7, NÅ)
    assert (tmp_path / "A.json").exists()


async def test_arkiver_markerer_lest_og_flytter_til_slettede(tmp_path):
    graph = FalskGraph([
        melding("a1", "A", "INN"),
        melding("a2", "A", "INN", isRead=True, tid="2026-10-22T09:00:00Z"),
        melding("a3", "A", "SENDT", fra=MEG.adresse),  # ikke i innboksen: blir der den er
        melding("b1", "B", "INN"),
    ])
    (tmp_path / "mail").mkdir()
    kanal = MailKanal(GraphFil(tmp_path / "mail", tmp_path / "outbox"), MEG, MailGraph(graph, tmp_path / "mail"))
    await kanal.hent()
    graph.kall_logg.clear()
    await kanal.arkiver("mail:A")
    assert graph.kall_logg == [
        ("PATCH", "/me/messages/a1", {"isRead": True}),
        ("POST", "/me/messages/a1/move", {"destinationId": "deleteditems"}),
        ("POST", "/me/messages/a2/move", {"destinationId": "deleteditems"}),
    ]
    assert kanal.fjernede() == ["mail:A"]
