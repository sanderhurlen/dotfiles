# The bins end to end against the fake ADO in conftest: right requests, readable output,
# and an ADO error that ends the command with ADO's message instead of a traceback.

import pytest

from conftest import item

BINS = ["wf", "wi", "wp", "wr", "fleet", "ops", "chores", "entra", "standup"]


@pytest.mark.parametrize("name", BINS)
def test_help(run, name):
    r = run(name, "--help")
    assert r.returncode == 0, r.stderr
    assert "usage" in r.stdout.lower()


@pytest.mark.parametrize("name", BINS)
def test_loads_as_a_module(name):
    from ado import load
    assert load(name).main


def items(ado, *its):
    ado.on("POST", r"/Demo/_apis/wit/wiql", {"workItems": [{"id": i["id"]} for i in its]})
    ado.on("POST", r"/_apis/wit/workitemsbatch",
           lambda body: {"value": [i for i in its if i["id"] in body["ids"]]})


def test_wi_ls(ado, run):
    items(ado, item(11, "Fiks innlogging", "Doing", "Bug"), item(12, "Ny rapport"))
    r = run("wi", "ls")
    assert r.returncode == 0, r.stderr
    assert "Fiks innlogging" in r.stdout and "Ny rapport" in r.stdout
    assert r.stdout.index("Ny rapport") < r.stdout.index("Fiks innlogging")  # To Do before Doing


def test_wi_tree(ado, run):
    items(ado, item(1, "Kart", tags="wayfinder:map", rels=[("System.LinkTypes.Hierarchy-Forward", 2),
                                                          ("System.LinkTypes.Hierarchy-Forward", 3)]),
          item(2, "Barn", "Doing", "Task"), item(3, "Ferdig barn", "Done", "Task"))
    r = run("wi", "tree", "1")
    assert r.returncode == 0, r.stderr
    assert "Kart" in r.stdout and "Barn" in r.stdout
    assert "Ferdig barn" not in r.stdout  # done children only with -a


def test_wf_show(ado, run):
    items(ado, item(7, "Et kart", tags="wayfinder:map"))
    ado.on("GET", r"/Demo/_apis/wit/workItems/7/comments", {"comments": [
        {"createdBy": {"displayName": "Kari"}, "createdDate": "2026-10-02T08:00:00Z", "text": "<p>ser bra ut</p>"}]})
    r = run("wf", "show", "7")
    assert r.returncode == 0, r.stderr
    assert "Et kart" in r.stdout and "ser bra ut" in r.stdout


def test_ado_error_ends_with_its_message(ado, run):
    r = run("wf", "show", "7")  # no routes: every call is a 404 with a message
    assert r.returncode == 1
    assert "no route for POST" in r.stderr and "Traceback" not in r.stderr


def test_wr_ls(ado, run):
    ado.on("GET", r"/_apis/connectionData", {"authenticatedUser": {"id": "me-id", "properties": {}}})
    ado.on("GET", r"/Demo/_apis/git/pullrequests", {"value": [{
        "pullRequestId": 41, "title": "Legg til eksport", "status": "active", "isDraft": False,
        "repository": {"name": "app", "id": "r1", "project": {"name": "Demo", "id": "p1"}},
        "sourceRefName": "refs/heads/feat/eksport", "targetRefName": "refs/heads/main",
        "createdBy": {"uniqueName": "kari@example.com", "id": "k"}, "creationDate": "2026-10-20T08:00:00Z",
        "mergeStatus": "succeeded", "reviewers": []}]})
    r = run("wr", "ls", "-A")
    assert r.returncode == 0, r.stderr
    assert "!41" in r.stdout and "Legg til eksport" in r.stdout


def test_wp_ls(ado, run):
    ado.on("GET", r"/Demo/_apis/build/builds", {"value": [{
        "id": 900, "buildNumber": "20261024.1", "definition": {"name": "app-ci"}, "status": "completed",
        "result": "failed", "sourceBranch": "refs/heads/main", "sourceVersion": "abc",
        "requestedFor": {"uniqueName": "kari@example.com"}, "queueTime": "2026-10-24T08:00:00Z",
        "startTime": "2026-10-24T08:00:10Z", "finishTime": "2026-10-24T08:05:10Z",
        "repository": {"name": "app"}}]})
    ado.on("GET", r"/Demo/_apis/pipelines/approvals", {"value": []})
    ado.on("GET", r"/Demo/_apis/build/builds/900/timeline", {"records": []})
    r = run("wp", "ls", "-A")
    assert r.returncode == 0, r.stderr
    assert "app-ci" in r.stdout and "20261024.1" not in r.stderr


