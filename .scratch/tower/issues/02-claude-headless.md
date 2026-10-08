# Hva gir `claude -p` headless oss for bakgrunnsagenter?

Type: research
Status: closed
Assignee: Sander Hurlen
Blocked by:

## Question

Fakta om `claude -p` i dagens Claude Code: valg av modell (haiku), `--output-format json/stream-json`, systemprompt/append, `--allowedTools`, at agenten ikke tar med prosjekt-CLAUDE.md og skills (isolasjon), kost og rate limits på abonnement, parallelle kjøringer, timeout, og hvordan man får ut strukturert svar (utkast + triage-felt).

## Resolution

Funn: [research/claude-headless.md](../research/claude-headless.md) (også på branch `research/claude-headless`, 7e6b5bd). Lokalt verifisert mot Claude Code 2.1.292.

- Strukturert output: `claude -p --model haiku --output-format json --json-schema '<schema>'` → validert JSON i `.structured_output`, pluss `session_id`, `total_cost_usd`, `subtype`, `is_error`. Feil-subtype `error_max_structured_output_retries`.
- `--bare` virker ikke på abonnement (krever API-nøkkel). Isolasjon: `--setting-sources "" --strict-mcp-config --disable-slash-commands --tools ...` (~700 input-tokens, ~$0.003/kall). `--system-prompt` alene fjerner ikke prosjekt-CLAUDE.md.
- Kost: `total_cost_usd` er estimat; Team-abonnement deler 5t/ukekvote med chat. Tak: `--max-budget-usd`, `--max-turns`.
- Ingen timeout-flagg → ekstern timeout; SIGINT avslutter rent, SIGTERM gir ingen result. 3 parallelle ok. Bruk `--no-session-persistence` eller unik `--session-id`.
- Fallgruve: `--tools`/`--allowedTools` sluker prompt etter seg → send prompt på stdin.
