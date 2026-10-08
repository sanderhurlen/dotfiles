# Kurator

Type: task
Status: closed
Assignee: Sander Hurlen
Blocked by: 15

## Question

Kunnskapsbasen i `~/.local/share/tower/kunnskapsbase/` (auto `git init`), Kurator-kø i SQLite (én om gangen, ett nytt forsøk, feil i statuslinja). Trigger: Utkast `sendt` og `besvart` oppdaget utenfra (uten diff), ikke avvis. Input/output/commit-format som i [Hva lærer kuratoren, og hvordan er kunnskapsbasen organisert?](08-kurator.md), inkl. Research fra Utkast-versjonene ([Hvilke verktøy får Utkast-agenten?](10-agentens-verktoy.md)). Sti-validering, `manuelt: endringer` først. `k` åpner kunnskapsbasen i $EDITOR; statuslinja viser siste kurator-commit.

Felles: testkrav og konvensjoner i [Hvordan deles byggingen av v1 i task-tickets?](09-bygg-slicing.md). Bygg på låste beslutninger i [kartet](../map.md); zoom inn på lenkede tickets. Direkte på master, én commit. AFK.

Fra [Handlinger: send, rediger, avvis, utsett](15-handlinger.md): trigg etter `Db.marker_sendt`; diff per versjon er `tekst` (agentens) → `gjeldende` (`redigert` hvis jeg endret).

## Resolution

Bygd i commit `f8dc649` på master. 121 tester grønne (14 nye i `test_kurator.py`). Manuelt kjørt i tmux med ekte sonnet mot fixtures: redigerte Nordlys-utkastet (fylte plassholdere med uke 46 / testbruker uke 44), sendte → Kuratoren laget `org/nordlys-energi.md`, `personer/kari-nordby.md`, `prosjekter/nordlys-erp.md` med frontmatter og daterte fakta, inkl. tilsagnene; én commit `kurator: Status på ERP-integrasjonen`, $0.018; `kb:` i statuslinja; `q` etterlater ingen `claude`-prosess.

- **Kø** (`kurator`-tabell): én jobb per (Tråd, `svar_pa`) = siste Melding jeg hadde sett da jeg svarte. Send i tower køer via `Db.kurator_etter_sending(u, rad.siste_melding_id)` (sendt tekst = `gjeldende`); poll som ser `besvart` (`registrer`, ikke første syn av Tråden) køer samme nøkkel med `INSERT OR IGNORE`. Tower-sending gir altså én jobb med diff, svar utenfra én uten. Avvis køer ingenting. Jobben husker `fra_versjon`/`til_versjon`: bare Utkast-versjoner siden forrige kjøring på Tråden går med.
- **Kjøring**: egen `Agenter(1)` (`Tower.kurator`), etikett `kurator <navn>` i statuslinja. `planlegg_kurator()` på slutten av hver poll køer ventende jobber for kjente Tråder (overlever omstart). Ett nytt forsøk (`med_nytt_forsøk`), deretter `feilet` + `✗ kurator: <feil>` i statuslinja. **Antakelse**: feilede jobber får ett nytt forsøk per oppstart av tower (ellers ble de liggende for alltid).
- **Prompt** (`tower/kurator.py`, `instrukser/kurator.md`): dagens dato, `<alle_filer>` (sti + frontmatter), `<berørte_filer>` (samme utvalg som oppslag, uavkortet opptil 60 kB), Tråden, `<utkast_versjoner>` (instruks, agentens tekst, min redigering, Research), `<sendt>`. Utenfra: bare instrukser og Research fra versjonene, ikke tekstene.
- **Validering**: `gyldig_sti` godtar bare `stil.md` og `{personer,org,prosjekter}/<slug>.md`; tomt innhold og symlenker ut av basen forkastes (toast med antall). Uendrede filer skrives ikke; ingen commit uten endringer.
- **Git**: `git init -b main` automatisk; hooks og signering av per kall. Kurator-commits har forfatter `tower kurator <kurator@tower.invalid>` (det `siste_commit` filtrerer på), `manuelt: endringer` har meg. Body `ny:`/`endret: <fil>`, trailer `Tråd: <id>`.
- **`k`**: `katalog_argv` → $EDITOR på basen (suspend), deretter `manuelt: endringer` hvis noe endret.
- Manuell test lærte ingen stil av én slettet avslutningssetning: riktig etter regelen om bare generaliserbare preferanser.
