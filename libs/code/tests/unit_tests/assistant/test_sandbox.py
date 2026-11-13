"""[F7] 계획 전 execute의 읽기 전용 샌드박스. 런처를 실제로 돌린다.

쓰기 실패는 이유 문구(Read-only file system, Operation not permitted, Network is
unreachable)까지 본다. 경로가 가려져서 실패한 것을 통과로 세지 않게 한다.
"""

from __future__ import annotations

import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from deepagents_code._env_vars import PLAN_SANDBOX
from deepagents_code.agent import create_cli_agent
from deepagents_code.assistant import sandbox
from deepagents_code.assistant.decider import FakeDecider
from deepagents_code.assistant.gate import SubagentWriteBlockMiddleware
from tests.unit_tests.assistant.fakes import make_options, tool_call
from tests.unit_tests.assistant.test_gate import (
    Harness,
    approved,
    done,
    tool_result,
)
from tests.unit_tests.assistant.test_subagents import _build
from tests.unit_tests.test_end_to_end import FixedGenericFakeChatModel, mock_settings

if TYPE_CHECKING:
    from collections.abc import Iterator

HAS_SANDBOX = sandbox.available({})
needs_sandbox = pytest.mark.skipif(
    not HAS_SANDBOX,
    reason="이 호스트에서 user/mount 네임스페이스나 mount_setattr, x86_64 seccomp를 "
    "쓸 수 없다 (런처 탐침 실패)",
)
EROFS = "Read-only file system"
EPERM = "Operation not permitted"


def launch(command: str, cwd: Path | str, **kwargs: Any) -> tuple[int, str]:
    done_ = subprocess.run(
        [sys.executable, "-I", sandbox.LAUNCHER, command],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        stdin=subprocess.DEVNULL,
        **kwargs,
    )
    return done_.returncode, done_.stdout + done_.stderr


def snapshot(root: Path) -> dict[str, tuple[int, bytes]]:
    return {
        str(p.relative_to(root)): (
            p.stat().st_mode,
            p.read_bytes() if p.is_file() else b"",
        )
        for p in sorted(root.rglob("*"))
    }


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@pytest.fixture(params=["under_tmp", "outside_tmp"])
def project(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Path]:
    """Git 저장소 하나. /tmp 아래(scratch가 /run/tmp)와 밖(scratch가 /tmp) 둘 다."""
    if request.param == "under_tmp":
        root = tmp_path / "repo"
        root.mkdir()
    else:
        cache = Path.home() / ".cache"
        cache.mkdir(exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="dcode-f7-", dir=cache))
    (root / "f").write_text("a\n")
    git(root, "init", "-q")
    git(root, "add", "f")
    git(root, "-c", "user.email=x@x", "-c", "user.name=x", "commit", "-qm", "init")
    try:
        yield root
    finally:
        if request.param == "outside_tmp":
            shutil.rmtree(root)


# ----- 런처 -----


def test_wrap_command_keeps_command_as_one_argument() -> None:
    command = """echo 'a b' "$HOME" ; touch x # c"""
    words = shlex.split(sandbox.wrap_command(command))
    assert words == ["exec", sys.executable, "-I", sandbox.LAUNCHER, command]


def test_scratch_dir_moves_off_tmp_when_cwd_is_under_tmp() -> None:
    assert sandbox.scratch_dir("/tmp") == "/run/tmp"
    assert sandbox.scratch_dir("/tmp/x/y") == "/run/tmp"
    assert sandbox.scratch_dir("/tmpx") == "/tmp"
    assert sandbox.scratch_dir("/home") == "/tmp"


def test_switch_turns_sandbox_off() -> None:
    assert not sandbox.available({PLAN_SANDBOX: "0"})
    assert not sandbox.available({PLAN_SANDBOX: "false"})


@needs_sandbox
def test_reads_work(project: Path) -> None:
    outside = git(project, "status", "-sb")
    code, out = launch("git status -sb", project)
    assert (code, out) == (0, outside)
    code, out = launch("ls && cat f", project)
    assert code == 0
    assert "f\na\n" in out
    code, out = launch(
        f"{shlex.quote(sys.executable)} -c 'import json, textual; print(6 * 7)'",
        project,
    )
    assert (code, out) == (0, "42\n")


