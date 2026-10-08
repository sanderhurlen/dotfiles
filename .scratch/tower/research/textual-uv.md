# Research: Textual-app kjørt med `uv run --script`

Ticket: `.scratch/tower/issues/03-textual-uv.md`. Dato: 2026-10-07.

Versjoner (PyPI JSON, 2026-10-07): **textual 8.2.8** (py >=3.9), **pytest-textual-snapshot 1.1.0** (dep: `syrupy==4.8.0`, `pytest>=8`), **uv 0.12.23** (brew stable).
API-fakta under er sjekket mot kildekoden i textual 8.2.8 sdist der det står `src:`.

## Lokal status

- **uv er IKKE installert.** `which uv` tom; ikke i `~/.local/bin`, `~/.cargo/bin`, `/opt/homebrew/bin`; `brew list uv` feiler. `brew info uv` → stable 0.12.23. Ikke i `Brewfile`.
  - Må legges til: `brew "uv"` i `Brewfile` (eller mise). Ingen startup-måling gjort pga dette.
- `python3` = 3.14.8 (homebrew). `/usr/bin/env -S` virker på macOS (testet).
- `bin/` i dotfiles ligger direkte på PATH (`system/_path.zsh`: `$ZSH/bin`), ikke symlinket.
- Presedens i repoet: `bin/fleet` er en enkelt-fil Python-TUI (`#!/usr/bin/env python3`, uten Textual/uv).

## 1. PEP 723 + shebang over flere moduler

Fakta:
- Inline-metadata: `# /// script` … `# dependencies = [...]` … `# ///`, støtter `requires-python`; uv laster ned Python ved behov. [uv scripts]
- Shebang: `#!/usr/bin/env -S uv run --script`. [uv scripts]
- `--script`: "parse the path as a PEP 723 script, irrespective of its extension" → `bin/tower` uten `.py` går fint. [uv CLI]
- Med inline-metadata ignoreres prosjektets deps; ingen `--no-project` nødvendig. [uv scripts]
- `uv add --script bin/tower 'textual'` skriver deps inn i fila. `uv lock --script bin/tower` lager `bin/tower.lock`, som gjenbrukes av `uv run --script`. `[tool.uv] exclude-newer = "<RFC3339>"` for reproduserbarhet. [uv scripts]
- `uv run --with-requirements <fil>` godtar "`.py` files with inline metadata" (ikke pyproject). [uv CLI] — nyttig for tester, se §7. (Uklart om en fil uten `.py` godtas; ikke verifisert.)

Imports (Python-regel, ikke uv): `python script.py` → "prepend the script's directory. If it's a symbolic link, resolve symbolic links." [python sys.path]
- Dvs. `sys.path[0] == <repo>/bin`, så `import tower` (pakke i `<repo>/tower/`) **feiler** uten hjelp.
- Testet lokalt med python3 (scratch-repo `bin/tower` + `tower/__init__.py`, direkte og via symlink): plain import feiler; etter `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` virker det. Symlink løses til ekte `bin/`.
- Antatt (ikke verifisert uten uv): uv kjører scriptet med sin python som `python <path>`, så samme regel gjelder.

Anbefalt form:
```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["textual>=8,<9"]
# ///
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tower.app import main
main()
```
- Deps deklareres KUN i `bin/tower`; `tower/`-modulene importerer bare. Alternativ (`tower/` som installerbar pakke via `--with-editable`) gir mer seremoni; ikke nødvendig.
- Navnekollisjon: `bin/tower` har ingen `.py`, så `bin/` skygger ikke for `tower/`-pakken.

Caching/startup:
- "When running scripts with inline metadata, uv creates a dedicated virtual environment for each script in the cache directory." Cache: `$XDG_CACHE_HOME/uv` el. `~/.cache/uv`; managed Python: `~/.local/share/uv/python`. [uv storage]
- `--offline` = kun cache; `--refresh` revaliderer; `uv cache prune`/`clean`. [uv CLI, uv cache]
- Dokumentasjonen sier **ikke** eksplisitt at script-env gjenbrukes mellom kjøringer eller gir tall for startup. Første kjøring resolver+installerer; senere kjøringer bruker cache-env. Mål `time bin/tower --help` når uv er installert (forventning: uv-overhead lav, Textual-import dominerer — umålt).
- Tips: `-q` i shebang (`uv run -q --script`) demper uv-output ved første installasjon. [uv CLI]

