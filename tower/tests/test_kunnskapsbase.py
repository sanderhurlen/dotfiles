from __future__ import annotations

from pathlib import Path

from tower.kanal import Melding, Person, Tråd
from tower.kunnskapsbase import frontmatter, oppslag, utvalg
from tower.tests.conftest import MEG, NÅ

KARI = Person("Kari Nordby", "kari.nordby@nordlys-energi.no")
OLA = Person("Ola Berg", "ola@visense.no")


def tråd(fra: Person, tekst: str = "Hei", emne: str = "Status", cc=()) -> Tråd:
    return Tråd("mail:x", "mail", emne, (Melding("m0", fra, (MEG,), tuple(cc), NÅ, tekst, False, False),))


def skriv(rot: Path, sti: str, tekst: str) -> None:
    (rot / sti).parent.mkdir(parents=True, exist_ok=True)
    (rot / sti).write_text(tekst)


def test_frontmatter():
    assert frontmatter("---\nnavn: [Kari Nordby, \"Kari\"]\nadresser:\n  - a@b.no\n  - c@d.no\norg: nordlys\n---\n- x") == {
        "navn": ["Kari Nordby", "Kari"], "adresser": ["a@b.no", "c@d.no"], "org": "nordlys"}
    assert frontmatter("# ingen") == {}


def test_tom_eller_manglende_base(tmp_path):
    assert oppslag(tmp_path / "finnes-ikke", tråd(KARI), MEG) == ""
    assert oppslag(tmp_path, tråd(KARI), MEG) == ""


def test_utvalg_i_prioritert_rekkefølge(tmp_path):
    skriv(tmp_path, "stil.md", "- Kort og direkte (2026-10-01)")
    skriv(tmp_path, "personer/kari-nordby.md", "---\nadresser: [Kari.Nordby@nordlys-energi.no]\nnavn: [Kari Nordby]\n---\n- Prosjektleder")
    skriv(tmp_path, "personer/ola-berg.md", "---\nadresser: [ola.gammel@visense.no]\nnavn: [Ola Berg, Ola]\n---\n- Utvikler")
    skriv(tmp_path, "personer/sander.md", "---\nadresser: [sander@visense.no]\n---\n- meg")
    skriv(tmp_path, "personer/per.md", "---\nadresser: [per@fjellbygg.no]\n---\n- uvedkommende")
    skriv(tmp_path, "org/nordlys-energi.md", "---\ndomener: [nordlys-energi.no]\n---\n- Kunde")
    skriv(tmp_path, "prosjekter/erp.md", "---\norg: nordlys-energi\n---\n- Levering uke 46")
    skriv(tmp_path, "prosjekter/intern-ola.md", "---\npersoner: [ola-berg]\n---\n- x")
    skriv(tmp_path, "prosjekter/harbor-api.md", "---\nnavn: [Harbor v2]\n---\n- /v2")
    skriv(tmp_path, "prosjekter/bryggen.md", "---\n---\n- nevnes ikke")

    t = tråd(KARI, "Hvordan går det med harbor api? Og Harbor v2?", cc=(OLA,))
    assert [str(p.relative_to(tmp_path)) for p in utvalg(tmp_path, t, MEG)] == [
        "stil.md", "personer/kari-nordby.md", "personer/ola-berg.md", "org/nordlys-energi.md",
        "prosjekter/erp.md", "prosjekter/intern-ola.md", "prosjekter/harbor-api.md"]
    tekst = oppslag(tmp_path, t, MEG)
    assert tekst.startswith("## stil.md\n- Kort og direkte") and "## prosjekter/erp.md\n---\norg" in tekst


def test_prosjekt_nevnt_krever_helt_ord(tmp_path):
    skriv(tmp_path, "prosjekter/erp.md", "- x")
    assert utvalg(tmp_path, tråd(KARI, "Status på ERP-integrasjonen"), MEG)
    assert not utvalg(tmp_path, tråd(KARI, "superpslag"), MEG)


def test_tak_hopper_over_filer_som_ikke_får_plass(tmp_path):
    skriv(tmp_path, "stil.md", "s" * 50)
    skriv(tmp_path, "personer/kari.md", "---\nadresser: [kari.nordby@nordlys-energi.no]\n---\n" + "k" * 500)
    skriv(tmp_path, "org/nordlys.md", "---\ndomener: [nordlys-energi.no]\n---\n- kort")
    tekst = oppslag(tmp_path, tråd(KARI), MEG, tak=200)
    assert "## stil.md" in tekst and "## org/nordlys.md" in tekst and "kkk" not in tekst
