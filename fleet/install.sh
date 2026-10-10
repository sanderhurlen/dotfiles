#!/bin/sh
#
# fleet: link its config into ~/.config/fleet.

src="$(cd "$(dirname "$0")" && pwd)/config.toml"
dst="$HOME/.config/fleet/config.toml"
mkdir -p "$(dirname "$dst")"
if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
  exit 0
fi
if [ -e "$dst" ] || [ -L "$dst" ]; then
  mv "$dst" "$dst.backup"
  echo "  moved $dst → $dst.backup"
fi
ln -s "$src" "$dst"
echo "  linked $dst"
