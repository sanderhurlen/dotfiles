#!/bin/sh
#
# Claude

# Check for Homebrew
if test ! $(which claude)
then
  echo "  Installing Claude cli for you."

  /bin/bash -c "$(curl -fsSL https://claude.ai/install.sh)"
fi

exit 0
