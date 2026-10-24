import pytest

from ado import tracker
from ado.tracker import CHILD, PARENT, Ado


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("WF_ORG", "Org")
    monkeypatch.setenv("WF_PROJECT", "My Project")
    a = Ado()
    a._token, a._expires = "tok", 9e9
    sent = []
    monkeypatch.setattr(tracker, "request", lambda url, body, method, headers, timeout, retry:
                        sent.append((url, body, method, retry)) or {})
    a.sent = sent
    return a


def test_org_and_project_from_the_environment(client):
    assert client.where == "https://dev.azure.com/Org/My Project"


@pytest.mark.parametrize("project", ["My Project", "My%20Project"])
def test_project_is_quoted_once(client, project):
    client.rest("wit/wiql", {"query": "x"}, project=project)
    assert client.sent[0][0] == "https://dev.azure.com/Org/My%20Project/_apis/wit/wiql?api-version=7.1"


def test_comments_use_the_preview_version(client):
    client.rest("wit/workItems/1/comments?order=asc", project="P")
    assert client.sent[0][0].endswith("comments?order=asc&api-version=7.1-preview.4")


@pytest.mark.parametrize("path,body,method,retry", [
    ("wit/workitems/1", None, None, True),
    ("wit/wiql?$top=5", {"query": "x"}, None, True),
    ("wit/workitemsbatch", {"ids": [1]}, None, True),
    ("wit/workitems/1", [{"op": "add"}], "PATCH", False),
    ("wit/workItems/1/comments", {"text": "hei"}, None, False),
])
def test_only_reads_are_retried(client, path, body, method, retry):
    client.rest(path, body, method)
    assert client.sent[0][3] is retry


def test_item_reads_links_and_repos(client):
    it = client.item({"id": 5, "fields": {"System.Title": "T", "System.State": "Done", "System.Tags": "a; spec",
                                          "System.TeamProject": "P"},
                      "relations": [{"rel": CHILD, "url": "https://x/_apis/wit/workItems/6"},
                                    {"rel": PARENT, "url": "https://x/_apis/wit/workItems/4"},
                                    {"rel": "ArtifactLink", "url": "vstfs:///Git/Commit/p%2frepo-id%2fsha"}]})
    assert (it.done, it.is_spec, it.links(CHILD), it.links(PARENT), it.repos) == (True, True, [6], [4], {"repo-id"})
