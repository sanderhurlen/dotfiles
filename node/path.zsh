# sets up path if directory exists
if [ -d $HOME"/.npm-global" ] 
then
    export PATH=~/.npm-global/bin:$PATH
fi
