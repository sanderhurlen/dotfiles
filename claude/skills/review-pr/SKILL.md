---
name: review-pr
description: >
    Review a pull request (Azure DevOps or GitHub) into a draft I go through before anything is posted,
    and post its comments, replies and vote when I say so. Use when the user asks to review, check or look
    at a PR, gives a PR number/URL, or wants to post or reply in a PR's threads.
argument-hint: '[pr-number | url]'
allowed-tools: Bash, Read, Grep, Glob, Skill
---

# PR review

A review is a **draft**: what the PR is meant to solve, whether it solves it, comments, a vote. I read it,
we adjust it together, and it is posted when I say so. Talk to me in Norwegian.

## 1. Resolve the PR

From `$ARGUMENTS`: a number (`42`, `!42`, `#42`) or a URL. None given: the PR whose source branch is the
current branch; else list my open review requests and ask.

Platform from `git remote get-url origin`: `dev.azure.com` → Azure DevOps (`wr`, `az repos`), `github.com`
→ GitHub (`gh`).

## 2. Read what it is meant to solve

The **goal** comes from the spec, not the code: the PR's title and description, and every work item it links
(ADO: `az repos pr work-item list --id <id>`, then `wi show <wi>` for each; GitHub: issues the body closes).
Done when you can say, in 2–4 sentences, the problem, for whom, and what is different once it is merged.
No spec at all: say so in the goal, and skip the Spec axis below.

## 3. Review

Check out the source in a worktree, unless you already stand in one (a fleet agent's directory):
`git fetch origin <source> <target>` and `git worktree add --detach .claude/worktrees/pr-<id> origin/<source>`.

Run `/code-review` there with `origin/<target>` as the fixed point and the goal's work items as spec. Then
weigh every finding against the goal: does the PR solve it — **ja**, **delvis** or **nei** — and what is
missing or solved differently.

ADO: read the existing threads too (`wr threads <id>`). A thread of mine the code now fixes goes in
`resolve`; one whose answer doesn't hold gets a `replies` entry.

## 4. Write the draft

ADO: write the draft exactly as `wr draft <id> --format` describes — `goal`, `summary` opening with
ja/delvis/nei, comments to the author, a vote, and my open decisions as `questions`. `wr draft <id>` shows it
back; outside a fleet worktree, tell me `/utkast <id>` puts it above the prompt with Post and vote
buttons. GitHub: the same fields in the chat.

Report here in this order: the goal, ja/delvis/nei with why, the findings, then the questions.

## 5. Adjust and post

My changes ("drop 2", "softer on 3", "vote wait", "reply in thread 812: …") go into the draft: rewrite the
whole file, or `wr draft <id> --skip N` / `--vote V`.

Posting waits for my explicit go ("post", "send it"):

- ADO: `wr post <id>` (`--again` after a new round). It posts each comment as a thread, inline at file:line,
  then replies and resolves, then my vote. Show me its one-line result.
- GitHub: one review via `gh api repos/{owner}/{repo}/pulls/<n>/reviews` with `event=COMMENT` and the
  comments inline; the vote stays with me.

A reply or comment I ask for after the draft is posted is a new draft holding only that (keep `goal`,
vote `none`), posted with `wr post <id> --again` — `--again` posts the whole file, so what was posted
before must be out of it.

## Comments

- Specific and actionable, with why: "null when the customer has no address (line 42)", in the PR's language.
- Findings that change behaviour, correctness, security or the goal. Formatting only when it breaks
  the codebase's convention.
- Point at the existing pattern when suggesting another way, and name what is done well.