WRITES = {
    "create": "touch new.txt",
    "redirect": "echo x > new.txt",
    "function": "cat() { echo pwned > fn.txt; }; cat",
    "branch": "git branch newb",
    "commit": "git -c user.email=x@x -c user.name=x commit --allow-empty -qm x",
    "find_exec": r"find . -name f -exec rm {} \;",
    "sed_i": "sed -i s/a/b/ f",
    "chmod": "chmod 600 f",
    "git_output": "git log -1 --output=out.txt",
    "python": f'{shlex.quote(sys.executable)} -c \'open("py.txt", "w")\'',
}


@needs_sandbox
@pytest.mark.parametrize("command", WRITES.values(), ids=WRITES.keys())
def test_writes_fail_without_side_effects(project: Path, command: str) -> None:
    before, head = snapshot(project), git(project, "rev-parse", "HEAD")
    code, out = launch(command, project)
    assert EROFS in out
    assert code != 0 or "find" in command  # find는 -exec가 실패해도 0이다
    assert snapshot(project) == before
    assert git(project, "rev-parse", "HEAD") == head
    assert git(project, "branch", "--list", "newb") == ""


@needs_sandbox
def test_submounts_and_outside_paths_are_read_only(project: Path) -> None:
    name = f"f7-{uuid.uuid4().hex}"
    outside = project.parent / name
    code, out = launch(
        f"echo x > /dev/shm/{name}; echo x > {outside}; echo x > $HOME/{name}", project
    )
    assert code != 0
    assert out.count(EROFS) == 3, out
    assert not Path("/dev/shm", name).exists()
    assert not outside.exists()
    assert not (Path.home() / name).exists()


@needs_sandbox
def test_scratch_is_writable_and_discarded(project: Path) -> None:
    name = f"f7-{uuid.uuid4().hex}"
    code, out = launch(f'echo hi > "$TMPDIR/{name}" && cat "$TMPDIR/{name}"', project)
    assert (code, out) == (0, "hi\n")
    assert not Path("/tmp", name).exists()
    if str(project).startswith("/tmp/"):
        # cwd를 가리지 않으려고 /tmp는 읽기 전용으로 남는다
        code, out = launch(f"echo x > /tmp/{name}", project)
        assert EROFS in out
        assert not Path("/tmp", name).exists()


@needs_sandbox
def test_pytest_cache_and_bytecode_writes_are_off(project: Path) -> None:
    """[F9] 기존 PYTEST_ADDOPTS는 남기고 pytest 캐시를 버리는 공간으로 옮긴다."""
    env = {**os.environ, "PYTEST_ADDOPTS": "-q"}
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    code, out = launch(
        'echo "$PYTEST_ADDOPTS|$PYTHONDONTWRITEBYTECODE"', project, env=env
    )
    assert code == 0
    assert out.startswith("-q -o cache_dir=/")
    assert out.endswith("/pytest-cache|1\n")
    # 리뷰 뒤: 캐시 플러그인을 끄면 cache 픽스처를 쓰는 테스트가 깨졌다
    env.pop("PYTEST_ADDOPTS")
    (project / "test_c.py").write_text(
        'def test_c(cache):\n    cache.set("k", 1)\n    assert cache.get("k", 0) == 1\n'
    )
    before = snapshot(project)
    code, out = launch(
        f"{shlex.quote(sys.executable)} -m pytest -p no:warnings test_c.py",
        project,
        env=env,
    )
    assert code == 0, out
    assert "1 passed" in out
    assert snapshot(project) == before


@needs_sandbox
def test_unix_socket_connect_is_denied(project: Path) -> None:
    path = project / "s.sock"
    server = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import socket, sys, time; s = socket.socket(socket.AF_UNIX); "
                "s.bind(sys.argv[1]); s.listen(); print('ready', flush=True); "
                "time.sleep(30)"
            ),
            str(path),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert server.stdout is not None
        assert server.stdout.readline() == "ready\n"
        connect = (
            f"{shlex.quote(sys.executable)} -c 'import socket; "
            "s = socket.socket(socket.AF_UNIX); "
            f's.connect("{path}"); print("connected")\''
        )
        control = subprocess.run(  # 같은 명령이 샌드박스 밖에서는 붙는다
            connect, shell=True, capture_output=True, text=True, check=False
        )
        assert control.stdout == "connected\n"
        code, out = launch(connect, project)
        assert code != 0
        assert EPERM in out
    finally:
        server.kill()
        server.communicate()


