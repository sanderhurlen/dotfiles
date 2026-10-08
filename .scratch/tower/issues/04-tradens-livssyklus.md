# Hva er livssyklusen til en Tråd og et Utkast?

Type: grilling
Status: closed
Assignee: Sander Hurlen
Blocked by: 01

## Question

Tilstandsmodell for Tråd og Utkast: ny → triagert → utkast klart → (sendt | avvist | utsatt), regenerering, ny melding i tråden som gjør utkastet utdatert, hva utsatt betyr (til når?), og hvor tilstanden lagres (filer vs SQLite i `~/.local/share/tower/`).

## Resolution

To tilstandsmaskiner; Tråd eier status, Utkast sin egen.

**Tråd**
- `ny → triagert → venter på meg | besvart | avvist | utsatt`, pluss `gammel`.
- Triage (svar / info / haster) er et felt, ikke tilstand; kjøres på nytt ved hver ny melding.
- `besvart` utledes: siste melding i tråden er fra meg (likt for outbox og sendt utenfor tower).
- `avvist` = trenger ikke svar fra meg; arkivert til ny melding. Info-tråder ligger i listen uten utkast til de kvitteres med samme handling (ingen auto-arkivering).
- `utsatt` = snooze med faste valg (1t / i morgen 08:00 / mandag 08:00). Ny melding vekker tidlig. Vekket av tid → eksisterende utkast gjenbrukes.
- Første oppstart: bare tråder der siste melding ikke er fra meg og er nyere enn N dager (N=7, config) triageres; eldre blir `gammel` uten kost, kan triageres manuelt.

**Utkast**
- `genererer → klart → sendt | forkastet | utdatert`, pluss `feilet` (feiltekst lagres; ett automatisk nytt forsøk, så manuell regenerer).
- Ny melding i tråden → utkast `utdatert`, automatisk ny triage + nytt utkast.
- Ny melding mens jeg redigerer → overskriv aldri; advarsel med valg: send likevel / se meldingen / regenerer.
- Alle versjoner beholdes med regenereringsinstruks (kurator-input).

**Lagring**
- Tower-tilstand i SQLite `~/.local/share/tower/tower.db` (stdlib `sqlite3`). Kanaldata blir i kanalen (JSON-mock).
- Krav til kanal-sømmen: mock-kanalen skriver outbox **og** legger mitt svar inn i trådfila, så `besvart` kan utledes. Form avgjøres i "Hvordan ser kanal-sømmen ut?".
