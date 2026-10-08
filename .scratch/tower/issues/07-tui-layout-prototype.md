# Hvordan skal tower se ut og oppføre seg?

Type: prototype
Status: closed
Assignee: Sander Hurlen
Blocked by: 03

## Question

Textual-prototype av hovedskjermen: trådliste (kanal, triage, utkaststatus), trådvisning med utkast, tastbindinger for send/rediger/regenerer/avvis/utsett, og hvordan kjørende agenter vises. Hva gjør det "fancy" uten å bli støy?

## Resolution

Prototype: [prototype/tui-layout/](../prototype/tui-layout/) (`./run --fart 3`, `[`/`]` bytter variant). Også på branch `prototype/tui-layout` (f76ce93). Tre varianter over ekte sonnet-data: A split/mailklient, B fokuskø, C tavle etter tilstand.

- **Layout: A, split.** `DataTable` venstre (kanal-ikon, fra, emne, triage, utkaststatus, alder; haster først, info nederst, ferdige dimmet). Høyre: hode med emne + triage-sammendrag + begrunnelse, tråden, så utkastet i ramme. Teams-chat uten topic viser starten av siste melding i stedet for deltakernavn.
- **Agenter: i statuslinja** nederst: spinner + hvilke agenter kjører (`utkast Kari · triage James`), antall i kø, antall utkast klare, kost i dag. Utkaststatus per rad i tabellen (`skriver… / klart vN / feilet / utdatert`).
- **Arbeidsmodus: bla fritt**, ingen kø-/auto-neste-modus.
- **Taster**: `s` send, `e` rediger ($EDITOR via suspend), `r` regenerer med instruks (tom = prøv igjen), `a` avvis (også kvittering av info), `u` utsett (1t / i morgen 08:00 / mandag 08:00), `q` avslutt.
- **Plassholdere `[[…]]` blokkerer sending**: `s` nekter og sier hvor mange som gjenstår. `e` åpner editoren med markøren på første plassholder. Plassholdere uthevet i utkastet.
- **Sjekk = lesbare hint, ingen avkrysning**, vist **over** utkastteksten.
- **Toasts bare ved feil** (send/hent feilet). Alt annet synes i tabell og statuslinje.
- Forkastet: B sin fokuskø og agentlogg, C sin tavle og detaljmodal.
