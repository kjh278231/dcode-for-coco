"""Jev 판정기와 판정 질문 테스트."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from deepagents_code._env_vars import PLAN_GATE_JEV_THRESHOLD
from deepagents_code.assistant.decider import (
    STATE_MAX_CHARS,
    DeciderError,
    FakeDecider,
    JevDecider,
    Noul,
    question_j1,
    question_j2,
    question_j3,
    question_j4,
    question_j5,
)
from deepagents_code.assistant.plan import parse_plan

if TYPE_CHECKING:
    from collections.abc import Callable

KEY = "sk-test-secret-123"
Q = Noul(name="J1", instructions="i", true="t", false="f")


def _decider(
    handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any
) -> JevDecider:
    return JevDecider(
        KEY, client=httpx.Client(transport=httpx.MockTransport(handler)), **kwargs
    )


def _answers(answers: object) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _req: httpx.Response(200, json={"answers": answers})


def test_body_shape_and_auth_header() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"answers": {"J1": {"noul": 0.9}}})

    [verdict] = _decider(handler).judge("STATE", [Q])

    assert verdict.passed
    assert verdict.reason == "ok"
    request = seen[0]
    assert str(request.url) == JevDecider.URL
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert json.loads(request.content) == {
        "model": "jev-latest",
        "state": "STATE",
        "questions": {
            "J1": {
                "type": "noul",
                "instructions": "i",
                "criteria": {"true": "t", "false": "f"},
            }
        },
    }


@pytest.mark.parametrize(
    ("value", "passed", "reason"),
    [
        (0.49, False, "below_threshold"),
        (0.5, True, "ok"),
        (0, False, "below_threshold"),
        (1, True, "ok"),
    ],
)
def test_threshold_boundary(value: float, passed: bool, reason: str) -> None:
    [verdict] = _decider(_answers({"J1": {"noul": value}})).judge("s", [Q])
    assert (verdict.passed, verdict.reason, verdict.probability) == (
        passed,
        reason,
        value,
    )


@pytest.mark.parametrize(
    ("answers", "reason"),
    [
        ({"J1": {"noul": "0.9"}}, "invalid"),
        ({"J1": {"noul": True}}, "invalid"),
        ({"J1": {"noul": 1.5}}, "invalid"),
        ({"J1": {"noul": -0.1}}, "invalid"),
        ({"J1": "0.9"}, "invalid"),
        ({"J1": {}}, "refused"),
        ({"J1": {"noul": None}}, "refused"),
        ({}, "refused"),
        (None, "transport_error"),
        ([0.9], "transport_error"),
    ],
)
def test_bad_answers_fail_closed(answers: object, reason: str) -> None:
    [verdict] = _decider(_answers(answers)).judge("s", [Q])
    assert not verdict.passed
    assert verdict.probability is None
    assert verdict.reason == reason


def test_nan_is_invalid() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"answers": {"J1": {"noul": NaN}}}')

    [verdict] = _decider(handler).judge("s", [Q])
    assert verdict.reason == "invalid"


@pytest.mark.parametrize(
    "handler",
    [
        lambda _req: httpx.Response(500, json={"error": "boom"}),
        lambda _req: httpx.Response(200, content=b"not json"),
        lambda _req: httpx.Response(200, json=["not", "a", "dict"]),
    ],
)
def test_server_errors_are_transport_error(
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    verdicts = _decider(handler).judge("s", [Q, Noul("J2", "i", "t", "f")])
    assert [v.reason for v in verdicts] == ["transport_error"] * 2
    assert not any(v.passed for v in verdicts)


def test_timeout_is_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        msg = "slow"
        raise httpx.ReadTimeout(msg, request=request)

    [verdict] = _decider(handler).judge("s", [Q])
    assert verdict.reason == "transport_error"


def test_forty_questions_split_into_two_calls_in_order() -> None:
    questions = [Noul(f"Q{i:02d}", "i", "t", "f") for i in range(40)]
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        names = list(json.loads(request.content)["questions"])
        sizes.append(len(names))
        if (
            len(sizes) == 2
        ):  # 두 번째 묶음만 실패시켜 실패가 묶음 밖으로 번지지 않는지 본다
            return httpx.Response(503)
        return httpx.Response(200, json={"answers": {n: {"noul": 0.8} for n in names}})

    verdicts = _decider(handler).judge("s", questions)

    assert sizes == [32, 8]
    assert [v.name for v in verdicts] == [q.name for q in questions]
    assert all(v.passed for v in verdicts[:32])
    assert all(v.reason == "transport_error" for v in verdicts[32:])


def test_key_not_in_errors_or_repr() -> None:
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY") as excinfo:
        JevDecider("   ")
    assert KEY not in str(excinfo.value)
    decider = JevDecider(KEY)
    assert KEY not in repr(decider)


def test_from_environment() -> None:
    decider = JevDecider.from_environment({"TYPESAFE_API_KEY": KEY})
    assert decider.threshold == pytest.approx(0.5)
    assert (decider.url, decider.model) == (JevDecider.URL, "jev-latest")
    decider = JevDecider.from_environment({"OPENROUTER_API_KEY": KEY})
    assert (decider.url, decider.model) == (
        JevDecider.OPENROUTER_URL,
        JevDecider.OPENROUTER_MODEL,
    )
    both = {"TYPESAFE_API_KEY": KEY, "OPENROUTER_API_KEY": "other"}
    assert JevDecider.from_environment(both).url == JevDecider.URL
    decider = JevDecider.from_environment(
        {"TYPESAFE_API_KEY": KEY, PLAN_GATE_JEV_THRESHOLD: "0.7"}
    )
    assert decider.threshold == pytest.approx(0.7)


@pytest.mark.parametrize(
    ("environ", "needle"),
    [
        ({}, "OPENROUTER_API_KEY"),
        ({"TYPESAFE_API_KEY": "  ", "OPENROUTER_API_KEY": ""}, "TYPESAFE_API_KEY"),
        (
            {"TYPESAFE_API_KEY": KEY, PLAN_GATE_JEV_THRESHOLD: "abc"},
            PLAN_GATE_JEV_THRESHOLD,
        ),
        (
            {"TYPESAFE_API_KEY": KEY, PLAN_GATE_JEV_THRESHOLD: "0"},
            PLAN_GATE_JEV_THRESHOLD,
        ),
        (
            {"TYPESAFE_API_KEY": KEY, PLAN_GATE_JEV_THRESHOLD: "nan"},
            PLAN_GATE_JEV_THRESHOLD,
        ),
        (
            {"TYPESAFE_API_KEY": KEY, PLAN_GATE_JEV_THRESHOLD: "1.5"},
            PLAN_GATE_JEV_THRESHOLD,
        ),
    ],
)
def test_from_environment_errors(environ: dict[str, str], needle: str) -> None:
    with pytest.raises(DeciderError, match=needle) as excinfo:
        JevDecider.from_environment(environ)
    assert KEY not in str(excinfo.value)


def test_fake_decider_without_script_uses_default() -> None:
    [verdict] = FakeDecider(None, default=0.0).judge("s", [Q])
    assert verdict.reason == "below_threshold"


def test_fake_decider_script_prefix_and_failure() -> None:
    decider = FakeDecider({"J4": 0.0, "J6": 0.2, "J6:keep": 0.9, "J5": None})
    questions = [Noul(n, "i", "t", "f") for n in ["J1", "J4", "J6:a", "J6:keep", "J5"]]

    verdicts = decider.judge("state", questions)

    assert [(v.passed, v.reason) for v in verdicts] == [
        (True, "ok"),
        (False, "below_threshold"),
        (False, "below_threshold"),
        (True, "ok"),
        (False, "transport_error"),
    ]
    assert decider.calls == [("state", ("J1", "J4", "J6:a", "J6:keep", "J5"))]


PLAN = parse_plan(
    """\
