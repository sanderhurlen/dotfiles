#!/bin/bash
# Stopper npm og yarn i kommandoposisjon. Heredoc-innhold og argumenter
# (f.eks. tekst som nevner «npm test») sjekkes ikke.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command')

# Fjern heredoc-kropper: alt fra linja etter <<TAG til linja som er TAG.
STRIPPED=$(echo "$COMMAND" | awk '
  tag != "" { if ($0 ~ "^[[:space:]]*" tag "[[:space:]]*$") tag = ""; next }
  {
    print
    if (match($0, /<<-?[[:space:]]*["'\'']?[A-Za-z_][A-Za-z0-9_]*/)) {
      t = substr($0, RSTART, RLENGTH)
      sub(/^<<-?[[:space:]]*["'\'']?/, "", t)
      tag = t
    }
  }')

# Kommandoposisjon: linjestart, eller etter ; & | ( $( og eventuelle mellomrom.
PATTERN='(^|[;&|(]|\$\()[[:space:]]*(npm|yarn)([[:space:]]|$)'

HIT=$(echo "$STRIPPED" | grep -m1 -oE "$PATTERN")
if [ -n "$HIT" ]; then
  TOOL=$(echo "$HIT" | grep -oE '(npm|yarn)')
  echo "BLOCKED: '$TOOL' — this project enforces pnpm. Use pnpm (pnpm install, pnpm run <script>, pnpm exec <bin>, pnpm add)." >&2
  exit 2
fi

exit 0
