"""LLM 리뷰어와 프롬프트 테스트."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from deepagents_code.assistant import prompts
from deepagents_code.assistant.decider import Verdict
from deepagents_code.assistant.reviewer import PlanReviewer, ReviewResult
from tests.unit_tests.assistant.fakes import FakeReviewer, scripted_model, tool_call
from tests.unit_tests.assistant.test_decider import PLAN


class _RecordingModel:
    """with_structured_output에 넘긴 메시지를 기록하고 실패하는 모델."""

    def __init__(self) -> None:
        self.seen: list[object] = []

    def with_structured_output(self, _schema: object) -> _RecordingModel:
        return self

    async def ainvoke(self, messages: object) -> object:
        self.seen.append(messages)
        msg = "boom with secret sk-123"
        raise RuntimeError(msg)


async def test_review_returns_comments_and_questions() -> None:
    model = scripted_model(
        [
            tool_call(
                "PlanReview",
                {"comments": ["완료 조건을 고쳐라"], "questions": ["Q?"]},
                "c1",
            )
        ]
    )
    result = await PlanReviewer(model).areview(PLAN, [], [])
    assert result == ReviewResult(("완료 조건을 고쳐라",), ("Q?",))


async def test_review_without_structured_output_is_error() -> None:
    result = await PlanReviewer(
        scripted_model([AIMessage(content="looks good")])
    ).areview(PLAN, [], [])
    assert result.error == "NoStructuredOutput"
    assert result.comments == ()


async def test_review_missing_key_is_error() -> None:
    model = scripted_model([tool_call("PlanReview", {"comments": []}, "c1")])
    result = await PlanReviewer(model).areview(PLAN, [], [])
    assert result.error is not None


async def test_review_exception_is_error_name_only() -> None:
    model = _RecordingModel()
    result = await PlanReviewer(model).areview(  # type: ignore[arg-type]
        PLAN,
        [
            Verdict("J1", 0.1, passed=False, reason="below_threshold"),
            Verdict("J2", 0.9, passed=True, reason="ok"),
        ],
        ["targets가 비었다"],
    )

    assert result == ReviewResult((), (), error="RuntimeError")
    [messages] = model.seen
    system, human = messages  # type: ignore[misc]
    assert system.content == prompts.REVIEWER_SYSTEM
    assert "J1 (below_threshold)" in human.content
    assert "J2" not in human.content
    assert "targets가 비었다" in human.content
    assert "REQ-TEXT" in human.content


async def test_fake_reviewer_follows_script() -> None:
    reviewer = FakeReviewer([ReviewResult(("a",), ())])
    assert (await reviewer.areview(PLAN, [], [])).comments == ("a",)
    assert (await reviewer.areview(PLAN, [], [])) == ReviewResult((), ())
    assert len(reviewer.calls) == 2


def test_gate_prompt_per_phase() -> None:
    assert prompts.ASK_HUMAN_CRITERIA in prompts.GATE_BASE
    assert prompts.ASK_HUMAN_CRITERIA in prompts.REVIEWER_SYSTEM
    executing = prompts.gate_prompt("executing", "계획 p1")
    assert executing.startswith(prompts.GATE_BASE)
    assert "승인됨" in executing
    assert executing.endswith("현재 계획:\n계획 p1")
    assert prompts.gate_prompt("idle", None) != prompts.gate_prompt("planning", None)
    assert prompts.gate_prompt("unknown", None) == prompts.GATE_BASE
