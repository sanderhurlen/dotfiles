# check if node is installed
if ! test $(which node)
  then
    echo "[NODE] Installing node from brew"
    brew install node
    echo "[NODE] Preparing to install .npm-global folder in ~"
    zsh npm_global.sh
fi