@needs_sandbox
def test_datagram_socketpair_cannot_reach_path_sockets(project: Path) -> None:
    """socket(AF_UNIX)을 막아도 데이터그램 socketpair 끝은 sendto로 경로에 닿는다."""
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    listener.bind(str(project / "d.sock"))
    listener.settimeout(0.5)
    send = (
        f"{shlex.quote(sys.executable)} -c 'import socket; "
        "a, _ = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM); "
        'a.sendto(b"x", "d.sock")\'; '
        f"{shlex.quote(sys.executable)} -c 'import socket; socket.socketpair(); "
        'print("stream ok")\''
    )
    try:
        code, out = launch(send, project)
        with pytest.raises(TimeoutError):
            listener.recv(10)
        outside = subprocess.run(send, shell=True, cwd=project, check=False)
        assert outside.returncode == 0
        assert listener.recv(10) == b"x"  # 밖에서는 닿는다
    finally:
        listener.close()
    assert (code, out.count(EPERM), out.startswith("stream ok\n")) == (0, 1, True), out


SYSCALL_PROBE = """\
import ctypes, os, sys
libc = ctypes.CDLL(None, use_errno=True)
libc.syscall.restype = ctypes.c_long
pid = os.getpid()
calls = {
    "ptrace": (101, 0, 0, 0, 0),
    "process_vm_readv": (310, pid, 0, 0, 0, 0, 0),
    "process_vm_writev": (311, pid, 0, 0, 0, 0, 0),
    "io_uring_setup": (425, 1, 0),
    "pidfd_getfd": (438, os.pidfd_open(pid), 0, 0),
    "add_key": (248, b"user", b"f7", b"x", 1, -3),
    "request_key": (249, b"user", b"f7", 0, -3),
    "keyctl": (250, 0, -3, 0),
}
for name, args in calls.items():
    ret = libc.syscall(*args)
    print(name, "EPERM" if ret == -1 and ctypes.get_errno() == 1 else "ok")
"""


@needs_sandbox
def test_seccomp_denies_cross_process_and_io_uring_syscalls(project: Path) -> None:
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(SYSCALL_PROBE)}"
    control = subprocess.run(  # 밖에서는 EPERM이 아니다
        command, shell=True, capture_output=True, text=True, check=True
    )
    assert "EPERM" not in control.stdout
    code, out = launch(command, project)
    assert code == 0, out
    assert out.count("EPERM") == 8, out


@needs_sandbox
def test_outside_processes_are_out_of_reach(project: Path) -> None:
    """PID 네임스페이스: 밖의 같은 uid 프로세스에 시그널을 못 보내고 안 보인다."""
    outside = subprocess.Popen(["sleep", "60"])
    try:
        _, out = launch(
            f"kill -STOP {outside.pid}; ls /proc/{outside.pid}; ls -d /proc/[0-9]*",
            project,
        )
        stat = Path(f"/proc/{outside.pid}/stat").read_text(encoding="ascii")
    finally:
        outside.kill()
        outside.wait()
    assert stat.split()[2] != "T", out
    assert "No such process" in out
    assert "/proc/1\n" in out
    assert f"/proc/{outside.pid}\n" not in out


@needs_sandbox
def test_background_processes_die_with_the_command(project: Path) -> None:
    marker = f"f7-linger-{uuid.uuid4().hex}"
    code, out = launch(
        f"(setsid sleep 60 {marker} >/dev/null 2>&1 &); echo ok", project
    )
    assert (code, out) == (0, "ok\n")
    ps = subprocess.run(
        ["ps", "-eo", "args"], capture_output=True, text=True, check=True
    ).stdout
    assert marker not in ps


