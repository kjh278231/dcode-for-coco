#!/bin/bash
# Runs probe commands under landlock_ro.py; repo = dcode-assistant (read-only probes), scratch dir for write probes.
LL="python3 $(dirname "$0")/landlock_ro.py"
REPO=/home/sds/workspace/dcode-assistant
PY=$REPO/libs/code/.venv/bin/python
W=$(mktemp -d); T=$(mktemp -d)
cd "$W"; git init -q g; echo a > g/f; git -C g add f; git -C g -c user.email=x@x -c user.name=x commit -qm init
run() { echo "--- $1"; (cd "$2" && $LL --allow-write "$T" "export TMPDIR=$T; $1"); echo "exit=$?"; }
echo "kernel=$(uname -r) python=$(python3 -V) sh=$(readlink -f /bin/sh)"
run "git status -sb" "$REPO"
run "GIT_OPTIONAL_LOCKS=0 git status -sb" "$REPO"
run "$PY -c 'import textual; print(textual.__version__)'" "$REPO"
run "python3 -c 'print(sum(range(10)))'" "$W"
run "echo hi > out.txt" "$W"
run "touch new.txt; rm -f g/f; mkdir d" "$W"
run "cat () (echo pwned > fn.txt); cat" "$W"
run "cat() { echo pwned > fn.txt; }; cat" "$W"
run "x=\"\$(echo 1 > subst.txt)\"; ls" "$W"
run "python3 -c 'import socket; print(socket.create_connection((\"1.1.1.1\", 53), 3).getpeername())'" "$W"
echo "--- same network probe inside unshare -rn (new empty net namespace) + Landlock"; (cd "$W" && unshare -rn $LL "python3 -c 'import socket; socket.create_connection((\"1.1.1.1\", 53), 3)' 2>&1 | tail -1"); echo "exit=$?"
run "git -C g log --output=gitout.txt" "$W"
run "git -C g diff --output=gitout2.txt HEAD" "$W"
run "find . -name f -exec rm {} \;" "$W"
run "sed -i s/a/b/ g/f" "$W"
run "python3 -c 'open(\"py.txt\",\"w\").write(\"x\")'" "$W"
run "ls >/dev/null 2>&1 && echo devnull-ok" "$W"
run "echo tmp > \$TMPDIR/t && cat \$TMPDIR/t" "$W"
run "rg --version >/dev/null 2>&1; sort /etc/hostname | head -1" "$W"
echo "--- open-fd inheritance (fd 3 opened before sandbox)"
(cd "$W" && exec 3>>fd.txt && $LL "echo via-fd >&3"); echo "exit=$?"
echo "=== files present after probes in scratch:"; ls -A "$W" "$W/g"; cat "$W/g/f"; cat "$W/fd.txt" 2>/dev/null
rm -rf "$W" "$T"
