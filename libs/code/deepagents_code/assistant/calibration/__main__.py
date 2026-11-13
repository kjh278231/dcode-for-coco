"""Jev 보정 명령 (SPEC 8장).

python -m deepagents_code.assistant.calibration generate --question J1 --count 40
python -m deepagents_code.assistant.calibration evaluate --question J1 --split dev
python -m deepagents_code.assistant.calibration evaluate --all --split holdout
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from dataclasses import asdict
from pathlib import Path

from deepagents_code.assistant.calibration.calibrate import (
    CASES_DIR,
    QUESTIONS,
    CalibrationReport,
    evaluate,
    generate,
    load_cases,
    plan_specs,
    report_at,
    write_cases,
)
from deepagents_code.assistant.decider import DeciderError, JevDecider

SWEEP = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def _line(r: CalibrationReport) -> str:
    return (
        f"{r.question} {r.split} n={r.n} 임계값 {r.threshold:.2f}: "
        f"TP {r.true_positive} FP {r.false_positive} TN {r.true_negative} "
        f"FN {r.false_negative} 판정불가 {r.failed} | 정밀도 {_fmt(r.precision)} "
        f"재현율 {_fmt(r.recall)} 차단 재현율 {_fmt(r.block_recall)}"
    )


def _load_env() -> None:
    # dcode와 같은 .env 규칙(셸, 프로젝트 .env, ~/.deepagents/.env)
    from deepagents_code.config import _load_dotenv

    _load_dotenv()  # start_path 없으면 작업 폴더에서 찾는다


def _generate(args: argparse.Namespace) -> int:
    questions = QUESTIONS if args.all else (args.question,)
    print(  # noqa: T201
        f"질문 {len(questions)}개 x 사례 {args.count}건 = 모델 호출 "
        f"{len(questions) * args.count}회 이상(실패 시 사례당 최대 4회)"
    )
    _load_env()
    from deepagents_code.config import create_model

    result = create_model(args.model)
    print(f"생성 모델: {result.provider}:{result.model_name}")  # noqa: T201
    tokens = {"input": 0, "output": 0, "calls": 0}
    lock = threading.Lock()

    def ask(prompt: str) -> str:
        message = result.model.invoke(prompt)
        usage = getattr(message, "usage_metadata", None) or {}
        with lock:
            tokens["calls"] += 1
            tokens["input"] += usage.get("input_tokens", 0)
            tokens["output"] += usage.get("output_tokens", 0)
        return message.text

    missing = 0
    for question in questions:
        # 이미 만든 사례는 다시 만들지 않는다. 실패로 빠진 것만 다음 실행에서 채운다
        have = {c.id: c for c in load_cases(question, Path(args.cases_dir))}
        specs = plan_specs(question, args.count)
        todo = [s for s in specs if s.id not in have]
        made = {c.id: c for c in generate(question, todo, ask, workers=args.workers)}
        cases = [have.get(s.id) or made.get(s.id) for s in specs]
        done = [c for c in cases if c is not None]
        path = write_cases(question, done, Path(args.cases_dir))
        missing += len(specs) - len(done)
        print(  # noqa: T201
            f"{question}: 새로 {len(made)}건, 모두 {len(done)}/{len(specs)}건 -> {path}"
        )
    print(  # noqa: T201
        f"모델 호출 {tokens['calls']}회, 입력 {tokens['input']} 출력 "
        f"{tokens['output']} 토큰"
    )
    if missing:
        print(f"못 만든 사례 {missing}건. 다시 실행하면 그것만 만든다.")  # noqa: T201
    return 1 if missing else 0


def _evaluate(args: argparse.Namespace) -> int:
    questions = QUESTIONS if args.all else (args.question,)
    cases = {
        q: [c for c in load_cases(q, Path(args.cases_dir)) if c.split == args.split]
        for q in questions
    }
    missing = [q for q, c in cases.items() if not c]
    if missing:
        print(f"사례가 없다: {', '.join(missing)}", file=sys.stderr)  # noqa: T201
        return 1
    print(  # noqa: T201
        f"Jev 호출 {sum(len(c) for c in cases.values())}회 ({args.split})"
    )
    _load_env()
    environ = dict(os.environ)
    try:
        decider = JevDecider.from_environment(environ)
    except DeciderError as exc:
        print(f"Jev 키 오류: {exc}", file=sys.stderr)  # noqa: T201
        return 2
    if args.threshold is not None:
        decider.threshold = args.threshold
    reports = []
    for question in questions:
        report = evaluate(question, cases[question], decider)
        reports.append(report)
        print(_line(report))  # noqa: T201
        if args.sweep:
            for t in SWEEP:
                swept = report_at(question, args.split, report.outcomes, t)
                print("  " + _line(swept))  # noqa: T201
    if args.out:
        payload = [
            {**asdict(r), "precision": r.precision, "recall": r.recall,
             "block_recall": r.block_recall}
            for r in reports
        ]  # fmt: skip
        Path(args.out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"결과: {args.out}")  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    """명령을 실행한다.

    Args:
        argv: 인자. 없으면 `sys.argv`.

    Returns:
        종료 코드. 사례나 키가 없으면 0이 아니다.
    """
    parser = argparse.ArgumentParser(
        prog="python -m deepagents_code.assistant.calibration"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("generate", "사례를 만든다"), ("evaluate", "Jev로 판정한다")):
        p = sub.add_parser(name, help=text)
        which = p.add_mutually_exclusive_group(required=True)
        which.add_argument("--question", choices=QUESTIONS)
        which.add_argument("--all", action="store_true")
        p.add_argument("--cases-dir", default=str(CASES_DIR))
    gen = sub.choices["generate"]
    gen.add_argument("--count", type=int, default=40)
    gen.add_argument("--model", help="provider:model. 없으면 dcode 기본 모델")
    gen.add_argument("--workers", type=int, default=8, help="동시 호출 수")
    ev = sub.choices["evaluate"]
    ev.add_argument("--split", choices=("dev", "holdout"), required=True)
    ev.add_argument("--threshold", type=float, help="판정기 임계값 덮어쓰기")
    ev.add_argument("--sweep", action="store_true", help="임계값별 결과도 출력")
    ev.add_argument("--out", help="사례별 확률을 담은 JSON 결과 파일")
    args = parser.parse_args(argv)
    if args.command == "generate":
        return _generate(args)
    return _evaluate(args)


if __name__ == "__main__":
    sys.exit(main())
