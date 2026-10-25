#!/bin/sh
#
# Links ssh/config to $HOME/.ssh/config — backs up a real file once.

src="$(cd "$(dirname "$0")" && pwd)/config"
dst="$HOME/.ssh/config"
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
