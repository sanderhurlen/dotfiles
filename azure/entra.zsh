# entra (bin/entra) can't export into the shell that started it, so when it
# switches tenant it leaves the az config dir in ~/.cache/entra/shell-<pid>.
# Picked up here before the next prompt.
_entra_handoff() {
  local f=~/.cache/entra/shell-$$
  [[ -r $f ]] || return 0
  export AZURE_CONFIG_DIR="$(<$f)"
  rm -f $f
}
autoload -Uz add-zsh-hook
add-zsh-hook precmd _entra_handoff
