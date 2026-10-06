#!/bin/sh
#
# Azure CLI extensions. The CLI itself comes from the Brewfile.

if test "$(which az)" && ! az extension show --name azure-devops >/dev/null 2>&1
then
  echo "  Installing az azure-devops extension for you."
  az extension add --name azure-devops --only-show-errors
fi

exit 0
