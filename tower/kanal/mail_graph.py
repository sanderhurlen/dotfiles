"""Ekte mail: Graph → trådfiler i samme form som mock (`{"conversationId", "value": [message…]}`).

Henter alle mapper unntatt kladd/slettet/søppel de siste `dager`, grupperer på `conversationId` og beholder
samtaler med minst én melding i innboksen. Fila skrives bare når innholdet endres, så GraphFil ser kun ekte endringer.
Samtaler uten noe igjen i innboksen (slettet eller arkivert) får fila slettet, uansett alder.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tower.graph import Graph, GraphFeil
from tower.kanal import Kladd, kladdtekst
from tower.kanal.graph_fil import skriv_atomisk

FELT = ("id,conversationId,subject,from,toRecipients,ccRecipients,replyTo,receivedDateTime,sentDateTime,"
        "body,bodyPreview,isRead,importance,hasAttachments,parentFolderId,isDraft")
UTELATT = ("drafts", "deleteditems", "junkemail", "outbox")


def _tid(m: dict) -> str:
    return m.get("receivedDateTime") or m.get("sentDateTime") or ""


def _filnavn(samtale: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", samtale)[:120] + ".json"


class MailGraph:
    def __init__(self, graph: Graph, katalog: Path) -> None:
        self.graph = graph
        self.katalog = katalog
        self._mapper: dict[str, str] | None = None

    def mapper(self) -> dict[str, str]:
        if self._mapper is None:
            self._mapper = {n: self.graph.kall("GET", f"/me/mailFolders/{n}?$select=id")["id"]
                            for n in UTELATT}
        return self._mapper

    def kladder(self) -> dict[str, Kladd]:
        """Alle kladder. `uniqueBody` er bare svaret, uten den siterte tråden."""
        ut = {}
        for m in self.graph.alle("/me/mailFolders/drafts/messages?$select=id,uniqueBody,webLink&$top=100",
                                 headers={"Prefer": 'outlook.body-content-type="text"'}):
            tekst = kladdtekst((m.get("uniqueBody") or {}).get("content") or "")
            ut[m["id"]] = Kladd(m["id"], m.get("webLink") or "", tekst)
        return ut

    def slett(self, kladd_id: str) -> None:
        try:
            self.graph.kall("DELETE", f"/me/messages/{kladd_id}")
        except GraphFeil as e:
            if "Graph 404" not in str(e):
                raise

    def synk(self, dager: int, nå: datetime | None = None) -> int:
        """Skriver endrede samtaler. Gir antall filer skrevet."""
        nå = nå or datetime.now(timezone.utc)
        fra = (nå - timedelta(days=dager)).strftime("%Y-%m-%dT%H:%M:%SZ")
        mapper = self.mapper()
        utelatt = {mapper[n] for n in UTELATT}
        meldinger = self.graph.alle(
            f"/me/messages?$filter=receivedDateTime ge {fra}&$orderby=receivedDateTime desc"
            f"&$select={FELT}&$top=100".replace(" ", "%20"),
            headers={"Prefer": 'outlook.body-content-type="text"'})
        samtaler: dict[str, list[dict]] = {}
        for m in meldinger:
            if m.get("isDraft") or m.get("parentFolderId") in utelatt or not m.get("conversationId"):
                continue
            samtaler.setdefault(m["conversationId"], []).append(m)
        i_innboks = {m["conversationId"] for m in self.graph.alle(
            "/me/mailFolders/inbox/messages?$select=conversationId&$top=500") if m.get("conversationId")}
        beholdt = {_filnavn(s) for s in i_innboks}
        for sti in self.katalog.glob("*.json"):
            if sti.name not in beholdt:
                sti.unlink()
        skrevet = 0
        for samtale, ms in samtaler.items():
            if samtale not in i_innboks:
                continue
            sti = self.katalog / _filnavn(samtale)
            ms = sorted(ms, key=_tid)
            data = {"conversationId": samtale, "value": ms}
            if sti.exists():
                try:
                    if json.loads(sti.read_text()) == data:
                        continue
                except ValueError:
                    pass
            skriv_atomisk(sti, data)
            skrevet += 1
        return skrevet
