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

# aliases to most visited dir
alias projects="cd ${HOME}/GitHub; ls"
alias playground="cd ${HOME}/Playground; ls"