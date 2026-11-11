"""assistant 테스트가 같이 쓰는 가짜 객체."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage

from deepagents_code._fake_models import _ToolBindingFakeModel
from deepagents_code.assistant.decider import FakeDecider
from deepagents_code.assistant.options import PlanGateOptions
from deepagents_code.assistant.reviewer import ReviewResult

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from langchain_core.language_models import BaseChatModel

    from deepagents_code.assistant.decider import Decider, Verdict
    from deepagents_code.assistant.plan import Plan
    from deepagents_code.assistant.reviewer import PlanReviewer


@dataclass
class FakeReviewer:
    """회차별 ReviewResult 대본으로 답하는 리뷰어. 대본이 끝나면 의견 없음."""

    script: Sequence[ReviewResult] = ()
    calls: list[tuple[Plan, tuple[Verdict, ...], tuple[str, ...]]] = field(
        default_factory=list
    )

    async def areview(
        self, plan: Plan, verdicts: Sequence[Verdict], format_issues: Sequence[str]
    ) -> ReviewResult:
        """대본의 다음 결과를 돌려준다.

        Returns:
            이번 회차의 ReviewResult.
        """
        index = len(self.calls)
        self.calls.append((plan, tuple(verdicts), tuple(format_issues)))
        if index < len(self.script):
            return self.script[index]
        return ReviewResult((), ())


def scripted_model(messages: Sequence[AIMessage]) -> BaseChatModel:
    """대본대로 답하는 모델.

    Returns:
        messages를 차례로 돌려주는 가짜 채팅 모델.
    """
    return _ToolBindingFakeModel(messages=iter(messages))


def tool_call(name: str, args: Mapping[str, Any], call_id: str) -> AIMessage:
    """도구 호출 하나를 담은 AI 메시지.

    Returns:
        tool_calls가 하나인 AIMessage.
    """
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": dict(args), "id": call_id, "type": "tool_call"}
        ],
    )


def make_options(
    tmp_path: Path,
    *,
    decider: Decider | None = None,
    reviewer: PlanReviewer | FakeReviewer | None = None,
    interactive: bool = True,
) -> PlanGateOptions:
    """가짜 판정기와 리뷰어로 게이트 옵션을 만든다.

    Returns:
        tmp_path를 프로젝트 루트로 하는 옵션.
    """
    return PlanGateOptions(
        project_root=tmp_path,
        decider=decider or FakeDecider(),
        reviewer=reviewer or FakeReviewer(),  # type: ignore[arg-type]
        interactive=interactive,
    )