## 2. Workers + async subprocess for `claude -p`

Fakta (src: `_work_decorator.py`, `dom.py`):
- `@work(name="", group="default", exit_on_error=True, exclusive=False, description=None, thread=False)`; `run_worker(work, name, group, description, exit_on_error=True, start=True, exclusive=False, thread=False) -> Worker`.
- Async-worker = `async def`; kall metoden uten `await`. `@work` på vanlig `def` krever `thread=True`, ellers exception. [textual workers]
- `exclusive=True` kansellerer tidligere workers i samme gruppe. `exit_on_error=True` (default) avslutter appen ved exception → **sett `exit_on_error=False`** for agent-workers.
- States: PENDING, RUNNING, CANCELLED, ERROR, SUCCESS; håndter `on_worker_state_changed(self, event: Worker.StateChanged)`. [textual workers]
- `Worker.cancel()` → `CancelledError` i coroutinen. Fjerning av en widget kansellerer dens workers (`widget.py`: `workers.cancel_node(self)`); app-exit kaller `workers.cancel_all()` (`app.py`).
- Fra thread-worker: `post_message` og `App.call_from_thread` er trådsikre; `App.notify` er også trådsikker (src docstring).

Mønster (asyncio stdlib, ingen Textual-spesifikk subprocess-API):
```python
@work(group="agents", exit_on_error=False)
async def run_agent(self, thread_id: str, prompt: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", "--model", "haiku", "--output-format", "stream-json", "--verbose", prompt,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        async for line in proc.stdout:
            self.post_message(AgentOutput(thread_id, line.decode()))
        await proc.wait()
    finally:
        if proc.returncode is None:
            proc.kill()   # CancelledError ved worker.cancel()/app-exit dreper ikke barnet av seg selv
```
- Async-worker kjører i appens event-loop → ingen tråd nødvendig, UI kan oppdateres direkte, men meldinger (`post_message`) holder koden ryddig.
- `claude -p`-flaggene over er ikke verifisert i denne researchen (egen ticket).

## 3. Filovervåking vs polling

- Textual har **ingen** offentlig file-watch-API. Intern `textual.file_monitor.FileMonitor` (brukt til CSS live-reload) **poller** `os.stat(...).st_mtime` (src). Ingen watchdog/watchfiles-avhengighet i textual.
- Anbefaling: `self.set_interval(2.0, self.scan_channels)` (src: `set_interval(interval, callback=None, *, name=None, repeat=0, pause=False) -> Timer`) og scan `~/.local/share/tower/{mail,teams}` med `os.scandir` + mtime. Billig for titalls/hundretalls JSON-filer, null ekstra deps, deterministisk i tester.
- `watchfiles` (`awatch`) er alternativet hvis latens blir viktig — ekstra dep; ikke vurdert mot primærkilde her.

## 4. Åpne `$EDITOR` (suspend)

Fakta (src `app.py`, [textual app guide]):
- `App.suspend()` er en **context manager**: "the app will stop reading input and emitting output. Other applications will have full control of the terminal, configured as it was before the app started running."
- Raises `SuspendNotSupported` hvis miljøet ikke støtter det. Støttet på Unix-lignende og Windows; ikke Textual Web. stdout/stderr redirectes til `sys.__stdout__/__stderr__` i blokken.
- Separat: `action_suspend_process` (Ctrl+Z / SIGTSTP, Unix) — ikke det vi trenger.
```python
def action_edit(self) -> None:
    path = draft_path(...)
    with self.suspend():
        subprocess.run([os.environ.get("EDITOR", "vi"), str(path)])
    self.reload_draft(path)
```
- Event-loopen kjører videre under suspend (bare driveren pauses) → bakgrunns-workers fortsetter; unngå at de pusher toasts som skal vises mens editor er åpen (de vises etter retur). (Utledet fra kilde, ikke dokumentert.)

## 5. Layout-widgets for liste + detalj

