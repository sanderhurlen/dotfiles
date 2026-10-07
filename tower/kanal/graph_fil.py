"""Fil-transport for mock-kanaler: "Graph fra disk".

Én JSON-fil per Tråd med ordrette Graph-objekter. Sending skriver den eksakte Graph-requesten til outbox.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def skriv_atomisk(sti: Path, data: dict) -> None:
    sti.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=sti.parent, prefix=".", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, sti)


class GraphFil:
    def __init__(self, katalog: Path, outbox: Path) -> None:
        self.katalog = katalog
        self.outbox = outbox
        self._mtimes: dict[Path, int] = {}

    def endrede(self) -> list[tuple[Path, dict]]:
        """Trådfiler endret (mtime) siden forrige kall. Halvskrevne filer prøves igjen neste gang."""
        ut = []
        if not self.katalog.is_dir():
            return ut
        for e in sorted(os.scandir(self.katalog), key=lambda e: e.name):
            if not e.name.endswith(".json") or not e.is_file():
                continue
            sti = Path(e.path)
            mtime = e.stat().st_mtime_ns
            if self._mtimes.get(sti) == mtime:
                continue
            try:
                data = json.loads(sti.read_text())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            self._mtimes[sti] = mtime
            ut.append((sti, data))
        return ut

    def skriv_outbox(self, kanal: str, tråd_id: str, request: dict) -> Path:
        nå = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        trygg = re.sub(r"[^A-Za-z0-9._-]+", "_", tråd_id)
        sti = self.outbox / f"{nå}-{trygg}.json"
        skriv_atomisk(sti, {"_towerChannel": kanal, **request})
        return sti

    def legg_til(self, sti: Path, nøkkel: str, objekt: dict) -> None:
        """Legger et Graph-objekt til i lista `nøkkel` i trådfila."""
        data = json.loads(sti.read_text())
        data.setdefault(nøkkel, []).append(objekt)
        skriv_atomisk(sti, data)
