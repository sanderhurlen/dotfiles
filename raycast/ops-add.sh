#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Ops Innspill
# @raycast.mode compact
# @raycast.icon 🗂️
# @raycast.packageName Visense
# @raycast.argument1 { "type": "text", "placeholder": "Innspill (t: tiltak, n: notat)" }

# `ops add` puts the line in its queue and returns at once; the worker sorts it onto
# the board and makes tiltak ADO issues. `ops kø` shows how far it has come.

# Raycast runs with a bare PATH; claude lives in ~/.local/bin, az/uv in Homebrew.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

"$HOME/.dotfiles/bin/ops" add "$1" >/dev/null 2>&1 && echo "I kø: $1" || { echo "ops add feilet"; exit 1; }
