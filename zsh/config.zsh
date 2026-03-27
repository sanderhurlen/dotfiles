export LSCOLORS="exfxcxdxbxegedabagacad"
export CLICOLOR=true

fpath=($ZSH/functions $fpath)

autoload -U $ZSH/functions/*(:t)

# modify history
HISTFILE=~/.zsh_history
HISTSIZE=10000
SAVEHIST=10000

#remove the irritating % at start of a new terminal session
unsetopt PROMPT_SP;

# enables you to type the directory name you want to switch to
setopt AUTO_CD

setopt complete_aliases

# bindkey '^[[5D' beginning-of-line
# bindkey '^[[5C' end-of-line
# bindkey '^[[3~' delete-char
# bindkey '^?' backward-delete-char

bindkey "^[b" backward-word        # alt+left       - move back one word
bindkey "^[f" forward-word         # alt+right      - move forward one word
bindkey "^[^?" backward-kill-word  # alt+backspace  - delete word back
bindkey "^[d" kill-word            # alt+d          - delete word forward
bindkey "^A" beginning-of-line     # ctrl+a         - jump to start of line
bindkey "^E" end-of-line           # ctrl+e         - jump to end of line
bindkey "^K" kill-line             # ctrl+k         - delete from cursor to end
bindkey "^xe" edit-command-line    # ctrl+x e       - open current command in $EDITOR