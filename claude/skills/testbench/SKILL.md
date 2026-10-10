---
name: testbench
description: Open a Ghostty tab with one pane per repo/app the current work touches, with env files copied in, ready to test locally.
disable-model-invocation: true
---

The user wants to test the current work locally. Build them a **test bench**: one Ghostty tab, one pane per process that must run, each pane in the right checkout with its env in place and its start command typed in. You set it up; the user drives it.

## 1. Find the processes

List every process the change needs running, and the checkout each runs from:

- The **changed** apps: every repo/app this session edited, at the path where the edits live (usually a worktree under `.claude/worktrees/`, not the main checkout).
- Their **dependencies**: whatever the changed app calls locally to work (a web app's API, that API's backend). Read the changed app's env (`API_BASE_URL`, `*_URL` pointing at `localhost`) to find them. Unchanged dependencies run from the main checkout.
- The start command for each, read from the environment: `package.json` scripts, the repo's `CLAUDE.md`, `docker-compose.yml`. Databases and emulators from `docker compose` get a pane too, unless `docker ps` shows them already running.

Done when every process has a path and a command, and you can say why each is on the list. Unsure whether a dependency is needed: include it.

## 2. Copy the env

A worktree starts without the main checkout's gitignored config. For each changed checkout:

1. Find the gitignored config in the main checkout: `.env*`, `appsettings.*.json`, `launchSettings.json`, `local.settings.json`, outside `node_modules`, `bin`, `obj`.
2. Copy each into the same relative path in the worktree. When the worktree already has the file, keep it and list the diff in key names only.
3. Compare against `.env.example` (or the equivalent): keys the change introduced and keys missing from the copy. Set new feature flags to their **safe** value (off, dry-run, sandbox, local URL) and tell the user which you set.
4. Secrets missing from the main checkout too: look where the repo's docs say they live (Keychain, `az keyvault`). Fetch them yourself when the docs give a command; otherwise list them as gaps.

Handle secrets as **opaque**: copy files with `cp`, write them from a script, read with `grep -c`/key-name extraction, and print key names, never values.

Done when every changed checkout has every key its `.env.example` names, or each gap is listed.

## 3. Prepare

Per checkout, without starting anything long-running: `pnpm install` where `node_modules` is missing, the workspace builds the start command depends on (e.g. `pnpm --filter <shared-package> build`), and `dotnet restore` for .NET. Check ports with `lsof -iTCP -sTCP:LISTEN -P` against each app's configured port, and name the owner of any taken one (`lsof -p <pid> -a -d cwd`).

## 4. Open the panes

Write an AppleScript to `$CLAUDE_JOB_DIR/tmp/testbench.applescript` (or `/tmp` outside a job) and run it with `osascript`. One new tab in the front Ghostty window, or a new window when Ghostty has none. Its first pane comes with the tab; each further pane is a `split` of the previous one, alternating `right` and `down` so the grid stays readable:

```applescript
tell application "Ghostty"
	set cfg to new surface configuration
	set initial working directory of cfg to "/abs/path/to/checkout-a"
	set initial input of cfg to "pnpm dev" & linefeed
	if (count of windows) > 0 then
		set tb to new tab in front window with configuration cfg
	else
		set tb to selected tab of (new window with configuration cfg)
	end if
	set t1 to focused terminal of tb

	set cfg to new surface configuration
	set initial working directory of cfg to "/abs/path/to/checkout-b"
	set initial input of cfg to "pnpm dev" & linefeed
	set t2 to split t1 direction right with configuration cfg
end tell
```

Use `initial input`, so the command runs inside the user's shell and the pane survives Ctrl-C. Order panes dependencies first, the changed app last, so it starts against services already booting. `osascript` failing on permissions: the user must allow the terminal running Claude to control Ghostty (System Settings → Privacy & Security → Automation); tell them and stop.

Done when every port from step 3 is listening; poll `lsof` for up to a minute and name any pane that never came up.

## 5. Hand over

Report:

- Pane → checkout → command, one line each.
- Env files copied, flags set to safe values, gaps.
- URLs to open and the concrete things to try for this change.

The test bench is the deliverable. The user starts testing; you stop here.
