// pr-utkast — the review draft a fleet agent writes (`wr draft`), above the prompt: its
// summary, buttons to switch the vote and to post, and a pane to pick which comments go
// out; /post and /utkast do the same from the prompt. The PR comes from the session's
// directory (fleet's worktree fleet-pr-<id>-review or -rereview), or `/utkast <id>` binds
// one. Everything about the draft — where it lives, what it says, posting it — is `wr`'s;
// this only shows what `wr draft --line` reports and runs `wr`.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Draft } from '../types'

const pr = atom({ plugin: 'pr-utkast', key: 'pr' } as const, null)
// the tag declines a draft stored by the version before vote and comments were kept
const draft = atom({ plugin: 'pr-utkast', key: 'draft' } as const, null, { shape: 'draft-2' })
const isConfirming = atom({ plugin: 'pr-utkast', key: 'isConfirming' } as const, false)

const PANE = 'pr-utkast'
const FLEET_REVIEW = /fleet-pr-(\d+)-(?:re)?review/
const VOTES = [
  ['approve', 'approve', 'a'],
  ['suggestions', 'forslag', 'f'],
  ['wait', 'vent', 'v'],
  ['reject', 'reject', 'r'],
] as const

type Line = { line: string; posted: boolean; vote: string; comments: { where: string; text: string; skip: boolean }[] }

async function wr($: EngineInterface, args: string[]) {
  const { exitCode, stdout, stderr } = await $.process.run(['wr', ...args], { timeoutMs: 60_000 })

  return { isOk: exitCode === 0, text: (exitCode === 0 ? stdout : stderr || stdout).trim() }
}

async function refresh($: EngineInterface) {
  const id = await read($, pr)
  if (id === null) {
    return
  }
  const { isOk, text } = await wr($, ['draft', String(id), '--line'])
  const found = isOk ? (JSON.parse(text) as Line | null) : null
  const next: Draft | null = found && {
    id,
    line: found.line,
    isPosted: found.posted,
    vote: found.vote,
    comments: found.comments.map(c => ({ where: c.where, text: c.text, isSkipped: c.skip })),
  }
  await update($, draft, () => next)
}

// one `wr draft` change, then the redraw; a refusal shows as a toast
async function edit($: EngineInterface, args: string[]) {
  const id = await read($, pr)
  if (id === null) {
    return
  }
  const { isOk, text } = await wr($, ['draft', String(id), ...args])
  if (!isOk) {
    $.ui.toast(text)
  }
  await refresh($)
}

async function post($: EngineInterface) {
  const id = await read($, pr)
  await update($, isConfirming, () => false)
  if (id === null) {
    return { isOk: false, text: 'Ingen PR i denne økta — /utkast <id> først.' }
  }
  const result = await wr($, ['post', String(id)])
  await refresh($)

  return result
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'post', description: 'Post review-utkastet (kommentarer og stemme) til PR-en' })
    await $.command.register({ name: 'utkast', description: 'Vis review-utkastet; /utkast <id> velger PR' })
    const found = FLEET_REVIEW.exec(await $.session.cwd())
    if (found && (await read($, pr)) === null) {
      await update($, pr, () => Number(found[1]))
    }
    await refresh($)

    return next(e)
  })

  // the agent writes and rewrites the draft during its turns
  on('turn.complete', async ($, e, next) => {
    await refresh($)

    return next(e)
  })

  on('command.run', { command: 'utkast' }, async ($, e) => {
    const id = e.args.trim()
    if (/^\d+$/.test(id)) {
      await update($, pr, () => Number(id))
      await refresh($)
    }
    const current = await read($, pr)
    if (current === null) {
      return { text: 'Ingen PR i denne økta — /utkast <id>.' }
    }
    const { text } = await wr($, ['draft', String(current)])

    return { text }
  })

  on('command.run', { command: 'post' }, async $ => {
    const { isOk, text } = await post($)

    return isOk ? { text, context: [`Jeg postet review-utkastet: ${text}`] } : { text }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const d = await read($, draft)
    if (e.props.hasSurvey || d === null) {
      return next(e)
    }
    const { Box, Button, Text } = $.ui.resolve(e)
    if (d.isPosted) {
      return (
        <Box>
          <Text dimColor>📝 !{d.id} {d.line}</Text>
        </Box>
      )
    }
    if (await read($, isConfirming)) {
      return (
        <Box gap={1}>
          <Text color="yellow">Post på !{d.id}: {d.line}?</Text>
          <Button
            key="yes"
            label="Ja, post"
            hotkey="j"
            onPress={async () => {
              const { text } = await post($)
              $.ui.toast(text)
            }}
          />
          <Button key="no" label="Avbryt" hotkey="n" onPress={() => update($, isConfirming, () => false)} />
        </Box>
      )
    }

    return (
      <Box flexDirection="column">
        <Text>📝 !{d.id} utkast: {d.line}</Text>
        <Box gap={1}>
          <Button key="post" label="Post" hotkey="p" onPress={() => update($, isConfirming, () => true)} />
          <Button
            key="comments"
            label={`Kommentarer (${d.comments.length})`}
            hotkey="k"
            onPress={() => $.ui.open({ id: PANE, title: `!${d.id} kommentarer` })}
          />
          <Text dimColor>stemme:</Text>
          {VOTES.map(([vote, label, key]) => (
            <Button
              key={`vote-${vote}`}
              label={d.vote === vote ? `[${label}]` : label}
              hotkey={key}
              onPress={() => edit($, ['--vote', vote])}
            />
          ))}
        </Box>
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const d = await read($, draft)
    if (d === null || d.comments.length === 0) {
      return <Text dimColor>Ingen kommentarer i utkastet.</Text>
    }

    return (
      <Box flexDirection="column" gap={1}>
        <Text dimColor>Trykk på en kommentar for å ta den med eller hoppe over den.</Text>
        {d.comments.map((c, i) => (
          <Button key={`comment-${i + 1}`} onPress={() => edit($, ['--skip', String(i + 1)])}>
            {c.isSkipped ? '[ ] ' : '[x] '}
            <Text color="cyan">{c.where}</Text> <Text dimColor={c.isSkipped}>{c.text}</Text>
          </Button>
        ))}
      </Box>
    )
  })
}