Tilgjengelig i `textual.widgets` 8.2.8 (src): `ListView`/`ListItem` (meldinger `Highlighted`, `Selected`), `DataTable` (kolonner, cursor rader), `OptionList`, `Tree`, `TabbedContent`/`TabPane` (`TabActivated`), `ContentSwitcher`, `Markdown`, `MarkdownViewer`, `TextArea`, `RichLog`, `Log`, `Header`, `Footer`, `Toast`.
- Liste: `DataTable` for tråder (kolonner: kanal, fra, emne, triage, alder; rask, sortérbar) eller `ListView` hvis rader skal være rike widgets. Tråder per kanal → `TabbedContent` eller en kolonne i tabellen.
- Detalj: `Horizontal` med liste venstre, `VerticalScroll` høyre med `Markdown` for tråd/utkast.
- `Markdown.update(md)`, `.append(md)`, `.load(path)`; `Markdown.get_stream(md)` → `MarkdownStream` med `write()`/`stop()` som slår sammen hyppige oppdateringer — passer for å strømme `claude -p`-output. `MarkdownViewer` legger til TOC/navigasjon (passer for kunnskapsbasen).

## 6. Notifikasjoner/toasts

- `App.notify(message, *, title="", severity="information", timeout=None, markup=True)`; severity ∈ `"information" | "warning" | "error"`; `timeout=None` → `NOTIFICATION_TIMEOUT = 5` s. Trådsikker. Finnes også `Widget.notify`. (src `app.py`, `notifications.py`)

## 7. Testing (Pilot + snapshot)

- `async with app.run_test(headless=True, size=(80, 24), tooltips=False, notifications=False, message_hook=None) as pilot:` (src). NB `notifications=False` default → sett `True` for å teste toasts.
- Pilot (src `pilot.py`): `press(*keys)`, `click(...)`, `double_click`, `hover`, `mouse_down`, `resize_terminal(w, h)`, `pause(delay=None)`, `wait_for_animation`, `wait_for_scheduled_animations`, `exit(result)`.
- Krever `pytest-asyncio`; `asyncio_mode = auto` sparer `@pytest.mark.asyncio`. [textual testing]
- Snapshot: fixture `snap_compare(app: str | PurePath | App, press=(), terminal_size=(80, 24), run_before=None) -> bool`; SVG-filer; oppdater med `pytest --snapshot-update` (syrupy). (src pytest_textual_snapshot 1.1.0, [textual testing])
- For tower: send en `App`-instans (konstruert mot en tmp data-dir med fixture-JSON) til `snap_compare`, ikke filsti — unngår sys.path-hacken og gjør data deterministisk. Mock `claude` via injisert runner (kanal-sømmen gjør dette naturlig).
- Kjøring uten prosjekt: `uv run --with-requirements bin/tower` er usikkert for fil uten `.py`; trygt alternativ: `uv run --with 'textual>=8,<9' --with pytest --with pytest-asyncio --with pytest-textual-snapshot pytest tests/` (evt. pakket i `bin/tower test`). Hold textual-pin synk med shebang-fila.

## Åpne punkter

- Installer uv (`brew "uv"` i Brewfile) og mål kald/varm startup.
- Verifiser `uv run --with-requirements` mot fil uten `.py`.
- `claude -p` stream-json-format og flagg: egen research.

## Kilder

- [uv scripts] https://docs.astral.sh/uv/guides/scripts/
- [uv CLI] https://docs.astral.sh/uv/reference/cli/
- [uv storage] https://docs.astral.sh/uv/reference/storage/
- [uv cache] https://docs.astral.sh/uv/concepts/cache/
- [uv run] https://docs.astral.sh/uv/concepts/projects/run/
- [python sys.path] https://docs.python.org/3/library/sys.html#sys.path
- [textual workers] https://textual.textualize.io/guide/workers/
- [textual app guide] https://textual.textualize.io/guide/app/
- [textual testing] https://textual.textualize.io/guide/testing/
- [textual API app] https://textual.textualize.io/api/app/
- src: textual 8.2.8 sdist fra PyPI (`app.py`, `dom.py`, `_work_decorator.py`, `message_pump.py`, `pilot.py`, `file_monitor.py`, `notifications.py`, `widgets/`); pytest-textual-snapshot 1.1.0 sdist (`pytest_textual_snapshot.py`).