def test_completions_are_up_to_date():
    import subprocess
    from conftest import ROOT
    r = subprocess.run([str(ROOT / "script" / "completions"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_wi_new(ado, run):
    ado.on("POST", r"/Demo/_apis/wit/workitems/\$Bug", {"id": 50})
    ado.on("POST", r"/Demo/_apis/wit/workItems/50/comments", {})
    r = run("wi", "new", "Knapp", "virker", "ikke", "-t", "Bug", "-p", "8", "-g", "needs-triage",
            "-d", "Steg:\n\n- trykk\n- ingenting skjer", "-c", "fra support")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("✓ #50 Bug") and "_workitems/edit/50" in r.stdout
    ops = {o["path"]: o["value"] for o in next(b for m, p, b in ado.seen if "$Bug" in p)}
    assert ops["/fields/System.Title"] == "Knapp virker ikke"
    assert ops["/fields/System.Tags"] == "needs-triage"
    assert ops["/fields/System.Description"] == "<p>Steg:</p><ul><li>trykk</li><li>ingenting skjer</li></ul>"
    assert ops["/relations/-"]["rel"] == "System.LinkTypes.Hierarchy-Reverse"
    assert ops["/relations/-"]["url"].endswith("/workItems/8")
    assert any("comments" in p and b == {"text": "<p>fra support</p>"} for m, p, b in ado.seen)


def test_wi_set_keeps_tags_and_replaces_parent(ado, run):
    raw = item(5, "Sak", "Doing", tags="a; needs-triage", rels=[("System.LinkTypes.Related", 9),
                                                                ("System.LinkTypes.Hierarchy-Reverse", 3)])
    raw["rev"] = 7
    ado.on("GET", r"/_apis/wit/workitems/5", raw)
    items(ado, raw)
    ado.on("GET", r"/Demo/_apis/wit/workitemtypes/Issue/states",
           {"value": [{"name": "To Do", "category": "Proposed"}, {"name": "Done", "category": "Completed"}]})
    ado.on("PATCH", r"/_apis/wit/workitems/5", {"id": 5})
    r = run("wi", "set", "5", "-s", "done", "-g", "ready-for-agent", "-G", "needs-triage", "-p", "4", "-b", "6")
    assert r.returncode == 0, r.stderr
    ops = next(b for m, p, b in ado.seen if m == "PATCH")
    assert ops[0] == {"op": "test", "path": "/rev", "value": 7}
    vals = {o["path"]: o.get("value") for o in ops}
    assert vals["/fields/System.State"] == "Done"
    assert vals["/fields/System.Tags"] == "a; ready-for-agent"
    assert {"op": "remove", "path": "/relations/1"} in ops  # the old parent, not the related link
    assert [o["value"]["rel"] for o in ops if o["path"] == "/relations/-"] == [
        "System.LinkTypes.Hierarchy-Reverse", "System.LinkTypes.Dependency-Reverse"]
    assert "+ready-for-agent" in r.stdout and "-needs-triage" in r.stdout


def test_wi_set_needs_something(ado, run):
    ado.on("GET", r"/_apis/wit/workitems/5", dict(item(5, "Sak"), rev=1))
    r = run("wi", "set", "5")
    assert r.returncode == 1 and "ingenting å endre" in r.stderr
    assert not any(m == "PATCH" for m, p, b in ado.seen)


def pr(id=41):
    return {"pullRequestId": id, "title": "Legg til eksport", "status": "active", "isDraft": False,
            "repository": {"name": "app", "id": "r1", "project": {"name": "Demo", "id": "p1"}},
            "sourceRefName": "refs/heads/feat/eksport", "targetRefName": "refs/heads/main",
            "createdBy": {"uniqueName": "kari@example.com", "id": "k"}, "creationDate": "2026-10-20T08:00:00Z"}


def test_wr_post(ado, run, tmp_path):
    import json
    run("wr", "draft", "41", "--path")  # the path is under HOME, which run() sets to tmp_path
    d = tmp_path / ".local/state/wr/review/41.json"
    d.parent.mkdir(parents=True)
    d.write_text(json.dumps({"summary": "ok", "vote": "suggestions", "questions": [],
                             "comments": [{"file": "src/a.cs", "line": 12, "text": "Navnet lyver"},
                                          {"text": "Fint ellers"}]}))
    ado.on("GET", r"/_apis/git/pullrequests/41", pr())
    ado.on("GET", r"/_apis/connectionData", {"authenticatedUser": {"id": "me-id", "properties": {}}})
    ado.on("POST", r"/Demo/_apis/git/repositories/r1/pullRequests/41/threads", {"id": 1})
    ado.on("PUT", r"/Demo/_apis/git/repositories/r1/pullRequests/41/reviewers/me-id", {"vote": 5})
    r = run("wr", "post", "41")
    assert r.returncode == 0, r.stderr
    assert "approve med forslag · 2 kommentarer (1 i koden)" in r.stdout
    threads = [b for m, p, b in ado.seen if p.split("?")[0].endswith("/threads")]
    assert threads[0]["threadContext"]["filePath"] == "/src/a.cs"
    assert threads[0]["threadContext"]["rightFileStart"] == {"line": 12, "offset": 1}
    assert "threadContext" not in threads[1]
    assert [b for m, p, b in ado.seen if m == "PUT"] == [{"vote": 5}]
    assert json.loads(d.read_text())["posted"]
    again = run("wr", "post", "41")
    assert again.returncode == 1 and "--again" in again.stderr


def test_wr_post_refuses_a_bad_draft(ado, run, tmp_path):
    d = tmp_path / ".local/state/wr/review/41.json"
    d.parent.mkdir(parents=True)
    d.write_text('{"vote": "lgtm", "comments": []}')
    r = run("wr", "post", "41")
    assert r.returncode == 1 and "ukjent vote" in r.stderr
    assert not ado.seen


def test_wr_draft_vote_and_skip(run, tmp_path):
    import json
    d = tmp_path / ".local/state/wr/review/41.json"
    d.parent.mkdir(parents=True)
    d.write_text(json.dumps({"vote": "suggestions", "comments": [{"text": "a"}, {"text": "b"}]}))
    assert run("wr", "draft", "41", "--vote", "wait").stdout.startswith("vent på forfatter")
    assert "1 av 2 kommentarer" in run("wr", "draft", "41", "--skip", "2").stdout
    assert json.loads(d.read_text())["comments"][1]["skip"] is True
    assert run("wr", "draft", "41", "--skip", "3").returncode == 1


def test_wr_post_skips_replies_resolves_and_logs(ado, run, tmp_path):
    import json
    d = tmp_path / ".local/state/wr/review/41.json"
    d.parent.mkdir(parents=True)
    d.write_text(json.dumps({"vote": "approve", "comments": [{"text": "med"}, {"text": "uten", "skip": True}],
                             "replies": [{"thread": 7, "text": "holder ikke"}], "resolve": [8]}))
    ado.on("GET", r"/_apis/git/pullrequests/41", dict(pr(), lastMergeSourceCommit={"commitId": "abc123"}))
    ado.on("GET", r"/_apis/connectionData", {"authenticatedUser": {"id": "me-id", "properties": {}}})
    ado.on("POST", r"/Demo/_apis/git/repositories/r1/pullRequests/41/threads", {"id": 9})
    ado.on("POST", r"/Demo/_apis/git/repositories/r1/pullRequests/41/threads/7/comments", {"id": 2})
    ado.on("PATCH", r"/Demo/_apis/git/repositories/r1/pullRequests/41/threads/8", {"id": 8})
    ado.on("PUT", r"/Demo/_apis/git/repositories/r1/pullRequests/41/reviewers/me-id", {"vote": 10})
    r = run("wr", "post", "41")
    assert r.returncode == 0, r.stderr
    new = [b for m, p, b in ado.seen if m == "POST" and p.split("?")[0].endswith("/threads")]
    assert [t["comments"][0]["content"] for t in new] == ["med"]
    assert any(p.split("?")[0].endswith("/threads/7/comments") and b["content"] == "holder ikke" for m, p, b in ado.seen)
    assert [b for m, p, b in ado.seen if m == "PATCH"] == [{"status": 2}]
    log = json.loads((d.parent / "41.log.jsonl").read_text())
    assert log["commit"] == "abc123" and log["threads"] == [9] and log["resolved"] == [8]


def test_fleet_rereview_after_a_push(tmp_path, monkeypatch):
    import json
    from ado import load
    fleet, wr = load("fleet"), load("wr")
    monkeypatch.setattr(wr, "DRAFTS", str(tmp_path))
    raw = dict(pr(), lastMergeSourceCommit={"commitId": "new456"},
               reviewers=[{"id": "me-id", "vote": -5}])
    monkeypatch.setattr(fleet.wr, "A", lambda: type("A", (), {"org": "https://x", "project": "Demo"})())
    r = fleet.Review(raw, "me-id")
    assert fleet.pushed_since(r) is None  # never posted
    (tmp_path / "41.log.jsonl").write_text(json.dumps({"commit": "old123"}) + "\n")
    assert fleet.pushed_since(r) == ("old123", "new456")
    pilot = fleet.Pilot.__new__(fleet.Pilot)
    pilot.c = {"triggers": ["review", "rereview"]}
    why, fp, _ = pilot.trigger(r)
    assert why == fleet.REREVIEW and fp == "fleet-pr-41@re-new456"
    auto = fleet.Auto(r, why)
    monkeypatch.setattr(fleet.Auto, "clone", lambda self: "/repo")
    assert fleet.agent_name(auto) == "fleet-pr-41-rereview"
    assert "git diff old123..origin/feat/eksport" in auto.prompt


def test_fleet_groups_reviews_by_shared_item_and_author(monkeypatch, tmp_path):
    from ado import load
    fleet = load("fleet")
    monkeypatch.setattr(fleet.wr, "A", lambda: type("A", (), {"org": "https://x", "project": "Demo"})())
    monkeypatch.setattr(fleet.wf, "fetch", lambda ids: None)
    monkeypatch.setattr(fleet.wf, "get", lambda i: type("I", (), {"id": i, "title": f"item {i}",
                                                                   "url": f"https://x/{i}", "project": "Demo"})())

    def review(id, items, who="kari@example.com", repo="app"):
        raw = dict(pr(id), createdBy={"uniqueName": who, "id": who},
                   repository={"name": repo, "id": repo, "project": {"name": "Demo", "id": "p1"}},
                   reviewers=[{"id": "me-id", "vote": 0}])
        r = fleet.Review(raw, "me-id")
        r.items = set(items)
        return r

    epic, core, bff, other, alone = (review(1, {100, 9249}, repo="core"), review(2, {100, 9249}, repo="bff"),
                                     review(3, {100}, repo="web"), review(4, {9249}, who="ola@example.com"),
                                     review(5, {77}))
    gs = fleet.groups([epic, core, bff, other, alone])
    assert [(g.id, [r.id for r in g.prs]) for g in gs] == [(9249, [1, 2])]  # the feature, not the shared epic
    assert bff.group is None and other.group is None and alone.group is None  # left over, other author, alone
    g = gs[0]
    monkeypatch.setattr(fleet, "HOME", str(tmp_path))
    monkeypatch.setattr(fleet, "clones", lambda: {("demo", "core"): "/src/core"})
    auto = fleet.Auto(g)
    assert fleet.agent_name(auto) == "fleet-wi-9249-review"
    cwd, wt = auto.where()
    assert wt is None and cwd.endswith(".claude/worktrees/fleet-wi-9249-review")
    assert '"id": 1' in (tmp_path / ".claude/worktrees/fleet-wi-9249-review/.fleet.json").read_text()
    text = auto.prompt
    assert "worktree add --detach /src/core/.claude/worktrees/fleet-wi-9249-review" in text
    assert "!2 bff" in text and "ingen lokal klone" in text and "wr draft <pr> --format" in text
    pilot = fleet.Pilot.__new__(fleet.Pilot)
    pilot.c = {"triggers": ["review", "rereview"]}
    assert pilot.trigger(g)[1] == "fleet-wi-9249@review-1-2"
