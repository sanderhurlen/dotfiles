// pr-utkast — the review drafts a fleet agent writes (`wr draft`), above the prompt: one
// line per PR with its summary, buttons to switch the vote and to post, and a pane to pick
// which comments go out; /post and /utkast do the same from the prompt. The PRs come from
// the session's directory: fleet's worktree fleet-pr-<id>-review (or -rereview) for one PR,
// a group's directory with .fleet.json for several; `/utkast <id>` binds one by hand.
// Everything about a draft — where it lives, what it says, posting it — is `wr`'s; this
// only shows what `wr draft --line` reports and runs `wr`.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Draft, Pr } from '../types'

// the tags decline what the one-PR version stored, which outlives a reload
const prs = atom({ plugin: 'pr-utkast', key: 'prs' } as const, [], { shape: 'prs-1' })
const drafts = atom({ plugin: 'pr-utkast', key: 'drafts' } as const, [], { shape: 'drafts-1' })
const confirming = atom({ plugin: 'pr-utkast', key: 'confirming' } as const, null)
const paneFor = atom({ plugin: 'pr-utkast', key: 'paneFor' } as const, null)

const PANE = 'pr-utkast'
const FLEET_REVIEW = /fleet-pr-(\d+)-(?:re)?review/
const VOTES = [
  ['approve', 'approve', 'a'],
  ['suggestions', 'forslag', 'f'],
  ['wait', 'vent', 'v'],
  ['reject', 'reject', 'r'],
] as const

type Line = { line: string; posted: boolean; vote: string; goal: string; comments: { where: string; text: string; skip: boolean }[] }

async function wr($: EngineInterface, args: string[]) {
  const { exitCode, stdout, stderr } = await $.process.run(['wr', ...args], { timeoutMs: 60_000 })

  return { isOk: exitCode === 0, text: (exitCode === 0 ? stdout : stderr || stdout).trim() }
}

// the PRs this session reviews: a group's .fleet.json, else the PR in fleet's worktree name
async function find($: EngineInterface): Promise<Pr[]> {
  const cwd = await $.session.cwd()
  try {
    const manifest = JSON.parse(await $.fs.read(`${cwd}/.fleet.json`)) as { prs: Pr[] }

    return manifest.prs
  } catch {
    const found = FLEET_REVIEW.exec(cwd)

    return found ? [{ id: Number(found[1]), repo: '' }] : []
  }
}

async function refresh($: EngineInterface) {
  const out: Draft[] = []
  for (const pr of await read($, prs)) {
    const { isOk, text } = await wr($, ['draft', String(pr.id), '--line'])
    const found = isOk ? (JSON.parse(text) as Line | null) : null
    if (found) {
      out.push({
        id: pr.id,
        repo: pr.repo,
        line: found.line,
        isPosted: found.posted,
        vote: found.vote,
        goal: found.goal ?? '',
        comments: found.comments.map(c => ({ where: c.where, text: c.text, isSkipped: c.skip })),
      })
    }
  }
  await update($, drafts, () => out)
}

// one `wr draft` change on PR id, then the redraw; a refusal shows as a toast
async function edit($: EngineInterface, id: number, args: string[]) {
  const { isOk, text } = await wr($, ['draft', String(id), ...args])
  if (!isOk) {
    $.ui.toast(text)
  }
  await refresh($)
}

async function post($: EngineInterface, id: number) {
  await update($, confirming, () => null)
  const result = await wr($, ['post', String(id)])
  await refresh($)

  return result
}

