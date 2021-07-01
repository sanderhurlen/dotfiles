if ! test $(which yarn)
  then
    echo "[NODE] Installing yarn via npm"
    npm install -g yarn
fi