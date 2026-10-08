# Research: `claude -p` (headless) for background agents

Ticket: `.scratch/tower/issues/02-claude-headless.md`
Date: 2026-10-07. Local version: **Claude Code 2.1.292**, auth `claude.ai` / subscription `team` (from `claude auth status`).

Sources:
- [H] https://code.claude.com/docs/en/headless (Run Claude Code programmatically)
- [CLI] https://code.claude.com/docs/en/cli-reference
- [SO] https://code.claude.com/docs/en/agent-sdk/structured-outputs
- [COST] https://code.claude.com/docs/en/agent-sdk/cost-tracking
- [COSTS] https://code.claude.com/docs/en/costs
- [HELP] local `claude --help` (2.1.292)
- [RUN] local experiments, described inline

## TL;DR

- `claude -p --model haiku --output-format json --json-schema '<schema>'` gives one JSON object with the validated answer in `.structured_output`. Works on our subscription login. Verified locally.
- On a subscription, **`--bare` can't be used**: it reads only `ANTHROPIC_API_KEY`/`apiKeyHelper` and fails with "Not logged in". For isolation without bare: `--setting-sources ""` + `--strict-mcp-config` + `--disable-slash-commands` + `--tools ...`.
- `--system-prompt` on its own **does not** remove the project CLAUDE.md. `--setting-sources ""` does. Verified locally.
- Cost: `total_cost_usd` is a client-side estimate at list price. On Team, usage comes out of the seat's 5-hour and weekly windows, which are shared with chat. No dollars are billed until usage credits kick in.
- There is no wall-clock timeout flag. Use `--max-turns`, `--max-budget-usd` and an external `timeout`/SIGTERM (exit 143).

## Model

- `--model <alias|full-name>`. The aliases include `sonnet`, `opus`, `haiku` and `fable` [CLI]. `--help` lists only `fable`/`opus`/`sonnet` as examples, but `haiku` works.
- [RUN] `--model haiku` resolved to `claude-haiku-4-5-20251001` (in `modelUsage`; `canonicalModel: "claude-haiku-4-5"`, `contextWindow: 200000`, `maxOutputTokens: 32000`).
- `--fallback-model sonnet,haiku`: a comma-separated chain used when the primary model is overloaded or unavailable [CLI][HELP].
- `--effort low|medium|high|xhigh|max` [HELP]. Haiku thinks by default. [RUN] showed `thinking_tokens` of 86–288 even on trivial prompts.

## Output format

- `--output-format text|json|stream-json` (print mode only) [HELP][CLI].
- `json` returns a single result object. `stream-json` returns NDJSON events: first `system/init` (model, tools, MCP servers, plugins, `mcp_server_errors`), then assistant/user messages, `system/api_retry` events, and finally a `result` [H]. For streaming, docs pair `stream-json` with `--verbose`, and `--include-partial-messages` adds token deltas [H].
- Exit code is 0 on success and non-zero on failure. Invalid flags go to stderr. Failures inside the run, such as missing auth, are printed as the `result` on stdout [H]. [RUN] with `--bare` on a subscription: `"result":"Not logged in · Please run /login"`, `terminal_reason:"api_error"`.
- Piped stdin is capped at 10 MB [H].

### Result fields (seen in [RUN], `--output-format json`)

`type:"result"`, `subtype` (`success` | `error_max_turns` | `error_max_budget_usd` | `error_during_execution` | `error_max_structured_output_retries` [SO][COST]), `is_error`, `result` (the text), `structured_output` (only with `--json-schema`), `session_id`, `num_turns`, `duration_ms`, `duration_api_ms`, `ttft_ms`, `total_cost_usd`, `usage` (input, output, cache_creation and cache_read tokens, `output_tokens_details.thinking_tokens`), `modelUsage{<model>:{inputTokens,outputTokens,costUSD,costBasis,...}}`, `permission_denials[]`, `stop_reason`, `terminal_reason`, `subagent_stats`, `uuid`.

- `usage` leaves out subagent tokens. `total_cost_usd` and `modelUsage` include them [COST].
- With `--resume`/`--continue`, the cost fields hold the whole session's running total (≥ v2.1.277) [COST].

## Structured output (draft + triage fields)

