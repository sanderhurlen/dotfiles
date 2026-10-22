"""Mail-adapter: Graph `message` → domene. Tråd = meldinger med samme `conversationId`."""

from __future__ import annotations

import asyncio
import html
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from tower.kanal import Kladd, Melding, Person, Tråd, kladdtekst
from tower.kanal.graph_fil import GraphFil
from tower.kanal.mail_graph import MailGraph
from tower.kanal.tekst import body_til_tekst

NAVN = "mail"


def graph_tid(s: str) -> datetime:
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _person(r: dict | None) -> Person:
    e = (r or {}).get("emailAddress") or {}
    adresse = e.get("address") or ""
    return Person(navn=e.get("name") or adresse, adresse=adresse)


def _graph_person(p: Person) -> dict:
    return {"emailAddress": {"name": p.navn, "address": p.adresse}}


def melding_fra_graph(m: dict, meg: Person) -> Melding:
    fra = _person(m.get("from"))
    return Melding(
        id=m["id"],
        fra=fra,
        til=tuple(_person(r) for r in m.get("toRecipients") or []),
        cc=tuple(_person(r) for r in m.get("ccRecipients") or []),
        tid=graph_tid(m.get("receivedDateTime") or m["sentDateTime"]),
        tekst=body_til_tekst(m.get("body")) or (m.get("bodyPreview") or ""),
        fra_meg=fra.adresse.lower() == meg.adresse.lower(),
        haster=m.get("importance") == "high",
    )


def tråd_fra_graph(data: dict, meg: Person) -> Tråd | None:
    verdier = data.get("value") or []
    if not verdier:
        return None
    verdier = sorted(verdier, key=lambda m: m.get("receivedDateTime") or m.get("sentDateTime") or "")
    samtale = data.get("conversationId") or verdier[0]["conversationId"]
    return Tråd(
        id=f"{NAVN}:{samtale}",
        kanal=NAVN,
        emne=verdier[0].get("subject") or "(uten emne)",
        meldinger=tuple(melding_fra_graph(m, meg) for m in verdier),
    )


