# Hva lærer kuratoren, og hvordan er kunnskapsbasen organisert?

Type: grilling
Status: closed
Assignee: Sander Hurlen
Blocked by: 06

## Question

Hva kuratoragenten trekker ut etter en sending (fakta om personer og prosjekter, stil fra diff mellom utkast og sendt svar, research), filstrukturen i kunnskapsbasen, hvordan den unngår duplikater og utdaterte fakta, commit-format i kunnskapsbase-repoet, og hvordan utkast-agenten henter relevante deler uten å lese alt.

Note (fra [Er haiku med klare instrukser god nok til triage og utkast?](06-utkast-agent-prototype.md)): intern/ekstern utledes av `@visense.no`, så kunnskapsbasen trenger ikke merke fakta. Stilregler (signatur, aldri foreslå å ringe) ligger i utkast-instruksen, ikke i kunnskapsbasen.

## Resolution

**Lærer**: fakta om personer, org, prosjekter, tilsagn jeg gir i sendte svar, og stil fra diff utkast→sendt og regenereringsinstrukser. Research fra Utkast-agenten skal også inn, men formen avgjøres i [Hvilke verktøy får Utkast-agenten?](10-agentens-verktoy.md); v1-kuratoren bygges uten.

**Struktur** (`~/.local/share/tower/kunnskapsbase/`, eget git-repo, `git init` automatisk, ingen remote):
- `personer/<slug>.md` (frontmatter `adresser: [...]`, `navn: [...]` inkl. kortformer), `org/<slug>.md` (`domener: [...]`), `prosjekter/<slug>.md` (`org:`, `personer:`), `stil.md`.
- Brødtekst: punktliste, hver faktalinje med dato: `- Levering uke 46 (2026-10-07)`. Nyere faktum erstatter eldre. Ingen kilde-id (git-loggen har den).
- Ny fil bare når det finnes et varig faktum (rolle, org, preferanse, tilsagn). Aldri for automatiske avsendere eller nyhetsbrev.
- `stil.md`: bare lærte, generaliserbare preferanser. Aldri rettelser som gjelder én Tråd, og aldri gjentakelse eller overstyring av faste regler i utkast-instruksen (signatur, ring aldri, intern/ekstern).

**Oppslag for Utkast-agenten** (deterministisk, ingen verktøy): `stil.md` + personer som matcher adresse, deretter eksakt navn + org fra domenet + prosjekter som lenker til disse + prosjekter der slug eller navn nevnes i emne/tekst. Tak ~20 kB.

**Trigger**: Utkast `sendt`, og `besvart` oppdaget fra svar sendt utenfor tower (da uten diff). Ikke ved avvis.

**Input**: Tråden, alle Utkast-versjoner med regenereringsinstrukser, sendt tekst, berørte KB-filer (valgt som ved oppslag) og liste over alle filer med frontmatter (mot duplikater).

**Output**: sonnet, `--json-schema` `{endringer: [{fil, innhold}]}`, hele filer skrevet om. Tom liste er lov. Tower validerer at stien ligger i basen, og skriver.

**Commit**: én per kjøring, `kurator: <emne>`, body med én linje per fil, trailer `Tråd: <tråd-id>`. Ingen commit uten endringer. Mine ucommittede endringer committes først som `manuelt: endringer`. Instruksen: fjern aldri nyere fakta enn eget input uten grunn.

**Kjøring**: én om gangen, kø i SQLite (overlever omstart). Ett nytt forsøk ved feil, deretter vises feilen i statuslinja og jobben ligger i køen som feilet. Sending påvirkes aldri. Kuratoren vises i statuslinja som de andre agentene.

Glossary: la til **Kurator**.
