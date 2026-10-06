#!/usr/bin/env python3
"""Read a mailbox via Microsoft Graph (app-only). Secret fetched from Azure Key Vault via az CLI."""
import argparse, json, os, subprocess, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json")))
TOKEN_CACHE = os.path.join(HERE, ".token.json")
GRAPH = "https://graph.microsoft.com/v1.0"


def secret():
    return subprocess.run(
        ["az", "keyvault", "secret", "show", "--vault-name", CFG["vault"], "--name", CFG["secretName"],
         "--query", "value", "-o", "tsv"],
        check=True, capture_output=True, text=True).stdout.strip()


def token():
    try:
        c = json.load(open(TOKEN_CACHE))
        if c["exp"] > time.time() + 60:
            return c["tok"]
    except Exception:
        pass
    data = urllib.parse.urlencode({
        "client_id": CFG["clientId"], "client_secret": secret(),
        "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"}).encode()
    r = json.load(urllib.request.urlopen(
        f"https://login.microsoftonline.com/{CFG['tenantId']}/oauth2/v2.0/token", data))
    fd = os.open(TOKEN_CACHE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"tok": r["access_token"], "exp": time.time() + r["expires_in"]}, f)
    return r["access_token"]


def get(path, params=None, text_body=False):
    url = f"{GRAPH}/users/{CFG['mailbox']}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    h = {"Authorization": f"Bearer {token()}", "ConsistencyLevel": "eventual"}
    if text_body:
        h["Prefer"] = 'outlook.body-content-type="text"'
    try:
        return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=h)))
    except urllib.error.HTTPError as e:
        sys.exit(f"Graph {e.code}: {e.read().decode()}")


def addr(a):
    e = (a or {}).get("emailAddress", {})
    return f"{e.get('name', '')} <{e.get('address', '')}>"


def cmd_list(a):
    p = {"$top": a.top, "$select": "id,subject,from,receivedDateTime,isRead,hasAttachments,bodyPreview"}
    if a.search:
        p["$search"] = f'"{a.search}"'
    else:
        p["$orderby"] = "receivedDateTime desc"
        filters = []
        if a.unread:
            filters.append("isRead eq false")
        if a.since:
            filters.append(f"receivedDateTime ge {a.since}T00:00:00Z")
        if filters:
            p["$filter"] = " and ".join(filters)
    path = f"/mailFolders/{a.folder}/messages" if a.folder else "/messages"
    for m in get(path, p).get("value", []):
        print(json.dumps({
            "id": m["id"], "date": m["receivedDateTime"], "from": addr(m.get("from")),
            "subject": m.get("subject"), "unread": not m["isRead"], "att": m["hasAttachments"],
            "preview": m.get("bodyPreview", "")[:200]}, ensure_ascii=False))


def cmd_read(a):
    m = get(f"/messages/{a.id}", {"$select": "subject,from,toRecipients,ccRecipients,receivedDateTime,body,hasAttachments"},
            text_body=True)
    print(f"Subject: {m.get('subject')}\nFrom: {addr(m.get('from'))}\n"
          f"To: {', '.join(addr(x) for x in m.get('toRecipients', []))}\n"
          f"Cc: {', '.join(addr(x) for x in m.get('ccRecipients', []))}\nDate: {m['receivedDateTime']}\n")
    print(m["body"]["content"][: a.max])
    if m["hasAttachments"]:
        att = get(f"/messages/{a.id}/attachments", {"$select": "id,name,contentType,size"})
        print("\nAttachments:")
        for x in att.get("value", []):
            print(f"  {x['id']}  {x['name']}  ({x['contentType']}, {x['size']} B)")


def cmd_attachment(a):
    import base64
    x = get(f"/messages/{a.id}/attachments/{a.att}")
    out = os.path.join(a.out, x["name"])
    open(out, "wb").write(base64.b64decode(x["contentBytes"]))
    print(out)


def cmd_folders(a):
    for f in get("/mailFolders", {"$top": 100, "$select": "id,displayName,unreadItemCount,totalItemCount"}).get("value", []):
        print(f"{f['displayName']}: {f['unreadItemCount']} unread / {f['totalItemCount']}  id={f['id']}")


ap = argparse.ArgumentParser()
sp = ap.add_subparsers(required=True)
p = sp.add_parser("list"); p.set_defaults(fn=cmd_list)
p.add_argument("--top", type=int, default=20); p.add_argument("--unread", action="store_true")
p.add_argument("--folder", default="inbox", help="inbox, sentitems, archive, ... or '' for all")
p.add_argument("--search", help="KQL search, e.g. 'from:foo subject:faktura'")
p.add_argument("--since", help="YYYY-MM-DD")
p = sp.add_parser("read"); p.set_defaults(fn=cmd_read); p.add_argument("id"); p.add_argument("--max", type=int, default=20000)
p = sp.add_parser("attachment"); p.set_defaults(fn=cmd_attachment)
p.add_argument("id"); p.add_argument("att"); p.add_argument("--out", default=".")
p = sp.add_parser("folders"); p.set_defaults(fn=cmd_folders)
a = ap.parse_args(); a.fn(a)