@needs_sandbox
def test_core_dumps_cannot_be_reenabled(project: Path) -> None:
    """core_pattern이 파이프면 한도 0도 덤프한다. 1로 고정하고 못 바꾸게 한다."""
    script = (
        "import resource as r\n"
        "print(r.getrlimit(r.RLIMIT_CORE))\n"
        "r.setrlimit(r.RLIMIT_NOFILE, r.getrlimit(r.RLIMIT_NOFILE))\n"
        "import ctypes\n"  # glibc는 prlimit64만 쓴다. setrlimit(160)은 직접 부른다
        "libc = ctypes.CDLL(None, use_errno=True)\n"
        "low = (ctypes.c_uint64 * 2)(0, 1)\n"
        "print('setrlimit', libc.syscall(160, 4, low), ctypes.get_errno())\n"
        "r.setrlimit(r.RLIMIT_CORE, (0, 1))\n"
    )
    code, out = launch(
        f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}; ulimit -c 0",
        project,
    )
    assert code != 0
    assert out.startswith("(1, 1)\nsetrlimit -1 1\n"), out
    # 파이썬은 setrlimit의 EPERM을 이 ValueError로 바꾼다
    assert "not allowed to raise maximum limit" in out
    assert f"ulimit: error setting limit ({EPERM})" in out
    crashes = Path("/proc/sys/kernel/core_pattern").read_text(encoding="ascii")
    dumps = next(Path("/mnt/c/Users").glob("*/AppData/Local/Temp/wsl-crashes"), None)
    if not crashes.startswith("|") or dumps is None:
        return
    before = set(dumps.iterdir())
    launch("kill -SEGV $$", project)
    assert set(dumps.iterdir()) == before


@needs_sandbox
def test_other_terminals_are_hidden(project: Path) -> None:
    code, out = launch("ls -A /dev/pts; echo end", project)
    assert (code, out) == (0, "end\n")


@needs_sandbox
def test_sysv_ipc_stays_inside(project: Path) -> None:
    if not shutil.which("ipcmk"):
        pytest.skip("ipcmk가 없다")

    def queues() -> set[str]:
        out = subprocess.run(
            ["ipcs", "-q"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return {line.split()[1] for line in out.splitlines() if line.startswith("0x")}

    before = queues()
    code, out = launch("ipcmk -Q", project)
    leaked = queues() - before
    for qid in leaked:
        subprocess.run(["ipcrm", "-q", qid], check=False)
    assert code == 0, out
    assert not leaked


@needs_sandbox
def test_vsock_is_denied(project: Path) -> None:
    """WSL에서 vsock은 net 네임스페이스와 관계없이 호스트(CID 2)에 닿는다."""
    command = (
        f"{shlex.quote(sys.executable)} -c 'import socket; "
        'socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM); print("created")\''
    )
    control = subprocess.run(
        command, shell=True, capture_output=True, text=True, check=False
    )
    if control.stdout != "created\n":
        pytest.skip("이 호스트는 vsock을 지원하지 않는다")
    code, out = launch(command, project)
    assert code != 0
    assert EPERM in out


@needs_sandbox
def test_network_is_unreachable(project: Path) -> None:
    code, out = launch(
        f"{shlex.quote(sys.executable)} -c 'import socket; "
        'socket.create_connection(("1.1.1.1", 53), 3)\'',
        project,
    )
    assert code != 0
    assert "Network is unreachable" in out


@needs_sandbox
def test_systemd_run_through_user_bus_cannot_write(project: Path) -> None:
    uid = os.getuid()
    buses = [
        p
        for p in (Path(f"/run/user/{uid}/bus"), Path(f"/mnt/wslg/run/user/{uid}/bus"))
        if p.exists()
    ]
    if not shutil.which("systemd-run") or not buses:
        pytest.skip("systemd-run이나 사용자 D-Bus 소켓이 없다")
    marker = project.parent / f"f7-bus-{uuid.uuid4().hex}"
    for bus in buses:
        code, out = launch(
            f"DBUS_SESSION_BUS_ADDRESS=unix:path={bus} "
            f"XDG_RUNTIME_DIR={bus.parent} "
            f"systemd-run --user --wait --quiet touch {marker}",
            project,
        )
        assert code != 0
        assert "Failed to connect to bus" in out
    assert not marker.exists()


@needs_sandbox
def test_wsl_interop_cannot_write_windows_drive(project: Path) -> None:
    cmd = Path("/mnt/c/Windows/System32/cmd.exe")
    if not cmd.exists():
        pytest.skip("WSL interop(cmd.exe)이 없다")
    name = f"f7-{uuid.uuid4().hex}.txt"
    _, out = launch(f'{cmd} /c "echo x > C:\\Users\\Public\\{name}"', project)
    assert not Path("/mnt/c/Users/Public", name).exists(), out


@needs_sandbox
def test_nested_user_namespace_cannot_remount_writable(project: Path) -> None:
    script = (
        "import ctypes, os\n"
        "libc = ctypes.CDLL(None, use_errno=True)\n"
        "os.unshare(os.CLONE_NEWUSER | os.CLONE_NEWNS)\n"
        "print('remount', libc.mount(None, b'/', None, ctypes.c_ulong(0x5020), None))\n"
        "attr = (ctypes.c_uint64 * 4)(0, 1, 0, 0)\n"
        "print('setattr', libc.syscall(442, -100, b'/', 0x8000, attr, 32))\n"
        "open('escaped.txt', 'w')\n"
    )
    code, out = launch(
        f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}", project
    )
    assert code != 0
    assert "remount -1" in out
    assert "setattr -1" in out
    assert EROFS in out
    assert not (project / "escaped.txt").exists()


@needs_sandbox
def test_setup_failure_exits_125_without_running() -> None:
    # cwd가 /run 아래면 tmpfs에 가려져 chdir가 실패한다
    hidden = next(
        (p for p in Path("/run").iterdir() if p.is_dir() and os.access(p, os.X_OK)),
        None,
    )
    if hidden is None:
        pytest.skip("/run 아래 폴더가 없다")
    code, out = launch("echo ran", hidden)
    assert code == sandbox.SETUP_FAILED_EXIT
    assert sandbox.SETUP_FAILED_TEXT in out
    assert "ran" not in out.replace(sandbox.SETUP_FAILED_TEXT, "")
    usage = subprocess.run(
        [sys.executable, "-I", sandbox.LAUNCHER], capture_output=True, check=False
    )
    assert usage.returncode == sandbox.SETUP_FAILED_EXIT


@needs_sandbox
def test_process_group_leader_still_gets_new_session(project: Path) -> None:
    """회귀: 그룹 리더면 setsid가 EPERM이다. 명령은 fork한 자식에서 새 세션을 만든다."""
    own_session = 'test "$(ps -o sid= -p $$ | tr -d " ")" = "$$" && echo own-session'
    code, out = launch(
        f"{own_session}; exit 7",
        project,
        process_group=0,
    )
    assert (code, out) == (7, "own-session\n")
    code, _ = launch("kill -9 $$", project, process_group=0)
    assert code == 128 + 9


# ----- 게이트 -----


@pytest.fixture
def sandbox_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PLAN_SANDBOX, raising=False)


