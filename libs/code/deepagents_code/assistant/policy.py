"""도구 호출을 Jev 없이 분류하는 순수 함수."""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from deepagents.backends.utils import validate_path

from deepagents_code.assistant.options import (
    ASYNC_SUBAGENT_TOOLS,
    OTHER_MUTATING_TOOLS,
    PLAN_TOOLS,
    PROTECTED_DIRS,
    SHELL_TOOLS,
    WRITE_PATH_TOOLS,
)

# 읽기 전용 git 판정은 auto mode와 같은 기준을 써야 해서 비공개 함수를 가져온다.
from deepagents_code.auto_mode import _SHELL_CONTROL_RE, _fixed_repo_command_allowed
from deepagents_code.config import (
    RECOMMENDED_SAFE_SHELL_COMMANDS,
    contains_dangerous_patterns,
    is_shell_command_allowed,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.tools import BaseTool

Decision = Literal["allow", "deny", "needs_scope_check"]

_SUMMARY_MAX = 200
# [F1] 업스트림 목록에 echo만 더한다. 리다이렉트는 따로 거부되므로 출력만 한다
_READ_ONLY_COMMANDS = [*RECOMMENDED_SAFE_SHELL_COMMANDS, "echo"]
# [F1][F5] 쓰기가 없는 리다이렉트: `2>&1`, /dev/null로 가는 `>`, `1>`, `2>`.
# `&>`는 받지 않는다. sh(dash)에서는 `cmd &`와 `>/dev/null`로 나뉘어 뒤가 실행된다
# 앞은 스페이스나 시작, 뒤는 스페이스, 끝, `;`, `|`, `&&`일 때만 지운다.
# 단독 `&`가 붙으면 지우지 않아 거부된다
# bash는 공백, 탭, 줄바꿈으로만 나눈다. \s의 유니코드 공백으로 경계를 잡으면 안 된다
_HARMLESS_REDIRECT_RE = re.compile(r"(?<![^ ])(?:2>&1|[12]?>/dev/null)(?= |\Z|;|\||&&)")
# [F5] find에서 실행하거나 쓰는 식. 앞부분 일치라 -execdir, -okdir, -fprint0,
# -fprintf도 잡는다. -rm은 bfs의 -delete 별칭
_FIND_WRITE_PRIMARIES = ("-exec", "-ok", "-delete", "-fprint", "-fls", "-rm")
_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
# 업스트림 is_shell_command_allowed와 같은 분할
_SHELL_SPLIT_RE = re.compile(r"&&|\|\||[|;]")
# `cat () ( touch x ) && cat`처럼 허용 이름으로 함수를 정의하면 첫 토큰 검사를 지난다
_FUNC_DEF_RE = re.compile(r"\(\s*\)")
# glob이 `--output=x` 같은 파일 이름을 git 옵션으로 펼칠 수 있다
_GLOB_CHARS = frozenset("*?[")
# [F5] 중괄호 펼침(`{--output=f,HEAD}`)과 `$@`, `$1`도 옵션을 만든다
# (업스트림은 `$` 뒤 글자만 막는다)
_GIT_UNSAFE_CHARS = _GLOB_CHARS | {"{", "$"}
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
    if (
        not isinstance(command, str)
        or not command.strip()
        or _FUNC_DEF_RE.search(command)
    ):
        return False
    if is_shell_command_allowed(command, list(RECOMMENDED_SAFE_SHELL_COMMANDS)):
        return True
    if _git_read_only(command, project_root):
        return True
    return _read_only_chain(command, project_root)


def _git_read_only(command: str, project_root: Path) -> bool:
    # [F5] 아래에서 shlex로 다시 짜므로 줄바꿈 같은 구분자를 원문에서 먼저 막는다.
    # 다시 짠 문자열에서는 줄바꿈이 공백이 돼 `status\ntouch x`가 지나간다
    if not _GIT_UNSAFE_CHARS.isdisjoint(command) or _SHELL_CONTROL_RE.search(command):
        return False
    # [F5] `git -C <루트>`는 루트로 간 `cd` 뒤의 git과 같다. 떼고 업스트림에 넘긴다
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if (
        parts[:2] == ["git", "-C"]
        and len(parts) > 2  # noqa: PLR2004  # git -C <경로>
        and _abs_dir(parts[2]) == project_root.resolve()
    ):
        command = shlex.join(["git", *parts[3:]])
    return _fixed_repo_command_allowed(command, project_root)


def _find_read_only(segment: str) -> bool:
    """[F5] 실행하거나 쓰는 식이 없는 find인가.

    따옴표 밖의 glob, 중괄호, `$`, 역슬래시가 있으면 펼친 결과가 식이 될 수 있어
    거부한다. 따옴표를 푼 토큰이 위험한 식으로 시작해도 거부한다.

    Returns:
        읽기 전용으로 확인되면 True.
    """
    if any(c in segment for c in "\\${"):
        return False
    unquoted = _QUOTED_RE.sub("", segment)
    if any(c in unquoted for c in "*?['\""):
        return False
    try:
        parts = shlex.split(segment)
    except ValueError:
        return False
    return parts[:1] == ["find"] and not any(
        p.startswith(_FIND_WRITE_PRIMARIES) for p in parts
    )


def _read_only_chain(command: str, project_root: Path) -> bool:
    """[F1] 조합 명령의 모든 조각이 읽기 전용인가.

    `2>&1`과 /dev/null로 가는 리다이렉트만 지우고 나머지는 업스트림 검사에
    맡긴다. find는 실행하거나 쓰는 식이 없을 때만 받는다. 맨 앞의
    `cd <절대 경로>`는 받지만, 그 뒤의 git은 `cd`가 프로젝트 루트일 때만 받는다.
    다른 저장소(하위 폴더의 중첩 저장소 포함)의 설정이 git 명령에서 프로그램을
    돌릴 수 있어서다.

    Returns:
        모든 조각이 읽기 전용으로 확인되면 True.
    """
    stripped = _HARMLESS_REDIRECT_RE.sub(" ", command)
    if contains_dangerous_patterns(stripped):
        return False
    segments = [s.strip() for s in _SHELL_SPLIT_RE.split(stripped)]
    if any(not s for s in segments):
        return False
    git_ok = True
    cd_target = _cd_target(segments[0])
    if cd_target is not None:
        segments = segments[1:]
        git_ok = cd_target == project_root.resolve()
    return bool(segments) and all(
        is_shell_command_allowed(s, _READ_ONLY_COMMANDS)
        or _find_read_only(s)
        or (git_ok and _git_read_only(s, project_root))
        for s in segments
    )


def _cd_target(segment: str) -> Path | None:
    try:
        parts = shlex.split(segment)
    except ValueError:
        return None
    if len(parts) != 2 or parts[0] != "cd":  # noqa: PLR2004  # cd와 경로 하나
        return None
    return _abs_dir(parts[1])


def _abs_dir(raw: str) -> Path | None:
    # 절대 경로만 받는다. 상대 경로는 CDPATH, `-`는 OLDPWD, `~`는 홈으로 간다
    if not raw.startswith("/") or any(c in raw for c in "*?["):
        return None
    return normalize_tool_path(raw)


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
    if tool_name in ASYNC_SUBAGENT_TOOLS:
        return "deny", "async_subagent"
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
