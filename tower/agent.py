"""Bakgrunnsagenter: runner rundt `claude -p` og kø med tak på samtidige kall.

Runneren er sømmen tester bytter ut: alt som har `async kjør(instruks, schema, prompt) -> Resultat` duger.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# Isolasjon uten --bare (krever API-nøkkel): ingen settings, MCP, skills eller prosjekt-CLAUDE.md.
ISOLASJON = ["--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands",
             "--permission-prompts", "none", "--no-session-persistence"]


@dataclass(frozen=True)
class Resultat:
    svar: dict
    usd: float


class AgentFeil(Exception):
    def __init__(self, melding: str, usd: float = 0.0) -> None:
        super().__init__(melding)
        self.usd = usd


class Runner(Protocol):
    async def kjør(self, instruks: str, schema: dict, prompt: str) -> Resultat: ...


def ren_env() -> dict[str, str]:
    """Miljøet uten Claude Code-variabler, så en tower startet fra en Claude-økt ikke smitter agenten."""
    return {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_CODE", "CLAUDECODE"))}


class ClaudeRunner:
    def __init__(self, modell: str, cwd: Path, timeout: float = 60, claude: str = "claude") -> None:
        self.modell = modell
        self.cwd = cwd  # nøytral katalog: ingen CLAUDE.md, .mcp.json eller hooks
        self.timeout = timeout
        self.claude = claude

    def argv(self, instruks: str, schema: dict) -> list[str]:
        # Prompten går på stdin: --tools er variadisk og ville slukt et posisjonelt argument.
        return [self.claude, "-p", "--model", self.modell, "--output-format", "json",
                "--json-schema", json.dumps(schema), "--system-prompt", instruks,
                *ISOLASJON, "--max-turns", "3", "--tools", ""]

    async def kjør(self, instruks: str, schema: dict, prompt: str) -> Resultat:
        self.cwd.mkdir(parents=True, exist_ok=True)
        p = await asyncio.create_subprocess_exec(
            *self.argv(instruks, schema), cwd=self.cwd, env=ren_env(),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            try:
                ut, feil = await asyncio.wait_for(p.communicate(prompt.encode()), self.timeout)
            except TimeoutError:
                raise AgentFeil(f"timeout etter {self.timeout:g} s") from None
        finally:
            if p.returncode is None:  # timeout eller avbrutt: barnet skal aldri overleve kallet
                p.kill()
                await p.wait()
        return tolk(ut, feil, p.returncode)


def tolk(ut: bytes, feil: bytes, kode: int | None) -> Resultat:
    try:
        r = json.loads(ut)
    except ValueError:
        tekst = (feil or ut).decode(errors="replace").strip()
        raise AgentFeil(tekst[-300:] or f"claude avsluttet med {kode}") from None
    usd = float(r.get("total_cost_usd") or 0)
    if r.get("subtype") != "success" or r.get("is_error") or r.get("structured_output") is None:
        raise AgentFeil(str(r.get("subtype") or r.get("result") or "ukjent feil")[:300], usd)
    return Resultat(r["structured_output"], usd)


@dataclass(eq=False)
class Jobb:
    nøkkel: tuple[str, str]  # (type, tråd-id); nyeste jobb per nøkkel vinner
    etikett: str  # "triage James" i statuslinja
    kjør: Callable[[], Awaitable[None]] = field(repr=False)


class Agenter:
    """Kø av agentjobber med maks `maks` samtidige. `endret` kalles når kø eller kjørende endres."""

    def __init__(self, maks: int = 2, endret: Callable[[], None] = lambda: None) -> None:
        self.maks = maks
        self.endret = endret
        self.kø: dict[tuple[str, str], Jobb] = {}
        self.kjørende: dict[tuple[str, str], tuple[Jobb, asyncio.Task]] = {}
        self.feil: str | None = None  # siste uventede unntak fra en jobb
        self._tom = asyncio.Event()
        self._tom.set()

    def legg_i_kø(self, jobb: Jobb) -> None:
        """Køer jobben. Kjører allerede en jobb med samme nøkkel, drepes den og denne tar over."""
        self.kø.pop(jobb.nøkkel, None)
        self.kø[jobb.nøkkel] = jobb
        if jobb.nøkkel in self.kjørende:
            self.kjørende[jobb.nøkkel][1].cancel()
        self._tom.clear()
        self._pump()

    def avbryt(self, nøkkel: tuple[str, str]) -> None:
        self.kø.pop(nøkkel, None)
        if nøkkel in self.kjørende:
            self.kjørende[nøkkel][1].cancel()
        self._pump()

    def venter(self, nøkkel: tuple[str, str]) -> bool:
        return nøkkel in self.kø or nøkkel in self.kjørende

    def _pump(self) -> None:
        # En avbrutt jobb holder plassen sin til barneprosessen er drept; samme nøkkel starter ikke dobbelt.
        for nøkkel in list(self.kø):
            if len(self.kjørende) >= self.maks:
                break
            if nøkkel in self.kjørende:
                continue
            jobb = self.kø.pop(nøkkel)
            task = asyncio.get_running_loop().create_task(jobb.kjør())
            self.kjørende[nøkkel] = (jobb, task)
            task.add_done_callback(lambda t, n=nøkkel, j=jobb: self._ferdig(n, j, t))
        if not self.kø and not self.kjørende:
            self._tom.set()
        self.endret()

    def _ferdig(self, nøkkel: tuple[str, str], jobb: Jobb, task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception():  # jobber håndterer egne feil; dette er bugs
            self.feil = f"{jobb.etikett}: {task.exception()!r}"
        if nøkkel in self.kjørende and self.kjørende[nøkkel][0] is jobb:
            del self.kjørende[nøkkel]
        self._pump()

    async def ferdig(self) -> None:
        """Venter til kø og kjørende er tomme."""
        await self._tom.wait()

    async def stopp(self) -> None:
        self.kø.clear()
        tasks = [t for _, t in self.kjørende.values()]
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
