# Hvilke verktøy får Utkast-agenten?

Type: grilling
Status: closed
Assignee: Sander Hurlen
Blocked by:

## Question

Hva får Utkast-agenten lov til utover kunnskapsbase-utdraget den får i prompten (websøk, ADO, repoer, mail-skill, Read/Grep på kunnskapsbasen)? Hva koster det i latens og kost mot sonnet ~4 s / ~$0.01, og hvordan isoleres det (`--allowedTools`, `--setting-sources ""`)? Og hvordan flyter research den gjør videre til Kuratoren: felt i utkast-schemaet, egen logg, eller noe annet?

Note (fra [Hva lærer kuratoren, og hvordan er kunnskapsbasen organisert?](08-kurator.md)): research skal inn i kunnskapsbasen ("superrelevant"), men v1-kuratoren bygges uten. Formen låses her.

## Resolution

Måling: sonnet, 2 tråder × 2 kjøringer (`$CLAUDE_JOB_DIR/tmp/tools-bench/`, forkastes). Uten verktøy, KB i prompt: ~5,5 s / $0.006–0.014. Read/Grep på KB: ~9 s / ~$0.04. Web tillatt: brukt aldri. Web påtvunget: ~15 s / ~$0.037, mest støy (navnebrødre).

- **Standard-utkast: ingen verktøy** (som i dag): KB-utdraget legges i prompten.
- **Verktøy bare ved regenerering med instruks** (`r` + tekst). Agenten bestemmer selv om den bruker dem.
- **Verktøy da**: `Read,Grep,Glob` med `--add-dir` på kunnskapsbasen og hele `~/visense/` (én config-verdi). KB-utdraget legges fortsatt i prompten. Ingen Bash (altså ikke ADO, mail, gh), ingen web.
- **Isolasjon**: som før (`--setting-sources "" --strict-mcp-config --disable-slash-commands`). I tillegg en fast deny-liste via `--settings` (`Read(**/.env*)`, `**/*secret*`, `**/appsettings.*.json`, nøkler/sertifikater o.l.). Utkast-instruksen: siter aldri konfig eller nøkler. Uten nettverksverktøy finnes ingen eksfiltrasjonsvei utenom utkastet, og det leser jeg før sending.
- **Tak** (bare med verktøy): `--max-turns 12`, ekstern timeout 120 s (60 s uten verktøy), `--max-budget-usd 0.25`. Treffes et tak, blir Utkastet `feilet` med årsak i statuslinja. Forrige versjon står.
- **Research → Kurator**: med verktøy får utkast-schemaet `research: [{faktum, kilde}]`. Research = bare fakta funnet med verktøy i kilder utenfor Tråden og det innlagte utdraget (målingen viste at agenten ellers gjentar KB-en). `kilde` = `repo/sti:linje` eller `kunnskapsbase/fil`. Tower validerer at stien ligger under en tillatt katalog. Lagres med Utkast-versjonen i SQLite. Kuratoren får det som input ved sending; forkastede utkast tar researchen med seg.
- **TUI**: «Kilder»-liste under sjekk-hintet i detaljpanelet.

Glossary: la til **Research**.
