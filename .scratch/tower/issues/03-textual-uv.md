# Hvordan bygger vi en Textual-app kjørt med `uv run --script`?

Type: research
Status: closed
Assignee: Sander Hurlen
Blocked by:

## Question

Dagens Textual-fakta: inline script-deps med `uv run --script`-shebang over flere moduler i `tower/`, workers/async subprocess for å spawne og følge `claude -p`, filovervåking/polling, åpne $EDITOR fra appen (suspend), layout-widgets for liste+detalj, og testing (Pilot/snapshot).

## Resolution

Funn: [research/textual-uv.md](../research/textual-uv.md) (også på branch `research/textual-uv`, ae643c7). Versjoner: textual 8.2.8, pytest-textual-snapshot 1.1.0.

- uv er ikke installert og mangler i Brewfile → `brew "uv"` må inn før bygging.
- `#!/usr/bin/env -S uv run --script` virker på fil uten `.py`, men `bin/` havner først på sys.path → `bin/tower` må legge repo-rot (`Path(__file__).resolve().parent.parent`) på sys.path. Deps deklareres bare i `bin/tower`.
- Agenter: `@work(group=..., exit_on_error=False)` + `asyncio.create_subprocess_exec`, les stdout linje for linje. Drep barneprosessen i `finally`: avbrutt worker/app-quit dreper den ikke.
- Ingen file-watch-API → poll med `set_interval` og skann katalog.
- `$EDITOR` via `with self.suspend():`. Liste: DataTable/ListView; detalj: Markdown (`Markdown.get_stream` for streaming). `notify()` er trådsikker.
- Test: `run_test(notifications=True)` for toasts; `snap_compare(app, press, terminal_size, run_before)` med App-instans.
- Åpent: kald/varm oppstartstid når uv er installert.