def execute(command: str, call_id: str = "e") -> AIMessage:
    return tool_call("execute", {"command": command}, call_id)


PRINT = f"{shlex.quote(sys.executable)} -c 'print(6 * 7)'"


@needs_sandbox
@pytest.mark.usefixtures("sandbox_on")
async def test_pre_plan_execute_runs_in_sandbox(tmp_path: Path) -> None:
    script = [execute(PRINT, "p"), execute("touch x", "t"), done()]
    h = Harness(tmp_path, script)
    result = await h.say("돌려 봐")
    assert "42" in str(tool_result(result, "p").content)
    touched = str(tool_result(result, "t").content)
    assert EROFS in touched
    assert "Exit code: 1" in touched or "exit code 1" in touched.lower()
    assert not (tmp_path / "x").exists()
    # 모델과 승인 화면이 보는 호출은 원래 명령이다
    calls = [
        c for m in result["messages"] if isinstance(m, AIMessage) for c in m.tool_calls
    ]
    assert [c["args"]["command"] for c in calls] == [PRINT, "touch x"]


@needs_sandbox
@pytest.mark.usefixtures("sandbox_on")
def test_pre_plan_execute_runs_in_sandbox_sync(tmp_path: Path) -> None:
    h = Harness(tmp_path, [execute("touch x"), done()])
    result = h.agent.invoke({"messages": [HumanMessage(content="만들어")]}, h.config)
    message = tool_result(result, "e")
    assert message.status != "error"  # 거부가 아니라 실행됐다
    assert f"touch: cannot touch 'x': {EROFS}" in str(message.content)
    assert not (tmp_path / "x").exists()


@needs_sandbox
@pytest.mark.usefixtures("sandbox_on")
async def test_protected_dir_shell_runs_read_only_in_sandbox(tmp_path: Path) -> None:
    """[F9] 보호 폴더를 언급한 명령은 거부 대신 샌드박스. 읽기는 되고 쓰기는 EROFS."""
    plans = tmp_path / ".deepagents" / "plans"
    plans.mkdir(parents=True)
    (plans / "p.md").write_text("")
    # 실사용에서 거부된 명령의 모양
    seen = "git diff HEAD --stat | head -5; ls .deepagents/plans/ 2>/dev/null | head"
    h = Harness(
        tmp_path, [execute("touch .deepagents/plans/x"), execute(seen, "l"), done()]
    )
    result = await h.say("만들어")
    assert EROFS in str(tool_result(result, "e").content)
    assert not (plans / "x").exists()
    listed = tool_result(result, "l")
    assert listed.status != "error"
    assert "p.md" in str(listed.content)


