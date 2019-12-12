alias reload!='. ~/.zshrc'

alias cls='clear' # Good 'ol Clear Screen command

# change directory tree aliases
alias ..="cd ..; ls"
alias ...="cd ../..; ls"
alias ....="cd ../../..; ls"



alias python="python3";

# Web server alias
export LOCAL_IP=`ipconfig getifaddr en0`;
alias serve="browser-sync start -s -f . --no-notify --host $LOCAL_IP --port 8889";