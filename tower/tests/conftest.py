from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tower.config import Config
from tower.kanal import Person

FIXTURES = Path(__file__).parent / "fixtures"
MEG = Person("Sander Hurlen", "sander@visense.no")
# Fixture-tidene er 5.–7. oktober 2026; "nå" er like etter siste Melding.
NÅ = datetime(2026, 10, 7, 11, 0, tzinfo=timezone.utc)


@pytest.fixture
def rot(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURES / "mail", tmp_path / "mail")
    shutil.copytree(FIXTURES / "teams", tmp_path / "teams")
    return tmp_path


@pytest.fixture
def config(rot: Path) -> Config:
    return Config(rot=rot, meg=MEG, kanaler=("mail",), dager=7, poll_sekunder=60)


class FalskRunner:
    """Kannet svar per kall i stedet for `claude -p`. `svar(prompt)` gir dict eller kaster AgentFeil.

    Med `porter=True` blokkerer hvert kall til testen slipper det med `slipp()`.
    """

    def __init__(self, svar=None, porter: bool = False) -> None:
        self.svar = svar or (lambda prompt: {"kategori": "svar", "haster": False, "sammendrag": "s",
                                             "begrunnelse": "b"})
        self.porter = porter
        self.kall: list[str] = []
        self.aktive = 0
        self.maks_aktive = 0
        self.avbrutt = 0
        self._port = None

    def slipp(self) -> None:
        if self._port:
            self._port.set()

    async def kjør(self, instruks, schema, prompt):
        import asyncio

        from tower.agent import Resultat

        self.kall.append(prompt)
        self.aktive += 1
        self.maks_aktive = max(self.maks_aktive, self.aktive)
        try:
            if self.porter:
                self._port = self._port or asyncio.Event()
                await self._port.wait()
            else:
                await asyncio.sleep(0)
            return Resultat(self.svar(prompt), 0.01)
        except asyncio.CancelledError:
            self.avbrutt += 1
            raise
        finally:
            self.aktive -= 1


@pytest.fixture
def runner() -> FalskRunner:
    return FalskRunner()