@pytest.mark.usefixtures("sandbox_on")
async def test_unavailable_sandbox_falls_back_to_static(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sandbox, "_probe", lambda: False)
    h = Harness(tmp_path, [execute(PRINT, "p"), execute("ls", "l"), done()])
    result = await h.say("돌려 봐")
    denied = tool_result(result, "p")
    assert denied.status == "error"
    assert "승인된 계획이 없다" in str(denied.content)
    assert tool_result(result, "l").status != "error"


@needs_sandbox
@pytest.mark.usefixtures("sandbox_on")
async def test_post_approval_execute_is_not_sandboxed(tmp_path: Path) -> None:
    host_run = sorted(os.listdir("/run"))  # noqa: PTH208
    h = await approved(
        tmp_path,
        [execute("touch y", "t"), execute("ls /run", "l"), done()],
        decider=FakeDecider(script={"J4": 1.0}),
    )
    assert (tmp_path / "y").exists()
    # 읽기 명령도 샌드박스 밖이다 (안에서는 /run이 비어 있다)
    assert host_run[0] in str(tool_result(h.last, "l").content)  # type: ignore[attr-defined]


NOTE_SCOPE = "[게이트] 승인된 계획의 범위 밖으로 판정돼"


@needs_sandbox
@pytest.mark.usefixtures("sandbox_on")
async def test_out_of_scope_execute_runs_read_only_after_approval(
    tmp_path: Path,
) -> None:
    """[F9] J4가 거부할 execute는 샌드박스에서 돈다. 대상 쓰기는 그대로 된다."""
    write_target = tool_call(
        "write_file", {"file_path": str(tmp_path / "app.py"), "content": "v1"}, "w"
    )
    write_other = tool_call(
        "write_file", {"file_path": str(tmp_path / "other.py"), "content": "x"}, "o"
    )
    script = [execute(PRINT, "p"), execute("touch other", "tc"), write_target]
    h = await approved(
        tmp_path,
        [*script, write_other, done()],
        decider=FakeDecider(script={"J4": 0.0}),
    )
    last = h.last  # type: ignore[attr-defined]
    probe = str(tool_result(last, "p").content)
    assert "42" in probe
    assert NOTE_SCOPE not in probe  # 성공한 명령에는 안 붙인다
    failed = str(tool_result(last, "tc").content)
    assert EROFS in failed
    assert NOTE_SCOPE in failed
    assert not (tmp_path / "other").exists()
    assert (tmp_path / "app.py").read_text() == "v1"  # 계획 대상 쓰기는 샌드박스 밖
    assert tool_result(last, "o").status == "error"  # 범위 밖 파일 쓰기는 거부
    assert not (tmp_path / "other.py").exists()
    counters = (await h.state())["_cg_counters"]
    assert counters.get("jev_denies") == 1  # write_file 하나만


@needs_sandbox
@pytest.mark.usefixtures("sandbox_on")
async def test_protected_dir_shell_never_reaches_j4_after_approval(
    tmp_path: Path,
) -> None:
    """[F9] J4가 통과시켜도 보호 폴더를 언급한 명령은 샌드박스 안이다."""
    h = await approved(
        tmp_path,
        [execute("touch .deepagents/plans/x"), done()],
        decider=FakeDecider(script={"J4": 1.0}),
    )
    message = str(tool_result(h.last, "e").content)  # type: ignore[attr-defined]
    assert EROFS in message
    assert "[게이트] .deepagents/ 보호 폴더를 언급해" in message
    assert not (tmp_path / ".deepagents" / "plans" / "x").exists()


@needs_sandbox
@pytest.mark.usefixtures("sandbox_on")
def test_protected_dir_shell_note_sync(tmp_path: Path) -> None:
    # submit_plan은 비동기만 있어 동기 경로는 계획 전 보호 폴더 명령으로 본다
    (tmp_path / ".deepagents" / "plans").mkdir(parents=True)
    h = Harness(tmp_path, [execute("touch .deepagents/plans/x"), done()])
    result = h.agent.invoke({"messages": [HumanMessage(content="만들어")]}, h.config)
    message = str(tool_result(result, "e").content)
    assert EROFS in message
    assert "[게이트] .deepagents/ 보호 폴더를 언급해" in message


