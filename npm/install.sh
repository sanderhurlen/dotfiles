#!/bin/sh
#
# ~/.npmrc holds a token, so it's copied from the example, not linked.

if [ ! -f "$HOME/.npmrc" ]; then
  cp "$(cd "$(dirname "$0")" && pwd)/npmrc.example" "$HOME/.npmrc"
  echo "  ~/.npmrc: replace NPM_TOKEN with an Azure Artifacts PAT"
fi
