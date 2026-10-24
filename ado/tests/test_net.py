import io
import urllib.error

import pytest

from ado import net
from ado.net import HttpError, request


class Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def http_error(code, body=b"", headers=None):
    return urllib.error.HTTPError("https://x", code, "err", headers or {}, io.BytesIO(body))


@pytest.fixture
def urlopen(monkeypatch):
    """Queue what each urlopen does: bytes are answered, exceptions raised."""
    calls, plan = [], []

    def fake(req, timeout=None):
        calls.append(req.get_method())
        step = plan.pop(0)
        if isinstance(step, BaseException):
            raise step
        return Answer(step)
    monkeypatch.setattr(net.urllib.request, "urlopen", fake)
    fake.calls, fake.plan = calls, plan
    return fake


def test_get_retries_a_connection_reset_and_answers(urlopen):
    urlopen.plan += [ConnectionResetError(54, "Connection reset by peer"), b'{"ok": 1}']
    assert request("https://x", sleep=lambda s: None) == {"ok": 1}
    assert urlopen.calls == ["GET", "GET"]


def test_post_is_sent_once(urlopen):
    urlopen.plan += [ConnectionResetError(54, "reset")]
    with pytest.raises(HttpError) as e:
        request("https://x", {"a": 1}, sleep=lambda s: None)
    assert urlopen.calls == ["POST"] and e.value.code is None


def test_a_read_post_is_retried_when_asked(urlopen):
    urlopen.plan += [http_error(503), b"[]"]
    assert request("https://x", {"q": 1}, retry=True, sleep=lambda s: None) == []


def test_gives_up_after_three_tries(urlopen):
    urlopen.plan += [urllib.error.URLError("down")] * 3
    waits = []
    with pytest.raises(HttpError, match="down"):
        request("https://x", sleep=waits.append)
    assert len(urlopen.calls) == 3 and waits == [1, 3]


def test_a_client_error_is_not_retried_and_says_what_ado_said(urlopen):
    urlopen.plan += [http_error(400, b'{"message": "TF51005: bad field"}')]
    with pytest.raises(HttpError, match="TF51005") as e:
        request("https://x")
    assert e.value.code == 400 and len(urlopen.calls) == 1


def test_retry_after_is_honoured_up_to_a_limit(urlopen):
    urlopen.plan += [http_error(429, headers={"Retry-After": "7"}), http_error(429, headers={"Retry-After": "600"}),
                     b"{}"]
    waits = []
    request("https://x", sleep=waits.append)
    assert waits == [7, net.MAX_WAIT]


def test_answers_with_a_bom_or_nothing(urlopen):
    urlopen.plan += [b'\xef\xbb\xbf{"a": 1}', b""]
    assert request("https://x") == {"a": 1}
    assert request("https://x") is None


def test_error_message_from_figma_and_oauth(urlopen):
    urlopen.plan += [http_error(403, b'{"err": "Invalid token"}'), http_error(401, b'{"error": "x", "error_description": "AADSTS"}')]
    with pytest.raises(HttpError, match="Invalid token"):
        request("https://x")
    with pytest.raises(HttpError, match="AADSTS"):
        request("https://x")
