alias reload!='. ~/.zshrc'
alias reinstall="cd ~/.dotfiles; script/bootstrap"

alias cls='clear' # Good 'ol Clear Screen command

# change directory tree aliases
alias ..="cd ..; ls"
alias ...="cd ../..; ls"
alias ....="cd ../../..; ls"

# ls commands
alias ls="ls -G"
alias l.='ls -d .*' # display all contents starting with .
alias ll='ls -l'


alias python="python3";

# Web server alias
export LOCAL_IP=`ipconfig getifaddr en0`;
alias serve="browser-sync start -s -f . --no-notify --host $LOCAL_IP --port 8889";

# aliases to most visited dir
alias projects="cd ${HOME}/GitHub; ls"
alias playground="cd ${HOME}/Playground; ls"