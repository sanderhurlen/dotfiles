# Hvordan ser kanal-sømmen ut?

Type: grilling
Status: closed
Assignee: Sander Hurlen
Blocked by: 01, 04

## Question

Grensesnittet mellom tower og en Kanal (list nye tråder, hent tråd, send svar, markér lest?), slik at mock-kanalen og en fremtidig Graph-kanal er utbyttbare. Push eller poll? Hvem eier tilstanden, kanalen eller tower? Bruk `codebase-design`.

## Resolution

Kanalen eier Meldinger, tower eier status (SQLite). Poll.

**Interface** (`Kanal`-Protocol, async):
- `async hent() -> list[Tråd]`: Tråder endret siden forrige kall, fullt innhold. Cursor/deltaToken intern i adapter. Første kall gir alle.
- `async svar(tråd_id, tekst) -> None`: sender, kaster ved feil.
- Ikke med: marker lest, hent enkelttråd, cursor i interfacet. Tower oppdager ny Melding ved å sammenligne siste meldings-id mot SQLite.

**Domenetyper** (frozen dataclasses, ingen Graph over sømmen):
- `Tråd{id, kanal, emne, meldinger}`, id = `"<kanal>:<conversationId|chatId>"`. Teams-emne = `topic` eller deltakernavn.
- `Melding{id, fra: Person, til, cc, tid, tekst, fra_meg, haster}`; `Person{navn, adresse}`.
- Adapter konverterer HTML → ren tekst; `fra_meg` fra én config-identitet. Tower utleder `besvart` fra siste `fra_meg`.

**Adaptere**: én per kanal (`mail`, `teams`), hver med indre transport-søm (fil / HTTP). Mock = "Graph fra disk": samme Graph→domene-mapping som ekte adapter.
- Fil-transport: endring via mtime.
- Mock `svar`: skriver outbox-fil (eksakt Graph-request) **og** legger min Melding (Graph-form) i trådfila.

**Sending**: mail alltid `replyAll`, mottakere ikke redigerbare; svar som `contentType: text`.

**Feil**: `hent` feiler → statuslinje, neste poll prøver igjen. `svar` feiler → Utkast forblir `klart` med feiltekst, aldri auto-retry.

**Plassering**: `tower/kanal/__init__.py` (Protocol + typer), `mail.py`, `teams.py`, `graph_fil.py`. Aktive kanaler fra config; data i `~/.local/share/tower/{mail,teams,outbox}/`.

Glossary: la til **Melding**.
