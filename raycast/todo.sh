#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Todo
# @raycast.mode silent
# @raycast.icon ✅
# @raycast.packageName Visense
# @raycast.argument1 { "type": "text", "placeholder": "Hva" }

# bin/todo: a file on the Desktop. Delete it when it's done.

"$HOME/.dotfiles/bin/todo" "$1" && echo "Todo: $1"
