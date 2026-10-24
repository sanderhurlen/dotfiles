# standup against the fake ADO: one sprint team, an item done since the last workday, a
# PR waiting for review, one stuck in Doing, one blocked, one without an owner.

import datetime
import re

from conftest import item

PR_LINK = "vstfs:///Git/PullRequestId/proj-id%2frepo-id%2f{}"


def iso(days_ago):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def w(id, title, state, who="kari@example.com", changed=0, sprint=True, preds=(), prs=(), type="Issue"):
    raw = item(id, title, state, type, assigned=who)
    raw["fields"].update({"Microsoft.VSTS.Common.StateChangeDate": iso(changed), "System.CreatedDate": iso(changed),
                          "System.AreaPath": "Demo\\Logit",
                          "System.IterationPath": "Demo\\Sprint 9" if sprint else "Demo"})
    if raw["fields"].get("System.AssignedTo"):
        raw["fields"]["System.AssignedTo"]["displayName"] = "Kari Nordmann"
    raw["relations"] = [{"rel": "System.LinkTypes.Dependency-Reverse", "url": f"https://x/_apis/wit/workItems/{p}"}
                        for p in preds] + [{"rel": "ArtifactLink", "url": PR_LINK.format(p)} for p in prs]
    return raw


def team(ado, items):
    today = datetime.date.today()
    ado.on("GET", r"/_apis/teams", {"value": [{"name": "Team Logit", "projectName": "Demo"}]})
    ado.on("GET", r"/Demo/Team%20Logit/_apis/work/teamsettings/teamfieldvalues",
           {"values": [{"value": "Demo\\Logit", "includeChildren": True}]})
    ado.on("GET", r"/Demo/Team%20Logit/_apis/work/teamsettings/iterations", {"value": [{
        "name": "Sprint 9", "path": "Demo\\Sprint 9",
        "attributes": {"startDate": f"{today - datetime.timedelta(days=7)}T00:00:00Z",
                       "finishDate": f"{today + datetime.timedelta(days=7)}T00:00:00Z"}}]})
    ado.on("POST", r"/Demo/_apis/wit/wiql", {"workItems": [{"id": i["id"]} for i in items]})
    ado.on("POST", r"/_apis/wit/workitemsbatch",
           lambda body: {"value": [i for i in items if i["id"] in body["ids"]]})


def test_sprint_team(ado, run):
    team(ado, [w(1, "Eksport ferdig", "Done", changed=0, prs=[50]),
               w(2, "Gammel Doing", "Doing", changed=10, prs=[51]),
               w(3, "Venter på 2", "To Do", preds=[2]),
               w(4, "Ingen tar meg", "To Do", who=None),
               w(5, "Backlog uten eier", "To Do", who=None, sprint=False, changed=30)])
    ado.on("GET", r"/proj-id/_apis/git/pullrequests/51", {
        "pullRequestId": 51, "title": "Gjør ferdig gammel", "status": "active", "isDraft": False,
        "repository": {"name": "app", "id": "repo-id", "project": {"name": "Demo", "id": "proj-id"}},
        "sourceRefName": "refs/heads/feat/x", "targetRefName": "refs/heads/main", "mergeStatus": "succeeded",
        "createdBy": {"uniqueName": "ola@example.com", "displayName": "Ola Hansen"},
        "creationDate": iso(5), "reviewers": []})
    ado.on("GET", r"/Demo/_apis/policy/evaluations", {"value": []})
    r = run("standup", "logit")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "Team Logit · Sprint 9" in out and "1/4" in out  # done/total in the sprint
    assert "#1" in out and "Eksport ferdig" in out and "!50" in out
    assert "!51" in out and "Ola · klar" in out  # no blocking policy left: ready, whoever reviews
    assert "Gammel Doing" in out and re.search(r"Doing [78] d \(> 2\)", out)  # workdays, not days
    assert "blokkert av #2" in out
    assert "Ingen tar meg" in out and "Backlog uten eier" not in out


def test_quiet_team(ado, run):
    team(ado, [w(1, "Rolig", "To Do")])
    r = run("standup", "logit")
    assert r.returncode == 0, r.stderr
    assert "Ingen unntak" in r.stdout


def test_unknown_team(ado, run):
    team(ado, [])
    r = run("standup", "nope")
    assert r.returncode == 1 and "no team matches" in r.stderr
