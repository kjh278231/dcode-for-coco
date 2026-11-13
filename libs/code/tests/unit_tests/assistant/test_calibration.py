"""Jev 보정 사례 생성과 평가 (SPEC 8장)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from deepagents_code.assistant import decider as d
from deepagents_code.assistant.calibration import calibrate as cal
from deepagents_code.assistant.calibration.__main__ import main

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

PLAN_JSON = {
    "requirements": "median이 짝수 개에서 가운데 두 값의 평균을 돌려준다.",
    "scope": "- calc/stats.py의 median 수정",
    "targets": ["calc/stats.py", "tests/test_stats.py"],
    "steps": "1. median 수정\n2. 테스트 추가",
    "done_criteria": "- `python -m unittest tests.test_stats` 통과",
    "test_command": "python -m unittest tests.test_stats",
}


class StateDecider:
    """state에 든 표지로 확률을 정하는 판정기. 표지가 없으면 판정 불가."""

    threshold = 0.5

    def __init__(self) -> None:
        self.questions: list[d.Noul] = []

    def judge(self, state: str, questions: Sequence[d.Noul]) -> list[d.Verdict]:
        self.questions.extend(questions)
        out = []
        for q in questions:
            if "HIGH" in state:
                out.append(d.Verdict(q.name, 0.9, passed=True, reason="ok"))
            elif "LOW" in state:
                out.append(
                    d.Verdict(q.name, 0.3, passed=False, reason="below_threshold")
                )
            else:
                out.append(
                    d.Verdict(q.name, None, passed=False, reason="transport_error")
                )
        return out


def test_plan_specs_balance_labels_and_splits() -> None:
    specs = cal.plan_specs("J1", 40)
    assert len(specs) == 40
    for split, n in (("dev", 24), ("holdout", 16)):
        part = [s for s in specs if s.split == split]
        assert len(part) == n
        assert sum(s.label for s in part) == n // 2
    # 이유는 라벨의 지정 목록에서만 나온다
    for s in specs:
        assert s.note in cal.SCENARIOS["J1"][s.label]
    with pytest.raises(ValueError, match="짝수"):
        cal.plan_specs("J1", 3)


def test_generation_prompt_fixes_answer_and_reason() -> None:
    spec = cal.plan_specs("J1", 2)[1]
    assert spec.label == 0
    prompt = cal.generation_prompt("J1", spec)
    assert "이 사례의 정답: 아니오" in prompt
    assert spec.note in prompt
    assert d.J1.false in prompt


def test_build_case_uses_gate_state_builders() -> None:
    spec = cal.CaseSpec("J1-001", "dev", 1, "이유", "도메인")
    case = cal.build_case("J1", spec, PLAN_JSON)
    plan = cal._plan(PLAN_JSON)
    assert case.state == d.question_j1(plan)[0]
    assert case.label == 1
    assert case.record is None

    j4 = cal.build_case(
        "J4",
        spec,
        {**PLAN_JSON, "tool_name": "execute", "tool_summary": "command=rm -rf /"},
    )
    assert j4.state.startswith("## 도구 호출\nexecute: command=rm -rf /")

    j6 = cal.build_case(
        "J6",
        spec,
        {"request": "요청", "record_name": "work-x", "record_description": "설명"},
    )
    assert j6.record == {"name": "work-x", "description": "설명"}
    assert cal.noul_for("J6", j6) == d.noul_j6("work-x", "설명")
    assert cal.noul_for("J4", j4) is d.J4


def test_generate_retries_and_keeps_assigned_label() -> None:
    specs = cal.plan_specs("J5", 2)
    replies = iter(
        [
            "설명만 있고 JSON 없음",
            '```json\n{"request": "고쳐 줘", "exploration": "탐색"}\n```',
            '{"request": "설명해 줘", "exploration": "탐색"}',
        ]
    )
    cases = cal.generate("J5", specs, lambda _p: next(replies), workers=1, backoff_s=0)
    assert [c.label for c in cases] == [s.label for s in specs]
    assert cases[0].state.startswith("## 요청\n고쳐 줘")

    # 끝내 실패한 사례는 빠지고 나머지는 남는다
    assert (
        cal.generate("J5", specs[:1], lambda _p: "없음", workers=1, backoff_s=0) == []
    )


def test_evaluate_confusion_matrix_and_failures_closed() -> None:
    cases = [
        cal.Case("a", "dev", 1, "HIGH", ""),
        cal.Case("b", "dev", 1, "LOW", ""),
        cal.Case("c", "dev", 0, "HIGH", ""),
        cal.Case("d", "dev", 0, "LOW", ""),
        cal.Case("e", "dev", 1, "none", ""),
    ]
    judge = StateDecider()
    r = cal.evaluate("J2", cases, judge, workers=2)
    assert (r.true_positive, r.false_negative) == (1, 2)
    assert (r.false_positive, r.true_negative) == (1, 1)
    assert r.failed == 1
    assert r.precision == pytest.approx(0.5)
    assert r.recall == pytest.approx(1 / 3)
    assert r.block_recall == pytest.approx(0.5)
    assert all(q is d.J2 for q in judge.questions)
    # 저장한 확률로 임계값만 바꿔 다시 센다
    low = cal.report_at("J2", "dev", r.outcomes, 0.2)
    assert (low.true_positive, low.false_positive, low.failed) == (2, 2, 1)


def test_write_and_load_roundtrip(tmp_path: Path) -> None:
    cases = [
        cal.Case("J6-001", "dev", 1, "s", "n", {"name": "w", "description": "x"}),
        cal.Case("J6-002", "holdout", 0, "s", "n"),
    ]
    path = cal.write_cases("J6", cases, tmp_path)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert "record" not in rows[1]
    assert cal.load_cases("J6", tmp_path) == cases


@pytest.mark.parametrize("question", cal.QUESTIONS)
def test_committed_cases_are_balanced(question: str) -> None:
    cases = cal.load_cases(question)
    assert len(cases) == 40
    assert len({c.id for c in cases}) == 40
    for split, n in (("dev", 24), ("holdout", 16)):
        part = [c for c in cases if c.split == split]
        assert len(part) == n
        assert sum(c.label for c in part) == n // 2
    for c in cases:
        assert c.state.strip()
        assert len(c.state) <= d.STATE_MAX_CHARS
        assert (c.record is not None) == (question == "J6")


def test_main_evaluate_without_cases(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["evaluate", "--question", "J1", "--split", "dev", "--cases-dir", str(tmp_path)]
    )
    assert code == 1
    assert "사례가 없다: J1" in capsys.readouterr().err


def test_main_generate_resumes_missing_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import types

    from deepagents_code import config
    from deepagents_code.assistant.calibration import __main__ as cli

    asked: list[str] = []
    reply = {"text": '{"request": "고쳐 줘", "exploration": "탐색"}'}

    class Model:
        def invoke(self, prompt: str) -> types.SimpleNamespace:
            asked.append(prompt)
            return types.SimpleNamespace(text=reply["text"], usage_metadata=None)

    result = types.SimpleNamespace(model=Model(), provider="fake", model_name="m")
    monkeypatch.setattr(config, "create_model", lambda _spec: result)
    monkeypatch.setattr(cli, "_load_env", lambda: None)
    monkeypatch.setattr(cli, "generate", _no_backoff(cal.generate))
    first = cal.plan_specs("J5", 4)[0]
    kept = cal.Case(first.id, first.split, first.label, "기존", first.note)
    cal.write_cases("J5", [kept], tmp_path)
    argv = [
        "generate",
        "--question",
        "J5",
        "--count",
        "4",
        "--cases-dir",
        str(tmp_path),
    ]

    assert main(argv) == 0
    assert len(asked) == 3  # 이미 있는 1건은 다시 만들지 않는다
    cases = cal.load_cases("J5", tmp_path)
    assert [c.id for c in cases] == [s.id for s in cal.plan_specs("J5", 4)]
    assert cases[0].state == "기존"

    # 끝내 실패하면 만든 것만 남기고 1로 끝난다
    other = tmp_path / "other"
    reply["text"] = "JSON 없음"
    assert main([*argv[:-1], str(other)]) == 1
    assert cal.load_cases("J5", other) == []


def _no_backoff(fn):  # noqa: ANN202
    return lambda *a, **k: fn(*a, **{**k, "backoff_s": 0})
