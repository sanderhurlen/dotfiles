# Agent-runner og Triage

Type: task
Status: closed
Assignee: Sander Hurlen
Blocked by: 11

## Question

Runner rundt `claude -p` (sonnet, `--json-schema`, prompt på stdin, isolasjon `--setting-sources "" --strict-mcp-config --disable-slash-commands`, ekstern timeout 60 s, drep barn i `finally`; se [Hva gir `claude -p` headless oss for bakgrunnsagenter?](02-claude-headless.md)) med injiserbar falsk runner for tester. Maks 2 samtidige kall; ny Melding midt i kjøring dreper og legger i kø på nytt. Triage med schema `{kategori,haster,sammendrag,begrunnelse}` og instruks fra `prototype/utkast-agent/triage.md` ([Er haiku med klare instrukser god nok til triage og utkast?](06-utkast-agent-prototype.md)); ny triage ved hver ny Melding; bare tråder nyere enn N dager ved første oppstart. Statuslinje: spinner, kjørende agenter, kø, kost i dag. Triage-kolonne og sortering (haster først, info nederst) i tabellen; sammendrag + begrunnelse i detaljhodet.

Felles: testkrav og konvensjoner i [Hvordan deles byggingen av v1 i task-tickets?](09-bygg-slicing.md). Bygg på låste beslutninger i [kartet](../map.md); zoom inn på lenkede tickets. Direkte på master, én commit. AFK.

## Resolution

Bygd i commit `5fea970` på master. 46 tester grønne (`tower/tests/kjør`); manuelt kjørt i tmux med ekte `claude -p` mot mail- + Teams-fixtures: 10 Tråder triagert ($0.070, 2 samtidige), haster øverst og info nederst; to nye Meldinger tett etter hverandre → første kjøring drept, én ny triage (→ haster); `q` midt i kjøring etterlater ingen `claude`-prosess.

Det senere slices bygger på:
- **Runner**: `tower/agent.py`. `Runner`-Protocol `async kjør(instruks, schema, prompt) -> Resultat(svar, usd)`, kaster `AgentFeil(melding, usd)`. `ClaudeRunner(modell, cwd, timeout=60)`: `--system-prompt` (instruksen), isolasjonsflagg, `--max-turns 3`, `--tools ""` sist, prompt på stdin, ren env (uten `CLAUDE_CODE*`), cwd `<data>/agent/`. Slice 16 må utvide `argv` med verktøy/`--add-dir`/budsjett/egen timeout.
- **Kø**: `Agenter(maks, endret)`. `Jobb(nøkkel=(type, tråd-id), etikett, kjør)`; nyeste jobb per nøkkel vinner (kjørende avbrytes, holder plassen til barnet er drept). `avbryt`, `venter`, `ferdig()` (tester), `stopp()` (on_unmount). Uventede unntak → `agenter.feil` i statuslinja. Kurator-køen (slice 7) skal være en egen `Agenter(maks=1)`.
- **Triage**: `tower/triage.py` (`SCHEMA`, `Triage`, `triager(runner, tråd, kunnskapsbase="")` med ett nytt forsøk), instruks i `tower/instrukser/triage.md` (utkast.md hører hjemme der). `tower/prompt.py` `tråd_tekst(tråd, kunnskapsbase)` med adresser (intern/ekstern) — gjenbrukes av Utkast.
- **DB**: `trad` fikk triage-kolonner (auto-migrering av eldre `tower.db`); `Rad.triage` (siste vellykkede, kan gjelde eldre Melding), `trenger_triage`, `triage_feilet`. `lagre_triage`/`lagre_triage_feil` ignoreres hvis Tråden har fått nyere Melding. Status `triagert` etter triage. Tabell `kjoring` logger hvert agentkall (jobb, tråd, usd, feil); `db.kost(nå)` = i dag.
- **App**: `Tower(config, kanaler, db, runner, …)` — runner er påkrevd (tester bruker `conftest.FalskRunner`, med `porter=True` for å holde kall). `planlegg(tråd)` etter hver `registrer`; feilet triage prøves ikke igjen før ny Melding. Sortering: ferdige nederst, så haster/svar/utriagert/info. Config fikk `modell` (standard `sonnet`).
