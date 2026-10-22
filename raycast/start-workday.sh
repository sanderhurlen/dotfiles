#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Start Workday
# @raycast.mode compact
# @raycast.icon 💼
# @raycast.packageName Visense

# Ghostty window: fleet in tab 1 (splits `claude agents` to its left by itself),
# tower in tab 2. `az login` / `tower login --ved-behov` open the browser only when
# the session no longer works. Whatever already runs is left alone.

running() { pgrep -f "$HOME/.dotfiles/bin/$1" >/dev/null; }

cmds=()
running fleet || cmds+=("az account get-access-token -o none 2>/dev/null || az login; fleet")
running tower || cmds+=("tower login --ved-behov && tower")

if ((${#cmds[@]})); then
  osascript - "$HOME/visense" "${cmds[@]}" <<'EOF'
on run argv
  set cwd to item 1 of argv
  set fresh to not (application "Ghostty" is running)
  tell application "Ghostty"
    activate
    if fresh then
      repeat until (count of windows) > 0
        delay 0.2
      end repeat
      set w to front window
      input text ("cd " & quoted form of cwd & " && " & item 2 of argv & linefeed) to focused terminal of selected tab of w
    else
      set w to new window with configuration {initial working directory:cwd, initial input:item 2 of argv & linefeed}
    end if
    set first_ to selected tab of w
    repeat with i from 3 to count of argv
      new tab in w with configuration {initial working directory:cwd, initial input:item i of argv & linefeed}
    end repeat
    select tab first_
  end tell
end run
EOF
fi

open -a "Microsoft Outlook"
open -a "Microsoft Teams"
