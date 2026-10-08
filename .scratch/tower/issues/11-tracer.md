# Tracer: mail-mock til tabell

Type: task
Status: closed
Assignee: Sander Hurlen
Blocked by: 

## Question

Første kjørbare tower uten agenter. `brew "uv"` i Brewfile; `bin/tower` (`uv run --script`, inline deps, repo-rot på sys.path, se [Hvordan bygger vi en Textual-app kjørt med `uv run --script`?](03-textual-uv.md)); `tower/kanal/` med `Kanal`-Protocol, domenetyper, `graph_fil`-transport og `mail`-adapter ([Hvordan ser kanal-sømmen ut?](05-kanal-somm.md)); config (identitet, aktive kanaler, N dager); SQLite `tower.db` med Trådstatus (`ny`, `gammel`, `besvart`-utledning, [Hva er livssyklusen til en Tråd og et Utkast?](04-tradens-livssyklus.md)); poll med `set_interval`; split-layout A (tabell + detalj, [Hvordan skal tower se ut og oppføre seg?](07-tui-layout-prototype.md)) og tom statuslinje; `q`. Testdata: håndlagde Graph-JSON-fixtures konvertert fra `prototype/utkast-agent/threads.json`. Etablerer pytest-oppsettet.

Felles: testkrav og konvensjoner i [Hvordan deles byggingen av v1 i task-tickets?](09-bygg-slicing.md). Bygg på låste beslutninger i [kartet](../map.md); zoom inn på lenkede tickets. Direkte på master, én commit. AFK.

## Resolution

Bygd i commit `e76726b` på master. 16 tester grønne (`tower/tests/kjør`); manuelt kjørt i tmux mot fixtures (`TOWER_DATA=<tmp> bin/tower`): tabell + detalj, svar lagt inn i trådfila utenfra → `besvart` og sortert ned ved neste poll, `q` avslutter, status overlever omstart.

Det senere slices bygger på:
- **Kjøring**: `bin/tower` (`uv run -q --script`, textual `>=8,<9`). `brew "uv"` i Brewfile (og installert). Data-rot `$TOWER_DATA` eller `~/.local/share/tower/`; `config.json` lages med standard (`meg`, `kanaler`, `dager`, `poll_sekunder`) ved første start.
- **Tester**: `tower/tests/kjør [pytest-args]` er et eget uv-script med pytest + pytest-asyncio (auto-modus). Hold textual-pinnen lik `bin/tower`. Fixtures i `tower/tests/fixtures/mail/` (7 Tråder fra utkast-prototypen, én HTML-body, én med `importance: high`). `conftest.NÅ` er fast klokke.
- **Søm**: `tower/kanal/__init__.py` (`Kanal`-Protocol med `navn`, `hent`, `svar`; `Tråd`, `Melding`, `Person`), `graph_fil.py` (`GraphFil.endrede/skriv_outbox/legg_til`, atomisk skriving, halvskrevne filer prøves igjen), `tekst.py` (HTML → tekst), `mail.py` (`MailKanal`; `svar` = replyAll på siste Melding + min Melding i trådfila). Ny kanal registreres i `config.lag_kanaler`.
- **Status**: `tower/db.py`, ren `ny_status(forrige, tråd, nå, dager)`; `ny`/`gammel`/`besvart`. Tolkning: `gammel` settes når en Tråd sees første gang og er eldre enn N dager (ikke bare ved aller første oppstart). Ny Melding fra andre → `ny`.
- **App**: `Tower(config, kanaler, db, nå=, poll=False)` for tester; `await app.poll()` er deterministisk poll-krok. Kolonnene Triage/Utkast finnes, Utkast er tom.