class MailKanal:
    navn = NAVN

    def __init__(self, transport: GraphFil, meg: Person, graph: MailGraph | None = None, dager: int = 7,
                 synk_sekunder: float = 60) -> None:
        self.transport = transport
        self.meg = meg
        self.graph = graph  # None: bare filene (mock)
        self.dager = dager
        self.synk_sekunder = synk_sekunder
        self._neste_synk = 0.0
        self._filer: dict[str, Path] = {}
        self._siste: dict[str, dict] = {}
        self._kladder: dict[str, Kladd] | None = None

    async def hent(self) -> list[Tråd]:
        return await asyncio.to_thread(self._hent)

    def _hent(self) -> list[Tråd]:
        if self.graph and time.monotonic() >= self._neste_synk:
            self._neste_synk = time.monotonic() + self.synk_sekunder
            self._kladder = self.graph.kladder()  # før meldingene, se `Kladder.kladder`
            self.graph.synk(self.dager)
        ut = []
        for sti, data in self.transport.endrede():
            tråd = tråd_fra_graph(data, self.meg)
            if tråd is None:
                continue
            self._filer[tråd.id] = sti
            self._siste[tråd.id] = max(data["value"], key=lambda m: m.get("receivedDateTime") or "")
            ut.append(tråd)
        return ut

    def fjernede(self) -> list[str]:
        borte = set(self.transport.fjernede())
        ids = [id for id, sti in self._filer.items() if sti in borte]
        for id in ids:
            del self._filer[id]
            getattr(self, "_siste", {}).pop(id, None)
        return ids

    def kladder(self) -> dict[str, Kladd] | None:
        kladder, self._kladder = self._kladder, None
        return kladder

    async def lag_kladd(self, tråd_id: str, tekst: str) -> Kladd:
        return await asyncio.to_thread(self._lag_kladd, tråd_id, tekst)

    def _lag_kladd(self, tråd_id: str, tekst: str) -> Kladd:
        if not self.graph:
            raise RuntimeError("kladder krever ekte Graph")
        if tråd_id not in self._filer:
            raise KeyError(f"ukjent Tråd: {tråd_id}")
        # Svar-alle på siste Melding. `comment` tolkes som HTML, så linjeskift må bli <br>.
        m = self.graph.graph.kall("POST", f"/me/messages/{self._siste[tråd_id]['id']}/createReplyAll",
                                  {"comment": html.escape(tekst).replace("\n", "<br>")})
        return Kladd(m["id"], m.get("webLink") or "", kladdtekst(tekst))

    async def slett_kladd(self, kladd_id: str) -> None:
        if not self.graph:
            raise RuntimeError("kladder krever ekte Graph")
        await asyncio.to_thread(self.graph.slett, kladd_id)

    async def arkiver(self, tråd_id: str) -> None:
        await asyncio.to_thread(self._arkiver, tråd_id)

    def _arkiver(self, tråd_id: str) -> None:
        if self.graph:
            self.graph.arkiver(tråd_id.removeprefix(f"{NAVN}:"))
            return
        if tråd_id not in self._filer:
            raise KeyError(f"ukjent Tråd: {tråd_id}")
        # Mock: requestene som én Graph-batch i outbox, og samtalen er borte fra innboksen.
        sti = self._filer[tråd_id]
        requests = []
        for m in json.loads(sti.read_text())["value"]:
            requests += [{"method": "PATCH", "url": f"/me/messages/{m['id']}", "body": {"isRead": True}},
                         {"method": "POST", "url": f"/me/messages/{m['id']}/move",
                          "body": {"destinationId": "deleteditems"}}]
        for i, r in enumerate(requests, 1):
            r["id"] = str(i)
            r["headers"] = {"Content-Type": "application/json"}
        self.transport.skriv_outbox(NAVN, tråd_id, {"method": "POST", "path": "/$batch",
                                                   "body": {"requests": requests}})
        sti.unlink(missing_ok=True)

    async def svar(self, tråd_id: str, tekst: str) -> None:
        await asyncio.to_thread(self._svar, tråd_id, tekst)

    def _svar(self, tråd_id: str, tekst: str) -> None:
        if self.graph:
            raise RuntimeError("ekte mail sendes aldri fra tower, bare som kladd")
        if tråd_id not in self._filer:
            raise KeyError(f"ukjent Tråd: {tråd_id}")
        mål = self._siste[tråd_id]
        self.transport.skriv_outbox(NAVN, tråd_id, {
            "method": "POST",
            "path": f"/me/messages/{mål['id']}/replyAll",
            "body": {"comment": tekst},
        })
        # Mock-siden av Graph: Sendte elementer dukker opp i samme samtale.
        meg = self.meg.adresse.lower()
        avsender = _person(mål.get("from"))
        til = [avsender] if avsender.adresse.lower() != meg else []
        til += [p for p in map(_person, mål.get("toRecipients") or []) if p.adresse.lower() != meg]
        cc = [p for p in map(_person, mål.get("ccRecipients") or []) if p.adresse.lower() != meg]
        nå = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        emne = mål.get("subject") or ""
        self.transport.legg_til(self._filer[tråd_id], "value", {
            "id": f"{mål['id']}-svar-{nå}",
            "conversationId": mål.get("conversationId"),
            "subject": emne if emne.upper().startswith("RE:") else f"RE: {emne}",
            "from": _graph_person(self.meg),
            "toRecipients": [_graph_person(p) for p in til],
            "ccRecipients": [_graph_person(p) for p in cc],
            "replyTo": [],
            "receivedDateTime": nå,
            "sentDateTime": nå,
            "body": {"contentType": "text", "content": tekst},
            "bodyPreview": " ".join(tekst.split())[:255],
            "isRead": True,
            "importance": "normal",
            "hasAttachments": False,
        })
