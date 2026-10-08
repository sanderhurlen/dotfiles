# Hvordan deles byggingen av v1 i task-tickets?

Type: grilling
Status: closed
Assignee: Sander Hurlen
Blocked by: 08, 10

## Question

Del v1 i task-tickets som hver passer i én agent-økt, med blocking mellom dem: tracer bullet først (f.eks. `bin/tower` + mail-mock-kanal + SQLite + tabell uten agenter?), så triage, utkast, handlinger, `tower mock`, kurator. Første steg inkluderer `brew "uv"` i Brewfile. Hvilken testdekning kreves per slice (Pilot/snapshot, falsk `claude`-runner)? Bygger på alle låste beslutninger i kartet.

## Resolution

Åtte task-tickets (AFK, én agent-økt hver), direkte på master, én commit per slice.

| Slice | Ticket | Blokkert av |
|---|---|---|
| 1 | [Tracer: mail-mock til tabell](11-tracer.md) | |
| 2 | [Teams-adapter](12-teams-adapter.md) | 11 |
| 3 | [Agent-runner og Triage](13-agent-runner-triage.md) | 11 |
| 4 | [Utkast-generering og livssyklus](14-utkast.md) | 13 |
| 5 | [Handlinger: send, rediger, avvis, utsett](15-handlinger.md) | 14 |
| 6 | [Regenerer med instruks og Research](16-regenerer-research.md) | 15 |
| 7 | [Kurator](17-kurator.md) | 15 |
| 8 | [`tower mock`](18-tower-mock.md) | 11 |

**Testkrav** (alle slices): pytest via `uv run --script` med inline deps. Enhetstester for ren logikk (Graph→domene, tilstandsmaskiner, KB-oppslag). Pilot-tester for taster og flyt. Falsk `claude`-runner (kanned JSON per kall), aldri ekte `claude` i tester. Ingen snapshot-tester i v1. Ferdig = grønne tester + manuelt kjørt mot mock-data.

**Fog avgjort her**:
- Samtidighet: maks 2 samtidige agentkall (triage/utkast), Kurator egen kø (én om gangen). Ny Melding midt i kjøring → drep barneprosessen, legg i kø på nytt.
- `tower mock [-n 5] [--kanal mail|teams]`: sonnet lager nye Tråder fra fast rollebesetning (fil i `tower/mock/`); `--svar` legger ny Melding i eksisterende Tråd (tester utdatering). Ikke idempotent.
- KB i TUI: `k` åpner `kunnskapsbase/` i $EDITOR, statuslinja viser siste kurator-commit. Bla/søk i TUI ute av v1.
