#!/bin/sh

if ! command -v mise >/dev/null 2>&1
then
  echo "Installing mise..."
  curl https://mise.run | sh
fi
