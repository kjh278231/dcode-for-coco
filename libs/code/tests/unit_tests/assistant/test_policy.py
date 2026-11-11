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
