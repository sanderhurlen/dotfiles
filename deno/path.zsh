# sets up path if directory exists
if [ -d $HOME"/.deno" ] 
then
    export PATH=$HOME/.deno/bin:$PATH
fi
