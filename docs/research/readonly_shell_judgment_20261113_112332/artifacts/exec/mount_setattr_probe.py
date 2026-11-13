#!/usr/bin/env python3
"""In a new user+mount(+net) namespace, make every mount read-only recursively with
mount_setattr(AT_RECURSIVE, MOUNT_ATTR_RDONLY), hide /run/WSL, then run `sh -c CMD`."""
import ctypes, os, sys
libc = ctypes.CDLL(None, use_errno=True)
libc.syscall.restype = ctypes.c_long
SYS_mount_setattr, AT_RECURSIVE, MOUNT_ATTR_RDONLY = 442, 0x8000, 0x1
class MountAttr(ctypes.Structure):
    _fields_ = [("attr_set", ctypes.c_uint64), ("attr_clr", ctypes.c_uint64), ("propagation", ctypes.c_uint64), ("userns_fd", ctypes.c_uint64)]
uid, gid = os.getuid(), os.getgid()
os.unshare(os.CLONE_NEWUSER | os.CLONE_NEWNS | os.CLONE_NEWNET)
open("/proc/self/setgroups", "w").write("deny")
open("/proc/self/uid_map", "w").write(f"{uid} {uid} 1")
open("/proc/self/gid_map", "w").write(f"{gid} {gid} 1")
def mount(src, tgt, fstype, flags, data=None):
    if libc.mount(src, tgt, fstype, ctypes.c_ulong(flags), data) != 0:
        e = ctypes.get_errno(); raise OSError(e, f"mount {tgt}: {os.strerror(e)}")
MS_REC, MS_PRIVATE = 0x4000, 1 << 18
mount(b"none", b"/", None, MS_REC | MS_PRIVATE)
if os.path.isdir("/run/WSL"):
    mount(b"tmpfs", b"/run/WSL", b"tmpfs", 0)  # hide WSL interop sockets
tmp = os.environ.get("RO_TMP")
attr = MountAttr(MOUNT_ATTR_RDONLY, 0, 0, 0)
if libc.syscall(SYS_mount_setattr, -100, b"/", AT_RECURSIVE, ctypes.byref(attr), ctypes.sizeof(attr)) != 0:
    e = ctypes.get_errno(); raise OSError(e, f"mount_setattr: {os.strerror(e)}")
if tmp:  # one writable scratch dir, mounted after the recursive RDONLY
    mount(b"tmpfs", tmp.encode(), b"tmpfs", 0)
os.execv("/bin/sh", ["sh", "-c", sys.argv[1]])