@needs_sandbox
@pytest.mark.usefixtures("sandbox_on")
async def test_out_of_scope_execute_sandboxed_sync_and_broken_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[F9] 리뷰 뒤: 동기 J4 실패도 샌드박스. 런처가 깨지면 명령이 돌지 않는다."""
    after = [done(), execute("touch other", "tc"), done(), execute("touch b", "b")]
    h = await approved(
        tmp_path, [*after, done()], decider=FakeDecider(script={"J4": 0.0})
    )
    result = h.agent.invoke({"messages": [HumanMessage(content="계속")]}, h.config)
    message = str(tool_result(result, "tc").content)
    assert EROFS in message
    assert NOTE_SCOPE in message
    assert not (tmp_path / "other").exists()
    # 탐침이 캐시된 뒤 런처가 사라져도 감싼 명령은 실패할 뿐 그대로 돌지 않는다
    monkeypatch.setattr(sandbox, "LAUNCHER", str(tmp_path / "missing.py"))
    result = await h.say("하나 더")
    assert "missing.py" in str(tool_result(result, "b").content)
    assert not (tmp_path / "b").exists()


@pytest.mark.usefixtures("sandbox_on")
async def test_unavailable_sandbox_keeps_denies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sandbox, "_probe", lambda: False)
    h = await approved(
        tmp_path,
        [execute(PRINT, "p"), execute("touch .deepagents/plans/x", "l"), done()],
        decider=FakeDecider(script={"J4": 0.0}),
    )
    last = h.last  # type: ignore[attr-defined]
    assert "범위 밖이다" in str(tool_result(last, "p").content)
    assert tool_result(last, "p").status == "error"
    assert ".deepagents/" in str(tool_result(last, "l").content)
    assert tool_result(last, "l").status == "error"


@needs_sandbox
@pytest.mark.usefixtures("sandbox_on")
async def test_subagent_execute_runs_in_sandbox(tmp_path: Path) -> None:
    from deepagents.backends import CompositeBackend, LocalShellBackend
    from deepagents.middleware.filesystem import FilesystemMiddleware
    from langchain.agents import create_agent

    from tests.unit_tests.assistant.fakes import scripted_model

    backend = CompositeBackend(
        default=LocalShellBackend(root_dir=tmp_path, virtual_mode=False), routes={}
    )
    agent = create_agent(
        model=scripted_model(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "execute", "args": {"command": "touch b"}, "id": "t"},
                        {"name": "execute", "args": {"command": PRINT}, "id": "p"},
                    ],
                ),
                done(),
            ]
        ),
        middleware=[
            FilesystemMiddleware(backend=backend),
            SubagentWriteBlockMiddleware(tmp_path, shell_sandbox=True),
        ],
    )
    result = await agent.ainvoke({"messages": [HumanMessage(content="봐")]})
    assert EROFS in str(tool_result(result, "t").content)
    assert "42" in str(tool_result(result, "p").content)
    assert not (tmp_path / "b").exists()


@needs_sandbox
@pytest.mark.usefixtures("sandbox_on")
async def test_create_cli_agent_sandboxes_pre_plan_execute(tmp_path: Path) -> None:
    model = FixedGenericFakeChatModel(
        messages=iter([execute("touch x; echo done-$?"), done()])
    )
    with mock_settings(tmp_path):
        agent, _ = create_cli_agent(
            model=model,
            assistant_id="test-agent",
            tools=[],
            auto_approve=True,
            cwd=tmp_path,
            checkpointer=InMemorySaver(),
            plan_gate=make_options(tmp_path),
        )
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content="만들어")]},
            {"configurable": {"thread_id": str(uuid.uuid4())}},
        )
    content = str(tool_result(result, "e").content)
    assert EROFS in content
    assert "done-1" in content
    assert not (tmp_path / "x").exists()


def test_create_cli_agent_sandboxes_local_subagents(tmp_path: Path) -> None:
    model = FixedGenericFakeChatModel(messages=iter([done()]))
    middleware, _ = _build(tmp_path, model, user_subagent=False)["general-purpose"]
    (block,) = [m for m in middleware if isinstance(m, SubagentWriteBlockMiddleware)]
    assert block._shell_sandbox
