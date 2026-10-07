"""Graph-body → ren tekst."""

from __future__ import annotations

import re
from html.parser import HTMLParser

_BLOKK = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}


class _Tekst(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.deler: list[str] = []
        self._skjul = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "head"):
            self._skjul += 1
        elif tag == "br":
            self.deler.append("\n")
        elif tag in _BLOKK:
            self.deler.append("\n\n")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head"):
            self._skjul = max(0, self._skjul - 1)
        elif tag in _BLOKK:
            self.deler.append("\n\n")

    def handle_data(self, data):
        if not self._skjul:
            self.deler.append(re.sub(r"[ \t\r\n]+", " ", data))


def html_til_tekst(html: str) -> str:
    p = _Tekst()
    p.feed(html)
    p.close()
    tekst = "".join(p.deler)
    tekst = re.sub(r"[ \t]*\n[ \t]*", "\n", tekst)
    tekst = re.sub(r"\n{3,}", "\n\n", tekst)
    return tekst.strip()


def body_til_tekst(body: dict | None) -> str:
    if not body:
        return ""
    innhold = body.get("content") or ""
    if (body.get("contentType") or "text").lower() == "html":
        return html_til_tekst(innhold)
    return innhold.strip()
