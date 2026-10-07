#!/bin/sh
#
# Azure CLI extensions. The CLI itself comes from the Brewfile.

if test "$(which az)" && ! az extension show --name azure-devops >/dev/null 2>&1
then
  echo "  Installing az azure-devops extension for you."
  az extension add --name azure-devops --only-show-errors
fi

# pg-token every 30 minutes, so ~/.pgpass always holds a live Entra token.
# Only on machines that have servers configured (see `pg-token --help`).
label="com.sanderhurlen.pg-token"
plist="$HOME/Library/LaunchAgents/$label.plist"
if test -f "$HOME/.config/pg-token/hosts"
then
  echo "  Scheduling pg-token every 30 minutes."
  mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
  cat >"$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array><string>$HOME/.dotfiles/bin/pg-token</string></array>
  <key>StartInterval</key><integer>1800</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/pg-token.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/pg-token.log</string>
</dict>
</plist>
PLIST
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist"
fi

exit 0
