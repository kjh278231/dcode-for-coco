"""계획 게이트가 공유하는 상수와 타입."""

from __future__ import annotations

from typing import Literal

PLAN_GATE_MIDDLEWARE_NAME: str = "PlanGateMiddleware"

WRITE_PATH_TOOLS: frozenset[str] = frozenset({"write_file", "edit_file", "delete"})
SHELL_TOOLS: frozenset[str] = frozenset({"execute"})
OTHER_MUTATING_TOOLS: frozenset[str] = frozenset(
    {"js_eval", "start_async_task", "update_async_task", "cancel_async_task"}
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

# PlanGateOptions는 Decider와 PlanReviewer가 생기는 M2에서 여기에 더한다.
