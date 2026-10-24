# The Azure DevOps client and its work items, shared by wf, wi, wp, wr, fleet and ops.
#
# Item is tracker-neutral (wf's GitHub tracker makes them too): child/parent/predecessor
# links carry ADO's rel names below.

import os
import re
import subprocess
import time
import urllib.parse

from ado.net import request
from ado.term import die

ADO_RESOURCE = "499b84ac-1321-427f-aa17-267ca6975798"
DONE = {"Done", "Closed", "Removed", "Resolved"}
CHILD = "System.LinkTypes.Hierarchy-Forward"
PARENT = "System.LinkTypes.Hierarchy-Reverse"
PRED = "System.LinkTypes.Dependency-Reverse"
SUCC = "System.LinkTypes.Dependency-Forward"
RELATED = "System.LinkTypes.Related"
HITL_TYPES = {"grilling", "prototype"}
READS = {"wit/wiql", "wit/workitemsbatch"}  # POSTs that change nothing, so retried like a GET


def sh(*cmd, input=None):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True, input=input).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


class Item:
    def __init__(self, id, title, state, done, tags, assignee, description, url,
                 rels, type="", criteria="", project=None, repos=()):
        self.id, self.title, self.state, self.done = id, title, state, done
        self.tags, self.assignee, self.description, self.url = tags, assignee, description, url
        self.rels, self.type, self.criteria, self.project = rels, type, criteria, project
        self.repos = set(repos)

    def links(self, rel):
        return sorted(t for r, t in self.rels if r == rel)

    @property
    def kind(self):
        for t in self.tags:
            if t.startswith("wayfinder:") and t not in ("wayfinder:ticket", "wayfinder:map"):
                return t.split(":", 1)[1]
        return None

    @property
    def is_map(self):
        return "wayfinder:map" in self.tags

    @property
    def is_spec(self):
        return "spec" in self.tags

    @property
    def hitl(self):
        return "hitl" in self.tags or "ready-for-human" in self.tags or self.kind in HITL_TYPES


# Each tracker exposes the same small surface: fetch items (with child/parent/
# predecessor links normalised to the ADO rel names above), list maps, read
# comments, claim a ticket, and say how an agent reads an item itself.


