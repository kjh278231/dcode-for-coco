"""[F7] 계획 승인 전 `execute`를 읽기 전용 네임스페이스 샌드박스에서 돌린다.

이 파일은 모듈이면서 런처다. 게이트는 `wrap_command`로 명령을
`<python> -I <이 파일> <명령>`으로 바꾼다. 런처는 표준 라이브러리만 쓰고
패키지를 import하지 않는다(`-I`라 스크립트 폴더도 sys.path에 없다).

런처가 하는 일 (근거: docs/research/readonly_shell_judgment_20261113_112332/):
1. user, mount, net, IPC, PID 네임스페이스. uid와 gid는 자기 자신으로 매핑한다
   (root로 매핑하지 않아 git의 소유자 검사가 그대로 돈다)
2. `/`를 재귀 private으로 바꿔 마운트가 호스트로 새지 않게 한다
3. `/run`에 tmpfs (systemd, D-Bus, WSL interop 소켓을 가린다), `/dev/pts`에
   tmpfs (다른 터미널에 글자나 OSC 52 같은 제어 문자를 쓰지 못하게)
4. `mount_setattr(AT_RECURSIVE, RDONLY)`로 하위 마운트까지 읽기 전용
   (최상위만 다시 마운트하면 /dev/shm 같은 하위 마운트는 쓸 수 있다)
5. 버리는 쓰기 공간 tmpfs. 보통은 `/tmp`. cwd가 `/tmp` 아래면 cwd를 가리지
   않게 `/tmp`는 읽기 전용으로 두고 `/run/tmp`에 올린다. TMPDIR을 거기로 둔다
6. seccomp: AF_INET, AF_INET6, AF_NETLINK 밖의 `socket`(AF_UNIX, AF_VSOCK 등),
   데이터그램 `socketpair`(sendto로 경로 소켓에 보낼 수 있다),
   io_uring, ptrace, process_vm_*, pidfd_getfd는 EPERM, x32 ABI와 x86_64가 아닌
   호출은 프로세스 종료. 경로 유닉스 소켓 connect는 읽기 전용 마운트로 막히지
   않고 (/mnt/wslg/run/user/*/bus), vsock은 net 네임스페이스로 막히지 않는다
   keyctl 계열(dcode와 같은 세션 키링)도 EPERM. RLIMIT_CORE는 1로 고정하고
   바꾸지 못하게 한다. core_pattern이 파이프(WSL은 `/wsl-capture-crash`)면 커널은
   한도 0에서도 root 도우미를 띄워 덤프를 샌드박스 밖(C: 드라이브)에 쓰고, 1일
   때만 덤프를 그만둔다
7. 두 번 fork한다. 첫 자식은 새 PID 네임스페이스의 1번으로 손자를 기다리기만
   하고, 손자가 새 `/proc`(읽기 전용)을 올리고 `setsid`로 제어 터미널을 뗀다.
   PID 네임스페이스라 밖의 같은 uid 프로세스에 시그널, prlimit, renice를 못 하고,
   1번이 끝나면 커널이 남은 백그라운드 프로세스를 모두 죽인다. 각 부모는 자식의
   종료 코드를 넘기고, 부모가 죽으면 자식도 SIGKILL로 죽는다
8. 손자가 `/bin/sh -c <명령>`을 cwd 그대로 exec한다. [F9] 환경에
   `PYTEST_ADDOPTS`(기존 값 뒤에 `-o cache_dir=<쓰기 공간>/pytest-cache`)와
   `PYTHONDONTWRITEBYTECODE=1`을 더한다

설정이 하나라도 실패하면 명령을 돌리지 않고 종료 코드 125로 끝난다.
"""

from __future__ import annotations

import ctypes
import functools
import os
import platform
import resource
import select
import shlex
import struct
import subprocess  # noqa: S404  # 가용성 탐침이 런처를 한 번 돌린다
import sys
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:
    from collections.abc import Mapping

SETUP_FAILED_EXIT = 125
SETUP_FAILED_TEXT = "plan sandbox: setup failed, command not run"
LAUNCHER = str(Path(__file__).resolve())
_TMP = "/tmp"  # noqa: S108  # 샌드박스 안에서 새 tmpfs로 덮는다

