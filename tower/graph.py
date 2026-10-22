"""Microsoft Graph som deg (delegert), via app-registreringen `sander-cli`.

Config (aldri i repoet) i `~/.config/sander-cli/config.json`: {"tenantId": "…", "clientId": "…"}.
`tower login` logger inn i nettleseren (PKCE); refresh-tokenet ligger i `token.json` ved siden av (0600).
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = "offline_access User.Read Mail.ReadWrite"  # aldri Mail.Send: tower lager bare utkast


# Sperre uansett hva tokenet tillater: ingen kall som sender mail.
SENDER = re.compile(r"/(send|sendMail|reply|replyAll|forward)/?(\?|$)", re.IGNORECASE)


class GraphFeil(Exception):
    pass


def katalog() -> Path:
    return Path(os.environ.get("SANDER_CLI") or Path.home() / ".config/sander-cli").expanduser()


def _post_form(url: str, data: dict) -> dict:
    try:
        with urllib.request.urlopen(url, urllib.parse.urlencode(data).encode(), timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}") | {"_status": e.code}


class Graph:
    def __init__(self, rot: Path | None = None) -> None:
        self.rot = rot or katalog()
        sti = self.rot / "config.json"
        if not sti.exists():
            raise GraphFeil(f"mangler {sti} med tenantId og clientId")
        cfg = json.loads(sti.read_text())
        self.tenant, self.klient = cfg["tenantId"], cfg["clientId"]
        self._token: dict | None = None

    @property
    def _token_sti(self) -> Path:
        return self.rot / "token.json"

    def _endepunkt(self, navn: str) -> str:
        return f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0/{navn}"

    def _lagre(self, svar: dict) -> None:
        if "access_token" not in svar:
            raise GraphFeil(svar.get("error_description") or svar.get("error") or "ingen access_token i svaret")
        self._token = {"access_token": svar["access_token"], "refresh_token": svar["refresh_token"],
                       "utløper": time.time() + int(svar["expires_in"])}
        fd = os.open(self._token_sti, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(self._token, f)

    def login(self, skriv=print) -> None:
        """Nettleser + PKCE mot http://localhost:<port> (device code stoppes av Conditional Access)."""
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(16)
        fikk: dict[str, str] = {}

        class Svar(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
                if "code" not in q and "error" not in q:
                    self.send_response(404)
                    self.end_headers()
                    return
                fikk.update(q)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write("tower: ferdig, du kan lukke fanen.".encode())

            def log_message(self, *a):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Svar)
        redirect = f"http://localhost:{server.server_port}"
        url = self._endepunkt("authorize") + "?" + urllib.parse.urlencode({
            "client_id": self.klient, "response_type": "code", "redirect_uri": redirect, "scope": SCOPES,
            "code_challenge": challenge, "code_challenge_method": "S256", "state": state})
        skriv(f"Åpner nettleseren. Hvis ikke, gå til:\n{url}")
        webbrowser.open(url)
        server.timeout, slutt = 5, time.time() + 300
        while not fikk and time.time() < slutt:
            server.handle_request()
        server.server_close()
        if "error" in fikk:
            raise GraphFeil(fikk.get("error_description") or fikk["error"])
        if fikk.get("state") != state or "code" not in fikk:
            raise GraphFeil("innloggingen ble ikke fullført")
        self._lagre(_post_form(self._endepunkt("token"), {
            "grant_type": "authorization_code", "client_id": self.klient, "scope": SCOPES,
            "code": fikk["code"], "redirect_uri": redirect, "code_verifier": verifier}))

    def token(self) -> str:
        if self._token is None:
            if not self._token_sti.exists():
                raise GraphFeil("ikke logget inn, kjør `tower login`")
            self._token = json.loads(self._token_sti.read_text())
        if self._token["utløper"] > time.time() + 120:
            return self._token["access_token"]
        svar = _post_form(self._endepunkt("token"), {
            "grant_type": "refresh_token", "client_id": self.klient, "scope": SCOPES,
            "refresh_token": self._token["refresh_token"]})
        if "access_token" not in svar:
            raise GraphFeil(f"refresh feilet, kjør `tower login`: {svar.get('error_description') or svar}")
        self._lagre(svar)
        return self._token["access_token"]

    def kall(self, method: str, path: str, body: dict | None = None, headers: dict | None = None) -> dict:
        """`path` er relativ til v1.0 (`/me/…`) eller en full `@odata.nextLink`."""
        url = path if path.startswith("https://") else GRAPH + path
        if SENDER.search(urllib.parse.urlsplit(url).path):
            raise GraphFeil(f"tower sender aldri mail: {path}")
        h = {"Authorization": f"Bearer {self.token()}", **(headers or {})}
        data = None
        if body is not None:
            data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data, h, method=method), timeout=60) as r:
                innhold = r.read()
        except urllib.error.HTTPError as e:
            try:
                feil = json.loads(e.read())["error"]["message"]
            except (ValueError, KeyError, TypeError):
                feil = e.reason
            raise GraphFeil(f"Graph {e.code}: {feil}") from None
        except urllib.error.URLError as e:
            raise GraphFeil(f"Graph utilgjengelig: {e.reason}") from None
        return json.loads(innhold) if innhold else {}

    def alle(self, path: str, headers: dict | None = None) -> list[dict]:
        ut, neste = [], path
        while neste:
            side = self.kall("GET", neste, headers=headers)
            ut += side.get("value", [])
            neste = side.get("@odata.nextLink")
        return ut