---
id: p1
status: draft
targets:
  - src/app.py
test_command: pytest tests/test_app.py
review_round: 0
trace_ids: []
created_at: "2026-11-11T00:00:00+09:00"
---
## 요구사항
REQ-TEXT
## 작업 범위
SCOPE-TEXT
## 완료 조건
DONE-TEXT
## 작업 순서
STEPS-TEXT
## 참고한 Memory
없음
"""
)


@pytest.mark.parametrize(
    ("build", "name", "needles"),
    [
        (lambda: question_j1(PLAN), "J1", ["DONE-TEXT", "pytest tests/test_app.py"]),
        (lambda: question_j2(PLAN), "J2", ["SCOPE-TEXT", "REQ-TEXT", "src/app.py"]),
        (lambda: question_j3(PLAN), "J3", ["STEPS-TEXT", "src/app.py", "pytest"]),
        (
            lambda: question_j4(PLAN, "write_file", "/r/src/x.py"),
            "J4",
            ["/r/src/x.py", "SCOPE-TEXT"],
        ),
        (lambda: question_j5("REQUEST", "EXPLORED"), "J5", ["REQUEST", "EXPLORED"]),
    ],
)
def test_questions_carry_needed_text(
    build: Callable[[], tuple[str, Noul]], name: str, needles: list[str]
) -> None:
    state, question = build()
    assert question.name == name
    for needle in needles:
        assert needle in state


def test_state_truncation_keeps_judged_item() -> None:
    long_plan = PLAN.with_updates(
        sections={**PLAN.sections, "요구사항": "x" * 10_000, "작업 범위": "y" * 10_000}
    )
    state, _ = question_j4(long_plan, "execute", "rm -rf build")
    assert len(state) <= STATE_MAX_CHARS
    assert state.startswith("## 도구 호출\nexecute: rm -rf build")

    for build in (question_j2, question_j3):
        state, _ = build(long_plan)
        assert len(state) <= STATE_MAX_CHARS
        assert "src/app.py" in state
    state, _ = question_j1(
        PLAN.with_updates(sections={**PLAN.sections, "완료 조건": "d" * 10_000})
    )
    assert "pytest tests/test_app.py" in state
    assert "REQ-TEXT" in state

    state, _ = question_j5("REQUEST", "z" * 10_000)
    assert len(state) <= STATE_MAX_CHARS
    assert "REQUEST" in state
