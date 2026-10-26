"""Config fra `<data>/config.json`. Data-roten er `$TOWER_DATA` eller `~/.local/share/tower`."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from tower.agent import Verktøy
from tower.kanal import Kanal, Person

STANDARD = {
    "meg": {"navn": "Sander Hurlen", "adresse": "sander@visense.no"},
    "kanaler": ["mail", "teams"],
    "graph": [],
    "synk_sekunder": 60,
    "dager": {"mail": 7, "teams": 3},
    "poll_sekunder": 2,
    "modell": "sonnet",
    "kilder": ["~/visense"],
}


def data_rot() -> Path:
    return Path(os.environ.get("TOWER_DATA") or Path.home() / ".local/share/tower").expanduser()


@dataclass(frozen=True)
class Config:
    rot: Path
    meg: Person
    kanaler: tuple[str, ...] = ("mail", "teams")
    dager: int | dict[str, int] = 7  # felles eller per kanal: hentes så langt tilbake, eldre ved første syn blir `gammel`
    poll_sekunder: float = 2
    modell: str = "sonnet"  # for triage og utkast
    graph: tuple[str, ...] = ()  # ekte Graph (`tower login`): mail blir kladd i Outlook, Teams kopieres; aldri sendt
    synk_sekunder: float = 60
    kilder: tuple[Path, ...] = ()  # Utkast-agenten kan lese her (og i Kunnskapsbasen) ved regenerering med instruks

    def dager_for(self, kanal: str) -> int:
        return self.dager if isinstance(self.dager, int) else self.dager.get(kanal, 7)

    @property
    def db(self) -> Path:
        return self.rot / "tower.db"

    @property
    def outbox(self) -> Path:
        return self.rot / "outbox"

    @property
    def kunnskapsbase(self) -> Path:
        return self.rot / "kunnskapsbase"

    def verktøy(self) -> Verktøy:
        """Lesetilgang ved regenerering med instruks. Kilder som ikke finnes hoppes over."""
        self.kunnskapsbase.mkdir(parents=True, exist_ok=True)
        return Verktøy((self.kunnskapsbase, *(k for k in self.kilder if k.is_dir())))

    @property
    def agent_cwd(self) -> Path:
        return self.rot / "agent"  # nøytral cwd for `claude -p`


def last(rot: Path | None = None) -> Config:
    rot = rot or data_rot()
    rot.mkdir(parents=True, exist_ok=True)
    sti = rot / "config.json"
    if not sti.exists():
        sti.write_text(json.dumps(STANDARD, ensure_ascii=False, indent=2) + "\n")
    data = {**STANDARD, **json.loads(sti.read_text())}
    return Config(
        rot=rot,
        meg=Person(**data["meg"]),
        kanaler=tuple(data["kanaler"]),
        dager=({k: int(v) for k, v in data["dager"].items()} if isinstance(data["dager"], dict)
               else int(data["dager"])),
        poll_sekunder=float(data["poll_sekunder"]),
        modell=str(data["modell"]),
        graph=tuple(data["graph"]),
        synk_sekunder=float(data["synk_sekunder"]),
        kilder=tuple(Path(k).expanduser() for k in data["kilder"]),
    )


def lag_kanaler(config: Config) -> list[Kanal]:
    from tower.kanal.graph_fil import GraphFil
    from tower.kanal.mail import MailKanal
    from tower.kanal.teams import TeamsKanal

    kanaler: list[Kanal] = []
    for navn in config.kanaler:
        katalog = config.rot / navn
        katalog.mkdir(parents=True, exist_ok=True)
        if navn == "mail":
            graph = None
            if "mail" in config.graph:
                from tower.graph import Graph
                from tower.kanal.mail_graph import MailGraph

                graph = MailGraph(Graph(), katalog)
            kanaler.append(MailKanal(GraphFil(katalog, config.outbox), config.meg, graph, config.dager_for("mail"),
                                     config.synk_sekunder))
        elif navn == "teams":
            graph = None
            if "teams" in config.graph:
                from tower.graph import Graph
                from tower.kanal.teams_graph import TeamsGraph

                graph = TeamsGraph(Graph(), katalog)
            kanaler.append(TeamsKanal(GraphFil(katalog, config.outbox), config.meg, graph, config.dager_for("teams"),
                                      config.synk_sekunder))
        else:
            raise ValueError(f"ukjent kanal i config: {navn}")
    if ukjent := set(config.graph) - {"mail", "teams"}:
        raise ValueError(f"graph støtter bare mail og teams, ikke: {', '.join(sorted(ukjent))}")
    return kanaler
