#!/bin/bash
# Same probes as metadata_socket_probe.sh but with a read-only bind mount (unshare userns) instead of Landlock.
W=$(mktemp -d); cd "$W"; echo data > f; chmod 644 f
python3 -c "
import socket
s=socket.socket(socket.AF_UNIX); s.bind('sock'); s.listen(1)
c,_=s.accept(); open('written_by_server.txt','wb').write(c.recv(100))" &
sleep 0.5
unshare --user --map-root-user --mount sh -c "mount --bind '$W' '$W' && mount -o remount,bind,ro '$W' && cd '$W' && { chmod 600 f; echo exit_chmod=\$?; touch -m f; echo exit_touch=\$?; python3 -c \"import socket; s=socket.socket(socket.AF_UNIX); s.connect('sock'); s.send(b'via-unix-socket')\"; echo exit_connect=\$?; }" 2>&1
wait; echo "mode: $(stat -c %a f)  server file: $(cat written_by_server.txt 2>&1)"
cd /; rm -rf "$W"
