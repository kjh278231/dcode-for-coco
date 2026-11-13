#!/usr/bin/env python3
"""Prototype pre-plan launcher: run `sh -c CMD` where no write can reach the host.

user+mount+net namespaces (identity uid map) -> private propagation -> tmpfs over /run
(hides systemd/dbus/docker/WSL interop sockets) -> mount_setattr(AT_RECURSIVE, RDONLY) on / ->
fresh writable tmpfs on /tmp (scratch, discarded) -> seccomp: socket(AF_UNIX) and io_uring_setup
return EPERM (pathname unix sockets are not stopped by a read-only mount) -> exec /bin/sh -c CMD.
Fails closed: any setup error exits 125 before the command runs.
"""
import ctypes, os, sys

libc = ctypes.CDLL(None, use_errno=True)
libc.syscall.restype = ctypes.c_long
SYS_mount_setattr, AT_FDCWD, AT_RECURSIVE, MOUNT_ATTR_RDONLY = 442, -100, 0x8000, 0x1
MS_REC, MS_PRIVATE = 0x4000, 1 << 18


class MountAttr(ctypes.Structure):
    _fields_ = [("attr_set", ctypes.c_uint64), ("attr_clr", ctypes.c_uint64),
                ("propagation", ctypes.c_uint64), ("userns_fd", ctypes.c_uint64)]


def _ok(ret, what):
    if ret != 0:
        e = ctypes.get_errno()
        raise OSError(e, f"{what}: {os.strerror(e)}")


def mount(src, tgt, fstype, flags, data=None):
    _ok(libc.mount(src, tgt, fstype, ctypes.c_ulong(flags), data), f"mount {tgt!r}")


def deny_unix_sockets():
    """seccomp-bpf: socket(AF_UNIX, ...) and io_uring_setup -> EPERM; x86_64 only."""
    import struct
    AUDIT_ARCH_X86_64, SYS_socket, SYS_io_uring_setup, AF_UNIX = 0xC000003E, 41, 425, 1
    RET_ALLOW, RET_KILL, RET_EPERM = 0x7FFF0000, 0x80000000, 0x00050000 | 1
    LD, JEQ, JGE, RET = 0x20, 0x15, 0x35, 0x06  # BPF_LD|W|ABS, BPF_JMP|JEQ|K, BPF_JMP|JGE|K, BPF_RET|K
    prog = [
        (LD, 0, 0, 4), (JEQ, 1, 0, AUDIT_ARCH_X86_64), (RET, 0, 0, RET_KILL),  # arch check
        (LD, 0, 0, 0),                                                        # nr
        (JGE, 0, 1, 0x40000000), (RET, 0, 0, RET_KILL),                       # x32 ABI numbers
        (JEQ, 0, 1, SYS_io_uring_setup), (RET, 0, 0, RET_EPERM),
        (JEQ, 0, 3, SYS_socket),
        (LD, 0, 0, 16),                                                       # args[0] low 32 bits
        (JEQ, 0, 1, AF_UNIX), (RET, 0, 0, RET_EPERM),
        (RET, 0, 0, RET_ALLOW),
    ]
    buf = ctypes.create_string_buffer(b"".join(struct.pack("HBBI", *i) for i in prog))
    class SockFprog(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.c_void_p)]
    fprog = SockFprog(len(prog), ctypes.addressof(buf))
    PR_SET_NO_NEW_PRIVS, PR_SET_SECCOMP, SECCOMP_MODE_FILTER = 38, 22, 2
    _ok(libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0), "no_new_privs")
    _ok(libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(fprog), 0, 0), "seccomp")


def setup():
    uid, gid = os.getuid(), os.getgid()
    os.unshare(os.CLONE_NEWUSER | os.CLONE_NEWNS | os.CLONE_NEWNET)
    with open("/proc/self/setgroups", "w") as f:
        f.write("deny")
    with open("/proc/self/uid_map", "w") as f:
        f.write(f"{uid} {uid} 1")
    with open("/proc/self/gid_map", "w") as f:
        f.write(f"{gid} {gid} 1")
    mount(b"none", b"/", None, MS_REC | MS_PRIVATE)
    mount(b"tmpfs", b"/run", b"tmpfs", 0, b"size=1m")
    attr = MountAttr(MOUNT_ATTR_RDONLY, 0, 0, 0)
    _ok(libc.syscall(SYS_mount_setattr, AT_FDCWD, b"/", AT_RECURSIVE, ctypes.byref(attr), ctypes.sizeof(attr)), "mount_setattr")
    mount(b"tmpfs", b"/tmp", b"tmpfs", 0, b"size=256m")
    deny_unix_sockets()


if __name__ == "__main__":
    cwd = os.getcwd()
    try:
        setup()
        os.chdir(cwd)
    except OSError as e:
        print(f"ro_launcher: sandbox setup failed, refusing to run: {e}", file=sys.stderr)
        sys.exit(125)
    os.environ["TMPDIR"] = "/tmp"
    os.setsid()  # drop the controlling terminal (TIOCSTI keystroke injection into the caller's TUI)
    os.execv("/bin/sh", ["sh", "-c", sys.argv[1]])
