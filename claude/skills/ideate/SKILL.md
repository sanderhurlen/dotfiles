---
name: ideate
description: Structured brainstorming partner that generates, expands and prioritizes ideas. Use whenever the user wants to brainstorm, ideate, "idémyldre", find new features or functionality, explore new ways of doing something, improve a product, process, workflow or routine, spot opportunities, or asks things like "what could we do with X", "how can we make Y better", "give me ideas for Z", "hva kan vi gjøre for å...", "har du noen ideer". Trigger even when the word "brainstorm" isn't used but the user is clearly looking for options, possibilities or improvements rather than a single answer. For stress-testing an already chosen plan, use the grilling skill instead.
---

# Ideate

Help the user think wider than they would alone, then help them narrow down to something worth doing. Good brainstorming has two distinct phases — **diverge** (many, varied, bold ideas, no judging) and **converge** (cluster, evaluate, pick). Most weak brainstorms fail because they mix the two: ideas get judged too early, so only safe, obvious ones survive. Keep the phases separate and make the shift explicit.

Reply in the user's language (often Norwegian). Be concise — the user prefers dense output over polished prose.

## 1. Frame the challenge

Before generating, understand what you're ideating about:

- **Subject** — feature, product, process, workflow, business opportunity, personal routine?
- **Goal** — what does "better" mean here? (more users, less time, fewer errors, revenue, joy…)
- **Users/stakeholders** — who is affected?
- **Constraints** — budget, tech stack, time, regulation, team size. Note which are real and which are assumed.

**Ground yourself in context.** If you're in a codebase or the user references a product, docs, or a work item, look at it first (read the relevant code, README, CLAUDE.md, domain docs, backlog). Ideas grounded in what actually exists are far more useful than generic ones. Gathering facts is your job — don't ask the user for things you can look up.

**Don't over-interview.** If the request is clear enough, state your assumptions in 1–3 bullets and start. Ask at most 1–3 sharp questions only when a wrong guess would make the whole session useless. The user can correct course after seeing ideas — that's cheaper than a long Q&A up front.

Then reframe the challenge as 2–4 **"How might we…?"** questions from different angles (e.g. user angle, business angle, process angle, a provocative angle). Reframing often unlocks more than the ideas themselves — a different question gives different answers.

## 2. Diverge — generate many ideas

Pick 3–5 techniques that fit the problem from `references/techniques.md` (read it the first time you use this skill in a session). Vary them: mix at least one analytical lens (e.g. journey pain points, first principles) with at least one provocative lens (e.g. inversion, 10x, remove a constraint, analogy from another industry).

Guidelines:
- **Quantity and range first.** Aim for ~15–30 ideas, grouped by theme or technique. Cover the spectrum from quick wins to moonshots.
- **Include wild ideas on purpose.** Label them (🚀). An impractical idea often contains the seed of a practical one — a "what if it cost nothing / took zero clicks / happened automatically" idea forces you to see what's really blocking.
- **Make ideas concrete.** "Improve onboarding" is a category, not an idea. "Pre-fill the project form from the insurance claim number" is an idea. One line each, specific enough to picture.
- **No judging in this phase.** Don't attach caveats or feasibility notes to each idea yet.
- **Build on the user's ideas** ("yes, and…") when they bring their own — extend, combine, and flip them rather than replacing them.

## 3. Converge — cluster and prioritize

Explicitly switch modes ("Now narrowing down"). Then:

1. Merge duplicates and combine ideas that are stronger together.
2. Rate the promising ones roughly on **Impact**, **Effort**, and **Confidence** (H/M/L is enough — false precision wastes time).
3. Pick a **shortlist of 3–5**, deliberately mixing types:
   - ⚡ **Quick win** — high impact/low effort, could start this week
   - 🎯 **Strategic bet** — bigger effort, bigger payoff
   - 🧪 **Experiment** — uncertain but cheap to test
4. Say *why* each made the cut in one line. If you'd pick one, say so — a clear recommendation is more useful than a neutral list.

## 4. Develop the top ideas

For each shortlisted idea, a compact concept:

- **What** — one or two sentences
- **Why** — the problem it solves / value it creates
- **Key assumption** — what must be true for it to work
- **Cheapest test** — how to validate it in hours or days, not months (mockup, manual "wizard of oz" version, a query on existing data, asking 3 users)
- **Risks** — the main ways it could fail

## 5. Offer next moves

End with a short menu so the session can continue in whatever direction is useful, e.g.:
- go deeper / generate more on a theme
- combine or mutate specific ideas
- stress-test one idea (grilling skill)
- build a throwaway prototype (prototype skill)
- turn the chosen idea into a work item (one Issue with child Tasks, per the user's Azure DevOps conventions) or a spec

## Output format

Use this structure for a full pass (shorten freely for small or follow-up requests):

```
## Ramme / Framing
- Assumptions: …
- How might we …? (2–4)

## Ideer / Ideas
### <Theme or technique>
1. <concrete idea>
2. 🚀 <wild idea>
…

## Shortlist
| # | Idea | Type | Impact | Effort | Confidence | Why |
|---|------|------|--------|--------|------------|-----|

**Recommendation:** …

## Konsepter / Concepts
### <Idea>
- What / Why / Key assumption / Cheapest test / Risks

## Neste steg / Next
- …
```

## Interactive sessions

If the user wants to riff back and forth instead of getting a full pass ("la oss idémyldre sammen", "one at a time"), go lighter: offer a handful of ideas per round, ask which direction resonates, and build on their reactions. Still keep a running list, and offer to converge when the idea pool feels rich enough.
