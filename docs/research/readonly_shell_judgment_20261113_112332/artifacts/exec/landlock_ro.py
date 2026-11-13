#!/usr/bin/env python3
"""Run `sh -c CMD` with the whole filesystem read-only via Landlock (ABI >= 1).

Usage: landlock_ro.py [--allow-write DIR]... CMD
Writable exceptions: /dev/null, /dev/tty, and any --allow-write DIR (e.g. a private TMPDIR).
Network is NOT restricted (Landlock ABI < 4 has no network rights; ABI 4 only TCP bind/connect).
"""
import ctypes
import os
import sys

SYS_create, SYS_add, SYS_restrict = 444, 445, 446  # x86_64
PR_SET_NO_NEW_PRIVS = 38
EXECUTE, WRITE_FILE, READ_FILE, READ_DIR = 1, 2, 4, 8
WRITE_ACCESS = WRITE_FILE
for bit in range(4, 13):  # REMOVE_DIR .. MAKE_SYM
    WRITE_ACCESS |= 1 << bit
REFER, TRUNCATE = 1 << 13, 1 << 14

libc = ctypes.CDLL(None, use_errno=True)
libc.syscall.restype = ctypes.c_long


def _check(ret, what):
    if ret < 0:
        err = ctypes.get_errno()
        raise OSError(err, f"{what}: {os.strerror(err)}")
    return ret


def restrict(writable):
    abi = _check(libc.syscall(SYS_create, None, ctypes.c_size_t(0), ctypes.c_uint32(1)), "abi")
    handled = WRITE_ACCESS | (REFER if abi >= 2 else 0) | (TRUNCATE if abi >= 3 else 0)
    attr = ctypes.c_uint64(handled)  # struct landlock_ruleset_attr, fs field only
    rfd = _check(libc.syscall(SYS_create, ctypes.byref(attr), ctypes.c_size_t(8), ctypes.c_uint32(0)), "create")

    class PathBeneath(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]

    for path in writable:
        fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
        file_ok = WRITE_FILE | (TRUNCATE if abi >= 3 else 0)
        allowed = handled if os.path.isdir(path) else file_ok
        rule = PathBeneath(allowed, fd)
        _check(libc.syscall(SYS_add, rfd, 1, ctypes.byref(rule), 0), f"add_rule {path}")
        os.close(fd)
    _check(libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0), "no_new_privs")
    _check(libc.syscall(SYS_restrict, rfd, 0), "restrict_self")
    os.close(rfd)
    return abi


def main(argv):
    writable = ["/dev/null"] + (["/dev/tty"] if os.path.exists("/dev/tty") else [])
    while len(argv) > 2 and argv[0] == "--allow-write":
        writable.append(argv[1])
        argv = argv[2:]
    restrict(writable)
    os.execv("/bin/sh", ["sh", "-c", argv[0]])


if __name__ == "__main__":
    main(sys.argv[1:])
