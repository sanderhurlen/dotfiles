export LSCOLORS="exfxcxdxbxegedabagacad"
export CLICOLOR=true

fpath=($ZSH/functions $fpath)

autoload -U $ZSH/functions/*(:t)

# modify history
HISTFILE=~/.zsh_history
HISTSIZE=100
SAVEHIST=100

#remove the irritating % at start of a new terminal session
unsetopt PROMPT_SP;

# enables you to type the directory name you want to switch to
setopt AUTO_CD

setopt complete_aliases

# bindkey '^[^[[D' backward-word
# bindkey '^[^[[C' forward-word
# bindkey '^[[5D' beginning-of-line
# bindkey '^[[5C' end-of-line
# bindkey '^[[3~' delete-char
# bindkey '^?' backward-delete-char