class Ado:
    name = "Azure DevOps"
    noun = "work item"
    doing = "Doing"

    def __init__(self, remote=""):
        org, proj = os.environ.get("WF_ORG"), os.environ.get("WF_PROJECT")
        m = re.search(r"dev\.azure\.com/([^/]+)/([^/]+)/_git/", remote) or \
            re.search(r"@dev\.azure\.com/([^/]+)/([^/]+)/", remote)
        if m and not (org or proj):
            org, proj = m.group(1), urllib.parse.unquote(m.group(2))
        if not (org and proj):
            out = sh("az", "devops", "configure", "-l")
            mo = re.search(r"^organization\s*=\s*(\S+)", out, re.M)
            mp = re.search(r"^project\s*=\s*(.+)$", out, re.M)
            org = org or (mo and mo.group(1))
            proj = proj or (mp and mp.group(1).strip())
        if not org or not proj:
            die("no ADO org/project — set WF_ORG/WF_PROJECT or `az devops configure -d ...`")
        if not org.startswith("http"):
            org = f"https://dev.azure.com/{org}"
        self.org, self.project = org.rstrip("/"), proj
        self.where = f"{self.org}/{self.project}"
        self._token, self._expires = None, 0

    def token(self):
        """az's ADO token, fetched again 5 minutes before it expires (they last about an
        hour), so long-running TUIs keep working. A failed refresh keeps the old token —
        ADO's 401 then says what's wrong instead of the process exiting."""
        if self._token is None or time.time() > self._expires - 300:
            out = sh("az", "account", "get-access-token", "--resource", ADO_RESOURCE,
                     "--query", "[accessToken, expires_on]", "-o", "tsv").split()
            if len(out) == 2:
                self._token, self._expires = out[0], int(out[1])
            elif self._token is None:
                die("no ADO token — run `az login` (or `azt main`)")
            else:
                self._expires = time.time() + 60  # try again in a minute
        return self._token

    def rest(self, path, body=None, method=None, project=None, version=None, ctype="application/json",
             timeout=30, retry=None):
        """One ADO REST call: org-level, or under project (quoted or not). Raises HttpError.
        Reads are retried; so are the POSTs that only read (WIQL, workitemsbatch)."""
        base = f"{self.org}/{urllib.parse.quote(urllib.parse.unquote(project))}" if project else self.org
        url = f"{base}/_apis/{path}"
        version = version or ("7.1-preview.4" if "comments" in path else "7.1")
        url += ("&" if "?" in url else "?") + f"api-version={version}"
        if retry is None:
            retry = method in (None, "GET") and (body is None or path.split("?")[0] in READS)
        return request(url, body, method, {"Authorization": f"Bearer {self.token()}", "Content-Type": ctype},
                       timeout=timeout, retry=retry)

    api = rest

    def item(self, raw):
        f = raw["fields"]
        a = f.get("System.AssignedTo")
        proj = f.get("System.TeamProject", self.project)
        state = f.get("System.State", "")
        return Item(
            id=raw["id"], title=f.get("System.Title", ""), state=state, done=state in DONE,
            tags=[t.strip() for t in (f.get("System.Tags") or "").split(";") if t.strip()],
            assignee=a.get("uniqueName") if isinstance(a, dict) else None,
            description=(f.get("System.Description") or "") + (f.get("Microsoft.VSTS.TCM.ReproSteps") or ""),
            criteria=f.get("Microsoft.VSTS.Common.AcceptanceCriteria") or "",
            url=f"{self.org}/{proj}/_workitems/edit/{raw['id']}",
            type=f.get("System.WorkItemType", ""), project=proj,
            # commit/PR links: vstfs:///Git/Commit/<project>%2f<repo>%2f<sha>
            repos=[urllib.parse.unquote(r["url"]).split("/Git/", 1)[1].split("/")[2]
                   for r in raw.get("relations") or [] if r["url"].startswith("vstfs:///Git/")],
            rels=[(r["rel"], int(r["url"].rsplit("/", 1)[1]))
                  for r in raw.get("relations") or [] if "/workItems/" in r["url"]])

    def fetch(self, ids):
        for n in range(0, len(ids), 200):
            res = self.api("wit/workitemsbatch", {"ids": ids[n:n + 200], "$expand": "relations",
                                                  "errorPolicy": "omit"})
            yield from (self.item(raw) for raw in res["value"] if raw)

    def maps(self, all):
        q = ("SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = @project "
             "AND [System.Tags] CONTAINS 'wayfinder:map'"
             + ("" if all else " AND [System.State] <> 'Done'") + " ORDER BY [System.Id]")
        return [w["id"] for w in self.api("wit/wiql", {"query": q}, project=self.project)["workItems"]]

    def repo_names(self):
        """{repo id: name} for every git repo in the org."""
        return {r["id"]: r["name"] for r in self.api("git/repositories")["value"]}

    def comments(self, item):
        res = self.api(f"wit/workItems/{item.id}/comments?order=asc", project=item.project)
        return [(c.get("createdBy", {}).get("displayName", "?"), c.get("createdDate", ""), c.get("text"))
                for c in res.get("comments", [])]

    def me(self):
        return os.environ.get("WF_ME") or sh("az", "account", "show", "--query", "user.name", "-o", "tsv")

    def claim(self, item, who):
        ops = [{"op": "add", "path": "/fields/System.AssignedTo", "value": who}]
        if item.state not in ("Doing", "Active", "In Progress"):
            ops.append({"op": "add", "path": "/fields/System.State", "value": "Doing"})
        self.api(f"wit/workitems/{item.id}", ops, method="PATCH", ctype="application/json-patch+json")

    def done_state(self, item):
        """The type's Completed-category state: Done, Closed, … depending on the process."""
        path = f"wit/workitemtypes/{urllib.parse.quote(item.type)}/states"
        states = self.api(path, project=urllib.parse.quote(item.project))["value"]
        return next((s["name"] for s in states if s.get("category") == "Completed"), "Done")

    def close(self, item):
        state = self.done_state(item)
        self.api(f"wit/workitems/{item.id}", [{"op": "add", "path": "/fields/System.State", "value": state}],
                 method="PATCH", ctype="application/json-patch+json")
        return state

    def read_hint(self, id):
        return f"`wi show {id}`"
