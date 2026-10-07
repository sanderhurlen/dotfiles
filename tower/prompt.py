"""Tråd som tekst til agentene. Adresser er med fordi `@visense.no` skiller intern fra ekstern."""

from __future__ import annotations

from tower.kanal import Person, Tråd


def person(p: Person) -> str:
    return f"{p.navn} <{p.adresse}>" if p.adresse else p.navn


def tråd_tekst(t: Tråd, kunnskapsbase: str = "") -> str:
    linjer = [f"Kanal: {t.kanal}", f"Emne: {t.emne}", ""]
    for m in t.meldinger:
        hvem = "Sander (meg)" if m.fra_meg else person(m.fra)
        til = f" til {', '.join(map(person, m.til))}" if m.til else ""
        cc = f" cc {', '.join(map(person, m.cc))}" if m.cc else ""
        haster = " [høy viktighet]" if m.haster else ""
        linjer += [f"--- {m.tid.isoformat(timespec='minutes')} fra {hvem}{til}{cc}{haster}", m.tekst, ""]
    kb = f"<kunnskapsbase>\n{kunnskapsbase}\n</kunnskapsbase>\n\n" if kunnskapsbase else ""
    return kb + "<tråd>\n" + "\n".join(linjer) + "</tråd>"
