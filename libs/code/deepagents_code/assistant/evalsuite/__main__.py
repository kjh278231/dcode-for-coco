"""평가 실행기 명령 (SPEC 7.5).

python -m deepagents_code.assistant.evalsuite verify
python -m deepagents_code.assistant.evalsuite run --improvement <id> [--trials 3] [--project <경로>]
python -m deepagents_code.assistant.evalsuite run --baseline-only [--trials 1]
"""  # noqa: E501

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from deepagents_code.assistant.evalsuite.suite import (
    JEV_PER_RUN,
    judge,
    load_tasks,
    run_suite,
    verify_task,
)
from deepagents_code.assistant.improve import ImprovementStore
from deepagents_code.assistant.runs import RunsClient, TracingUnavailableError


def _verify(tasks: list) -> bool:
    ok = True
    for task in tasks:
        problems = verify_task(task)
        print(f"{task.name}: {'통과' if not problems else '문제 있음'}")  # noqa: T201
        for p in problems:
            print(f"  - {p}")  # noqa: T201
        ok = ok and not problems
    return ok


def _run(args: argparse.Namespace, tasks: list) -> int:
    improvement = None
    store = None
    if args.improvement:
        # CLI 프로세스라 작업 폴더가 곧 사용자가 가리킨 프로젝트다
        store = ImprovementStore(Path(args.project).resolve())
        improvement = store.load(args.improvement)
        # 검증 기록을 덮어쓰지 않는다. 떨어진 기록도 남긴다 (SPEC 13장)
        if improvement.status != "proposed":
            print(  # noqa: T201
                f"검증 전(proposed)인 개선안만 검증한다. 지금 상태: "
                f"{improvement.status}",
                file=sys.stderr,
            )
            return 1
    dcode = Path(sys.executable).with_name("dcode")
    if not dcode.is_file():
        print(f"dcode를 찾지 못했다: {dcode}", file=sys.stderr)  # noqa: T201
        return 2
    if not _verify(tasks):
        print("과제 검사에 실패해 실행하지 않는다.", file=sys.stderr)  # noqa: T201
        return 1
    sides = 2 if improvement else 1
    agent_runs = len(tasks) * args.trials * sides
    print(  # noqa: T201
        f"과제 {len(tasks)}개 x 반복 {args.trials}회 x "
        f"{'전후 2' if improvement else 'baseline 1'} = 에이전트 실행 {agent_runs}회, "
        f"Jev 호출 약 {agent_runs * JEV_PER_RUN}회 (어림)"
    )
    try:
        runs = RunsClient(os.environ)
    except TracingUnavailableError:
        runs = None
        print("Langfuse 키가 없어 신호 없이 실행한다. 지표(C)는 판정 불가다.")  # noqa: T201
    root = Path(tempfile.mkdtemp(prefix="dcode-eval-"))
    print(f"작업 폴더: {root}")  # noqa: T201
    results = run_suite(
        tasks,
        trials=args.trials,
        improvement=improvement,
        dcode=dcode,
        root=root,
        runs=runs,
        report=lambda line: print(line, flush=True),  # noqa: T201
    )
    record: dict = {"results": [asdict(r) for r in results]}
    passed_all = all(r.passed for r in results)
    if improvement is not None and store is not None:
        verdict = judge(results, trials=args.trials)
        record = {**verdict, **record}
        store.record_validation(improvement.id, record)
        passed_all = verdict["passed"]
        print(  # noqa: T201
            f"판정: {'통과' if verdict['passed'] else '탈락'} "
            f"(A {verdict['A']['passed']}, B {verdict['B']['passed']}, "
            f"C {verdict['C']['status']})\n{verdict['limits']}"
        )
    (root / "results.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"결과: {root / 'results.json'}")  # noqa: T201
    return 0 if passed_all else 1


def main(argv: list[str] | None = None) -> int:
    """명령을 실행한다.

    Args:
        argv: 인자. 없으면 `sys.argv`.

    Returns:
        종료 코드. 과제 검사나 판정에 실패하면 1.
    """
    parser = argparse.ArgumentParser(
        prog="python -m deepagents_code.assistant.evalsuite"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify", help="과제 정의를 검사한다 (모델을 부르지 않는다)")
    run = sub.add_parser("run", help="과제를 실제 dcode로 실행한다")
    which = run.add_mutually_exclusive_group(required=True)
    which.add_argument("--improvement", metavar="ID", help="검증할 개선안 id")
    which.add_argument("--baseline-only", action="store_true", help="개선안 없이만")
    run.add_argument("--trials", type=int, default=None, help="반복 수")
    run.add_argument("--project", default=".", help="개선안이 있는 프로젝트 루트")
    args = parser.parse_args(argv)
    tasks = load_tasks()
    if args.command == "verify":
        return 0 if _verify(tasks) else 1
    if args.trials is None:
        args.trials = 1 if args.baseline_only else 3
    if args.trials < 1:
        parser.error("--trials는 1 이상이어야 한다")
    return _run(args, tasks)


if __name__ == "__main__":
    sys.exit(main())
