#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Nytt Work Item
# @raycast.mode compact
# @raycast.icon 📌
# @raycast.packageName Visense
# @raycast.argument1 { "type": "text", "placeholder": "Tittel" }
# @raycast.argument2 { "type": "dropdown", "placeholder": "Type", "optional": true, "data": [{"title": "Issue", "value": "Issue"}, {"title": "Bug", "value": "Bug"}, {"title": "Task", "value": "Task"}] }

# `wi new` assigned to me, Issue unless another type is picked. The link goes to the
# clipboard, so a description or parent can be added right away.

# Raycast runs with a bare PATH; claude lives in ~/.local/bin, az/uv in Homebrew.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

err=$(mktemp)
trap 'rm -f "$err"' EXIT
if ! out=$("$HOME/.dotfiles/bin/wi" new "$1" -t "${2:-Issue}" -a @me 2>"$err"); then
  tail -1 "$err"
  exit 1
fi
# out: «✓ #9400 Issue · …  https://dev.azure.com/…»
printf '%s' "${out##* }" | pbcopy
echo "${out%%  http*} · lenke kopiert"
