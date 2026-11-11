"""도구 호출을 Jev 없이 분류하는 순수 함수."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from deepagents.backends.utils import validate_path

from deepagents_code.assistant.options import (
    OTHER_MUTATING_TOOLS,
    PLAN_TOOLS,
    PROTECTED_DIRS,
    SHELL_TOOLS,
    WRITE_PATH_TOOLS,
)

# 읽기 전용 git 판정은 auto mode와 같은 기준을 써야 해서 비공개 함수를 가져온다.
from deepagents_code.auto_mode import _fixed_repo_command_allowed
from deepagents_code.config import (
    RECOMMENDED_SAFE_SHELL_COMMANDS,
    is_shell_command_allowed,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.tools import BaseTool

Decision = Literal["allow", "deny", "needs_scope_check"]

_SUMMARY_MAX = 200
_PROTECTED_NAMES = "|".join(re.escape(d.split("/", 1)[1]) for d in PROTECTED_DIRS)
# 보호 폴더 자체, 또는 그 상위인 .deepagents 전체(뒤에 구분자·끝·glob)를 잡는다.
_PROTECTED_MENTION_RE = re.compile(
    rf"\.deepagents(?:/+(?:{_PROTECTED_NAMES})(?![\w.-])|/*(?=$|[\s'\";|&)*?\[]))"
)


def tool_name_of(tool: BaseTool | Mapping[str, Any]) -> str | None:
    """도구 객체나 사전에서 이름을 꺼낸다. 공급자 내장 도구는 사전으로 온다.

    Args:
        tool: 도구 객체 또는 사전.

    Returns:
        이름. 없으면 None.
    """
    name = tool.get("name") if isinstance(tool, Mapping) else tool.name
    return name if isinstance(name, str) else None


def normalize_tool_path(raw: object) -> Path | None:
    """도구 인자의 경로를 실제로 쓰일 절대 경로로 바꾼다.

    도구와 같은 `validate_path`를 쓴다. dcode 백엔드는 `virtual_mode=False`라서
    `docs/x.md`는 `/docs/x.md`, 즉 파일시스템 루트 기준 경로가 된다.

    Args:
        raw: 도구 인자 값.

    Returns:
        심볼릭 링크를 푼 절대 경로. 바꿀 수 없으면 None.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return Path(validate_path(raw)).resolve()
    except ValueError, OSError:
        return None


def relative_target(path: Path, project_root: Path) -> str | None:
    """프로젝트 루트 기준 POSIX 상대 경로를 돌려준다.

    Args:
        path: 절대 경로.
        project_root: 프로젝트 루트.

    Returns:
        상대 경로. 루트 밖이면 None.
    """
    try:
        return path.relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return None


def is_protected(path: Path, project_root: Path) -> bool:
    """경로가 보호 폴더 안이거나 그 상위인가.

    `delete`가 상위 폴더를 지우는 경우도 잡는다.

    Args:
        path: 정규화된 절대 경로.
        project_root: 프로젝트 루트.

    Returns:
        보호 폴더 안이거나 보호 폴더를 담는 경로면 True.
    """
    root = project_root.resolve()
    for name in PROTECTED_DIRS:
        protected = root / name
        if path.is_relative_to(protected) or protected.is_relative_to(path):
            return True
    return False


def is_read_only_shell(command: object, project_root: Path) -> bool:
    """셸 명령이 읽기 전용으로 확인되는가. 확신이 없으면 False.

    Args:
        command: `execute`의 `command` 인자.
        project_root: 프로젝트 루트.

    Returns:
        읽기 전용으로 확인되면 True.
    """
    if not isinstance(command, str) or not command.strip():
        return False
    if is_shell_command_allowed(command, list(RECOMMENDED_SAFE_SHELL_COMMANDS)):
        return True
    return _fixed_repo_command_allowed(command, project_root)


def mentions_protected(command: str) -> bool:
    """명령 문자열에 보호 폴더 경로가 있는가. 문자열 대조다.

    Args:
        command: 셸 명령.

    Returns:
        보호 폴더나 그 상위 `.deepagents`가 보이면 True.
    """
    return _PROTECTED_MENTION_RE.search(command) is not None


def summarize_call(tool_name: str, args: Mapping[str, Any]) -> str:
    """J4와 기록에 쓸 한 줄 요약을 만든다.

    Args:
        tool_name: 도구 이름.
        args: 도구 인자.

    Returns:
        도구 이름과 경로 또는 명령. 200자에서 자른다.
    """
    detail = next(
        (
            args[key]
            for key in ("file_path", "path", "command")
            if isinstance(args.get(key), str)
        ),
        "",
    )
    text = " ".join(f"{tool_name} {detail}".split())
    return text[:_SUMMARY_MAX]


def classify_call(
    *,
    phase: str,
    tool_name: str,
    args: Mapping[str, Any],
    targets: Sequence[str],
    project_root: Path,
    mcp_mutating: frozenset[str],
    fresh_approval: bool,
) -> tuple[Decision, str]:
    """도구 호출 하나를 Jev 없이 분류한다.

    규칙은 `docs/SPEC.md` 3.4절 표다. 위에서부터 처음 맞는 규칙을 쓴다.

    Args:
        phase: 게이트 단계.
        tool_name: 도구 이름.
        args: 도구 인자.
        targets: 승인된 계획의 대상 파일.
        project_root: 프로젝트 루트.
        mcp_mutating: 쓰기 계열 MCP 도구 이름.
        fresh_approval: 이번 사람 메시지 뒤에 받은 승인인가.

    Returns:
        (결정, 사유 코드).
    """
    if tool_name in PLAN_TOOLS:
        return "allow", "plan_tool"
    path: Path | None = None
    if tool_name in WRITE_PATH_TOOLS:
        path = normalize_tool_path(args.get("file_path"))
        if path is None:
            return "deny", "bad_path"
        if is_protected(path, project_root):
            return "deny", "protected_path"
    if tool_name in SHELL_TOOLS:
        command = args.get("command")
        if is_read_only_shell(command, project_root):
            return "allow", "read_only_shell"
        if isinstance(command, str) and mentions_protected(command):
            return "deny", "protected_path"
    mutating = WRITE_PATH_TOOLS | SHELL_TOOLS | OTHER_MUTATING_TOOLS | mcp_mutating
    if tool_name not in mutating:
        return "allow", "not_mutating"
    if phase != "executing":
        return "deny", "no_approved_plan"
    if (
        path is not None
        and fresh_approval
        and relative_target(path, project_root) in targets
    ):
        return "allow", "in_targets"
    return "needs_scope_check", "scope_check"
