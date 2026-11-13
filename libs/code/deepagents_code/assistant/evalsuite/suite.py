"""평가 실행기: 과제, 과제 검사, 실행, 판정 (SPEC 7.5).

과제 셋을 실제 `dcode -n`으로 풀게 하고 숨긴 테스트로 채점한다. 개선안 검증에서는
baseline(개선안 없음)과 candidate(개선안 넣음)를 같은 횟수 돌려 `judge`로 비교한다.
과제 몇 개의 반복 실행이라 회귀 검사일 뿐 개선의 통계적 입증이 아니다.
"""

from __future__ import annotations

import hashlib
import logging
import operator
import os
import re
import shutil
import subprocess  # noqa: S404  # dcode와 테스트를 자식 프로세스로 돌린다
import sys
import tempfile
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import TYPE_CHECKING, Any, Literal

from deepagents_code._paths import project_paths
from deepagents_code.assistant.improve import THRESHOLDS, install
from deepagents_code.assistant.memory import MemoryStore
from deepagents_code.assistant.options import APPROVE_WORDS
from deepagents_code.assistant.plan import PlanFormatError, PlanStore

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

    from deepagents_code.assistant.improve import Improvement
    from deepagents_code.assistant.plan import Plan
    from deepagents_code.assistant.runs import RunsClient

logger = logging.getLogger(__name__)

