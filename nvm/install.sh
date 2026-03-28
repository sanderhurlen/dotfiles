#!/bin/sh

if ! test -d ~/.nvm
then
  echo "Creating ~/.nvm"
  mkdir ~/.nvm
fi

# Install nvm
if ! test -f ~/.nvm/nvm.sh
then
  echo "Installing nvm..."
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
fi

# Install latest LTS node
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

if ! nvm ls --no-colors | grep -q "lts/"
then
  echo "Installing Node LTS..."
  nvm install --lts
  nvm use --lts
  nvm alias default node
fi