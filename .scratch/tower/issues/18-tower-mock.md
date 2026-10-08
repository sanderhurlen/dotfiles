# `tower mock`

Type: task
Status: closed
Assignee: Sander Hurlen
Blocked by: 11

## Question

`tower mock [-n 5] [--kanal mail|teams]`: sonnet (via runner fra 13 hvis den finnes, ellers enkel `claude -p`) lager nye Tråder som Graph-JSON fra fast rollebesetning i `tower/mock/` (personer, org, prosjekter; NO/EN; kunde/kollega/ledelse/info). `--svar [tråd]` legger en ny Melding i en eksisterende Tråd for å teste utdatering. Ikke idempotent. Validerer output mot samme Graph→domene-mapping som adapteren.

Felles: testkrav og konvensjoner i [Hvordan deles byggingen av v1 i task-tickets?](09-bygg-slicing.md). Bygg på låste beslutninger i [kartet](../map.md); zoom inn på lenkede tickets. Direkte på master, én commit. AFK.

## Resolution

Bygd i commit `38599ac` på master (rebaset etter Handlinger). 94 tester grønne; manuelt kjørt mot ekte sonnet: `-n 3` (12 s, $0.03), `--kanal teams -n 2`, `--svar` uten/med søk; tower plukket opp, triagerte og lagde utkast; `--svar` på åpent utkast → `↻ utdatert` + ny triage.

- **Form**: agenten svarer i kompakt schema (person-id fra `tower/mock/rollebesetning.json`, til/cc, `alder_minutter`, `viktig`, tekst); `tower/mock/__init__.py` lager adresser, id-er og ordrett Graph-JSON og validerer hver Tråd via adapterens `tråd_fra_graph`. Ugyldige Tråder avvises enkeltvis (stderr), resten skrives. Personer med `bare_mail` (nyhetsbrev) avvises i Teams.
- **Rollebesetning**: 15 personer (meg, kolleger, ledelse, kunder i Nordlys/Fjellbygg/Harbor, info-avsendere), 4 org, 4 prosjekter; samme navn som test-fixturene. Instruks i `tower/instrukser/mock.md`. Eksisterende emner sendes med for å unngå gjentak.
- **`--svar [TRÅD]`**: søk på filnavn, Tråd-id eller emne (tvetydig/ukjent → feil med treff); tom = tilfeldig Tråd som venter på meg. Avsender begrenset til trådens andre deltakere (schema-enum på adresse).
- **Funn**: API avviser schema-nøkler med ikke-ASCII (`tråder` → `trader`). Slike API-feil kom som `subtype: success` + `is_error`; `agent.tolk` viser nå feilteksten.
- Runner: `ClaudeRunner` med timeout 300 s, `med_nytt_forsøk`.
