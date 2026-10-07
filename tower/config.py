"""Config fra `<data>/config.json`. Data-roten er `$TOWER_DATA` eller `~/.local/share/tower`."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from tower.kanal import Kanal, Person

STANDARD = {
    "meg": {"navn": "Sander Hurlen", "adresse": "sander@visense.no"},
    "kanaler": ["mail", "teams"],
    "dager": 7,
    "poll_sekunder": 2,
    "modell": "sonnet",
}


def data_rot() -> Path:
    return Path(os.environ.get("TOWER_DATA") or Path.home() / ".local/share/tower").expanduser()


@dataclass(frozen=True)
class Config:
    rot: Path
    meg: Person
    kanaler: tuple[str, ...] = ("mail", "teams")
    dager: int = 7  # Tråder eldre enn dette ved første syn blir `gammel`
    poll_sekunder: float = 2
    modell: str = "sonnet"  # for triage og utkast

    @property
    def db(self) -> Path:
        return self.rot / "tower.db"

    @property
    def outbox(self) -> Path:
        return self.rot / "outbox"

    @property
    def kunnskapsbase(self) -> Path:
        return self.rot / "kunnskapsbase"

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
        dager=int(data["dager"]),
        poll_sekunder=float(data["poll_sekunder"]),
        modell=str(data["modell"]),
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
            kanaler.append(MailKanal(GraphFil(katalog, config.outbox), config.meg))
        elif navn == "teams":
            kanaler.append(TeamsKanal(GraphFil(katalog, config.outbox), config.meg))
        else:
            raise ValueError(f"ukjent kanal i config: {navn}")
    return kanaler