_SYS_MOUNT_SETATTR, _AT_FDCWD, _AT_RECURSIVE, _MOUNT_ATTR_RDONLY = 442, -100, 0x8000, 1
_MS_RDONLY, _MS_NOSUID, _MS_NODEV, _MS_NOEXEC = 1, 2, 4, 8
_MS_REC, _MS_PRIVATE = 0x4000, 1 << 18
_PR_SET_PDEATHSIG, _PR_SET_NO_NEW_PRIVS, _PR_SET_SECCOMP = 1, 38, 22
_SECCOMP_MODE_FILTER = 2
_AUDIT_ARCH_X86_64, _X32_SYSCALL_BIT = 0xC000003E, 0x40000000
_SYS_SOCKET, _SYS_SOCKETPAIR, _SOCK_DGRAM = 41, 53, 2
# socket()은 빈 net 네임스페이스 안에서만 닿는 AF_INET, AF_INET6, AF_NETLINK만 연다.
# AF_UNIX는 경로 소켓으로 D-Bus에 붙고, AF_VSOCK은 net 네임스페이스와 관계없이
# WSL 호스트(CID 2)에 붙는다(실행해서 확인)
_ALLOWED_SOCKET_FAMILIES = (2, 10, 16)
# ptrace 101, process_vm_readv 310, process_vm_writev 311, io_uring_setup 425,
# pidfd_getfd 438. ptrace_scope=0인 호스트에서 같은 uid의 dcode를 고치지 못하게.
# add_key 248, request_key 249, keyctl 250. 세션 키링은 dcode와 같다
_DENIED_SYSCALLS = (101, 310, 311, 425, 438, 248, 249, 250)
_SYS_SETRLIMIT, _SYS_PRLIMIT64 = 160, 302


class _MountAttr(ctypes.Structure):
    _fields_ = (  # ctypes 구조체 선언
        ("attr_set", ctypes.c_uint64),
        ("attr_clr", ctypes.c_uint64),
        ("propagation", ctypes.c_uint64),
        ("userns_fd", ctypes.c_uint64),
    )


class _SockFprog(ctypes.Structure):
    _fields_ = (  # ctypes 구조체 선언
        ("len", ctypes.c_ushort),
        ("filter", ctypes.c_void_p),
    )


def _libc() -> ctypes.CDLL:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    return libc


def _ok(ret: int, what: str) -> None:
    if ret != 0:
        err = ctypes.get_errno()
        raise OSError(err, f"{what}: {os.strerror(err)}")


def _mount(
    libc: ctypes.CDLL, src: bytes, target: bytes, fstype: bytes | None, flags: int
) -> None:
    data = b"size=256m" if fstype == b"tmpfs" else None
    _ok(
        libc.mount(src, target, fstype, ctypes.c_ulong(flags), data),
        f"mount {target!r}",
    )


def _seccomp_program() -> list[tuple[int, int, int, int]]:
    """Seccomp BPF. 위에서부터 처음 맞는 RET을 쓴다.

    Returns:
        (code, jt, jf, k) 목록.
    """
    ld, jeq, jge, ret = 0x20, 0x15, 0x35, 0x06  # LD|W|ABS, JMP|JEQ|K, JMP|JGE|K, RET|K
    and_ = 0x54  # ALU|AND|K
    allow, kill, eperm = 0x7FFF0000, 0x80000000, 0x00050000 | 1
    prog = [
        (ld, 0, 0, 4),  # seccomp_data.arch
        (jeq, 1, 0, _AUDIT_ARCH_X86_64),
        (ret, 0, 0, kill),
        (ld, 0, 0, 0),  # seccomp_data.nr
        (jge, 0, 1, _X32_SYSCALL_BIT),
        (ret, 0, 0, kill),
    ]
    for nr in _DENIED_SYSCALLS:
        prog += [(jeq, 0, 1, nr), (ret, 0, 0, eperm)]
    core = resource.RLIMIT_CORE
    prog += [  # setrlimit(RLIMIT_CORE, ...)
        (jeq, 0, 4, _SYS_SETRLIMIT),
        (ld, 0, 0, 16),  # args[0]
        (jeq, 0, 1, core),
        (ret, 0, 0, eperm),
        (ret, 0, 0, allow),
    ]
    prog += [  # prlimit64(pid, RLIMIT_CORE, new != NULL, ...). 읽기만은 된다
        (jeq, 0, 8, _SYS_PRLIMIT64),
        (ld, 0, 0, 24),  # args[1]
        (jeq, 0, 5, core),
        (ld, 0, 0, 32),  # args[2] 낮은 32비트
        (jeq, 0, 2, 0),
        (ld, 0, 0, 36),  # args[2] 높은 32비트
        (jeq, 1, 0, 0),
        (ret, 0, 0, eperm),
        (ret, 0, 0, allow),
    ]
    # socketpair(..., SOCK_DGRAM). 데이터그램 끝은 sendto로 경로 소켓에 닿는다
    prog += [
        (jeq, 0, 5, _SYS_SOCKETPAIR),
        (ld, 0, 0, 24),  # args[1]
        (and_, 0, 0, 0xF),  # SOCK_NONBLOCK, SOCK_CLOEXEC를 뗀다
        (jeq, 0, 1, _SOCK_DGRAM),
        (ret, 0, 0, eperm),
        (ret, 0, 0, allow),
    ]
    families = len(_ALLOWED_SOCKET_FAMILIES)
    prog += [
        (jeq, 0, families + 2, _SYS_SOCKET),
        (ld, 0, 0, 16),  # args[0]의 낮은 32비트 (x86_64는 little endian)
    ]
    for i, family in enumerate(_ALLOWED_SOCKET_FAMILIES):
        prog.append((jeq, families - i, 0, family))  # 맞으면 allow로
    prog += [(ret, 0, 0, eperm), (ret, 0, 0, allow)]
    return prog


