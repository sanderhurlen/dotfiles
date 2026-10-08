# Map: tower

Label: wayfinder:map

## Destination

`tower` v1 kjører: Textual-TUI der mockede kanaler (mail, Teams) gir tråder, en billig bakgrunnsagent triagerer og lager utkast, jeg vurderer og sender (til outbox), og en kuratoragent bygger kunnskapsbasen. Kartet bærer også byggingen, ikke bare beslutningene.

## Notes

- Domene: personlig jobbverktøy i dotfiles. Begreper i `GLOSSARY.md` (Kanal, Tråd, Utkast, Kunnskapsbase), bruk dem.
- **Overstyrer "plan, don't do"**: kartet bærer gjennomføring. Når beslutningene er låst, graduerer byggingen til task-tickets her.
- Skills: `grilling` + `domain-modeling` for beslutninger, `prototype` for UI og agent-kvalitet, `research` for API-fakta, `codebase-design` for kanal-sømmen.
- Låste valg fra charting (mer skal ikke til):
  - Stack: Python + Textual, kjørt via `uv run --script` med inline deps
  - Agent: `claude -p` headless (modell: se Decisions; sonnet)
  - Utkast lages automatisk mens tower er åpen (poller kanaler)
  - Mock: JSON-filer per tråd i `mail/` og `teams/` som speiler Graph-felt. Sending skriver til `outbox/`. `tower mock` genererer realistiske tråder med LLM
  - Triage før utkast (trenger svar / info / haster), utkast bare der det trengs svar
  - Kunnskapsbase: markdown-filer per tema, eget git-repo. Kuratoragent skriver automatisk etter sending og lærer også av diff mellom utkast og sendt svar. Starter tom
  - Vurderingshandlinger: send, rediger, regenerer med instruks, avvis, utsett
  - Kode i `tower/` med tynn `bin/tower`. Data i `~/.local/share/tower/`
- Kanal-sømmen er obligatorisk: ekte Graph skal kunne plugges inn senere uten omskriving.

## Decisions so far

