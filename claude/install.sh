#!/bin/sh
#
# Claude
#
# Installs the CLI and links the versioned config into ~/.claude. Bootstrap's
# *.symlink only reaches $HOME, so ~/.claude/* is linked here instead.
#
# Not versioned on purpose (this repo is public): skills with private details
# (parkeringsfaktura), herdr's own hook, and the mail skill's config.json —
# copy config.json.example to config.json and fill it in.

if test ! "$(which claude)"
then
  echo "  Installing Claude cli for you."

  /bin/bash -c "$(curl -fsSL https://claude.ai/install.sh)"
fi

DOTFILES_CLAUDE="$(cd "$(dirname "$0")" && pwd)"

# link <path relative to claude/> — backs up a real file/dir once, then links
link () {
  src="$DOTFILES_CLAUDE/$1"
  dst="$HOME/.claude/$1"
  mkdir -p "$(dirname "$dst")"
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    return
  fi
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    mv "$dst" "$dst.backup"
    echo "  moved $dst → $dst.backup"
  fi
  ln -s "$src" "$dst"
  echo "  linked $dst"
}

link settings.json
link CLAUDE.md
for hook in "$DOTFILES_CLAUDE"/hooks/*; do link "hooks/$(basename "$hook")"; done
for skill in "$DOTFILES_CLAUDE"/skills/*/; do link "skills/$(basename "$skill")"; done

if [ ! -f "$DOTFILES_CLAUDE/skills/mail/config.json" ]; then
  echo "  mail skill: copy claude/skills/mail/config.json.example to config.json and fill it in"
fi

exit 0