def _deny_syscalls(libc: ctypes.CDLL) -> None:
    prog = _seccomp_program()
    buf = ctypes.create_string_buffer(b"".join(struct.pack("HBBI", *i) for i in prog))
    fprog = _SockFprog(len(prog), ctypes.addressof(buf))
    _ok(libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0), "no_new_privs")
    _ok(
        libc.prctl(_PR_SET_SECCOMP, _SECCOMP_MODE_FILTER, ctypes.byref(fprog), 0, 0),
        "seccomp",
    )


def scratch_dir(cwd: str) -> str:
    """버리는 쓰기 공간의 경로.

    Args:
        cwd: 명령의 작업 폴더.

    Returns:
        cwd나 이 파이썬(dcode 설치)이 `/tmp` 아래면 `/run/tmp`, 아니면 `/tmp`.
        `/tmp`에 tmpfs를 덮으면 그 아래 프로젝트와 설치가 가려진다.
    """

    def under_tmp(path: str) -> bool:
        # 가상환경 파이썬은 /tmp 밖으로 가는 링크라 링크를 풀기 전후를 다 본다
        return any(
            p == _TMP or p.startswith(_TMP + "/")
            for p in (os.path.realpath(path), os.path.normpath(path))
        )

    return "/run/tmp" if under_tmp(cwd) or under_tmp(sys.executable) else _TMP


def _setup(cwd: str) -> str:
    if platform.machine() != "x86_64":
        raise OSError(0, "seccomp filter supports x86_64 only")
    libc = _libc()
    uid, gid = os.getuid(), os.getgid()
    os.unshare(
        os.CLONE_NEWUSER
        | os.CLONE_NEWNS
        | os.CLONE_NEWNET
        | os.CLONE_NEWIPC
        | os.CLONE_NEWPID
    )
    for name, text in (
        ("setgroups", "deny"),
        ("uid_map", f"{uid} {uid} 1"),
        ("gid_map", f"{gid} {gid} 1"),
    ):
        Path(f"/proc/self/{name}").write_text(text, encoding="ascii")
    _mount(libc, b"none", b"/", None, _MS_REC | _MS_PRIVATE)
    _mount(libc, b"tmpfs", b"/run", b"tmpfs", 0)
    _mount(libc, b"tmpfs", b"/dev/pts", b"tmpfs", 0)
    scratch = scratch_dir(cwd)
    if scratch != _TMP:
        Path(scratch).mkdir()  # 읽기 전용이 되기 전에 마운트 지점을 만든다
    attr = _MountAttr(_MOUNT_ATTR_RDONLY, 0, 0, 0)
    _ok(
        libc.syscall(
            _SYS_MOUNT_SETATTR,
            _AT_FDCWD,
            b"/",
            _AT_RECURSIVE,
            ctypes.byref(attr),
            ctypes.sizeof(attr),
        ),
        "mount_setattr",
    )
    _mount(libc, b"tmpfs", scratch.encode(), b"tmpfs", 0)
    resource.setrlimit(resource.RLIMIT_CORE, (1, 1))
    _deny_syscalls(libc)  # 여기서부터 fork하는 셋 다 걸린다
    return scratch


def _enter(libc: ctypes.CDLL) -> None:
    # 손자(새 PID 네임스페이스 안)에서 명령 직전에
    flags = _MS_RDONLY | _MS_NOSUID | _MS_NODEV | _MS_NOEXEC
    _mount(libc, b"proc", b"/proc", b"proc", flags)
    os.setsid()  # fork한 자식이라 그룹 리더가 아니다


