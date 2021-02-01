# check if deno is installed
if ! test $(which deno)
  then
    echo "[DENO] Installing deno from brew"
    brew install deno
fi