- `--json-schema '<JSON Schema>'` (print only). The validated value lands in `.structured_output`, and `.result` holds the same thing as a JSON string [H][RUN].
- How it works: the agent ends by calling an internal output tool. Output is validated against the schema and re-prompted on mismatch. If it still fails, `subtype: error_max_structured_output_retries` [SO]. [RUN] confirms this: `num_turns: 2` and `stop_reason: "tool_use"` even with `--tools ""`.
- Draft-07 validation. Supports `enum`, `const`, `required`, nested objects and `$ref`. `format` is accepted but not enforced. An invalid schema stops the run at startup (≥ v2.1.205) [SO][H].
- Treat `subtype=="success"` without `structured_output` as a failure too [SO].
- [RUN] example: schema `{severity: enum[low,medium,high], draft: string}` returned `structured_output: {"severity":"high","draft":"Thanks for reporting…"}`. It took about 4 s and was estimated at $0.0136.

## System prompt

- `--system-prompt` / `--system-prompt-file` replace the whole default prompt. `--append-system-prompt` / `--append-system-prompt-file` add to the end of it. A replace flag and an append flag can be combined [CLI].
- Replacing drops the default tool and safety guidance. Docs recommend it for a "non-coding agent in a pipeline that no human watches" [CLI].
- `__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__` on its own line splits a custom prompt into a cached static part and a dynamic part (≥ 2.1.275) [CLI].
- **Gotcha [RUN]:** `--system-prompt` does NOT stop CLAUDE.md from loading. CLAUDE.md is injected as context, not as part of the system prompt (see Isolation).

## Tools and permissions

- `--tools "Read,Grep"` limits which built-in tools exist; `""` means none. MCP tools are not affected, so use `--disallowedTools "mcp__*"` for those [CLI].
- `--allowedTools` auto-approves tools (permission rule syntax, e.g. `Bash(git diff *)`). It does not restrict which tools are available [CLI][H].
- `--disallowedTools`: a bare name removes the tool, and a scoped rule denies matching calls [CLI].
- `--permission-mode dontAsk|acceptEdits|auto|plan|bypassPermissions|manual` [HELP]. `--permission-prompts none` denies anything that would prompt, removes `AskUserQuestion`, and tells Claude not to retry (≥ 2.1.259) [H]. Denials show up in `permission_denials`.
- **Gotcha [RUN]:** `--tools`, `--allowedTools` and `--disallowedTools` are variadic (`<tools...>`). `claude -p --tools "" "prompt"` swallowed the prompt and failed with "Input must be provided…". Put the prompt before the flag, end the list with `--`, or pipe the prompt on stdin.

## Isolation: CLAUDE.md, skills, MCP, settings, hooks

By default `-p` loads the same context as an interactive session: user and project CLAUDE.md, hooks, skills, plugins, `.mcp.json` and auto memory. It also skips the workspace trust dialog [H][HELP].

| Mechanism | Effect | Subscription OK? |
|---|---|---|
| `--bare` | Skips hooks, skills/commands, subagents, plugins, MCP, auto memory, CLAUDE.md, LSP, keychain. Tools: Bash, Read and Edit. Context is passed explicitly with flags. Recommended for scripts and will become the default for `-p` in the future [H][CLI][HELP] | **No.** Auth is strictly `ANTHROPIC_API_KEY` or `apiKeyHelper`, and OAuth/keychain are never read [H][HELP]. [RUN]: "Not logged in" |
| `--setting-sources ""` (or a subset of `user,project,local`) | Choose which settings files load. [RUN]: also dropped the project CLAUDE.md (canary not found) | Yes |
| `--strict-mcp-config` (+ optional `--mcp-config`) | Only MCP servers from `--mcp-config` [CLI] | Yes |
| `--disable-slash-commands` | Disables all skills and commands [HELP][CLI] | Yes |
| `--safe-mode` | Turns off CLAUDE.md, skills, plugins, hooks, MCP, agents, memory and more. Auth and built-in tools work as usual [HELP][CLI] | Yes (meant for troubleshooting) |
| `--restricted` | Removes the code-running tools and WebFetch, ignores user/project/local settings, confines file tools to the working dirs [HELP][CLI] | Yes |
| `--no-session-persistence` | No transcript is written, so the run can't be resumed [CLI] | Yes |

[RUN] canary test: a project dir whose CLAUDE.md said "codeword PELICAN-42", 3 haiku calls run in parallel:

| Flags | Answer | cache_creation tokens |
|---|---|---|
| (none) | PELICAN-42 | 16 470 |
| `--setting-sources ""` | NONE | 7 306 |
| `--system-prompt "You are a bot."` | PELICAN-42 | 13 181 |

