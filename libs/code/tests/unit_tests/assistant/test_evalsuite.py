"""평가 실행기: 판정, 과제 읽기와 검사, 승인 왕복, 한 번 실행 (SPEC 7.5).

네트워크와 실제 모델은 쓰지 않는다. dcode는 같은 인자를 받는 작은 스크립트로 바꾸고,
Langfuse 조회는 가짜 `RunsClient`를 넣는다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from deepagents_code.assistant.evalsuite import suite
from deepagents_code.assistant.evalsuite.__main__ import main
from deepagents_code.assistant.evalsuite.suite import (
    APPROVE,
    TrialResult,
    judge,
    load_task,
    load_tasks,
    next_reply,
    read_signals,
    run_trial,
    verify_task,
)
from deepagents_code.assistant.improve import ImprovementStore
from deepagents_code.assistant.plan import Plan
from deepagents_code.assistant.runs import RunSummary, TracingUnavailableError

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
THREAD = "0190aaaa-bbbb-7ccc-8ddd-eeeeeeeeeeee"


def trial(
    task: str = "t1",
    variant: str = "candidate",
    n: int = 1,
    *,
    ok: bool = True,
    **signals: float,
) -> TrialResult:
    return TrialResult(
        task=task,
        variant=variant,  # ty: ignore[invalid-argument-type]
        trial=n,
        target_passed=ok,
        regression_passed=True,
        tests_untouched=True,
        signals={f"cg.{k}": v for k, v in signals.items()},
        trace_id=None,
        error=None,
    )


def both(task: str, base: list[float], cand: list[float]) -> list[TrialResult]:
    """신호 `test_failures`만 다른 baseline과 candidate 반복들."""
    return [
        trial(task, "baseline", i + 1, test_failures=v) for i, v in enumerate(base)
    ] + [trial(task, "candidate", i + 1, test_failures=v) for i, v in enumerate(cand)]


# ----- judge -----


def test_judge_all_pass_within_noise() -> None:
    # baseline 평균 1, 잡음 폭 2 → candidate 평균 2는 나빠지지 않음
    result = judge(both("t1", [0, 2, 1], [2, 2, 2]), trials=3)
    assert result["passed"] is True
    assert result["A"] == {"passed": True, "failures": []}
    assert result["B"] == {"passed": True, "regressed": []}
    assert result["C"]["status"] == "나빠지지 않음"
    detail = result["C"]["details"]["t1"]["cg.test_failures"]
    assert detail == {"baseline": 1, "candidate": 2, "noise": 2, "worse": False}
    assert result["tasks"] == {"t1": {"baseline": "3/3", "candidate": "3/3"}}
    assert result["limits"] == (
        "과제 1개, 반복 3회의 회귀 검사다. 개선의 통계적 입증이 아니다"
    )


def test_judge_signal_worse_than_noise_fails() -> None:
    result = judge(both("t1", [1, 1, 1], [1, 2, 2]), trials=3)
    assert result["A"]["passed"] is True
    assert result["C"]["status"] == "나빠짐"
    assert result["C"]["worse"] == ["t1 cg.test_failures"]
    assert result["passed"] is False


def test_judge_candidate_failure_fails_a_and_b() -> None:
    results = both("t1", [0, 0, 0], [0, 0, 0])
    results[-1] = replace(results[-1], target_passed=False)
    result = judge(results, trials=3)
    assert result["passed"] is False
    assert result["A"]["passed"] is False
    assert result["A"]["failures"] == ["t1 #3: 목표 False, 회귀 True"]
    assert result["B"] == {"passed": False, "regressed": ["t1"]}
    assert result["tasks"]["t1"] == {"baseline": "3/3", "candidate": "2/3"}


def test_judge_b_only_for_tasks_baseline_passed() -> None:
    # baseline부터 실패하던 과제는 A로 떨어지지만 B(회귀)는 아니다
    results = [
        trial("t1", "baseline", ok=False),
        trial("t1", "candidate", ok=False),
    ]
    result = judge(results, trials=1)
    assert result["A"]["passed"] is False
    assert result["B"] == {"passed": True, "regressed": []}
    assert result["passed"] is False


def test_judge_one_trial_c_undecided_a_decides() -> None:
    result = judge(both("t1", [0], [5]), trials=1)
    assert result["C"]["status"] == "판정 불가"
    assert "1회" in result["C"]["reason"]
    assert result["passed"] is True
    assert "반복 1회" in result["limits"]


def test_judge_missing_signals_c_undecided() -> None:
    results = both("t1", [0, 0, 0], [9, 9, 9])
    results[0] = replace(results[0], signals={})
    result = judge(results, trials=3)
    assert result["C"]["status"] == "판정 불가"
    assert result["C"]["reason"] == "신호를 읽지 못한 실행이 있다"
    assert result["passed"] is True


def test_judge_without_candidate_fails() -> None:
    result = judge([trial("t1", "baseline")], trials=1)
    assert result["passed"] is False
    assert result["A"]["failures"] == ["candidate 결과가 없다"]


def test_judge_regression_failure_counts() -> None:
    results = both("t1", [0], [0])
    results[1] = replace(results[1], regression_passed=False)
    assert judge(results, trials=1)["A"]["passed"] is False


# ----- 과제 -----


def test_shipped_tasks_load_and_verify() -> None:
    tasks = load_tasks()
    assert [t.name for t in tasks] == [
        "add-slugify",
        "fix-median",
        "trap-test-command",
    ]
    for task in tasks:
        assert task.instruction
        assert task.answers
        assert verify_task(task) == [], task.name


def test_load_task_missing_key(tmp_path: Path) -> None:
    (tmp_path / "task.toml").write_text('name = "x"\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"task\.toml"):
        load_task(tmp_path)


@pytest.fixture
def median_task(tmp_path: Path):
    shutil.copytree(suite.TASKS_DIR / "fix-median", tmp_path / "task")
    return load_task(tmp_path / "task")


def test_verify_task_reports_each_problem(median_task) -> None:
    # 해법이 목표를 못 고치고, 시작 상태에서 회귀 테스트가 깨지게 바꾼다
    median_task.solution.write_text("not a patch\n", encoding="utf-8")
    stats = median_task.repo / "calc" / "stats.py"
    stats.write_text(stats.read_text().replace("/ len(values)", "/ 1"))
    problems = verify_task(median_task)
    assert "repo 상태에서 회귀 테스트가 실패한다" in problems
    assert any(p.startswith("solution.patch를 적용하지 못했다") for p in problems)


def test_verify_task_target_already_passing(median_task) -> None:
    # 시작 상태가 이미 고쳐져 있으면 목표 테스트가 쓸모없다
    subprocess.run(
        ["git", "apply", str(median_task.solution)], cwd=median_task.repo, check=True
    )
    problems = verify_task(median_task)
    assert "repo 상태에서 목표 테스트가 통과한다" in problems


def test_run_tests_ignores_agent_harness_files(tmp_path: Path, median_task) -> None:
    # 고치지 않은 저장소에 채점을 속이는 파일을 둬도 목표 테스트는 실패한다
    work = tmp_path / "work"
    suite.prepare_repo(median_task, work)
    (work / "unittest").mkdir()
    (work / "unittest" / "__init__.py").touch()
    (work / "unittest" / "__main__.py").write_text("raise SystemExit(0)\n")
    (work / "tests" / "__init__.py").write_text(
        "import unittest\nunittest.TestCase.assertEqual = lambda *a, **k: None\n"
    )
    assert not suite.run_tests(work, median_task.test_target, 60)
    assert not (work / "tests" / "__init__.py").exists()


# ----- 승인 왕복 -----


def plan(status: str, questions: str = "없음") -> Plan:
    return Plan(
        id="20261113-090000-x",
        status=status,  # ty: ignore[invalid-argument-type]
        targets=("calc/stats.py",),
        test_command="python3 -m unittest discover -s tests",
        review_round=1,
        trace_ids=(),
        created_at=NOW.isoformat(),
        sections={
            "요구사항": "고친다",
            "작업 범위": "- calc/stats.py",
            "완료 조건": "- 테스트 통과",
            "작업 순서": "1. 고친다",
            "참고한 Memory": "없음",
            "미결 질문": questions,
        },
    )


def test_next_reply() -> None:
    answers = iter(["둘 다"])
    assert next_reply(None, answers) is None
    for status in ("draft", "approved", "done", "failed", "rejected"):
        assert next_reply(plan(status), answers) is None
    assert next_reply(plan("reviewed"), answers) == APPROVE
    # 미결 질문이 있으면 "승인"이 아니라 답을 준다 (게이트는 "승인"을 답으로 받는다)
    assert next_reply(plan("reviewed", "- 어느 쪽?"), answers) == "둘 다"
    with pytest.raises(suite._NoAnswerError):
        next_reply(plan("reviewed", "- 또?"), answers)


# ----- 한 번 실행 -----

STUB = """\
import json, os, pathlib, subprocess, sys, time
args = sys.argv[1:]
if os.environ.get("STUB_SLEEP"):
    import signal
    def on_term(*_):
        pathlib.Path(os.environ["STUB_SLEEP"]).write_text("SIGTERM")
        sys.exit(143)
    signal.signal(signal.SIGTERM, on_term)
    time.sleep(60)
