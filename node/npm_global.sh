#!/bin/sh
#
# creates a global folder for installing npm packages globally without getting permission
# error or using sudo.
#
# @author Sander Hurlen
#

if [ -d $HOME"/.npm-global" ] 
then
    echo "Directory  exists." 
else
    echo "Directory ~/.npm-global does not exists."
    echo "creating a new folder.."
    # create new directory
    mkdir ~/.npm-global

    # configure npm to use the new directory path
    npm config set prefix '~/.npm-global'

    # add to your path
    #export PATH=~/.npm-global/bin:$PATH
fi




