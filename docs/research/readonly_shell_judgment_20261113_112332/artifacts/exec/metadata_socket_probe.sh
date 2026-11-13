#!/bin/bash
# Probes what Landlock ABI 3 (landlock_ro.py) does NOT block: metadata changes and unix-socket connect.
LL="python3 $(dirname "$0")/landlock_ro.py"
W=$(mktemp -d); cd "$W"; echo data > f; chmod 644 f; touch -d '2000-01-01' f
echo "before: $(stat -c '%a %y' f)"
$LL "chmod 600 f; touch -m f; echo exit_chmod_touch=\$?"
echo "after:  $(stat -c '%a %y' f)"
# unix socket server outside the sandbox writes whatever it receives to a file
python3 -c "
import socket,os
s=socket.socket(socket.AF_UNIX); s.bind('sock'); s.listen(1)
c,_=s.accept(); open('written_by_server.txt','wb').write(c.recv(100))" &
sleep 0.5
$LL "python3 -c \"import socket; s=socket.socket(socket.AF_UNIX); s.connect('sock'); s.send(b'via-unix-socket')\"; echo exit_connect=\$?"
wait; echo "server file: $(cat written_by_server.txt 2>&1)"
cd /; rm -rf "$W"
