"""Rene hjelpere for handlingene: utsettelsestider og $EDITOR med markøren på første plassholder."""

from __future__ import annotations

import os
import shlex
from datetime import datetime, timedelta
from pathlib import Path

from tower.utkast import PLASSHOLDER

UTSETT_VALG = {"1": "1 time", "2": "i morgen 08:00", "3": "mandag 08:00"}


def utsett_til(valg: str, nå: datetime) -> datetime:
    """Tidspunkt for et utsett-valg, regnet i lokal tid. Mandag = neste mandag (om en uke hvis i dag er mandag)."""
    lokal = nå.astimezone()
    if valg == "1":
        return lokal + timedelta(hours=1)
    dager = 1 if valg == "2" else 7 - lokal.weekday()
    dag = lokal.date() + timedelta(days=dager)
    return datetime(dag.year, dag.month, dag.day, 8, tzinfo=lokal.tzinfo)


def første_plassholder(tekst: str) -> tuple[int, int]:
    """(linje, kolonne), 1-basert. Starten av teksten når det ikke finnes noen."""
    m = PLASSHOLDER.search(tekst)
    if not m:
        return 1, 1
    før = tekst[:m.start()]
    return før.count("\n") + 1, m.start() - (før.rfind("\n") + 1) + 1


def editor_argv(sti: Path, linje: int, kol: int, editor: str | None = None) -> list[str]:
    """`$VISUAL`/`$EDITOR` med markøren på (linje, kol) der editoren forstår det."""
    argv = shlex.split(editor or os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi")
    navn = Path(argv[0]).name
    if navn in ("code", "code-insiders", "cursor", "codium"):
        return [*argv, "--goto", f"{sti}:{linje}:{kol}"]
    if navn in ("vi", "vim", "nvim", "mvim"):
        return [*argv, f"+call cursor({linje}, {kol})", str(sti)]
    if navn in ("hx", "helix"):
        return [*argv, f"{sti}:{linje}:{kol}"]
    if navn == "nano":
        return [*argv, f"+{linje},{kol}", str(sti)]
    if navn in ("emacs", "emacsclient", "micro"):
        return [*argv, f"+{linje}:{kol}", str(sti)]
    return [*argv, str(sti)]
