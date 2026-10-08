# Handlinger: send, rediger, avvis, utsett

Type: task
Status: closed
Assignee: Sander Hurlen
Blocked by: 14

## Question

`s` send via `Kanal.svar` (replyAll, ren tekst; nekter ved gjenstående `[[…]]` og sier hvor mange; feil → toast, Utkast forblir `klart` med feiltekst, aldri auto-retry). `e` rediger i $EDITOR via suspend, markør på første plassholder; ny Melding under redigering → advarsel: send likevel / se meldingen / regenerer. `a` avvis (også kvittering av info). `u` utsett (1t / i morgen 08:00 / mandag 08:00), vekkes tidlig av ny Melding, utkast gjenbrukes. Se [Hva er livssyklusen til en Tråd og et Utkast?](04-tradens-livssyklus.md) og [Hvordan skal tower se ut og oppføre seg?](07-tui-layout-prototype.md).

Felles: testkrav og konvensjoner i [Hvordan deles byggingen av v1 i task-tickets?](09-bygg-slicing.md). Bygg på låste beslutninger i [kartet](../map.md); zoom inn på lenkede tickets. Direkte på master, én commit. AFK.

## Resolution

Bygd i commit `41ed063` på master. 82 tester grønne (`tower/tests/kjør`); manuelt kjørt i tmux med ekte `claude -p` mot mail- + Teams-fixtures: `s` på Ingrid-utkastet nektet («1 plassholder igjen»), `e` via suspend med test-editor fylte inn, `s` skrev Teams-request til outbox og raden ble `besvart`/`sendt`; `a` på info-tråd → `avvist`; `u` → dialog, `2` → `⏾ to 08:00`; `q` etterlater ingen `claude`-prosess.

Det senere slices bygger på:
- **Tråd**: nye statuser `avvist`, `utsatt` (begge i `FERDIG`: dimmet nederst, ingen agenter). Kolonne `utsatt_til`; `Db.avvis`, `Db.utsett`, `Db.vekk(nå)` (kalles hver poll; tilbake til `triagert` hvis gyldig triage for siste Melding, ellers `ny`). `registrer` nullstiller `utsatt_til` ved ny Melding.
- **Utkast**: kolonne `redigert` (min tekst; `tekst` er agentens, urørt), `Utkast.gjeldende` = det som vises/sendes, `plassholdere` regnes på den. `Db.lagre_redigert`, `Db.marker_sendt` (forkaster andre åpne versjoner), `Db.lagre_sendefeil` (status står `klart`, `feil` vises).
- **App**: `prøv_send(tråd_id)` / `send()` som worker, deretter `poll_nå()` så `besvart` utledes fra kanalen. `editor`-parameter (tekst → tekst | None) for tester; ekte bruker `$VISUAL`/`$EDITOR` via `tower/handlinger.py` (`editor_argv` kjenner code/vim/nano/hx/emacs/micro). `Valg`-dialog (`UtsettValg`, `NyMeldingValg`) med skjermbindinger.
- **Hold**: `Tower._hold` = Tråder der jeg redigerte et Utkast som ble utdatert; `planlegg` lager ikke auto-utkast for dem. Fjernes av send, avvis, utsett og dialogvalget «regenerer» (som bare slipper auto-utkastet løs). I minnet: omstart slipper holdet, redigeringen står i v1.
- Etter handling som flytter raden blir markøren stående på samme indeks.

For [Regenerer med instruks og Research](16-regenerer-research.md): `r` må fjerne `_hold`; vurder å la dialogvalget «regenerer» åpne instruks-prompten. For [Kurator](17-kurator.md): trigger på `marker_sendt`; diff = `tekst` → `gjeldende` per versjon.
