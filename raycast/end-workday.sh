#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title End Workday
# @raycast.mode compact
# @raycast.icon 🌙
# @raycast.packageName Visense

# Counterpart to start-workday.sh. Writes a todo on the Desktop summing up where the
# day ended (today's commits, unfinished worktrees, fleet agents, the fleet list),
# so tomorrow starts where today stopped. First stops fleet and tower and prunes
# finished fleet agents and worktrees, so the todo shows only what is left; then
# quits Outlook and Teams.
# Running agents are left alone; the Ghostty window stays open.

# Raycast runs with a bare PATH; claude lives in ~/.local/bin, az/uv in Homebrew.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

root="$HOME/visense"
day=$(date +%F)
note="$HOME/Desktop/Fortsett der du slapp $day.md"
midnight_ms=$(($(date -j -f '%F %T' "$day 00:00:00" +%s) * 1000))

facts() {
  echo "## Commits i dag, per repo/worktree (alle brancher)"
  for git in "$root"/*/.git; do
    # A .git file is a worktree of another repo, which lists it already.
    [[ -d $git ]] || continue
    repo=$(dirname "$git")
    git -C "$repo" worktree list --porcelain | sed -n 's/^worktree //p' | while read -r wt; do
      branch=$(git -C "$wt" branch --show-current)
      dirty=$(git -C "$wt" status --porcelain | wc -l | tr -d ' ')
      track=
      [[ -n $branch ]] && track=$(git -C "$wt" for-each-ref --format='%(upstream:track)' "refs/heads/$branch")
      log=$(git -C "$wt" log --since=midnight --author="$(git -C "$wt" config user.email)" --format='  - %s' HEAD)
      # Only today's work, uncommitted files or unpushed commits; behind or [gone] alone is not left over.
      [[ -z $log && $dirty == 0 && $track != *ahead* ]] && continue
      echo "### ${wt#"$root"/} ($branch) · ${dirty} uncommitted filer ${track:+· $track}"
      echo "$log"
    done
  done
  echo
  echo "## Claude-agenter startet i dag"
  claude agents --json --all 2>/dev/null |
    jq -r --argjson t "$midnight_ms" '.[] | select(.startedAt >= $t) | "- \(.name) · \(.state) · \(.cwd)"'
  echo
  echo "## fleet-lista nå"
  cat "$HOME/.cache/fleet/screen.txt" 2>/dev/null
}

# fleet's caffeinate is tied to its pid (-w), so it ends with fleet.
pkill -TERM -f "$HOME/.dotfiles/bin/fleet"
pkill -TERM -f "$HOME/.dotfiles/bin/tower"
"$HOME/.dotfiles/bin/fleet" prune >/dev/null 2>&1
"$HOME/.dotfiles/bin/fleet" clean >/dev/null 2>&1

data=$(facts)
prompt="Under er rådata fra arbeidsdagen min ($day). Skriv en kort todo på norsk i Markdown \
som lar meg fortsette der jeg slapp i morgen: 1) hva jeg fikk gjort i dag, 2) hva som er \
halvferdig og hvor (repo, branch, worktree, agent som er blocked/running, uncommitted/upushet), \
3) forslag til første steg i morgen. Bare fakta fra dataene, ingen innledning, maks ~30 linjer."
claude -p --model sonnet "$prompt" <<<"$data" >"$note" 2>/dev/null || printf '%s\n' "$data" >"$note"

running=$(claude agents --json 2>/dev/null | jq '[.[] | select(.state == "running")] | length')
((running)) || running=

osascript -e 'quit app "Microsoft Outlook"' -e 'quit app "Microsoft Teams"' 2>/dev/null

echo "Todo på skrivebordet · fleet+tower stoppet${running:+ · $running agenter kjører fortsatt}"
