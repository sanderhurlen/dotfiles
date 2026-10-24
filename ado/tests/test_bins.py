# The bins end to end against the fake ADO in conftest: right requests, readable output,
# and an ADO error that ends the command with ADO's message instead of a traceback.

import pytest

from conftest import item

BINS = ["wf", "wi", "wp", "wr", "fleet", "ops", "chores", "entra"]


@pytest.mark.parametrize("name", BINS)
def test_help(run, name):
    r = run(name, "--help")
    assert r.returncode == 0, r.stderr
    assert "usage" in r.stdout.lower()


@pytest.mark.parametrize("name", ["wf", "wi", "wp", "wr", "fleet", "ops", "chores", "entra"])
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