// the PR a command means: the one given, else the only one
async function pick($: EngineInterface, args: string): Promise<number | string> {
  const given = args.trim().replace(/^!/, '')
  if (/^\d+$/.test(given)) {
    return Number(given)
  }
  const ids = (await read($, prs)).map(p => p.id)
  if (ids.length === 1 && ids[0] !== undefined) {
    return ids[0]
  }

  return ids.length === 0 ? 'Ingen PR i denne økta — /utkast <id>.' : `Hvilken? ${ids.map(i => `!${i}`).join(', ')}`
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'post', description: 'Post review-utkastet til PR-en; /post <id> i en gruppe' })
    await $.command.register({ name: 'utkast', description: 'Vis review-utkastene; /utkast <id> velger PR' })
    if ((await read($, prs)).length === 0) {
      const found = await find($)
      await update($, prs, () => found)
    }
    await refresh($)

    return next(e)
  })

  // the agent writes and rewrites the drafts during its turns
  on('turn.complete', async ($, e, next) => {
    await refresh($)

    return next(e)
  })

  on('command.run', { command: 'utkast' }, async ($, e) => {
    const given = e.args.trim().replace(/^!/, '')
    if (/^\d+$/.test(given) && !(await read($, prs)).some(p => p.id === Number(given))) {
      await update($, prs, list => [...list, { id: Number(given), repo: '' }])
      await refresh($)
    }
    const ids = /^\d+$/.test(given) ? [Number(given)] : (await read($, prs)).map(p => p.id)
    if (ids.length === 0) {
      return { text: 'Ingen PR i denne økta — /utkast <id>.' }
    }
    const texts = await Promise.all(ids.map(async id => (await wr($, ['draft', String(id)])).text))

    return { text: texts.join('\n\n') }
  })

  on('command.run', { command: 'post' }, async ($, e) => {
    const id = await pick($, e.args)
    if (typeof id === 'string') {
      return { text: id }
    }
    const { isOk, text } = await post($, id)

    return isOk ? { text, context: [`Jeg postet review-utkastet: ${text}`] } : { text }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const list = await read($, drafts)
    if (e.props.hasSurvey || list.length === 0) {
      return next(e)
    }
    const { Box, Button, Text } = $.ui.resolve(e)
    const asking = await read($, confirming)
    const isOne = list.length === 1 // hotkeys only where they can't clash

    return (
      <Box flexDirection="column">
        {list.map(d => {
          const name = d.repo ? `!${d.id} ${d.repo}` : `!${d.id}`
          if (d.isPosted) {
            return <Text key={`line-${d.id}`} dimColor>📝 {name} {d.line}</Text>
          }
          if (asking === d.id) {
            return (
              <Box key={`line-${d.id}`} gap={1}>
                <Text color="yellow">Post på {name}: {d.line}?</Text>
                <Button
                  key={`yes-${d.id}`}
                  label="Ja, post"
                  hotkey="j"
                  onPress={async () => {
                    const { text } = await post($, d.id)
                    $.ui.toast(text)
                  }}
                />
                <Button key={`no-${d.id}`} label="Avbryt" hotkey="n" onPress={() => update($, confirming, () => null)} />
              </Box>
            )
          }

          return (
            <Box key={`line-${d.id}`} flexDirection="column">
              {d.goal ? <Text><Text color="yellow">skal løse:</Text> {d.goal}</Text> : null}
              <Text>📝 {name} utkast: {d.line}</Text>
              <Box gap={1}>
                <Button
                  key={`post-${d.id}`}
                  label="Post"
                  hotkey={isOne ? 'p' : undefined}
                  onPress={() => update($, confirming, () => d.id)}
                />
                <Button
                  key={`comments-${d.id}`}
                  label={`Kommentarer (${d.comments.length})`}
                  hotkey={isOne ? 'k' : undefined}
                  onPress={async () => {
                    await update($, paneFor, () => d.id)
                    await $.ui.open({ id: PANE, title: `${name} kommentarer` })
                  }}
                />
                <Text dimColor>stemme:</Text>
                {VOTES.map(([vote, label, key]) => (
                  <Button
                    key={`vote-${d.id}-${vote}`}
                    label={d.vote === vote ? `[${label}]` : label}
                    hotkey={isOne ? key : undefined}
                    onPress={() => edit($, d.id, ['--vote', vote])}
                  />
                ))}
              </Box>
            </Box>
          )
        })}
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const id = await read($, paneFor)
    const d = (await read($, drafts)).find(one => one.id === id)
    if (d === undefined || d.comments.length === 0) {
      return <Text dimColor>Ingen kommentarer i utkastet.</Text>
    }

    return (
      <Box flexDirection="column" gap={1}>
        <Text dimColor>Trykk på en kommentar for å ta den med eller hoppe over den.</Text>
        {d.comments.map((c, i) => (
          <Button key={`comment-${i + 1}`} onPress={() => edit($, d.id, ['--skip', String(i + 1)])}>
            {c.isSkipped ? '[ ] ' : '[x] '}
            <Text color="cyan">{c.where}</Text> <Text dimColor={c.isSkipped}>{c.text}</Text>
          </Button>
        ))}
      </Box>
    )
  })
}
