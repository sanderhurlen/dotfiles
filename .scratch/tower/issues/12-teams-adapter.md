# Teams-adapter

Type: task
Status: closed
Assignee: Sander Hurlen
Blocked by: 11

## Question

`tower/kanal/teams.py` over `graph_fil`: chats (ikke kanalmeldinger), emne = `topic` eller deltakernavn, tabellen viser start av siste melding når topic mangler, mock-`svar` skriver outbox (eksakt Graph-request) og legger min Melding i trådfila. Se [Hvilke Graph-felt må mock-formatet speile?](01-graph-meldingsform.md) og [Hvordan ser kanal-sømmen ut?](05-kanal-somm.md). Fixtures for Teams.

Felles: testkrav og konvensjoner i [Hvordan deles byggingen av v1 i task-tickets?](09-bygg-slicing.md). Bygg på låste beslutninger i [kartet](../map.md); zoom inn på lenkede tickets. Direkte på master, én commit. AFK.

## Resolution

Bygd i commit `0884182` på master. 21 tester grønne (`tower/tests/kjør`); manuelt kjørt i tmux mot mail- + Teams-fixtures: 11 Tråder, chat uten topic viser start av siste Melding, svar lagt i chatfila utenfra → `besvart` og sortert ned.

Det senere slices bygger på:
- **Adapter**: `tower/kanal/teams.py` (`TeamsKanal`), samme form som `MailKanal`. Tråd-id `teams:<chat.id>`. Bare `messageType: message` (systemhendelser filtreres; chat med bare systemhendelser gir ingen Tråd).
- **Meg i Teams**: ingen ny config. `from.user.id` slås opp i `chat.members` → `email`, sammenlignes med `meg.adresse` som i mail. Person-adresse = e-post (fallback userId).
- **Melding**: `til` = alle andre medlemmer, `cc` tom; `haster` = `importance` `high`/`urgent`. Mentions: `<at>` → `@Navn` i teksten (endring i `tekst.py`, gjelder alle kanaler).
- **Emne**: `topic` eller andre deltakeres navn (komma-separert). Nytt domenefelt `Tråd.emne_utledet: bool = False`; tabellen (`app.emne_kort`) viser da start av siste Melding, detaljhodet viser deltakernavn.
- **Svar**: outbox `POST /chats/{chat.id}/messages` med `{"body":{"contentType":"text",...}}`; min chatMessage (id = epoch-ms) legges i chatfila. `viewpoint` røres ikke.
- **Config**: `kanaler` standard `["mail","teams"]` (eksisterende `config.json` med bare `mail` må oppdateres for hånd). Testenes `config`-fixture er fortsatt bare `mail`; `rot` kopierer begge fixture-mapper (`tower/tests/fixtures/teams/`: 4 chatter, én gruppe med topic + HTML-mention + systemhendelse, to 1:1, én gruppe uten topic der jeg svarte sist).
