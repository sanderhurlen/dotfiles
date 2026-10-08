# Regenerer med instruks og Research

Type: task
Status: closed
Assignee: Sander Hurlen
Blocked by: 15

## Question

`r` regenerer med instruks (tom = prøv igjen), instruks lagres med versjonen. Med instruks: `Read,Grep,Glob` med `--add-dir` på kunnskapsbasen og `~/visense/` (config), deny-liste via `--settings`, `--max-turns 12`, timeout 120 s, `--max-budget-usd 0.25`; tak treffes → `feilet` med årsak, forrige versjon står. Schema får `research: [{faktum,kilde}]`, sti validert under tillatte kataloger, lagret med versjonen; «Kilder» under sjekk-hintet. Se [Hvilke verktøy får Utkast-agenten?](10-agentens-verktoy.md).

Felles: testkrav og konvensjoner i [Hvordan deles byggingen av v1 i task-tickets?](09-bygg-slicing.md). Bygg på låste beslutninger i [kartet](../map.md); zoom inn på lenkede tickets. Direkte på master, én commit. AFK.

Fra [Handlinger: send, rediger, avvis, utsett](15-handlinger.md): `r` fjerner `Tower._hold`; dialogvalget «regenerer» i `NyMeldingValg` bør åpne samme instruks-prompt.

## Resolution

Bygd i commit `3e27107` på master (rebaset på `tower mock`; 107 tester grønne etter rebase). 95 tester grønne; manuelt kjørt i tmux med ekte sonnet mot fixtures + falsk kildekatalog (plan.md + `.env`-lokkedue) og ekte `~/visense`: Nordlys-utkastet regenerert med instruks fant uke 46 og ventende testbruker, «Kilder» med to gyldige stier, intern budsjett-% ikke lekket (~23 s, $0.051); instruks om å lese `.env` → avslått, 0 treff på nøkkelen i DB; `q` etterlater ingen `claude`-prosess.

- **Målt før koding**: deny-regler i `--settings` gjelder også med `--setting-sources ""`, men **relative mønstre (`**/.env*`) gjelder bare under cwd** og blokkerte ingenting. Alle mønstre er nå absolutte (`Read(//**/.env*)`). Lesing utenfor `--add-dir` nektes uansett. Budsjett-tak gir `subtype: error_max_budget_usd`.
- **Runner**: `Verktøy(kataloger, maks_runder=12, timeout=120, maks_usd=0.25)` som valgfri `verktøy=` til `Runner.kjør`; `agent.DENY` er listen. `tolk` gjør `error_max_turns`/`error_max_budget_usd` til «tak: …». Med verktøy ingen nye forsøk.
- **Config**: `kilder` (standard `["~/visense"]`), `Config.verktøy()` = Kunnskapsbasen (opprettes) + kilder som finnes.
- **Utkast**: `skriv_utkast(runner, t, kb, instruks, forrige, verktøy) -> Skrevet(tekst, sjekk, usd, research, forkastet)`. Prompt får `<kataloger>`, `<forrige_utkast>` (forrige versjons `gjeldende`, altså min redigering) og `<instruks>`. Tilleggsinstruks i `instrukser/utkast-verktøy.md`. `Research(faktum, kilde)`; `kilde()` løser symlenker/`..`, krever fil under en tillatt katalog, og normaliserer til sti relativt til katalogens forelder (`visense/repo/fil:12`, `kunnskapsbase/personer/x.md`). Ugyldige forkastes og telles i `sjekk`.
- **DB**: kolonne `research` (JSON). `lagre_utkast(..., research)` forkaster eldre åpne versjoner. `Rad.utkast` er nå den **synlige** versjonen (`db.synlig`): feilet siste versjon med klar forrige for samme Melding → forrige vises, `Rad.regenerering_feil` har årsaken (toast + linje i rammen, ikke statuslinja). `Db.utkast()` er fortsatt siste versjon. Kjøringer logges som jobb `regenerer`.
- **App**: `r` → `InstruksPrompt` (escape avbryter) → `regenerer()` lager ny `genererer`-versjon med instruks og lar `planlegg` køe den; `kjør_utkast` bruker verktøy når versjonen har instruks (også etter omstart). Nektes for ferdige Tråder, uten utkast, og mens agenten skriver. `NyMeldingValg` «r» åpner samme prompt.

For [Kurator](17-kurator.md): Research ligger på hver versjon (`Db.versjoner(t)[i].research`), også forkastede; kilder er allerede validert.
