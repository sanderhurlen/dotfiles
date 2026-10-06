#!/bin/bash

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command')

BLOCKED_PATTERNS=(
  "^npm "
  " npm "
  "&&npm "
  "&&\ npm "
  ";npm "
  ";\ npm "
  "^yarn "
  " yarn "
  "&&yarn "
  "&&\ yarn "
  ";yarn "
  ";\ yarn "
)

for pattern in "${BLOCKED_PATTERNS[@]}"; do
  if echo "$COMMAND" | grep -qE "$pattern"; then
    echo "BLOCKED: '$COMMAND' uses npm/yarn. This project enforces pnpm. Use 'pnpm' instead (e.g. 'pnpm install', 'pnpm run', 'pnpm add')." >&2
    exit 2
  fi
done

exit 0
