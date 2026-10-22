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
    emne_utledet: bool = False  # emne laget av deltakernavn (Teams-chat uten topic)

    @property
    def siste(self) -> Melding:
        return self.meldinger[-1]


def kladdtekst(tekst: str) -> str:
    """Tekst slik den sammenlignes med en Kladd: Outlook endrer linjeskift og blanke på slutten."""
    return "\n".join(l.rstrip() for l in tekst.replace("\r\n", "\n").split("\n")).strip()


@dataclass(frozen=True)
class Kladd:
    """Svar-alle-utkast i Outlook-kladdene: tower lager, erstatter og sletter dem, jeg sender selv."""
    id: str
    lenke: str
    tekst: str  # bare svaret, uten sitert tråd, gjennom `kladdtekst`


class Kanal(Protocol):
    navn: str

    async def hent(self) -> list[Tråd]:
        """Tråder endret siden forrige kall, fullt innhold. Første kall gir alle."""
        ...

    def fjernede(self) -> list[str]:
        """Id-er til Tråder som er borte siden forrige `hent` (f.eks. slettet i Outlook)."""
        ...

    async def svar(self, tråd_id: str, tekst: str) -> None:
        """Sender svar på Tråden. Kaster ved feil."""
        ...


class Arkiv(Protocol):
    """Kanaler med innboks (mail): arkivert er lest og flyttet til Slettede elementer."""

    async def arkiver(self, tråd_id: str) -> None:
        """Tråden ut av innboksen. Kaster ved feil."""
        ...


class Kladder(Protocol):
    """Kanaler med ekte Graph (`config.graph`): svar blir Kladder, aldri sendt herfra."""

    async def lag_kladd(self, tråd_id: str, tekst: str) -> Kladd:
        ...

    async def slett_kladd(self, kladd_id: str) -> None:
        """Borte allerede er ok."""
        ...

    def kladder(self) -> dict[str, Kladd] | None:
        """Kladdene slik de var ved siste synk, eller None når de ikke er hentet på nytt siden forrige kall.

        Hentes før meldingene: en kladd som er borte mens svaret ennå ikke synes, ser slettet ut én synk.
        """
        ...