def _fork_and_wait() -> None:
    """Fork한다. 자식은 돌아오고, 부모는 자식을 기다렸다가 같은 종료 코드로 끝난다.

    부모가 죽으면 자식도 SIGKILL로 죽는다. 새 PID 네임스페이스의 자식에게는
    부모가 보이지 않아(getppid가 0) 부모가 먼저 죽었는지는 pidfd로 본다.
    """
    parent = os.pidfd_open(os.getpid())
    child = os.fork()
    if child == 0:
        _ok(_libc().prctl(_PR_SET_PDEATHSIG, 9, 0, 0, 0), "pdeathsig")
        if select.select([parent], [], [], 0)[0]:  # 부모가 prctl 전에 죽었다
            os._exit(SETUP_FAILED_EXIT)
        os.close(parent)
        return
    _, status = os.waitpid(child, 0)
    code = os.waitstatus_to_exitcode(status)
    os._exit(code if code >= 0 else 128 - code)


def main(argv: list[str]) -> NoReturn:
    """런처 진입점. 샌드박스를 만들고 `/bin/sh -c argv[1]`을 exec한다.

    Args:
        argv: `sys.argv`. 명령 하나만 받는다.
    """
    if len(argv) != 2:  # noqa: PLR2004  # 프로그램 이름과 명령
        print(f"{SETUP_FAILED_TEXT}: usage: {argv[0]} COMMAND", file=sys.stderr)  # noqa: T201
        sys.exit(SETUP_FAILED_EXIT)
    cwd = os.getcwd()  # noqa: PTH109  # 런처는 cwd를 그대로 이어받는다
    try:
        scratch = _setup(cwd)
        _fork_and_wait()  # 1번: 새 PID 네임스페이스의 init
        _fork_and_wait()  # 명령
        _enter(_libc())
        os.chdir(cwd)
    except (OSError, ValueError) as e:  # setrlimit은 hard 한도가 0이면 ValueError
        print(f"{SETUP_FAILED_TEXT}: {e}", file=sys.stderr)  # noqa: T201
        sys.exit(SETUP_FAILED_EXIT)
    os.environ["TMPDIR"] = scratch
    # [F9] 읽기 전용이라 pytest 캐시와 .pyc 쓰기가 EROFS 경고만 낸다.
    # 캐시 플러그인을 끄면 cache 픽스처가 깨져 캐시를 버리는 공간으로 옮긴다
    addopts = os.environ.get("PYTEST_ADDOPTS", "")
    cache = shlex.quote(f"cache_dir={scratch}/pytest-cache")
    os.environ["PYTEST_ADDOPTS"] = f"{addopts} -o {cache}".strip()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.execv("/bin/sh", ["sh", "-c", argv[1]])  # noqa: S606  # 이 런처의 목적


# ----- 게이트가 쓰는 쪽 -----


def wrap_command(command: str) -> str:
    """`execute`의 명령을 런처를 거치게 바꾼다.

    Args:
        command: 모델이 낸 셸 명령.

    Returns:
        LocalShellBackend가 `sh -c`로 돌릴 명령. `exec`로 셸을 런처로 바꿔
        시간 초과 때 죽는 프로세스가 명령 쪽이 되게 한다.
    """
    return " ".join(
        (
            "exec",
            shlex.quote(sys.executable),
            "-I",
            shlex.quote(LAUNCHER),
            shlex.quote(command),
        )
    )


@functools.cache
def _probe() -> bool:
    # 프로세스마다 한 번. 런처가 끝까지 설정되면 `true`가 0으로 끝난다
    if sys.platform != "linux" or platform.machine() != "x86_64" or not sys.executable:
        return False
    try:
        done = subprocess.run(  # noqa: S603  # 고정 인자
            [sys.executable, "-I", LAUNCHER, "true"],
            cwd="/",
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return False
    return done.returncode == 0


def available(environ: Mapping[str, str] | None = None) -> bool:
    """샌드박스를 쓸 수 있는가. 끄기 스위치를 보고 탐침 결과(캐시)를 돌려준다.

    Args:
        environ: 환경변수 사전. None이면 `os.environ`.

    Returns:
        `DEEPAGENTS_CODE_PLAN_SANDBOX`가 `0`이나 `false`가 아니고 탐침이 성공하면 True.
    """
    from deepagents_code._env_vars import (
        PLAN_SANDBOX,  # 런처는 패키지를 import하지 않는다
    )

    env = os.environ if environ is None else environ
    if env.get(PLAN_SANDBOX, "").strip().lower() in {"0", "false"}:
        return False
    return _probe()


if __name__ == "__main__":
    main(sys.argv)
