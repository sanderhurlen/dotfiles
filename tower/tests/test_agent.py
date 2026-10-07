from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from tower.agent import AgentFeil, Agenter, ClaudeRunner, Jobb, ren_env, tolk
from tower.tests.conftest import FalskRunner

SCHEMA = {"type": "object"}

# Falsk `claude`: logger argv, stdin og pid, og oppfører seg etter $FALSK_CLAUDE.
FALSK_CLAUDE = """\
import json, os, sys, time
d = os.environ["FALSK_KATALOG"]
open(os.path.join(d, "argv.json"), "w").write(json.dumps(sys.argv[1:]))
open(os.path.join(d, "pid"), "w").write(str(os.getpid()))
open(os.path.join(d, "stdin"), "w").write(sys.stdin.read())
open(os.path.join(d, "env.json"), "w").write(json.dumps(dict(os.environ)))
modus = os.environ["FALSK_CLAUDE"]
if modus == "ok":
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                      "structured_output": {"kategori": "info"}, "total_cost_usd": 0.004}))
elif modus == "feil":
    print(json.dumps({"type": "result", "subtype": "error_max_structured_output_retries",
                      "is_error": True, "total_cost_usd": 0.002}))
elif modus == "søppel":
    print("Not logged in", file=sys.stderr)
    sys.exit(1)
elif modus == "heng":
    time.sleep(60)
"""


@pytest.fixture
def falsk_claude(tmp_path, monkeypatch) -> Path:
    skript = tmp_path / "claude.py"
    skript.write_text(FALSK_CLAUDE)
    bin_ = tmp_path / "claude"
    bin_.write_text(f"#!/bin/sh\nexec {sys.executable} {skript} \"$@\"\n")
    bin_.chmod(0o755)
    monkeypatch.setenv("FALSK_KATALOG", str(tmp_path))
    return bin_


def runner(falsk_claude: Path, **kw) -> ClaudeRunner:
    return ClaudeRunner("sonnet", falsk_claude.parent / "cwd", claude=str(falsk_claude), **kw)


def lever(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def test_runner_isolert_med_prompt_på_stdin(falsk_claude, monkeypatch):
    monkeypatch.setenv("FALSK_CLAUDE", "ok")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    r = await runner(falsk_claude).kjør("instruks", SCHEMA, "hei tråd")
    assert r.svar == {"kategori": "info"} and r.usd == 0.004

    d = falsk_claude.parent
    argv = json.loads((d / "argv.json").read_text())
    assert (d / "stdin").read_text() == "hei tråd"
    assert "hei tråd" not in argv
    for flagg in ("--setting-sources", "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
        assert flagg in argv
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert argv[argv.index("--system-prompt") + 1] == "instruks"
    assert json.loads(argv[argv.index("--json-schema") + 1]) == SCHEMA
    assert argv[-2:] == ["--tools", ""]
    assert "CLAUDE_CODE_ENTRYPOINT" not in json.loads((d / "env.json").read_text())


async def test_runner_feil_subtype_gir_agentfeil_med_kost(falsk_claude, monkeypatch):
    monkeypatch.setenv("FALSK_CLAUDE", "feil")
    with pytest.raises(AgentFeil, match="error_max_structured_output_retries") as e:
        await runner(falsk_claude).kjør("i", SCHEMA, "p")
    assert e.value.usd == 0.002


def test_api_feil_med_subtype_success_gir_feilteksten():
    ut = json.dumps({"subtype": "success", "is_error": True, "total_cost_usd": 0,
                     "result": "API Error: 400 tools.1.custom.input_schema.properties"}).encode()
    with pytest.raises(AgentFeil, match="API Error: 400"):
        tolk(ut, b"", 0)


async def test_runner_ikke_json_gir_stderr(falsk_claude, monkeypatch):
    monkeypatch.setenv("FALSK_CLAUDE", "søppel")
    with pytest.raises(AgentFeil, match="Not logged in"):
        await runner(falsk_claude).kjør("i", SCHEMA, "p")


async def test_runner_timeout_dreper_barnet(falsk_claude, monkeypatch):
    monkeypatch.setenv("FALSK_CLAUDE", "heng")
    with pytest.raises(AgentFeil, match="timeout"):
        await runner(falsk_claude, timeout=1).kjør("i", SCHEMA, "p")
    assert not lever(int((falsk_claude.parent / "pid").read_text()))


async def test_runner_avbrutt_dreper_barnet(falsk_claude, monkeypatch):
    monkeypatch.setenv("FALSK_CLAUDE", "heng")
    pidfil = falsk_claude.parent / "pid"
    oppgave = asyncio.create_task(runner(falsk_claude).kjør("i", SCHEMA, "p"))
    while not pidfil.exists() or not pidfil.read_text():
        await asyncio.sleep(0.05)
    oppgave.cancel()
    with pytest.raises(asyncio.CancelledError):
        await oppgave
    assert not lever(int(pidfil.read_text()))


def test_ren_env(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SSE_PORT", "1")
    env = ren_env()
    assert "CLAUDECODE" not in env and "CLAUDE_CODE_SSE_PORT" not in env and "PATH" in env


def jobb(r: FalskRunner, id: str, ferdige: list[str]) -> Jobb:
    async def kjør():
        ferdige.append((await r.kjør("i", SCHEMA, id)).svar["id"])
    return Jobb(("triage", id), f"triage {id}", kjør)


async def test_maks_to_samtidige():
    r = FalskRunner(svar=lambda p: {"id": p}, porter=True)
    ferdige: list[str] = []
    a = Agenter(maks=2)
    for id in "abcde":
        a.legg_i_kø(jobb(r, id, ferdige))
    await asyncio.sleep(0.01)
    assert len(a.kjørende) == 2 and len(a.kø) == 3
    r.slipp()
    await a.ferdig()
    assert sorted(ferdige) == list("abcde") and r.maks_aktive == 2


async def test_ny_jobb_med_samme_nøkkel_dreper_den_kjørende():
    r = FalskRunner(svar=lambda p: {"id": p}, porter=True)
    ferdige: list[str] = []
    a = Agenter(maks=2)
    a.legg_i_kø(jobb(r, "a", ferdige))
    await asyncio.sleep(0.01)
    første = a.kjørende[("triage", "a")][1]
    a.legg_i_kø(jobb(r, "a", ferdige))
    assert ("triage", "a") in a.kø  # venter til den gamle er drept
    await asyncio.sleep(0.01)
    assert første.cancelled() and r.avbrutt == 1
    assert r.maks_aktive == 1
    r.slipp()
    await a.ferdig()
    assert ferdige == ["a"] and len(r.kall) == 2


async def test_avbryt_fjerner_køet_og_kjørende():
    r = FalskRunner(svar=lambda p: {"id": p}, porter=True)
    ferdige: list[str] = []
    a = Agenter(maks=1)
    a.legg_i_kø(jobb(r, "a", ferdige))
    a.legg_i_kø(jobb(r, "b", ferdige))
    await asyncio.sleep(0.01)
    a.avbryt(("triage", "b"))
    a.avbryt(("triage", "a"))
    await a.ferdig()
    assert ferdige == [] and r.avbrutt == 1 and len(r.kall) == 1


async def test_uventet_unntak_i_jobb_vises():
    async def kræsj():
        raise RuntimeError("bug")
    a = Agenter()
    a.legg_i_kø(Jobb(("triage", "x"), "triage X", kræsj))
    await a.ferdig()
    assert "triage X" in a.feil and "bug" in a.feil
