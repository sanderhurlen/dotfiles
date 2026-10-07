"""Teams-adapter: Graph `chat` + `chatMessage` → domene. Tråd = én chat (1:1 eller gruppe), ikke kanalmeldinger."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from tower.kanal import Melding, Person, Tråd
from tower.kanal.graph_fil import GraphFil
from tower.kanal.mail import graph_tid
from tower.kanal.tekst import body_til_tekst

NAVN = "teams"


def _medlemmer(chat: dict) -> dict[str, Person]:
    """userId → Person. Adressen er e-post fra `members`, så "meg" matches likt som i mail."""
    ut = {}
    for m in chat.get("members") or []:
        bruker = m.get("userId") or m.get("id") or ""
        adresse = m.get("email") or bruker
        ut[bruker] = Person(navn=m.get("displayName") or adresse, adresse=adresse)
    return ut


def _er_meg(p: Person, meg: Person) -> bool:
    return p.adresse.lower() == meg.adresse.lower()


def melding_fra_graph(m: dict, medlemmer: dict[str, Person], meg: Person) -> Melding:
    u = ((m.get("from") or {}).get("user")) or {}
    fra = medlemmer.get(u.get("id") or "") or Person(navn=u.get("displayName") or "?", adresse=u.get("id") or "")
    return Melding(
        id=m["id"],
        fra=fra,
        til=tuple(p for p in medlemmer.values() if p != fra),
        cc=(),
        tid=graph_tid(m["createdDateTime"]),
        tekst=body_til_tekst(m.get("body")),
        fra_meg=_er_meg(fra, meg),
        haster=m.get("importance") in ("high", "urgent"),
    )


def tråd_fra_graph(data: dict, meg: Person) -> Tråd | None:
    chat = data.get("chat") or {}
    # Systemhendelser (medlem lagt til o.l.) har `from: null` og er ikke Meldinger.
    verdier = [m for m in data.get("value") or [] if m.get("messageType", "message") == "message"]
    if not chat.get("id") or not verdier:
        return None
    verdier.sort(key=lambda m: m["createdDateTime"])
    medlemmer = _medlemmer(chat)
    andre = [p.navn for p in medlemmer.values() if not _er_meg(p, meg)]
    topic = (chat.get("topic") or "").strip()
    return Tråd(
        id=f"{NAVN}:{chat['id']}",
        kanal=NAVN,
        emne=topic or ", ".join(andre) or "(chat)",
        meldinger=tuple(melding_fra_graph(m, medlemmer, meg) for m in verdier),
        emne_utledet=not topic,
    )


class TeamsKanal:
    navn = NAVN

    def __init__(self, transport: GraphFil, meg: Person) -> None:
        self.transport = transport
        self.meg = meg
        self._filer: dict[str, Path] = {}
        self._chatter: dict[str, dict] = {}

    async def hent(self) -> list[Tråd]:
        return await asyncio.to_thread(self._hent)

    def _hent(self) -> list[Tråd]:
        ut = []
        for sti, data in self.transport.endrede():
            tråd = tråd_fra_graph(data, self.meg)
            if tråd is None:
                continue
            self._filer[tråd.id] = sti
            self._chatter[tråd.id] = data["chat"]
            ut.append(tråd)
        return ut

    async def svar(self, tråd_id: str, tekst: str) -> None:
        await asyncio.to_thread(self._svar, tråd_id, tekst)

    def _svar(self, tråd_id: str, tekst: str) -> None:
        if tråd_id not in self._filer:
            raise KeyError(f"ukjent Tråd: {tråd_id}")
        chat = self._chatter[tråd_id]
        body = {"contentType": "text", "content": tekst}
        self.transport.skriv_outbox(NAVN, tråd_id, {
            "method": "POST",
            "path": f"/chats/{chat['id']}/messages",
            "body": {"body": body},
        })
        # Mock-siden av Graph: den opprettede chatMessage havner i chatten.
        bruker = next((b for b, p in _medlemmer(chat).items() if _er_meg(p, self.meg)), self.meg.adresse)
        nå = datetime.now(timezone.utc)
        tid = nå.strftime("%Y-%m-%dT%H:%M:%S.") + f"{nå.microsecond // 1000:03d}Z"
        self.transport.legg_til(self._filer[tråd_id], "value", {
            "id": str(int(nå.timestamp() * 1000)),
            "chatId": chat["id"],
            "messageType": "message",
            "createdDateTime": tid,
            "lastModifiedDateTime": tid,
            "from": {"application": None, "device": None,
                     "user": {"id": bruker, "displayName": self.meg.navn, "userIdentityType": "aadUser"}},
            "body": body,
            "importance": "normal",
            "mentions": [],
        })
