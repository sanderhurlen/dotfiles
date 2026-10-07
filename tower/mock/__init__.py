"""`tower mock`: sonnet dikter opp Tråder fra en fast rollebesetning, koden skriver dem som Graph-JSON.

Agenten svarer i et kompakt schema (person-id-er, tekst, alder); adresser, id-er og Graph-formen lages her,
og hver Tråd valideres gjennom samme Graph→domene-mapping som adapteren før den skrives. Ikke idempotent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import secrets
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tower import config as cfg
from tower.agent import AgentFeil, ClaudeRunner, Runner, med_nytt_forsøk
from tower.kanal import Person, Tråd
from tower.kanal import mail, teams
from tower.kanal.graph_fil import skriv_atomisk
from tower.prompt import tråd_tekst

ROLLEBESETNING = json.loads((Path(__file__).parent / "rollebesetning.json").read_text())
INSTRUKS = (Path(__file__).parent.parent / "instrukser" / "mock.md").read_text()
ADAPTERE = {"mail": mail.tråd_fra_graph, "teams": teams.tråd_fra_graph}


class MockFeil(Exception):
    pass


def personer() -> dict[str, dict]:
    return {p["id"]: p for p in ROLLEBESETNING["personer"]}


def _person(p: dict) -> Person:
    return Person(p["navn"], p["adresse"])


def _bruker_id(adresse: str) -> str:
    return "u-" + adresse.split("@")[0].replace(".", "-")


def _slug(tekst: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", tekst).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:30] or "trad"


def _tid(t: datetime, ms: bool = False) -> str:
    t = t.astimezone(timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z" if ms else t.strftime("%Y-%m-%dT%H:%M:%SZ")


# --- schema ---

def schema_nye(n: int, kanaler: list[str]) -> dict:
    id_er = list(personer())
    melding = {
        "type": "object",
        "properties": {
            "fra": {"type": "string", "enum": id_er},
            "til": {"type": "array", "items": {"type": "string", "enum": id_er}},
            "cc": {"type": "array", "items": {"type": "string", "enum": id_er}},
            "alder_minutter": {"type": "integer", "minimum": 0},
            "viktig": {"type": "boolean"},
            "tekst": {"type": "string"},
        },
        "required": ["fra", "til", "cc", "alder_minutter", "viktig", "tekst"],
        "additionalProperties": False,
    }
    tråd = {
        "type": "object",
        "properties": {
            "kanal": {"type": "string", "enum": kanaler},
            "emne": {"type": "string", "description": "Mail: emnefeltet. Teams: tomt, unntatt gruppechatter med eget navn (f.eks. «Release 4.2»). Aldri deltakernavn."},
            "meldinger": {"type": "array", "items": melding, "minItems": 1, "maxItems": 4},
        },
        "required": ["kanal", "emne", "meldinger"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"trader": {"type": "array", "items": tråd, "minItems": n, "maxItems": n}},
        "required": ["trader"],
        "additionalProperties": False,
    }


def schema_svar(avsendere: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "fra": {"type": "string", "enum": avsendere},
            "viktig": {"type": "boolean"},
            "tekst": {"type": "string"},
        },
        "required": ["fra", "viktig", "tekst"],
        "additionalProperties": False,
    }


# --- Graph-former ---

def _graph_adresse(p: dict) -> dict:
    return {"emailAddress": {"name": p["navn"], "address": p["adresse"]}}


def _mail_melding(samtale: str, emne: str, fra: dict, til: list[dict], cc: list[dict], tid: datetime,
                  viktig: bool, tekst: str, meg: str) -> dict:
    mid = f"AAMkADMock-{secrets.token_hex(6)}"
    return {
        "id": mid,
        "conversationId": samtale,
        "subject": emne,
        "from": _graph_adresse(fra),
        "toRecipients": [_graph_adresse(p) for p in til],
        "ccRecipients": [_graph_adresse(p) for p in cc],
        "replyTo": [],
        "receivedDateTime": _tid(tid),
        "sentDateTime": _tid(tid),
        "body": {"contentType": "text", "content": tekst},
        "bodyPreview": " ".join(tekst.split())[:255],
        "isRead": fra["id"] == meg,
        "importance": "high" if viktig else "normal",
        "hasAttachments": False,
        "webLink": f"https://outlook.office365.com/owa/?ItemID={mid}",
    }


def _teams_melding(chat_id: str, fra: dict, tid: datetime, viktig: bool, tekst: str) -> dict:
    return {
        "id": str(int(tid.timestamp() * 1000)),
        "chatId": chat_id,
        "messageType": "message",
        "createdDateTime": _tid(tid, ms=True),
        "lastModifiedDateTime": _tid(tid, ms=True),
        "deletedDateTime": None,
        "subject": None,
        "from": {"application": None, "device": None,
                 "user": {"id": _bruker_id(fra["adresse"]), "displayName": fra["navn"], "userIdentityType": "aadUser"}},
        "body": {"contentType": "text", "content": tekst},
        "importance": "high" if viktig else "normal",
        "mentions": [],
        "attachments": [],
        "webUrl": None,
    }


def graph_mail(t: dict, nå: datetime, meg: str = "meg") -> tuple[str, dict]:
    """Filnavn og trådfil for en ny mail-Tråd fra agentens kompakte form."""
    ps = personer()
    emne = t["emne"].strip() or "(uten emne)"
    samtale = f"AAQkADMock-{_slug(emne)}-{secrets.token_hex(4)}"
    verdier = []
    for i, m in enumerate(t["meldinger"]):
        til, cc = list(dict.fromkeys(m["til"])), list(dict.fromkeys(m["cc"]))
        if meg not in (m["fra"], *til, *cc):  # det er min innboks: jeg er alltid med
            cc.append(meg)
        tid = nå - timedelta(minutes=m["alder_minutter"])
        verdier.append(_mail_melding(samtale, emne if i == 0 else f"RE: {emne}", ps[m["fra"]],
                                     [ps[p] for p in til if p != m["fra"]], [ps[p] for p in cc if p != m["fra"]],
                                     tid, m["viktig"], m["tekst"], meg))
    return f"{samtale}.json", {"_towerChannel": "mail", "conversationId": samtale, "value": verdier}


def graph_teams(t: dict, nå: datetime, meg: str = "meg") -> tuple[str, dict]:
    """Filnavn og trådfil for en ny Teams-chat fra agentens kompakte form."""
    ps = personer()
    deltakere = list(dict.fromkeys([meg] + [p for m in t["meldinger"] for p in (m["fra"], *m["til"], *m["cc"])]))
    if utenfor := [p for p in deltakere if ps[p].get("bare_mail")]:
        raise MockFeil(f"{', '.join(utenfor)} finnes ikke i Teams")
    if len(deltakere) < 2:
        raise MockFeil("chat uten andre deltakere")
    topic = t["emne"].strip() or None
    hale = secrets.token_hex(4)
    if len(deltakere) == 2 and not topic:
        chat_id = f"19:{_bruker_id(ps[deltakere[1]]['adresse'])}_{_bruker_id(ps[meg]['adresse'])}-{hale}@unq.gbl.spaces"
        type_ = "oneOnOne"
    else:
        chat_id = f"19:mock-{_slug(topic or deltakere[1])}-{hale}@thread.v2"
        type_ = "group"
    tider = [nå - timedelta(minutes=m["alder_minutter"]) for m in t["meldinger"]]
    chat = {
        "id": chat_id,
        "chatType": type_,
        "topic": topic,
        "webUrl": f"https://teams.microsoft.com/l/chat/{chat_id}/0",
        "viewpoint": {"isHidden": False, "lastMessageReadDateTime": _tid(min(tider) - timedelta(minutes=1), ms=True)},
        "members": [{
            "@odata.type": "#microsoft.graph.aadUserConversationMember",
            "id": f"m-{p}",
            "roles": ["owner"],
            "displayName": ps[p]["navn"],
            "userId": _bruker_id(ps[p]["adresse"]),
            "email": ps[p]["adresse"],
        } for p in deltakere],
    }
    verdier = [_teams_melding(chat_id, ps[m["fra"]], tid + timedelta(milliseconds=i), m["viktig"], m["tekst"])
               for i, (m, tid) in enumerate(zip(t["meldinger"], tider))]
    return f"{_slug(topic or ps[deltakere[1]]['navn'])}-{hale}.json", {"_towerChannel": "teams", "chat": chat, "value": verdier}


def valider(kanal: str, data: dict, meg: Person, meldinger: int) -> Tråd:
    """Samme Graph→domene-mapping som adapteren: det den ikke kan lese, skrives ikke."""
    try:
        t = ADAPTERE[kanal](data, meg)
    except (KeyError, TypeError, ValueError) as e:
        raise MockFeil(f"adapteren kan ikke lese tråden: {e!r}") from e
    if t is None or len(t.meldinger) != meldinger:
        raise MockFeil("adapteren fant ikke alle meldingene")
    if any(not m.tekst.strip() for m in t.meldinger):
        raise MockFeil("tom melding")
    return t


# --- eksisterende Tråder ---

def eksisterende(config: cfg.Config) -> list[tuple[Path, dict, Tråd]]:
    ut = []
    for kanal in ADAPTERE:
        katalog = config.rot / kanal
        for sti in sorted(katalog.glob("*.json")) if katalog.is_dir() else []:
            try:
                data = json.loads(sti.read_text())
                t = ADAPTERE[kanal](data, config.meg)
            except (ValueError, KeyError, TypeError):
                continue
            if t:
                ut.append((sti, data, t))
    return ut


def finn(config: cfg.Config, søk: str | None, velg=random.choice) -> tuple[Path, dict, Tråd]:
    """Tråden `søk` peker på (filnavn, Tråd-id eller del av emnet). Uten søk: en tilfeldig som venter på meg."""
    alle = eksisterende(config)
    if not alle:
        raise MockFeil(f"ingen Tråder under {config.rot}")
    if søk is None:
        venter = [x for x in alle if not x[2].siste.fra_meg]
        return velg(venter or alle)
    s = søk.lower()
    treff = [x for x in alle if s in (x[0].stem.lower(), x[2].id.lower())]
    treff = treff or [x for x in alle if s in x[0].stem.lower() or s in x[2].id.lower() or s in x[2].emne.lower()]
    if len(treff) != 1:
        navn = ", ".join(x[0].name for x in treff[:8])
        raise MockFeil(f"«{søk}» treffer {len(treff)} Tråder" + (f": {navn}" if navn else ""))
    return treff[0]


# --- agentkall ---

def _rollebesetning_tekst() -> str:
    return "<rollebesetning>\n" + json.dumps(ROLLEBESETNING, ensure_ascii=False, indent=1) + "\n</rollebesetning>"


async def lag_tråder(runner: Runner, config: cfg.Config, n: int = 5, kanal: str | None = None,
                     nå: datetime | None = None) -> tuple[list[Path], list[str], float]:
    """Skriver n nye Tråder. Gir skrevne filer, avviste Tråder (med årsak) og kost."""
    nå = nå or datetime.now(timezone.utc)
    kanaler = [kanal] if kanal else list(ADAPTERE)
    emner = sorted({t.emne for _, _, t in eksisterende(config)})
    prompt = "\n\n".join([
        _rollebesetning_tekst(),
        f"Lag {n} nye Tråder. Kanal: {' eller '.join(kanaler)}." + (" Bland kanalene." if len(kanaler) > 1 else ""),
        "Emner som finnes fra før:\n" + "\n".join(f"- {e}" for e in emner) if emner else "",
    ]).strip()
    r = await med_nytt_forsøk(runner, INSTRUKS, schema_nye(n, kanaler), prompt)
    skrevne, avvist = [], []
    meg = personer()["meg"]["id"]
    for i, t in enumerate(r.svar["trader"], 1):
        try:
            if t["kanal"] not in kanaler:
                raise MockFeil(f"kanal {t['kanal']} er ikke bedt om")
            navn, data = (graph_mail if t["kanal"] == "mail" else graph_teams)(t, nå, meg)
            valider(t["kanal"], data, config.meg, len(t["meldinger"]))
        except (MockFeil, KeyError) as e:
            avvist.append(f"{i} «{t.get('emne', '')}»: {e}")
            continue
        sti = config.rot / t["kanal"] / navn
        skriv_atomisk(sti, data)
        skrevne.append(sti)
    return skrevne, avvist, r.usd


async def ny_melding(runner: Runner, config: cfg.Config, søk: str | None = None,
                     nå: datetime | None = None, velg=random.choice) -> tuple[Path, Tråd, float]:
    """Legger én ny Melding fra en av de andre deltakerne i en eksisterende Tråd."""
    sti, data, t = finn(config, søk, velg)
    andre = {p.adresse.lower(): p for m in t.meldinger for p in (m.fra, *m.til, *m.cc)
             if p.adresse and p.adresse.lower() != config.meg.adresse.lower()}
    if not andre:
        raise MockFeil(f"{sti.name} har ingen andre deltakere")
    ps = {p["adresse"].lower(): p for p in personer().values()}
    prompt = "\n\n".join([
        _rollebesetning_tekst(),
        "Skriv neste Melding i denne Tråden. `fra` er avsenderens e-postadresse.",
        tråd_tekst(t),
    ])
    r = await med_nytt_forsøk(runner, INSTRUKS, schema_svar(sorted(andre)), prompt)
    s = r.svar
    avsender = andre.get(s["fra"].lower())
    if avsender is None:
        raise MockFeil(f"ukjent avsender {s['fra']}")
    fra = ps.get(avsender.adresse.lower()) or {"id": "", "navn": avsender.navn, "adresse": avsender.adresse}
    tid = max(nå or datetime.now(timezone.utc), t.siste.tid + timedelta(minutes=1))
    if t.kanal == "mail":
        resten = [{"navn": p.navn, "adresse": p.adresse} for a, p in andre.items() if a != avsender.adresse.lower()]
        emne = t.emne if t.emne.upper().startswith("RE:") else f"RE: {t.emne}"
        melding = _mail_melding(data.get("conversationId") or data["value"][0]["conversationId"], emne, fra,
                                [{"navn": config.meg.navn, "adresse": config.meg.adresse}], resten,
                                tid, s["viktig"], s["tekst"], meg="")
    else:
        medlem = next((m for m in data["chat"]["members"] if (m.get("email") or "").lower() == avsender.adresse.lower()), None)
        melding = _teams_melding(data["chat"]["id"], fra, tid, s["viktig"], s["tekst"])
        if medlem:
            melding["from"]["user"]["id"] = medlem.get("userId") or medlem.get("id")
    ny = {**data, "value": [*data["value"], melding]}
    ny_tråd = valider(t.kanal, ny, config.meg, len(t.meldinger) + 1)
    skriv_atomisk(sti, ny)
    return sti, ny_tråd, r.usd


# --- CLI ---

def main(argv: list[str], runner: Runner | None = None, config: cfg.Config | None = None) -> int:
    p = argparse.ArgumentParser(prog="tower mock", description="Lager mock-Tråder med sonnet. Ikke idempotent.")
    p.add_argument("-n", type=int, default=5, help="antall nye Tråder (standard 5)")
    p.add_argument("--kanal", choices=list(ADAPTERE), help="bare denne kanalen (standard begge)")
    p.add_argument("--svar", nargs="?", const="", metavar="TRÅD",
                   help="ny Melding i en eksisterende Tråd (filnavn, id eller del av emnet; tom = tilfeldig som venter på meg)")
    a = p.parse_args(argv)
    if a.n < 1:
        p.error("-n må være minst 1")
    config = config or cfg.last()
    runner = runner or ClaudeRunner(config.modell, config.agent_cwd, timeout=300)
    try:
        if a.svar is not None:
            sti, t, usd = asyncio.run(ny_melding(runner, config, a.svar or None))
            print(f"{t.kanal}: {t.emne} ← {t.siste.fra.navn}  ({sti.name})")
        else:
            skrevne, avvist, usd = asyncio.run(lag_tråder(runner, config, a.n, a.kanal))
            for sti in skrevne:
                print(f"{sti.parent.name}: {sti.name}")
            for grunn in avvist:
                print(f"avvist {grunn}", file=sys.stderr)
            if not skrevne:
                return 1
    except (AgentFeil, MockFeil) as e:
        print(f"tower mock: {e}", file=sys.stderr)
        return 1
    print(f"kost ${usd:.3f}", file=sys.stderr)
    return 0
