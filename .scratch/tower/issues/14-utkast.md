# Utkast-generering og livssyklus

Type: task
Status: closed
Assignee: Sander Hurlen
Blocked by: 13

## Question

Utkast-agent med schema `{tekst,sjekk}` + `[[plassholder]]`, instruks fra `prototype/utkast-agent/utkast.md`, bare for Tråder som trenger svar. Utkast-tilstander `genererer → klart → sendt | forkastet | utdatert` + `feilet` (ett automatisk nytt forsøk), alle versjoner i SQLite. Ny Melding → `utdatert` + ny triage + nytt utkast. Deterministisk KB-oppslag (stil + personer + org + prosjekter, tak ~20 kB, [Hva lærer kuratoren, og hvordan er kunnskapsbasen organisert?](08-kurator.md)) mot tom/fixture-base. Detaljpanel: sjekk-hint over utkastet i ramme, plassholdere uthevet; utkaststatus per rad; antall klare i statuslinja.

Felles: testkrav og konvensjoner i [Hvordan deles byggingen av v1 i task-tickets?](09-bygg-slicing.md). Bygg på låste beslutninger i [kartet](../map.md); zoom inn på lenkede tickets. Direkte på master, én commit. AFK.

## Resolution

Bygd i commit `708c4f2` på master. 61 tester grønne (`tower/tests/kjør`); manuelt kjørt i tmux med ekte `claude -p` mot mail- + Teams-fixtures og en liten KB: 7 utkast klare for svar-trådene, info får `—`; Nordlys-utkastet brukte KB-fakta (uke 46, testtilgang 20. sept); ny Melding → `↻ utdatert`, ny triage, `klart v2` (begge versjoner i SQLite); `q` etterlater ingen `claude`-prosess.

Det senere slices bygger på:
- **Utkast**: `tower/utkast.py`. `SCHEMA`, `Utkast(tråd_id, versjon, melding_id, status, tekst, sjekk, feil, instruks)`, `plassholdere(tekst)` / `Utkast.plassholdere`, tilstandskonstanter og `ÅPNE = (genererer, klart, feilet)`. `skriv_utkast(runner, tråd, kb) -> (tekst, sjekk, usd)`. Instruks i `tower/instrukser/utkast.md`. Felles `agent.med_nytt_forsøk` (triage bruker den også).
- **DB**: tabell `utkast` (PK tråd+versjon, sjekk som JSON). `nytt_utkast(tråd, melding, nå, instruks=None)` (16 sender instruks), `lagre_utkast`/`lagre_utkast_feil` går bare fra `genererer` (None hvis utdatert i mellomtiden), `utkast()` = siste versjon, `versjoner()` = alle (Kurator-input). `registrer` gjør åpne versjoner for eldre Melding `utdatert`. `Rad.utkast` + `Rad.trenger_utkast`. Slice 15 må legge til overganger `klart → sendt | forkastet`.
- **KB-oppslag**: `tower/kunnskapsbase.py`. `utvalg(rot, tråd, meg) -> [Path]` (prioritert; Kurator i 17 kan gjenbruke den for «berørte filer»), `oppslag()` = tekst med `## <sti>` per fil, tak 20 kB (filer som ikke får plass hoppes over). `frontmatter()` leser inline- og blokklister. `Config.kunnskapsbase`. Avvik: også triage får oppslaget (samme input som i prototypen).
- **App**: `planlegg` køer utkast etter triage (nøkkel `("utkast", tråd)`, etikett `utkast Kari`), avbryter når den ikke trengs. Avbrutt `genererer` kjøres ved neste oppstart; `feilet` prøves ikke igjen før ny Melding (manuell regenerer er 16). `#utkast`-ramme (grønn når klart, skjult for info/ferdige), sjekk-hint `›` over teksten. Egen `escape` i app.py: `rich.markup.escape` gir `[\[` for `[[` i Textual 8-markup.
- **Tester**: `FalskRunner(svar, porter, utkast=…)` velger agent ut fra schemaet; `kall` = triage, `utkast_kall` = utkast; `porter="utkast"` holder bare utkast.

Observert, ikke fikset (instruks-kvalitet): Teams-utkastet til Ingrid («Ring meg») skrev «Kan ikke ringe nå», og sjekk-listen kommenterte egen regel. Justeres i `instrukser/utkast.md` ved behov.
