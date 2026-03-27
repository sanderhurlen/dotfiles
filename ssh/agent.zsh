# Start ssh-agent only if not already running
if [ -z "$SSH_AUTH_SOCK" ]; then
  eval $(ssh-agent -s) > /dev/null
fi
