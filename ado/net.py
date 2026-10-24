# JSON over HTTP, retried when the network or the server stumbles.
#
# Only calls that change nothing are retried: GET, or a POST the caller says is a
# read (WIQL, workitemsbatch). An approval or a new comment sent twice is worse than
# one that failed. Every failure, network ones included, is an HttpError — a
# RuntimeError — so a TUI or watcher that catches RuntimeError survives it.

import http.client
import json
import time
import urllib.error
import urllib.request

TRIES = 3
BACKOFF = (1, 3)  # seconds before the 2nd and 3rd try
TRANSIENT = {429, 500, 502, 503, 504}
MAX_WAIT = 30  # longest Retry-After we honour


class HttpError(RuntimeError):
    """code is the HTTP status, None when the request never got an answer; body is the answer."""

    def __init__(self, message, code=None, body=""):
        super().__init__(message)
        self.code, self.body = code, body


def _message(code, body):
    """The server's own words: ADO's message, Figma's err, OAuth's error_description."""
    try:
        d = json.loads(body)
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    e = d.get("error")
    return (d.get("message") or d.get("err") or d.get("error_description")
            or (e.get("message") if isinstance(e, dict) else e) or None)


def request(url, body=None, method=None, headers=None, timeout=30, retry=None, raw=False, sleep=time.sleep):
    """body: dict/list is sent as JSON, bytes as they are. Returns the parsed JSON (None for
    an empty answer), or the bytes when raw. retry: None = only when the method is GET."""
    data = json.dumps(body).encode() if body is not None and not isinstance(body, bytes) else body
    method = method or ("POST" if data is not None else "GET")
    if retry is None:
        retry = method == "GET"
    tries = TRIES if retry else 1
    for n in range(tries):
        req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
        wait = BACKOFF[min(n, len(BACKOFF) - 1)]
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = r.read()
            if raw:
                return out
            text = out.decode("utf-8-sig")
            return json.loads(text) if text.strip() else None
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8-sig", "replace")
            err = HttpError(_message(e.code, text) or f"HTTP {e.code}", e.code, text)
            if e.code not in TRANSIENT:
                raise err
            after = e.headers.get("Retry-After", "") if e.headers else ""
            if after.isdigit():
                wait = min(int(after), MAX_WAIT)
        except urllib.error.URLError as e:
            err = HttpError(str(e.reason))
        except (OSError, http.client.HTTPException) as e:  # reset mid-read, timeout, RemoteDisconnected
            err = HttpError(str(e) or type(e).__name__)
        if n + 1 < tries:
            sleep(wait)
    raise err