TASKS_DIR = Path(__file__).parent / "tasks"
MAX_ROUNDS = 5
"""과제 하나에서 dcode를 부르는 횟수의 상한 (요청 1 + 승인과 답)."""
SHELL_ALLOW = "recommended,python3"
"""비대화 실행의 셸 허용 목록. 없으면 셸이 꺼져 `complete_plan`이 테스트를 못 돈다."""
APPROVE = "승인"
JEV_PER_RUN = 5
"""에이전트 실행 한 번의 Jev 호출 수 어림 (J6, J5, 리뷰 뒤 J4 몇 번). 근거 없음."""
SIGNAL_WAIT_ATTEMPTS = 24
"""점수는 실행이 끝나고 1분 가까이 지나야 조회됐다 (M8 확인)."""
SIGNAL_WAIT_DELAY_S = 5.0
_TERM_GRACE_S = 60
JUDGED_SIGNALS: tuple[str, ...] = tuple(t.signal for t in THRESHOLDS)
"""C 비교에 쓰는 신호. 모두 클수록 나쁜 값이다."""
UNDECIDED = "판정 불가"
# 비대화 헤더 "Thread: <uuid7>". Rich가 줄을 바꿔 "Thread:" 앞뒤가 갈릴 수 있다
_THREAD_RE = re.compile(
    r"Thread:\s+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)

_RUN_UNITTEST = (
    "import sys, unittest; sys.path.insert(0, ''); "
    "unittest.main(module=None, argv=['unittest', *sys.argv[1:]])"
)

assert APPROVE in APPROVE_WORDS  # noqa: S101  # 게이트가 받는 단어여야 한다

Variant = Literal["baseline", "candidate"]


@dataclass(frozen=True, slots=True)
class Task:
    """과제 하나 (`tasks/<이름>/`)."""

    name: str
    path: Path
    instruction: str
    test_target: Path
    test_regression: Path
    timeout_s: int
    answers: tuple[str, ...]
    """미결 질문이 나오면 차례로 주는 답."""

    @property
    def repo(self) -> Path:
        """시작 상태의 저장소."""
        return self.path / "repo"

    @property
    def solution(self) -> Path:
        """참조 해법."""
        return self.path / "solution.patch"


def load_task(path: Path) -> Task:
    """`task.toml`을 읽는다.

    Args:
        path: 과제 폴더.

    Returns:
        과제.

    Raises:
        ValueError: 필수 키가 없거나 값이 잘못됐을 때.
    """
    meta = tomllib.loads((path / "task.toml").read_text(encoding="utf-8"))
    try:
        instruction = (path / meta["instruction_file"]).read_text(encoding="utf-8")
        return Task(
            name=str(meta["name"]),
            path=path,
            instruction=instruction.strip(),
            test_target=path / meta["test_target"],
            test_regression=path / meta["test_regression"],
            timeout_s=int(meta["timeout_s"]),
            answers=tuple(str(a) for a in meta.get("answers", ())),
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        msg = f"{path.name}/task.toml을 읽지 못했다: {exc!r}"
        raise ValueError(msg) from exc


def load_tasks(root: Path = TASKS_DIR) -> list[Task]:
    """과제를 이름순으로 모두 읽는다.

    Args:
        root: 과제 폴더들의 부모.

    Returns:
        과제 목록.
    """
    return [load_task(p.parent) for p in sorted(root.glob("*/task.toml"))]


def _test_files(directory: Path) -> list[str]:
    return sorted(p.relative_to(directory).as_posix() for p in directory.rglob("*.py"))


def _git(workdir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["git", "-c", "user.name=eval", "-c", "user.email=eval@localhost", *args],  # noqa: S607
        cwd=workdir,
        capture_output=True,
        text=True,
        check=False,
    )


def prepare_repo(task: Task, workdir: Path) -> None:
    """작업 저장소를 만든다. repo/와 회귀 테스트를 넣고 커밋 하나로 시작한다.

    과제 폴더의 git 이력이 에이전트에게 보이지 않게 새로 `git init` 한다.

    Args:
        task: 과제.
        workdir: 만들 폴더. 없어야 한다.

    Raises:
        RuntimeError: git이 실패할 때.
    """
    shutil.copytree(task.repo, workdir)
    shutil.copytree(task.test_regression, workdir, dirs_exist_ok=True)
    for args in (("init", "-q"), ("add", "-A"), ("commit", "-qm", "start")):
        done = _git(workdir, *args)
        if done.returncode:
            msg = f"git {args[0]} 실패: {done.stderr.strip()}"
            raise RuntimeError(msg)


def run_tests(workdir: Path, tests: Path, timeout_s: int) -> bool:
    """테스트 폴더를 workdir에 덮어써 복사하고 unittest로 돌린다.

    Args:
        workdir: 작업 저장소.
        tests: 과제의 테스트 폴더 (`tests_target` 또는 `tests_regression`).
        timeout_s: 시간 제한.

    Returns:
        모두 통과하면 True. 시간을 넘기면 False.
    """
    # 에이전트가 테스트 폴더에 둔 파일(`tests/__init__.py`, 링크)이 채점에 끼지 않게
    for top in tests.iterdir():
        dest = workdir / top.name
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        elif dest.is_dir():
            shutil.rmtree(dest)
    shutil.copytree(tests, workdir, dirs_exist_ok=True)
    try:
        done = subprocess.run(  # noqa: S603
            # -I로 표준 unittest를 먼저 읽어 작업 저장소의 `unittest/`가 가리지 못한다.
            # 환경은 PATH만 넘긴다. 에이전트가 쓴 코드에 키를 주지 않는다
            [sys.executable, "-I", "-B", "-c", _RUN_UNITTEST, *_test_files(tests)],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env={"PATH": os.environ.get("PATH", "")},
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


def verify_task(task: Task) -> list[str]:
    """과제 정의의 문제를 문장 목록으로 돌려준다. 모델을 부르지 않는다.

    Args:
        task: 과제.

    Returns:
        문제 목록. 비었으면 쓸 수 있는 과제다.
    """
    problems = [
        f"{label} 폴더에 테스트가 없다"
        for label, d in (("목표", task.test_target), ("회귀", task.test_regression))
        if not d.is_dir() or not _test_files(d)
    ]
    if not task.instruction:
        problems.append("요청문이 비었다")
    if problems:
        return problems
    with tempfile.TemporaryDirectory(prefix="dcode-eval-verify-") as tmp:
        work = Path(tmp) / "repo"
        try:
            prepare_repo(task, work)
        except (OSError, RuntimeError) as exc:
            return [f"저장소를 만들지 못했다: {exc}"]
        if not run_tests(work, task.test_regression, task.timeout_s):
            problems.append("repo 상태에서 회귀 테스트가 실패한다")
        if run_tests(work, task.test_target, task.timeout_s):
            problems.append("repo 상태에서 목표 테스트가 통과한다")
        _git(work, "checkout", "-q", "--", ".")
        _git(work, "clean", "-qfd")
        applied = _git(work, "apply", str(task.solution))
        if applied.returncode:
            problems.append(
                f"solution.patch를 적용하지 못했다: {applied.stderr.strip()}"
            )
            return problems
        if not run_tests(work, task.test_regression, task.timeout_s):
            problems.append("해법을 적용해도 회귀 테스트가 실패한다")
        if not run_tests(work, task.test_target, task.timeout_s):
            problems.append("해법을 적용해도 목표 테스트가 실패한다")
    return problems


@dataclass(frozen=True, slots=True)
class TrialResult:
    """과제 한 번의 실행과 채점 결과."""

    task: str
    variant: Variant
    trial: int
    target_passed: bool
    regression_passed: bool
    tests_untouched: bool
    """에이전트가 회귀 테스트 파일을 바꾸지 않았다. 채점은 원본으로 덮어써서 한다."""
    signals: Mapping[str, float]
    """세션(thread) trace들의 `cg.*` 점수 합(리뷰 회차는 최댓값). 못 읽으면 빈 사전."""
    trace_id: str | None
    error: str | None
    thread_id: str | None = None
    calls: int = 0
    """dcode를 부른 횟수."""
    elapsed_s: float = 0.0

    @property
    def passed(self) -> bool:
        """목표 테스트와 회귀 테스트가 모두 통과했다."""
        return self.target_passed and self.regression_passed


class _NoAnswerError(Exception):
    """미결 질문에 줄 답이 task.toml에 없다."""


def latest_plan(workdir: Path) -> Plan | None:
    """작업 저장소의 가장 최근 계획. 없거나 읽을 수 없으면 None.

    Args:
        workdir: 작업 저장소.

    Returns:
        계획 또는 None.
    """
    store = PlanStore(workdir)
    ids = store.list_ids()  # id가 시각으로 시작해 이름순이 시간순이다
    if not ids:
        return None
    try:
        return store.load(ids[-1])
    except OSError, PlanFormatError:
        return None


def next_reply(plan: Plan | None, answers: Iterator[str]) -> str | None:
    """계획 파일 상태로 다음에 보낼 사람 메시지를 정한다. 모델 출력 문장은 보지 않는다.

    검토가 끝난(`reviewed`) 계획만 승인 대기로 본다. 미결 질문이 있으면 게이트가
    "승인"을 답으로 받으므로 답을 먼저 준다. 메시지 하나가 질문 전부의 답이다.

    Args:
        plan: 가장 최근 계획.
        answers: 남은 답.

    Returns:
        보낼 메시지. 더 보낼 것이 없으면 None.

    Raises:
        _NoAnswerError: 미결 질문이 있는데 남은 답이 없을 때.
    """
    if plan is None or plan.status != "reviewed":
        return None
    if plan.open_questions():
        answer = next(answers, None)
        if answer is None:
            raise _NoAnswerError
        return answer
    return APPROVE


def _digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _untouched(workdir: Path, tests: Path) -> bool:
    return all(_digest(workdir / f) == _digest(tests / f) for f in _test_files(tests))


def _task_tests(task: Task) -> dict[str, str | None]:
    # 채점 원본. 에이전트는 절대 경로로 패키지 안 과제 폴더에도 닿는다 (승인 뒤 J4)
    return {
        str(f): _digest(f)
        for d in (task.test_target, task.test_regression)
        for f in sorted(d.rglob("*"))
    }


def _run_dcode(
    cmd: list[str], workdir: Path, env: Mapping[str, str], timeout_s: int
) -> tuple[int | None, str]:
    """dcode를 한 번 돌린다. 시간을 넘기면 종료 코드 대신 None.

    시간을 넘기면 SIGTERM부터 보낸다. dcode는 그 신호에 자기가 띄운 서버(새 세션이라
    프로세스 그룹이 다르다)를 닫고 끝난다. 바로 SIGKILL이면 서버가 고아로 남는다.

    Args:
        cmd: dcode 명령.
        workdir: 작업 저장소.
        env: 환경.
        timeout_s: 시간 제한.

    Returns:
        (종료 코드 또는 None, stdout과 stderr를 합친 출력).
    """
    with subprocess.Popen(  # noqa: S603
        cmd,
        cwd=workdir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    ) as proc:
        try:
            output, _ = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                output, _ = proc.communicate(timeout=_TERM_GRACE_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                # 손자 프로세스가 출력 파이프를 쥐면 끝나지 않으니 기다림에도 상한
                try:
                    output, _ = proc.communicate(timeout=_TERM_GRACE_S)
                except subprocess.TimeoutExpired:
                    output = ""
            return None, output or ""
    return proc.returncode, output or ""


def read_signals(
    runs: RunsClient, thread_id: str, calls: int
) -> tuple[dict[str, float], str | None]:
    """세션의 trace들을 기다려 점수를 합한다.

    trace id는 thread id와 turn id로 만들어져 실행기가 알 수 없다. 세션 id가 thread
    id이고 dcode 호출 하나가 trace 하나라서, 호출 수만큼 trace가 보이고 모두 점수가
    붙을 때까지 기다린다. 끝내 다 보이지 않으면 일부로 평균을 내지 않고 비운다.

    Args:
        runs: 조회 클라이언트.
        thread_id: dcode thread id.
        calls: dcode를 부른 횟수.

    Returns:
        (점수 합, 가장 최근 trace id). `cg.review_rounds`는 합 대신 최댓값.
        읽지 못했으면 ({}, None).
    """
    for attempt in range(SIGNAL_WAIT_ATTEMPTS):
        found = runs.list_runs(limit=calls + 5, session_id=thread_id)
        if len(found) >= calls and all(r.scores for r in found):
            total: dict[str, float] = {}
            for r in found:
                for name, value in r.scores.items():
                    # 리뷰 회차는 요청의 증가분이 아니라 계획의 누적값이라 합하지 않는다
                    merge = max if name == "cg.review_rounds" else operator.add
                    total[name] = merge(total.get(name, 0.0), value)
            return total, found[0].trace_id
        if attempt + 1 < SIGNAL_WAIT_ATTEMPTS:
            time.sleep(SIGNAL_WAIT_DELAY_S)
    return {}, None


def run_trial(
    task: Task,
    variant: Variant,
    trial: int,
    *,
    improvement: Improvement | None,
    dcode: Path,
    workdir: Path,
    runs: RunsClient | None,
) -> TrialResult:
    """과제를 한 번 실행하고 채점한다.

    dcode 출력은 `<workdir>.log`에 남긴다.

    Args:
        task: 과제.
        variant: `baseline` 또는 `candidate`.
        trial: 반복 번호 (1부터).
        improvement: candidate이면 넣을 개선안.
        dcode: dcode 실행 파일.
        workdir: 작업 저장소를 만들 폴더. 없어야 한다.
        runs: 신호를 읽을 클라이언트. 없으면 신호 없이.

    Returns:
        실행 결과.
    """
    start = time.monotonic()
    originals = _task_tests(task)
    prepare_repo(task, workdir)
    if improvement is not None:
        skills = project_paths(workdir).skills_dir
        install(improvement, MemoryStore(workdir), skills, workdir)
    # 폭을 넓혀 헤더 줄이 잘리지 않게 한다
    env = {**os.environ, "COLUMNS": "400"}
    log = workdir.parent / f"{workdir.name}.log"
    thread_id: str | None = None
    error: str | None = None
    calls = 0
    message: str | None = task.instruction
    answers = iter(task.answers)
    with log.open("w", encoding="utf-8") as out:
        while message is not None:
            if calls == MAX_ROUNDS:
                error = f"dcode 호출 상한 {MAX_ROUNDS}회를 넘었다"
                break
            resume = ["-r", thread_id] if thread_id else []
            cmd = [str(dcode), *resume, "-n", message, "-S", SHELL_ALLOW]
            calls += 1
            out.write(f"\n===== 호출 {calls}: {message[:80]!r}\n")
            returncode, output = _run_dcode(cmd, workdir, env, task.timeout_s)
            out.write(output)
            if returncode is None:
                error = f"dcode가 {task.timeout_s}초 안에 끝나지 않았다"
                break
            if returncode:
                error = f"dcode 종료 코드 {returncode}"
                break
            if thread_id is None:
                match = _THREAD_RE.search(output)
                if match is None:
                    error = "dcode 출력에서 thread id를 찾지 못했다"
                    break
                thread_id = match.group(1)
            try:
                message = next_reply(latest_plan(workdir), answers)
            except _NoAnswerError:
                error = "미결 질문에 줄 답이 task.toml에 없다"
                break
    untouched = _untouched(workdir, task.test_regression)
    regression = target = False
    if _task_tests(task) != originals:
        error = "과제 폴더의 테스트가 실행 중에 바뀌었다"
    else:
        regression = run_tests(workdir, task.test_regression, task.timeout_s)
        target = run_tests(workdir, task.test_target, task.timeout_s)
    signals: dict[str, float] = {}
    trace_id = None
    if runs is not None and thread_id is not None:
        try:
            signals, trace_id = read_signals(runs, thread_id, calls)
        except Exception as exc:  # noqa: BLE001  # 신호는 보조 지표라 채점을 막지 않는다
            logger.warning("신호를 읽지 못했다: %s", type(exc).__name__)
    return TrialResult(
        task=task.name,
        variant=variant,
        trial=trial,
        target_passed=target,
        regression_passed=regression,
        tests_untouched=untouched,
        signals=signals,
        trace_id=trace_id,
        error=error,
        thread_id=thread_id,
        calls=calls,
        elapsed_s=round(time.monotonic() - start, 1),
    )


def run_suite(
    tasks: Sequence[Task],
    *,
    trials: int,
    improvement: Improvement | None,
    dcode: Path,
    root: Path,
    runs: RunsClient | None,
    report: Callable[[str], None],
) -> list[TrialResult]:
    """과제마다 baseline(과 candidate)을 `trials`번씩 돌린다.

    Args:
        tasks: 과제 목록.
        trials: 반복 수.
        improvement: 있으면 candidate도 돌린다.
        dcode: dcode 실행 파일.
        root: 작업 저장소들을 만들 폴더.
        runs: 신호를 읽을 클라이언트.
        report: 진행을 알릴 함수.

    Returns:
        모든 실행 결과.
    """
    variants: list[Variant] = ["baseline", "candidate"] if improvement else ["baseline"]
    results = []
    for task in tasks:
        for variant in variants:
            for trial in range(1, trials + 1):
                result = run_trial(
                    task,
                    variant,
                    trial,
                    improvement=improvement if variant == "candidate" else None,
                    dcode=dcode,
                    workdir=root / f"{task.name}-{variant}-{trial}",
                    runs=runs,
                )
                report(format_trial(result))
                results.append(result)
    return results


def format_trial(r: TrialResult) -> str:
    """실행 결과 한 줄.

    Args:
        r: 실행 결과.

    Returns:
        화면에 띄울 줄.
    """
    verdict = "통과" if r.passed else "실패"
    signals = (
        " ".join(f"{k.removeprefix('cg.')}={v:g}" for k, v in sorted(r.signals.items()))
        or "신호 없음"
    )
    tail = f" 오류: {r.error}" if r.error else ""
    return (
        f"{r.task} {r.variant} #{r.trial}: {verdict} (목표 {r.target_passed}, "
        f"회귀 {r.regression_passed}, 테스트 그대로 {r.tests_untouched}) "
        f"호출 {r.calls}회 {r.elapsed_s:.0f}초 {signals}{tail}"
    )


def _signal_check(
    base: Sequence[TrialResult], cand: Sequence[TrialResult], trials: int
) -> dict[str, Any]:
    if trials < 2:  # noqa: PLR2004  # 반복 2회부터 잡음 폭이 생긴다
        return {"status": UNDECIDED, "reason": "반복이 1회라 잡음 폭을 잴 수 없다"}
    if not base or not cand or any(not r.signals for r in (*base, *cand)):
        return {"status": UNDECIDED, "reason": "신호를 읽지 못한 실행이 있다"}
    details: dict[str, dict[str, dict[str, Any]]] = {}
    worse = []
    for task in sorted({r.task for r in (*base, *cand)}):
        b = [r.signals for r in base if r.task == task]
        c = [r.signals for r in cand if r.task == task]
        if not b or not c:
            return {"status": UNDECIDED, "reason": f"{task}의 전후 결과가 다 있지 않다"}
        details[task] = {}
        for signal in JUDGED_SIGNALS:
            bv = [s.get(signal, 0.0) for s in b]
            cv = [s.get(signal, 0.0) for s in c]
            noise = max(bv) - min(bv)
            is_worse = fmean(cv) > fmean(bv) + noise
            details[task][signal] = {
                "baseline": fmean(bv),
                "candidate": fmean(cv),
                "noise": noise,
                "worse": is_worse,
            }
            if is_worse:
                worse.append(f"{task} {signal}")
    return {
        "status": "나빠짐" if worse else "나빠지지 않음",
        "worse": worse,
        "details": details,
    }


def _pass_counts(
    task: str, base: Sequence[TrialResult], cand: Sequence[TrialResult]
) -> dict[str, str]:
    counts = {}
    for variant, group in (("baseline", base), ("candidate", cand)):
        mine = [r for r in group if r.task == task]
        if mine:
            counts[variant] = f"{sum(r.passed for r in mine)}/{len(mine)}"
    return counts


def judge(results: Sequence[TrialResult], *, trials: int) -> dict[str, Any]:
    """전후 결과에서 통과 여부를 정한다. 순수 함수다.

    A(필수): candidate의 모든 과제, 모든 반복이 통과. B(필수, A의 사유): baseline에서
    매번 통과하던 과제가 candidate에서 실패. C(지표): 과제별 신호 평균이 baseline 평균
    + 잡음 폭(baseline 최댓값 - 최솟값) 이하. 판정할 수 있는 C가 "나빠짐"이면 떨어진다.
    반복 1회나 신호가 빠진 실행이 있으면 C는 판정 불가이고 A만으로 판정한다.

    Args:
        results: baseline과 candidate 실행 결과.
        trials: 반복 수.

    Returns:
        판정. `passed`, `A`, `B`, `C`, `tasks`, `limits`, `trials`.
    """
    base = [r for r in results if r.variant == "baseline"]
    cand = [r for r in results if r.variant == "candidate"]
    names = sorted({r.task for r in results})
    failures = [
        f"{r.task} #{r.trial}: 목표 {r.target_passed}, 회귀 {r.regression_passed}"
        + (f", 오류 {r.error}" if r.error else "")
        for r in cand
        if not r.passed
    ]
    if not cand:
        failures.append("candidate 결과가 없다")
    stable = {
        n
        for n in names
        if (b := [r for r in base if r.task == n]) and all(r.passed for r in b)
    }
    regressed = sorted({r.task for r in cand if r.task in stable and not r.passed})
    signals = _signal_check(base, cand, trials)
    a_passed = not failures
    return {
        "passed": a_passed and signals["status"] != "나빠짐",
        "trials": trials,
        "A": {"passed": a_passed, "failures": failures},
        "B": {"passed": not regressed, "regressed": regressed},
        "C": signals,
        "tasks": {n: _pass_counts(n, base, cand) for n in names},
        "limits": (
            f"과제 {len(names)}개, 반복 {trials}회의 회귀 검사다. "
            "개선의 통계적 입증이 아니다"
        ),
    }
