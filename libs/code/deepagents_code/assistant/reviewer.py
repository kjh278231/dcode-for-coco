"""계획을 읽고 수정 의견을 쓰는 LLM 리뷰어."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from deepagents_code.assistant import prompts

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.language_models import BaseChatModel

    from deepagents_code.assistant.decider import Verdict
    from deepagents_code.assistant.plan import Plan

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReviewResult:
    """리뷰 한 회의 결과."""

    comments: tuple[str, ...]
    questions: tuple[str, ...]
    error: str | None = None


class PlanReview(BaseModel):
    """계획 리뷰 결과를 제출한다."""

    # 기본값을 두지 않는다. 필드가 빠진 답은 검증 실패로 error가 된다
    comments: list[str] = Field(description="작성자가 고칠 수정 의견. 없으면 빈 목록.")
    questions: list[str] = Field(
        description="사람에게 물어야 하는 질문. 없으면 빈 목록."
    )


def _review_input(
    plan: Plan, verdicts: Sequence[Verdict], format_issues: Sequence[str]
) -> str:
    failed = [f"- {v.name} ({v.reason})" for v in verdicts if not v.passed]
    issues = [f"- {issue}" for issue in format_issues]
    return "\n\n".join(
        [
            "# 계획\n" + plan.to_markdown(),
            "# 판정기를 통과하지 못한 질문\n" + ("\n".join(failed) or "없음"),
            "# 형식 문제\n" + ("\n".join(issues) or "없음"),
        ]
    )


class PlanReviewer:
    """계획을 읽고 수정 의견을 쓰는 리뷰어."""

    def __init__(self, model: BaseChatModel) -> None:
        """리뷰어를 만든다.

        Args:
            model: 세션의 주 모델. create_cli_agent가 해석한 객체를 받는다.
        """
        self._model = model

    async def areview(
        self,
        plan: Plan,
        verdicts: Sequence[Verdict],
        format_issues: Sequence[str],
    ) -> ReviewResult:
        """계획 하나를 리뷰한다. 예외를 던지지 않는다.

        Args:
            plan: 리뷰할 계획.
            verdicts: J1~J3 판정 결과.
            format_issues: validate_plan이 찾은 형식 문제.

        Returns:
            리뷰 결과. 실패하면 error에 예외 종류 이름을 담는다.
        """
        messages = [
            SystemMessage(prompts.REVIEWER_SYSTEM),
            HumanMessage(_review_input(plan, verdicts, format_issues)),
        ]
        try:
            structured = self._model.with_structured_output(PlanReview)
            result = await structured.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001  # 리뷰 실패는 error로 돌려준다
            logger.warning("Plan review call failed: %s", type(exc).__name__)
            return ReviewResult((), (), error=type(exc).__name__)
        # 빈 결과를 "의견 없음"으로 세면 리뷰 실패가 리뷰 통과가 된다
        if not isinstance(result, PlanReview):
            return ReviewResult((), (), error="NoStructuredOutput")
        return ReviewResult(tuple(result.comments), tuple(result.questions))
