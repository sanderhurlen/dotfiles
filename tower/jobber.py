"""launchd-jobbene mine (`chores status`), for J-modalen. Lånt rett fra bin/chores, så fleet og tower viser det samme."""

from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path

_STI = Path(__file__).resolve().parent.parent / "bin" / "chores"


def _chores():
    loader = importlib.machinery.SourceFileLoader("chores", str(_STI))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("chores", loader))
    loader.exec_module(mod)
    return mod


def jobber() -> list[dict]:
    """Jobbene fra `chores status --json`, med `merke` (✓ ⚠ ✗ …) og `linje` («sist i dag 07:12 · neste …»)."""
    c = _chores()
    return [j | {"merke": c.MARK[j["status"]], "linje": c.line(j)} for j in c.status()]


def kjør(label: str) -> None:
    """Kjører jobben nå, slik launchd ville (RuntimeError hvis launchctl sier nei)."""
    _chores().kickstart(label)


def detaljer_argv(navn: str) -> list[str]:
    """`chores status <navn>` i less: hva den gjør, hva som feilet sist og hva jeg kan gjøre."""
    return _chores().pager(navn)


def logg_argv(navn: str, logg: str) -> list[str]:
    return _chores().pager(navn, logg)
