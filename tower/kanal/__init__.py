"""Kanal-sømmen: domenetyper og Protocol. Ingen Graph-former krysser denne grensen."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Person:
    navn: str
    adresse: str


@dataclass(frozen=True)
class Melding:
    id: str
    fra: Person
    til: tuple[Person, ...]
    cc: tuple[Person, ...]
    tid: datetime  # tz-aware UTC
    tekst: str
    fra_meg: bool
    haster: bool


@dataclass(frozen=True)
class Tråd:
    id: str  # "<kanal>:<conversationId|chatId>"
    kanal: str
    emne: str
    meldinger: tuple[Melding, ...]  # stigende på tid

    @property
    def siste(self) -> Melding:
        return self.meldinger[-1]


class Kanal(Protocol):
    navn: str

    async def hent(self) -> list[Tråd]:
        """Tråder endret siden forrige kall, fullt innhold. Første kall gir alle."""
        ...

    async def svar(self, tråd_id: str, tekst: str) -> None:
        """Sender svar på Tråden. Kaster ved feil."""
        ...
