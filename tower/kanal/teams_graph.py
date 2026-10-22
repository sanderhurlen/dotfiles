"""Ekte Teams: Graph → trådfiler i samme form som mock (`{"chat": chat+members, "value": [chatMessage…]}`).

Bare personlige chatter (1:1 og grupper, ikke møtechatter eller kanaler), med siste Melding de siste `dager`.
Chatlista kommer nyeste først, så sidene leses til første chat som er for gammel. Meldingene (siste 50) hentes
bare når chatten har fått en ny siste melding. Chatter som har blitt for gamle får fila slettet.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tower.graph import Graph
from tower.kanal.graph_fil import skriv_atomisk

TYPER = ("oneOnOne", "group")


def _filnavn(chat_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", chat_id)[:120] + ".json"


def _sti(chat_id: str) -> str:
    return urllib.parse.quote(chat_id, safe="")


class TeamsGraph:
    def __init__(self, graph: Graph, katalog: Path) -> None:
        self.graph = graph
        self.katalog = katalog

    def chatter(self, fra: str) -> list[dict]:
        """Personlige chatter med siste melding etter `fra`, nyeste først."""
        ut, neste = [], ("/me/chats?$expand=lastMessagePreview&$orderby=lastMessagePreview/createdDateTime%20desc"
                         "&$top=50")
        while neste:
            side = self.graph.kall("GET", neste)
            for c in side.get("value", []):
                if ((c.get("lastMessagePreview") or {}).get("createdDateTime") or "") < fra:
                    return ut
                if c.get("chatType") in TYPER:
                    ut.append(c)
            neste = side.get("@odata.nextLink")
        return ut

    def synk(self, dager: int, nå: datetime | None = None) -> int:
        """Skriver chatter med ny siste melding. Gir antall filer skrevet."""
        nå = nå or datetime.now(timezone.utc)
        fra = (nå - timedelta(days=dager)).strftime("%Y-%m-%dT%H:%M:%SZ")
        chatter = self.chatter(fra)
        beholdt = {_filnavn(c["id"]) for c in chatter}
        for sti in self.katalog.glob("*.json"):
            if sti.name not in beholdt:
                sti.unlink()
        skrevet = 0
        for c in chatter:
            sti = self.katalog / _filnavn(c["id"])
            if sti.exists():
                try:
                    if json.loads(sti.read_text())["chat"]["lastMessagePreview"]["id"] == c["lastMessagePreview"]["id"]:
                        continue
                except (ValueError, KeyError, TypeError):
                    pass
            c["members"] = self.graph.alle(f"/chats/{_sti(c['id'])}/members")
            meldinger = self.graph.kall("GET", f"/chats/{_sti(c['id'])}/messages?$top=50"
                                               "&$orderby=createdDateTime%20desc").get("value", [])
            meldinger = [m for m in meldinger if not m.get("deletedDateTime")]
            skriv_atomisk(sti, {"chat": c, "value": sorted(meldinger, key=lambda m: m["createdDateTime"])})
            skrevet += 1
        return skrevet
