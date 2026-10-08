# Er haiku med klare instrukser god nok til triage og utkast?

Type: prototype
Status: closed
Assignee: Sander Hurlen
Blocked by: 01, 02

## Question

Prototyp promptene og instruksen for triage og utkast-agenten med `claude -p --model haiku` på noen realistiske mock-tråder (norsk og engelsk, kunde, kollega, ledelse). Er kvaliteten god nok, eller trengs sonnet for utkast? Hva må instruksen inneholde, og hvilket strukturert output skal agenten levere?

## Resolution

Prototype: [prototype/utkast-agent/](../prototype/utkast-agent/) (`report.html`, `run.py`, `triage.md`, `utkast.md`). Også på branch `prototype/utkast-agent` (44777c7). 10 mock-tråder (NO/EN, kunde/kollega/ledelse, 3 info), haiku vs haiku `--effort low` vs sonnet.

- **Modell: sonnet for både triage og utkast** (config-styrt). Haiku sorterte svar/info riktig (10/10), men tenker mye: 8–70 s mot sonnet 3–5 s, og estimert kost er omtrent lik (~$0.005–0.015 per kall). Utkastene fra haiku lover ting på mine vegne og hopper over plassholdere. `--effort low` hjalp ikke.
- **Triage-schema**: `{kategori: svar|info, haster: bool, sammendrag: ≤80 tegn på trådens språk, begrunnelse}`.
- **Utkast-schema**: `{tekst, sjekk: [str]}`. Fakta som mangler blir `[[plassholder]]` i `tekst` og står også i `sjekk`.
- **Instruksen** (se `utkast.md`): samme språk som avsender; finn aldri på fakta og gi aldri tilsagn på mine vegne; plassholder bare for fakta, ikke for formuleringer; **foreslå aldri å ringe**; mail avsluttes alltid med `--\nSander\nVisense` (uansett språk); Teams uten signatur.
- **Intern/ekstern** utledes av domenet: `@visense.no` = intern. Interne tall og vurderinger (budsjett, fremdrift, risiko) skal aldri deles med eksterne. Kunnskapsbasen trenger altså ikke merke fakta som interne eller eksterne. (Teams-mock har bare navn: ekte adapter må hente e-post fra `members`.)
- Input til agenten: utdrag av kunnskapsbasen + tråden som tekst, med prompt på stdin og isolasjonsflaggene fra `claude -p`-researchen.
