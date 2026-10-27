#!/bin/sh
#
# chores: launchd jobs — `chores sync` every day 07:00, `chores mise` Mondays 07:05,
# `wp upkeep -A` (pipeline warnings → Issue, Task and fleet agent per repo) every day 13:00.
# A job missed while the Mac sleeps runs when it wakes.

root="$(cd "$(dirname "$0")/.." && pwd)"
agents="$HOME/Library/LaunchAgents"
log="$HOME/Library/Logs/chores.log"
mkdir -p "$agents"

job() { # name, StartCalendarInterval entries, program and args (default: chores <name> --notify)
  label="com.sanderhurlen.chores-$1"
  plist="$agents/$label.plist"
  name=$1 when=$2
  shift 2
  [ $# -gt 0 ] || set -- "$root/bin/chores" "$name" --notify
  args=""
  for a in "$@"; do args="$args<string>$a</string>"; done
  # ~/.local/bin: claude, for the agents wp upkeep starts
  new="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>$args</array>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>StartCalendarInterval</key>
  <dict>$when</dict>
  <key>StandardOutPath</key><string>$log</string>
  <key>StandardErrorPath</key><string>$log</string>
</dict>
</plist>"
  if [ -f "$plist" ] && [ "$(cat "$plist")" = "$new" ]; then
    return
  fi
  printf '%s\n' "$new" > "$plist"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null
  launchctl bootstrap "gui/$(id -u)" "$plist"
  echo "  loaded $label"
}

job sync "<key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer>"
job mise "<key>Weekday</key><integer>1</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>5</integer>"
job pipelines "<key>Hour</key><integer>13</integer><key>Minute</key><integer>0</integer>" "$root/bin/wp" upkeep -A --notify
