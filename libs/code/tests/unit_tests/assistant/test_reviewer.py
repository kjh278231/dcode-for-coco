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


def test_f9_prompt_rules_from_real_run() -> None:
    """[F9] 실사용 검토에서 나온 규칙이 프롬프트에 있다."""
    reviewer = prompts.REVIEWER_SYSTEM
    assert "게이트가 쓰는 절이라 작성자가 쓸 수 없다" in reviewer
    assert "그 절에 적으라고 하지 말고" in reviewer
    assert "요구사항이나 작업 순서 본문에 넣으라고" in reviewer
    assert "비어 있는 절" in reviewer
    assert "되풀이하지 않는다" in reviewer
    assert '"하지 않을 것"' in reviewer
    assert "느린 전체 테스트" in reviewer
    assert "두 쪽을 함께 단언" in reviewer
    assert "본문에 넣는다" in prompts.GATE_BASE
    assert "(사용자 결정: ...)" in prompts.GATE_BASE
    idle = prompts.gate_prompt("idle", None)
    assert 'submit_plan 전에 task(subagent_type="explorer")' in idle
    for phase in ("idle", "planning"):
        assert "상수만 출력하는" in prompts.gate_prompt(phase, None)
    executing = prompts.gate_prompt("executing", None)
    assert "바로 앞에 같은 명령을 돌리지" in executing
    assert "테스트를 다시 돌리지 않는다" in executing
    assert "읽기 전용 샌드박스" in executing
