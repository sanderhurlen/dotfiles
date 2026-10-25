#!/bin/sh

if ! command -v mise >/dev/null 2>&1
then
  echo "Installing mise..."
  curl https://mise.run | sh
fi

src="$(cd "$(dirname "$0")" && pwd)/config.toml"
dst="$HOME/.config/mise/config.toml"
mkdir -p "$(dirname "$dst")"
if ! { [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; }; then
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    mv "$dst" "$dst.backup"
    echo "  moved $dst → $dst.backup"
  fi
  ln -s "$src" "$dst"
  echo "  linked $dst"
fi
