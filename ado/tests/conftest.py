# A fake Azure DevOps for the bins: an HTTP server on localhost that answers from
# routes the test sets, and a fake `az` on PATH that hands out a token. Run a bin
# against it with run(); WF_ORG points it at the server. Data is made up.

import http.server
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

AZ = """#!/bin/sh
case "$*" in
  *get-access-token*) echo "tok"; echo "9999999999" ;;
  *"account show"*) echo "me@example.com" ;;
  *) exit 1 ;;
esac
"""


class Ado:
    """routes: {(method, path regex): answer dict or callable(body) -> dict}. Unknown → 404."""

    def __init__(self):
        self.routes, self.seen = {}, []

    def on(self, method, pattern, answer):
        self.routes[(method, re.compile(pattern + r"$"))] = answer

    def answer(self, method, path, body):
        self.seen.append((method, path, body))
        for (m, rx), a in self.routes.items():
            if m == method and rx.search(path.split("?")[0]):
                return 200, a(body) if callable(a) else a
        return 404, {"message": f"no route for {method} {path}"}


@pytest.fixture
def ado():
    fake = Ado()

    class Handler(http.server.BaseHTTPRequestHandler):
        def handle_one(self, method):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n)) if n else None
            code, out = fake.answer(method, self.path, body)
            data = json.dumps(out).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = lambda self: self.handle_one("GET")
        do_POST = lambda self: self.handle_one("POST")
        do_PATCH = lambda self: self.handle_one("PATCH")

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    fake.url = f"http://127.0.0.1:{srv.server_address[1]}/demo"
    yield fake
    srv.shutdown()


@pytest.fixture
def run(ado, tmp_path):
    """run("wi", "ls") → CompletedProcess, the bin talking to the fake ADO, from a dir with no git."""
    (tmp_path / "bin").mkdir()
    az = tmp_path / "bin" / "az"
    az.write_text(AZ)
    az.chmod(0o755)
    env = dict(os.environ, PATH=f"{tmp_path / 'bin'}:{os.environ['PATH']}", WF_ORG=ado.url, WF_PROJECT="Demo",
               WF_TRACKER="ado", WF_ME="me@example.com", WI_TEAM="Demo Team", HOME=str(tmp_path),
               XDG_CACHE_HOME=str(tmp_path / "cache"), GIT_CEILING_DIRECTORIES=str(tmp_path))
    env.pop("CLICOLOR_FORCE", None)

    def go(name, *args):
        return subprocess.run([str(ROOT / "bin" / name), *args], capture_output=True, text=True, env=env,
                              cwd=tmp_path, timeout=60)
    return go


def item(id, title, state="To Do", type="Issue", tags="", assigned="me@example.com", rels=()):
    """A work item the way workitemsbatch returns it."""
    f = {"System.Title": title, "System.State": state, "System.WorkItemType": type, "System.Tags": tags,
         "System.TeamProject": "Demo", "System.CreatedDate": "2026-10-01T08:00:00Z"}
    if assigned:
        f["System.AssignedTo"] = {"uniqueName": assigned, "displayName": assigned.split("@")[0]}
    return {"id": id, "fields": f,
            "relations": [{"rel": r, "url": f"https://x/_apis/wit/workItems/{t}"} for r, t in rels]}
