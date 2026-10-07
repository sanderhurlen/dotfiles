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
