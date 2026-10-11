#!/bin/sh
#
# chores: launchd jobs — `chores sync` every day 07:00, `chores mise` Mondays 07:05.
# A job missed while the Mac sleeps runs when it wakes.

bin="$(cd "$(dirname "$0")/.." && pwd)/bin/chores"
agents="$HOME/Library/LaunchAgents"
log="$HOME/Library/Logs/chores.log"
mkdir -p "$agents"

job() { # name, StartCalendarInterval entries
  label="com.sanderhurlen.chores-$1"
  plist="$agents/$label.plist"
  new="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array><string>$bin</string><string>$1</string><string>--notify</string></array>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>StartCalendarInterval</key>
  <dict>$2</dict>
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