with open(os.environ["STUB_LOG"], "a") as f:
    f.write(json.dumps(args) + "\\n")
if os.environ.get("STUB_FAIL"):
    sys.exit(3)
plans = pathlib.Path(".deepagents/plans")
plans.mkdir(parents=True, exist_ok=True)
text = pathlib.Path(os.environ["STUB_PLAN"]).read_text()
if "-r" not in args:
    print("App: v0 | Agent: agent |\\nThread: {thread}")
    (plans / "20261113-090000-x.md").write_text(text)
elif not os.environ.get("STUB_STUCK"):
    if os.environ.get("STUB_TAMPER"):
        pathlib.Path(os.environ["STUB_TAMPER"]).write_text("")
    subprocess.run(["git", "apply", os.environ["STUB_PATCH"]], check=True)
    (plans / "20261113-090000-x.md").write_text(
        text.replace("status: reviewed", "status: done")
    )
"""


class FakeRuns:
    def __init__(self, batches: list[list[RunSummary]]) -> None:
        self.batches = batches
        self.calls: list[tuple[int, str | None]] = []

    def list_runs(
        self, *, limit: int = 10, session_id: str | None = None
    ) -> list[RunSummary]:
        self.calls.append((limit, session_id))
        return self.batches[min(len(self.calls), len(self.batches)) - 1]


def summary(trace_id: str, **scores: float) -> RunSummary:
    return RunSummary(
        trace_id=trace_id,
        timestamp="2026-11-13T09:00:00",
        name="LangGraph",
        session_id=THREAD,
        latency_s=1.0,
        scores={f"cg.{k}": v for k, v in scores.items()},
        error_count=0,
        url=None,
    )


@pytest.fixture
def stub_dcode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, median_task):
    dcode = tmp_path / "dcode"
    dcode.write_text(f"#!{sys.executable}\n" + STUB.format(thread=THREAD))
    dcode.chmod(0o755)
    plan_file = tmp_path / "plan.md"
    plan_file.write_text(plan("reviewed").to_markdown(), encoding="utf-8")
    monkeypatch.setenv("STUB_LOG", str(tmp_path / "calls.jsonl"))
    monkeypatch.setenv("STUB_PLAN", str(plan_file))
    monkeypatch.setenv("STUB_PATCH", str(median_task.solution))
    monkeypatch.setattr(suite, "SIGNAL_WAIT_DELAY_S", 0)
    return dcode


def calls(tmp_path: Path) -> list[list[str]]:
    lines = (tmp_path / "calls.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


def test_run_trial_approves_and_grades(tmp_path: Path, stub_dcode, median_task) -> None:
    runs = FakeRuns(
        [
            [summary("b", review_rounds=1)],  # 아직 하나만 보인다
            [
                summary("b", test_failures=1, review_rounds=2),
                summary("a", test_failures=2, review_rounds=1),
            ],
        ]
    )
    result = run_trial(
        median_task,
        "baseline",
        1,
        improvement=None,
        dcode=stub_dcode,
        workdir=tmp_path / "work",
        runs=runs,  # ty: ignore[invalid-argument-type]
    )
    assert result.error is None
    assert result.passed
    assert result.tests_untouched
    assert result.thread_id == THREAD
    assert result.calls == 2
    # 실패 수는 합하고 리뷰 회차(계획의 누적값)는 최댓값
    assert result.signals == {"cg.test_failures": 3, "cg.review_rounds": 2}
    assert result.trace_id == "b"
    assert runs.calls[-1] == (7, THREAD)
    first, second = calls(tmp_path)
    assert first[:2] == ["-n", median_task.instruction]
    assert second[:4] == ["-r", THREAD, "-n", APPROVE]
    assert "-S" in second
    assert "Thread:" in (tmp_path / "work.log").read_text()
    # 저장소는 커밋 하나로 시작한다
    assert (tmp_path / "work" / ".git").is_dir()


def test_run_trial_dcode_failure_is_recorded(
    tmp_path: Path, stub_dcode, median_task, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STUB_FAIL", "1")
    result = run_trial(
        median_task,
        "baseline",
        1,
        improvement=None,
        dcode=stub_dcode,
        workdir=tmp_path / "work",
        runs=None,
    )
    assert result.error == "dcode 종료 코드 3"
    assert not result.target_passed
    assert result.regression_passed
    assert result.signals == {}
    assert result.calls == 1


def test_run_trial_timeout_terminates(
    tmp_path: Path, stub_dcode, median_task, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 시간을 넘기면 SIGTERM으로 끝내고(dcode가 서버를 닫을 수 있게) 실패로 기록한다
    marker = tmp_path / "term"
    monkeypatch.setenv("STUB_SLEEP", str(marker))
    result = run_trial(
        replace(median_task, timeout_s=1),
        "baseline",
        1,
        improvement=None,
        dcode=stub_dcode,
        workdir=tmp_path / "work",
        runs=None,
    )
    assert result.error == "dcode가 1초 안에 끝나지 않았다"
    assert result.elapsed_s < 30
    assert marker.read_text() == "SIGTERM"
    assert not result.passed


def test_run_trial_task_tests_tampered(
    tmp_path: Path, stub_dcode, median_task, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 에이전트가 과제 폴더의 목표 테스트를 비우면 통과가 아니라 실패다
    target = median_task.test_target / "tests" / "test_median_even.py"
    monkeypatch.setenv("STUB_TAMPER", str(target))
    result = run_trial(
        median_task,
        "baseline",
        1,
        improvement=None,
        dcode=stub_dcode,
        workdir=tmp_path / "work",
        runs=None,
    )
    assert result.error == "과제 폴더의 테스트가 실행 중에 바뀌었다"
    assert not result.passed


def test_run_trial_round_cap(
    tmp_path: Path, stub_dcode, median_task, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 승인해도 계획이 계속 승인 대기면 상한에서 멈춘다
    monkeypatch.setenv("STUB_STUCK", "1")
    monkeypatch.setattr(suite, "MAX_ROUNDS", 3)
    result = run_trial(
        median_task,
        "baseline",
        1,
        improvement=None,
        dcode=stub_dcode,
        workdir=tmp_path / "work",
        runs=None,
    )
    assert result.error == "dcode 호출 상한 3회를 넘었다"
    assert result.calls == 3
    assert [c[:4] for c in calls(tmp_path)[1:]] == [["-r", THREAD, "-n", APPROVE]] * 2
    assert not result.passed


def test_run_trial_candidate_gets_rule(tmp_path: Path, stub_dcode, median_task) -> None:
    store = ImprovementStore(tmp_path / "project")
    improvement_id = store.create(
        kind="rule",
        name="use-unittest",
        description="테스트는 unittest로 돌린다",
        body="테스트는 python3 -m unittest discover -s tests로 돌린다.",
        rationale="반복 실패",
        observations=(),
        now=NOW,
    )
    result = run_trial(
        median_task,
        "candidate",
        1,
        improvement=store.load(improvement_id),
        dcode=stub_dcode,
        workdir=tmp_path / "work",
        runs=None,
    )
    memory = tmp_path / "work" / ".deepagents" / "memory"
    assert (memory / "rule-use-unittest.md").is_file()
    assert "rule-use-unittest" in (memory / "MEMORY.md").read_text()
    assert result.passed
    # 개선안 자체의 상태는 바뀌지 않는다
    assert store.load(improvement_id).status == "proposed"


def test_read_signals_gives_up_without_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(suite, "SIGNAL_WAIT_DELAY_S", 0)
    monkeypatch.setattr(suite, "SIGNAL_WAIT_ATTEMPTS", 3)
    # trace 둘 중 하나에 점수가 끝내 붙지 않는다
    runs = FakeRuns([[summary("b"), summary("a", test_failures=2)]])
    assert read_signals(runs, THREAD, 2) == ({}, None)  # ty: ignore[invalid-argument-type]
    assert len(runs.calls) == 3


# ----- 명령 -----


def test_main_verify(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["verify"]) == 0
    out = capsys.readouterr().out
    assert "fix-median: 통과" in out


def test_main_run_records_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    store = ImprovementStore(tmp_path)
    improvement_id = store.create(
        kind="rule",
        name="x",
        description="설명",
        body="본문",
        rationale="근거",
        observations=(),
        now=NOW,
    )
    seen: dict = {}

    def fake_suite(tasks, *, trials, improvement, **_: object) -> list[TrialResult]:
        seen.update(trials=trials, improvement=improvement.id)
        return [
            trial(t.name, v, n)
            for t in tasks
            for v in ("baseline", "candidate")
            for n in range(1, trials + 1)
        ]

    cli = "deepagents_code.assistant.evalsuite.__main__"
    monkeypatch.setattr(f"{cli}.run_suite", fake_suite)

    def no_keys(_environ: object) -> None:
        raise TracingUnavailableError

    monkeypatch.setattr(f"{cli}.RunsClient", no_keys)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    code = main(["run", "--improvement", improvement_id, "--project", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert seen == {"trials": 3, "improvement": improvement_id}
    assert "과제 3개 x 반복 3회 x 전후 2 = 에이전트 실행 18회" in out
    assert "판정: 통과" in out
    loaded = store.load(improvement_id)
    assert loaded.status == "validated"
    assert loaded.validation is not None
    assert loaded.validation["C"]["status"] == "판정 불가"
    assert len(loaded.validation["results"]) == 18


def test_main_run_refuses_validated_improvement(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = ImprovementStore(tmp_path)
    improvement_id = store.create(
        kind="rule",
        name="x",
        description="설명",
        body="본문",
        rationale="근거",
        observations=(),
        now=NOW,
    )
    store.record_validation(improvement_id, {"passed": False, "note": "처음 결과"})
    code = main(["run", "--improvement", improvement_id, "--project", str(tmp_path)])
    assert code == 1
    assert "지금 상태: failed" in capsys.readouterr().err
    # 떨어진 기록이 그대로 남는다
    assert store.load(improvement_id).validation == {
        "passed": False,
        "note": "처음 결과",
    }