- [Hvilke Graph-felt må mock-formatet speile?](issues/01-graph-meldingsform.md): én JSON per Tråd med ordrette Graph-objekter; outbox = eksakt Graph-request; Teams-kanaler ute (admin-consent)
- [Hva gir `claude -p` headless oss for bakgrunnsagenter?](issues/02-claude-headless.md): `--json-schema` gir validert output på abonnement; isoler med `--setting-sources ""` (ikke `--bare`); prompt på stdin, ekstern timeout
- [Hvordan bygger vi en Textual-app kjørt med `uv run --script`?](issues/03-textual-uv.md): `bin/tower` med inline deps legger repo-rot på sys.path; workers + async subprocess (drep barn i `finally`); poll med `set_interval`; uv må inn i Brewfile
- [Hva er livssyklusen til en Tråd og et Utkast?](issues/04-tradens-livssyklus.md): to tilstandsmaskiner; `besvart` utledes av siste avsender; ny melding → auto-regenerer; utsett = snooze; tilstand i SQLite
- [Hvordan ser kanal-sømmen ut?](issues/05-kanal-somm.md): async `hent()`/`svar()` med domenetyper; én adapter per kanal med fil/HTTP-transport inni (mock = Graph fra disk); replyAll, ren tekst, ingen auto-retry
- [Er haiku med klare instrukser god nok til triage og utkast?](issues/06-utkast-agent-prototype.md): sonnet for begge (haiku er tregere og ikke billigere); schema `{kategori,haster,sammendrag,begrunnelse}` / `{tekst,sjekk}` + `[[plassholder]]`; intern = `@visense.no`
- [Hvordan skal tower se ut og oppføre seg?](issues/07-tui-layout-prototype.md): split (tabell + detalj), agenter i statuslinja, bla fritt; plassholdere blokkerer send, sjekk som hint over utkastet, toasts bare ved feil
- [Hva lærer kuratoren, og hvordan er kunnskapsbasen organisert?](issues/08-kurator.md): `personer/`, `org/`, `prosjekter/`, `stil.md` med frontmatter for deterministisk oppslag; datert fakta; sonnet skriver hele filer via schema; kø, én commit per kjøring
- [Hvilke verktøy får Utkast-agenten?](issues/10-agentens-verktoy.md): standard uten verktøy; ved regenerering med instruks Read/Grep/Glob på KB + `~/visense/` med deny-liste for hemmeligheter, ingen web/Bash; `research: [{faktum,kilde}]` → Kurator, vises som Kilder
- [Hvordan deles byggingen av v1 i task-tickets?](issues/09-bygg-slicing.md): 8 AFK-tasks på master, tracer først; pytest + Pilot + falsk runner; maks 2 samtidige agenter, ny Melding dreper kjøring; `tower mock` med fast rollebesetning; KB via `k` → $EDITOR
- [Tracer: mail-mock til tabell](issues/11-tracer.md): bygd (`e76726b`); `bin/tower` + `tower/kanal/` + SQLite-status + split-tabell; tester via `tower/tests/kjør`, data-rot `$TOWER_DATA`
- [Teams-adapter](issues/12-teams-adapter.md): bygd (`0884182`); `TeamsKanal`, meg via `members`-e-post, `Tråd.emne_utledet` → tabellen viser start av siste Melding, `kanaler` standard mail+teams
- [Agent-runner og Triage](issues/13-agent-runner-triage.md): bygd (`5fea970`); `ClaudeRunner` + `Agenter`-kø (nøkkel per Tråd, nyeste vinner), `triager()` med ett nytt forsøk, triage i `trad`, kost i `kjoring`, `FalskRunner` i conftest
- [Utkast-generering og livssyklus](issues/14-utkast.md): bygd (`708c4f2`); `tower/utkast.py` + `utkast`-tabell med alle versjoner, åpne → `utdatert` ved ny Melding; KB-oppslag `tower/kunnskapsbase.py` (`utvalg`/`oppslag`) også til triage; `FalskRunner` velger agent etter schema
- [Handlinger: send, rediger, avvis, utsett](issues/15-handlinger.md): bygd (`41ed063`); `avvist`/`utsatt` + `utsatt_til`/`vekk`; `Utkast.redigert` ved siden av agentens `tekst`; ny Melding under redigering holder igjen auto-utkast (`_hold`) og gir dialog; markøren blir stående
- [`tower mock`](issues/18-tower-mock.md): bygd (`38599ac`); sonnet → kompakt schema fra `tower/mock/rollebesetning.json`, koden skriver Graph-JSON validert via adapteren; `--svar [tråd]`; schema-nøkler må være ASCII

- [Regenerer med instruks og Research](issues/16-regenerer-research.md): bygd (`3e27107`); `r` → instruks-prompt, `Verktøy` på runneren; deny-mønstre må være absolutte (`//**/…`); mislykket regenerering lar forrige klare versjon stå (`Rad.regenerering_feil`)
- [Kurator](issues/17-kurator.md): bygd (`f8dc649`); kø per besvart Melding (send og poll dedupes), egen `Agenter(1)`, bare gyldige KB-stier, forfatter `tower kurator`; feilede jobber prøves igjen ved oppstart

## Not yet specified

_(tomt: veien er kartlagt, resten er task-tickets)_

## Out of scope

- Teams-kanalmeldinger (`ChannelMessage.Read.All` krever admin-consent): bare chats i v1. Se [Hvilke Graph-felt må mock-formatet speile?](issues/01-graph-meldingsform.md).
- Ekte Graph-integrasjon (mail/Teams): mangler tilgang. Bare sømmen er med.
- Bakgrunnsdaemon (launchd), varsler, flere brukere, vedlegg i svar, kalenderinvitasjoner: ute av v1 (valgt ved charting).
- Bla/søk i Kunnskapsbasen inne i TUI-en: v1 åpner den i $EDITOR. Se [Hvordan deles byggingen av v1 i task-tickets?](issues/09-bygg-slicing.md).
