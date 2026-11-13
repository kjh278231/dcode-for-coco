"""도구 호출 분류 테스트."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from deepagents_code._paths import project_paths
from deepagents_code.assistant.policy import (
    classify_call,
    is_protected,
    is_read_only_shell,
    mentions_protected,
    normalize_tool_path,
    relative_target,
    summarize_call,
    tool_name_of,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path.resolve()


def _classify(
    root: Path,
    tool_name: str,
    args: dict[str, Any],
    *,
    phase: str = "idle",
    targets: tuple[str, ...] = (),
    mcp_mutating: frozenset[str] = frozenset(),
    fresh_approval: bool = False,
) -> tuple[str, str]:
    return classify_call(
        phase=phase,
        tool_name=tool_name,
        args=args,
        targets=targets,
        project_root=root,
        mcp_mutating=mcp_mutating,
        fresh_approval=fresh_approval,
    )


# 규칙표 1~9 각각.


def test_rule1_plan_tool(root: Path) -> None:
    assert _classify(root, "submit_plan", {}) == ("allow", "plan_tool")


@pytest.mark.parametrize("tool", ["start_async_task", "update_async_task"])
def test_async_subagent_denied_even_after_approval(root: Path, tool: str) -> None:
    """원격 서브에이전트는 쓰기 차단이 없어 승인 뒤에도 거부한다 (P3)."""
    for phase in ("idle", "executing"):
        decision = _classify(root, tool, {}, phase=phase, fresh_approval=True)
        assert decision == ("deny", "async_subagent")


@pytest.mark.parametrize("raw", [None, "", "../etc/passwd", "~/x", 3])
def test_rule2_bad_path(root: Path, raw: object) -> None:
    assert _classify(root, "write_file", {"file_path": raw}) == ("deny", "bad_path")


@pytest.mark.parametrize("phase", ["idle", "executing"])
def test_rule3_protected_path(root: Path, phase: str) -> None:
    path = str(root / ".deepagents/plans/x.md")
    decision = _classify(
        root,
        "write_file",
        {"file_path": path},
        phase=phase,
        targets=(".deepagents/plans/x.md",),
        fresh_approval=True,
    )
    assert decision == ("deny", "protected_path")


def test_rule3_delete_parent_of_protected(root: Path) -> None:
    for parent in (root / ".deepagents", root):
        args = {"file_path": str(parent)}
        assert _classify(root, "delete", args) == ("deny", "protected_path")


@pytest.mark.parametrize("command", ["ls", "cat a.txt | grep x", "git status"])
def test_rule4_read_only_shell(root: Path, command: str) -> None:
    decision = _classify(root, "execute", {"command": command})
    assert decision == ("allow", "read_only_shell")


def test_rule4_redirect_is_not_read_only(root: Path) -> None:
    assert not is_read_only_shell("cat a > b", root)
    decision = _classify(root, "execute", {"command": "cat a > b"})
    assert decision == ("deny", "no_approved_plan")


# [F1] dcode-a 사용 중 거부된 명령 (체크포인트의 원문, 경로만 바꿈)과 쓰기 닮은꼴.


@pytest.mark.parametrize(
    "command",
    [
        "echo probe",
        'ls {o}/mascot/ && echo "---coco.sh---" && head -60 {o}/mascot/coco.sh',
        "cd {r} && git log --oneline -3 2>&1 | head -5",
        (
            "cd {r} && git log --oneline -3 && git status --short | head -5 "
            "&& ls libs/code/.venv/bin/pytest libs/code/Makefile 2>&1 | head -5"
        ),
        "cd {r}/src && cat a.py 2>/dev/null | grep -n x",
        "cd /tmp && ls",
        "git diff --stat; git status --short",
    ],
)
def test_f1_read_only_chains_allowed(root: Path, command: str) -> None:
    command = command.format(r=root, o="/tmp/other")
    assert _classify(root, "execute", {"command": command}) == (
        "allow",
        "read_only_shell",
    )


@pytest.mark.parametrize(
    "command",
    [
        # 관찰된 명령 중 프로그램 실행
        "cd {r} && python3 coco.sh 2>&1 | head -30",
        # 남는 리다이렉트
        "echo a > b",
        "echo a >> b",
        "ls 2>&1>out",
        "ls 2>&1 >out",
        "ls 2>/dev/nullx",
        "ls 2>/dev/null\u00a0x",
        "ls 2>/dev/null\x0bx",
        "ls\u00a02>/dev/null",
        "ls 2>/dev/null/../x",
        "ls 2> /dev/null",
        "ls 2> out",
        "ls >&2",
        "ls &>/dev/null",
        "cat < a",
        "ls & rm x",
        # 치환과 변수
        "echo $(rm x)",
        "echo `rm x`",
        "echo $HOME",
        # 쓰기 도구, 미지의 명령
        "git log | tee f",
        "ls | xargs rm",
        "ls; sed -i s/a/b/ f",
        "cd {r} && rm y",
        "find . -delete",
        "python3 -c 'print(1)'",
        "ls || rm x",
        "ls |& tee f",
        # 쓰는 git
        "cd {r} && git commit -m x",
        "git status | git checkout .",
        "git log --output=f",
        "git log && git push",
        # cd는 맨 앞, 절대 경로만. git은 cd가 루트일 때만
        "cd /tmp && git status",
        "cd {r}/.. && git status",
        "cd ~ && git status",
        "cd - && git status",
        "cd src && git status",
        "cd {r}/* && git status",
        "cd {r}/src && git status",
        "cd {r}/src/ && git log",
        # 상대 경로는 validate_path가 /를 붙여 루트로 보이지만 bash에서는 하위 폴더다
        "cd {rel} && git status",
        "ls && cd {r} && git status",
        "cd {r}",
        "cd {r} &&",
        # [리뷰] 허용 이름의 함수 정의는 본문을 실행한다 (업스트림 판정도 통과했다)
        "cat () ( touch x ) && cat",
        "ls () ( touch x ); ls",
        "echo ( ) ( touch x ) | echo",
        # [리뷰] glob이 `--output=x` 파일 이름을 git 옵션으로 펼친다
        "git diff *",
        "git log ?*",
        "git diff [-]*",
        "ls && git diff *",
    ],
)
def test_f1_write_capable_lookalikes_denied(root: Path, command: str) -> None:
    command = command.format(r=root, rel=str(root).lstrip("/"))
    assert not is_read_only_shell(command, root)
    assert _classify(root, "execute", {"command": command}) == (
        "deny",
        "no_approved_plan",
    )


# [F5] dcode-a(glm-5.3-flash) 실사용에서 아직 거부된 명령과 닮은꼴. {r}는 루트.


@pytest.mark.parametrize(
    "command",
    [
        # 관찰된 명령 (/root는 프로젝트 밖)
        "ls /root/a.py 2>/dev/null; ls /root/b.py",
        "ls /root/README.md >/dev/null && echo ok",
        ("git -C {r} status --short --branch && git -C {r} log --oneline -3"),
        'find /root -maxdepth 3 -name "pyvenv.cfg"',
        # 구분자 경계와 /dev/null 리다이렉트
        "ls 2>/dev/null|head -1",
        "ls 2>&1&& echo ok",
        "ls 2>/dev/null||echo none",
        "ls 1>/dev/null",
        "ls >/dev/null 2>&1 && echo ok",
        "cd {r} && git status --short 2>/dev/null;git log -1",
        "git -C {r}/ diff --stat",
        # 따옴표 안의 glob은 펼쳐지지 않는다
        "find . -name '*.py' -type f | head -5",
        'find {r} -maxdepth 2 -name "*.toml" -print',
    ],
)
def test_f5_read_only_allowed(root: Path, command: str) -> None:
    command = command.format(r=root)
    assert _classify(root, "execute", {"command": command}) == (
        "allow",
        "read_only_shell",
    )


@pytest.mark.parametrize(
    "command",
    [
        # 구분자 경계: 단독 &(백그라운드)는 계속 거부
        "ls 2>/dev/null& rm x",
        "ls 2>/dev/null &",
        "ls >/dev/null&",
        "ls 2>&1& touch x",
        "ls &>/dev/null&",
        # sh(dash)에서 `&>`는 백그라운드 + 리다이렉트다
        "echo a &>/dev/null touch pw",
        "ls &>/dev/null; echo done",
        "ls 2>/dev/null|& tee f",
        # /dev/null이 아닌 리다이렉트
        "ls >/dev/nullx",
        "ls >/dev/null/x",
        "ls >/dev/null/../tmp/x",
        "ls >|/dev/null",
        "ls >>/dev/null",
        "ls &>>/dev/null",
        "ls > /dev/null",
        "ls >out",
        "ls 1>out",
        "ls &>out",
        "ls 3>/dev/null",
        "ls 1>&2",
        "ls 2>&3",
        "ls >&/dev/null",
        "ls x>/dev/null",
        "ls >/dev/null; echo a > b",
        # git -C: 루트 자체의 절대 경로 하나만
        "git -C /tmp status",
        "git -C {r}/.. status",
        "git -C {r}/sub status",
        "git -C . status",
        "git -C {rel} status",
        "git -C ~ status",
        "git -C {r} -C /tmp status",
        "git -C {r} -C {r} status",
        "git -C{r} status",
        "git -C {r}* status",
        "git -C",
        "git -C {r}",
        "git -C {r} commit -m x",
        "git -C {r} -c core.pager=x log",
        "git -C {r} --git-dir=/tmp/x status",
        "git -C {r} --work-tree=/tmp status",
        "git -C {r} log --output=f",
        "git -C {r} diff --ext-diff",
        "git -C {r} diff *",
        "cd /tmp && git -C {r} status",
        # [F5 리뷰] -C를 떼고 다시 짤 때 줄바꿈이 공백이 되면 뒤 명령이 돈다
        "git -C {r} status\ntouch pw",
        "git -C {r} status\rtouch pw",
        "git -C {r} status;touch pw",
        "git -C {r} status 'a;b'",
        # [F5] 중괄호 펼침과 $@, $1이 git 옵션을 만든다 (전부터 있던 우회)
        "git log {{--output=f,HEAD}}",
        "git log $@--output=f",
        "git -C {r} log $1--output=f",
        # find: 실행하거나 쓰는 식
        "find . -exec rm {{}} +",
        "find . -execdir rm {{}} +",
        "find . -ok rm {{}} +",
        "find . -okdir rm {{}} +",
        "find . -ok rm",
        "find . -okdir rm",
        "find . -execdir rm",
        "find . -delete",
        "find . -fprint f",
        "find . -fprint0 f",
        "find . -fprintf f %p",
        "find . -fls f",
        "find . -rm",
        # 따옴표와 역슬래시로 숨긴 식
        "find . '-delete'",
        'find . "-delete"',
        "find . -de'le'te",
        'find . "-exec" rm',
        "find . -ex\\ec rm",
        "find . \\-delete",
        # 펼쳐서 식이 되는 것
        "find . -name x *",
        "find . -name x -del?te",
        "find . -name x [-]delete",
        "find . -{{delete,print}}",
        "find . -del$@ete",
        "find . -del$1ete",
        "find . -name 'x",
        # 다른 검사는 그대로
        "find . | xargs rm",
        "find . -name x > out",
        "find . -name $(rm x)",
        "find . -name `rm x`",
        "find . -name x & rm y",
        "cd {r} && find . -delete",
        "ls && find . -delete",
    ],
)
def test_f5_lookalikes_denied(root: Path, command: str) -> None:
    command = command.format(r=root, rel=str(root).lstrip("/"))
    assert not is_read_only_shell(command, root)
    assert _classify(root, "execute", {"command": command}) == (
        "deny",
        "no_approved_plan",
    )


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf .deepagents/plans",
        "echo x > .deepagents/memory/a.md",
        "rm -rf .deepagents",
        "rm -rf .deepagents/*",
        "mv /p/.deepagents/improvements/x /tmp",
    ],
)
def test_rule5_shell_mentions_protected(root: Path, command: str) -> None:
    decision = _classify(root, "execute", {"command": command}, phase="executing")
    assert decision == ("deny", "protected_path")


def test_mentions_protected_ignores_other_dirs() -> None:
    assert not mentions_protected("rm -rf .deepagents/skills/x")
    assert not mentions_protected("rm .deepagents/plans-old")


@pytest.mark.parametrize("tool", ["read_file", "grep", "web_search", "task"])
def test_rule6_not_mutating(root: Path, tool: str) -> None:
    assert _classify(root, tool, {}) == ("allow", "not_mutating")


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("write_file", {"file_path": "/tmp/x"}),
        ("execute", {"command": "rm -rf x"}),
        ("js_eval", {}),
        ("mcp_write", {}),
    ],
)
@pytest.mark.parametrize("phase", ["idle", "planning", "awaiting_approval"])
def test_rule7_no_approved_plan(
    root: Path, tool: str, args: dict[str, Any], phase: str
) -> None:
    decision = _classify(
        root, tool, args, phase=phase, mcp_mutating=frozenset({"mcp_write"})
    )
    assert decision == ("deny", "no_approved_plan")


def test_rule8_in_targets(root: Path) -> None:
    args = {"file_path": str(root / "src/a.py")}
    decision = _classify(
        root,
        "edit_file",
        args,
        phase="executing",
        targets=("src/a.py",),
        fresh_approval=True,
    )
    assert decision == ("allow", "in_targets")


@pytest.mark.parametrize(("name", "fresh"), [("src/b.py", True), ("src/a.py", False)])
def test_rule9_scope_check(root: Path, name: str, *, fresh: bool) -> None:
    decision = _classify(
        root,
        "write_file",
        {"file_path": str(root / name)},
        phase="executing",
        targets=("src/a.py",),
        fresh_approval=fresh,
    )
    assert decision == ("needs_scope_check", "scope_check")


def test_rule9_shell_after_approval(root: Path) -> None:
    decision = _classify(root, "execute", {"command": "make"}, phase="executing")
    assert decision == ("needs_scope_check", "scope_check")


# 경로 정규화.


def test_relative_tool_path_is_outside_root(root: Path) -> None:
    path = normalize_tool_path("docs/x.md")
    assert path == Path("/docs/x.md").resolve()
    assert relative_target(path, root) is None


def test_symlink_into_protected_dir(root: Path) -> None:
    plans = root / ".deepagents" / "plans"
    plans.mkdir(parents=True)
    link = root / "innocent"
    link.symlink_to(plans)
    path = normalize_tool_path(str(link / "x.md"))
    assert path is not None
    assert is_protected(path, root)
    decision = _classify(root, "write_file", {"file_path": str(link / "x.md")})
    assert decision == ("deny", "protected_path")


def test_is_protected_unrelated_path(root: Path) -> None:
    assert not is_protected(root / ".deepagents" / "skills" / "a", root)
    assert not is_protected(root / "src" / "a.py", root)


def test_project_paths_has_protected_dirs(root: Path) -> None:
    paths = project_paths(root)
    for directory in (paths.plans_dir, paths.memory_dir, paths.improvements_dir):
        assert directory.parent == paths.config_dir
        assert is_protected(directory, root)


# 작은 도우미.


def test_tool_name_of() -> None:
    assert tool_name_of({"type": "web_search_20250305", "name": "web_search"}) == (
        "web_search"
    )
    assert tool_name_of({"type": "x"}) is None


def test_summarize_call() -> None:
    assert summarize_call("execute", {"command": "ls   -la\n"}) == "execute ls -la"
    assert summarize_call("write_file", {"file_path": "/a", "content": "secret"}) == (
        "write_file /a"
    )
    assert len(summarize_call("execute", {"command": "x" * 500})) == 200
