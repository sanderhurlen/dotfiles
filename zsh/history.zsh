HISTFILE="$HOME/.zsh_history"
HISTSIZE=50000
SAVEHIST=50000

setopt EXTENDED_HISTORY       # record timestamp with each command
setopt HIST_EXPIRE_DUPS_FIRST # expire duplicates first when trimming
setopt HIST_IGNORE_DUPS       # don't record consecutive duplicates
setopt HIST_IGNORE_SPACE      # don't record commands starting with a space
setopt HIST_VERIFY            # show expanded history before executing
setopt SHARE_HISTORY          # share history across sessions
