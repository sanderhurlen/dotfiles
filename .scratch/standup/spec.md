# standup — forslag

`bin/standup` skriver standupen per ADO-team ut fra det som faktisk skjedde i ADO (og fleet),
så ingen trenger å lese opp status. Gruppert per team, ikke per person — personen er en egenskap
på linja. Bare unntak og bevegelse; det som går som det skal vises ikke (`-v` viser alt).

Deler tracker, auth og PR-plumbing med wf/wp/wr/wi/fleet (`_load`, `wr.rest`, `wf.many`).

## Teamene (fra ADO, 2026-10-11)

| Team | Area paths | Sprint nå |
|---|---|---|
| Innsikt Team | `Innsikt`, `Innsikt\Support` | Sprint 41 |
| Team Logit | `Visense\Logit`, `Visense\Support` | Sprint 15 |
| Risiko | `Visense\Risiko` | ingen |
| Huseier | `Visense\Huseier` | ingen |
| Team Nettbutikk og logistikk | `Visense\Nettbutikk og logistikk` | ingen |

Team med sprint → sprintvisning. Team uten → tavlevisning (alt åpent i area path).

## Kommandoer

```
standup                  alle mine team (eller config default), ett avsnitt per team
standup logit            ett team (prefiks-match på navnet)
standup logit -c         til utklippstavla (kort format, klart for Teams)
standup logit --claude   + 3 samtaleemner: risiko, avhengighet, dobbeltarbeid
standup logit post       til teamets kanal (webhook per team i config)
standup teams            list teamene med area/sprint
standup help             forklart (norsk)
```

«Siden sist» = forrige arbeidsdag (mandag → fredag).

## Eksempel: `standup logit`

```
Team Logit · Sprint 15 (dag 6/10) · mål: «Support-mail → Supportsaker»   ▓▓▓▓▓▓░░░░ 9/15

Ferdig siden fre
  ✓ #9068 Bytt sweep-markør til Outlook-kategori     Sander · !7123 completed
  ✓ #9012 Fraktetiketter i ordreoversikt              Jesper

Nesten ferdig  (tavla fra høyre)
  ⏳ !7130 Triage-schema (#8706)                      Sander · venter review 1 d · ingen reviewer
  ⏳ !7131 Retur-API (#8990)                          Håkon · bygg ✗

Står fast
  ▶ #8708 Koble AI-triage inn i sweep                Sander · Doing 3 d (> 2)
  ⛔ #8710 Varsling til kunde                         Endre · blokkert av #8706
  ⚠ Tom Robert: 3 i Doing (WIP > 2)

Uten eier
  ○ #9101 Bug: dobbel sak ved svar på svar            Visense\Support · 2 d

🤖 Agenter (mine): 3 review · 1 fix (ga opp på !7088) · 2 triage-forslag ikke godkjent
```

## Avgrensning per team

- **Work items** — WIQL `[System.AreaPath] UNDER '<area>'` for alle teamets areas, state ≠
  Done/Removed, + Done siden forrige arbeidsdag. Areas fra `work/teamsettings/teamfieldvalues`.
- **Sprint** — `work/teamsettings/iterations?$timeframe=current`; ingen → tavlevisning.
- **PRer** — lenket til teamets work items + der teamet er reviewer-gruppe. Ikke per repo
  (repoer deles på tvers av team).
- **Bevegelse** — `wit/workitems/{id}/updates` siden forrige arbeidsdag (state fra→til, hvem).
- **Blokkert** — `wf.blockers`.
- **Agenter** — fleet `~/.cache/fleet/state.json`, filtrert på teamets items. Bare mine lokale
  agenter; linja sier det.
- **Commits** — ikke med (lokale og personlige).

## Config `~/.config/standup/config.toml`

```toml
default = ["Team Logit", "Innsikt Team"]   # `standup` uten arg; tom = alle mine
stale_days = 2                             # Doing lenger enn dette = står fast
pr_wait_days = 1                           # PR uten stemme lenger enn dette
wip = 2                                    # flere i Doing per person = varsel
weekdays = "mon-fri"

[post]
"Team Logit" = "https://…webhook"
```

## Faser

1. **v1** — `standup [team]` + `teams` + `-c`. Kun ADO, ingen Claude.
2. **v2** — `--claude`, agentlinje fra fleet, sprintmål.
3. **v3** — `post` + launchd 08:50 per team (tid per team i config).

## Åpne spørsmål

- Sprintmål: ADO-iterasjoner har ikke et mål-felt. Config per team, eller største åpne
  Issue/kart i sprinten?
- Skal team uten sprint (Risiko, Huseier, Nettbutikk) være med i default?
