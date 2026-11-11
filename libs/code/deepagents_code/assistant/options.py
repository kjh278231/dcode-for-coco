"""계획 게이트가 공유하는 상수와 타입."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from deepagents_code._env_vars import PLAN_GATE

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    # decider와 reviewer가 이 모듈을 import하므로 타입 검사 때만 가져온다
    from deepagents_code.assistant.decider import Decider
    from deepagents_code.assistant.reviewer import PlanReviewer

PLAN_GATE_MIDDLEWARE_NAME: str = "PlanGateMiddleware"

WRITE_PATH_TOOLS: frozenset[str] = frozenset({"write_file", "edit_file", "delete"})
SHELL_TOOLS: frozenset[str] = frozenset({"execute"})
OTHER_MUTATING_TOOLS: frozenset[str] = frozenset(
    {"js_eval", "start_async_task", "update_async_task", "cancel_async_task"}
)
# 원격 서브에이전트를 시작하거나 지시를 바꾼다. 원격에는 쓰기 차단이 없다 (P3)
ASYNC_SUBAGENT_TOOLS: frozenset[str] = frozenset(
    {"start_async_task", "update_async_task"}
)
# 서브에이전트가 쓸 수 있는 도구. 그 밖은 거부한다. execute는 읽기 전용 명령만
SUBAGENT_ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "ls",
        "read_file",
        "glob",
        "grep",
        "execute",
        "ask_user",
        "compact_conversation",
        "fetch_url",
        "web_search",
        "get_current_thread_id",
    }
)
PLAN_TOOLS: frozenset[str] = frozenset(
    {
        "submit_plan",
        "request_plan_approval",
        "complete_plan",
        "propose_rule",
        "propose_improvement",
    }
)
EXPLORER_SUBAGENT_NAME: str = "explorer"
MAX_REVIEW_ROUNDS: int = 2
JEV_THRESHOLD_DEFAULT: float = 0.5
APPROVE_WORDS: frozenset[str] = frozenset({"승인", "approve", "approved", "yes", "y"})
REJECT_WORDS: frozenset[str] = frozenset({"거부", "reject", "rejected", "no", "n"})

PROTECTED_DIRS: tuple[str, ...] = (
    ".deepagents/plans",
    ".deepagents/memory",
    ".deepagents/improvements",
)
"""프로젝트 루트 기준으로 에이전트가 직접 쓰면 안 되는 폴더."""

Phase = Literal["idle", "planning", "awaiting_approval", "executing"]

# 게이트 상태 키. gate와 tools가 서로를 import하지 않고 같이 쓴다
PHASE_KEY = "_cg_phase"
PLAN_ID_KEY = "_cg_plan_id"
REVIEW_ROUND_KEY = "_cg_review_round"
EXPLORED_KEY = "_cg_explored"
NEEDS_CHANGE_KEY = "_cg_needs_change"
LAST_HUMAN_ID_KEY = "_cg_last_human_id"
APPROVED_HUMAN_ID_KEY = "_cg_approved_human_id"
REQUEST_TEXT_KEY = "_cg_request_text"
COUNTERS_KEY = "_cg_counters"
LAST_ERROR_KEY = "_cg_last_error"


@dataclass(frozen=True, slots=True)
class PlanGateOptions:
    """계획 게이트를 조립하는 데 필요한 값 묶음."""

    project_root: Path
    decider: Decider
    reviewer: PlanReviewer
    interactive: bool
    # 쓰기 계열로 보는 MCP 도구와 확장 도구 이름. create_cli_agent가 확장 이름을 더한다
    mcp_mutating_tool_names: frozenset[str] = frozenset()
    threshold: float = JEV_THRESHOLD_DEFAULT


def plan_gate_enabled(environ: Mapping[str, str]) -> bool:
    """게이트 끄기 스위치를 읽는다.

    Args:
        environ: 환경변수 사전.

    Returns:
        `DEEPAGENTS_CODE_PLAN_GATE`가 `0`이나 `false`가 아니면 True.
    """
    return environ.get(PLAN_GATE, "").strip().lower() not in {"0", "false"}