Combining `--setting-sources "" --strict-mcp-config --disable-slash-commands --system-prompt … --tools ""` brought input down to about 700 tokens with no cache write, at roughly $0.0026 per call [RUN].

Caveat: [RUN] calls made from inside a Claude Code session inherited `CLAUDE_CODE_*` env vars. One isolated run still said it was in a "git worktree setup". Tower should spawn with a clean env.

## cwd

- The process cwd is the working directory: it determines project CLAUDE.md, `.claude/settings.json`, `.mcp.json`, file tool scope and which project dir the transcript goes in [H][CLI]. `--add-dir` grants extra file access but doesn't load most `.claude/` config from those dirs [CLI].
- `-p` runs hooks and `.mcp.json` from the cwd even in untrusted folders [H]. Run in a neutral dir, or use the isolation flags.
- If the cwd is deleted mid-run, the session continues and shell commands fail [H].
- `--resume <id>` finds the session from any directory (≥ 2.1.223) [H].

## Cost and rate limits

- `total_cost_usd` / `costUSD` are **client-side estimates** at list price (`costBasis: "list"`), not billing data [COST][COSTS].
- Team/Enterprise: "each member's Claude Code usage draws from a per-seat allowance that resets on a rolling five-hour window and a weekly window", shared with Claude chat and Cowork. Usage inside the allowance isn't metered in dollars. Beyond it, usage credits apply only if an admin has enabled them [COSTS]. Headless runs count against the same seat (no exception documented).
- When the limit is hit you get "You've hit your session limit / weekly limit". The window is shared across models, so switching to haiku doesn't help [COSTS].
- API keys / Console: billed per token, with org-level TPM/RPM limits. Docs recommend 200–300k TPM and 5–7 RPM per user for 1–5 users [COSTS].
- Prompt cache TTL is 1 h on a subscription and 5 min on an API key by default [COSTS][COST]. Parallel calls with an identical prefix can share the cache.
- `--max-budget-usd <n>` caps spend against the estimate (print only). It returns `error_max_budget_usd` [CLI][COST].
- `claude setup-token` creates a long-lived OAuth token for scripts (requires a subscription) [CLI]. The docs don't say whether `--bare` accepts it, and its help says OAuth is never read.
- [RUN] cost estimates: about $0.012 for a trivial haiku call with full context, and about $0.0026 isolated.

## Parallel runs

- No documented concurrency limit for `-p` processes. The real ceiling is the seat allowance or API rate limit plus `system/api_retry` with `error: rate_limit` [H][COSTS].
- [RUN] 3 parallel haiku calls in the same cwd ran without trouble (1.2–4 s each).
- Use `--no-session-persistence` or a unique `--session-id <uuid>` to avoid confusion between sessions. `--continue` picks "most recent", which is unsafe when runs are parallel [H][CLI].

## Timeouts and stopping

- **No wall-clock timeout flag.** The available limits are:
  - `--max-turns N` (print only; exits with an error when reached). It doesn't appear in `--help` but is documented [CLI]. The docs note that `--help` doesn't list every flag.
  - `--max-budget-usd`.
  - External: `timeout`, or SIGTERM gives exit 143 with the turn left unfinished and no result. SIGINT ends the turn cleanly [H].
- Background subagents/workflows: `-p` waits for them, up to 10 min of idle time (`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`). Background Bash shells are killed about 5 s after the result [H].
- `MCP_TIMEOUT` (default 30 s) for MCP startup with `--mcp-config` [H].

## Suggested invocation for tower (subscription, triage agent)

```bash
cd "$NEUTRAL_DIR" && printf '%s' "$PROMPT" | claude -p \
  --model haiku --fallback-model sonnet \
  --output-format json --json-schema "$SCHEMA" \
  --system-prompt-file triage.md \
  --setting-sources "" --strict-mcp-config --disable-slash-commands \
  --tools "" --permission-prompts none \
  --no-session-persistence --max-turns 3 --max-budget-usd 0.10
# parse: .subtype=="success" && .structured_output != null
```

Add `Read`/`Grep` to `--tools` (with the cwd set to the repo) only if the agent needs to read code. Doing so brings back the project CLAUDE.md unless `--setting-sources ""` stays in place.

## Open questions

- Whether `CLAUDE_CODE_OAUTH_TOKEN` (from `setup-token`) is accepted by `--bare`. The docs say no. Untested.
- Exactly how much `-p` usage weighs against the Team seat window compared with interactive use. Not documented.
