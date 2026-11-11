"""계획 형식, 검사, 저장 테스트."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import pytest

from deepagents_code.assistant.plan import (
    PlanFormatError,
    PlanStore,
    new_plan_id,
    parse_plan,
    validate_plan,
)

if TYPE_CHECKING:
    from pathlib import Path

EXAMPLE = """\
---
id: 20261111-153000-fix-login
status: draft
targets:
  - src/auth/login.py
  - tests/test_login.py
test_command: uv run pytest tests/test_login.py -q
review_round: 1
trace_ids: []
created_at: "2026-11-11T15:30:00+09:00"
---

## 요구사항
로그인 실패 시 500 대신 401을 돌려준다.
## 작업 범위
login.py의 예외 처리.
## 완료 조건
test_login.py 통과.
## 작업 순서
1. 테스트 추가
2. 예외 처리 수정
## 참고한 Memory
없음
## 미결 질문
- 토큰 만료도 401인가?
- 로그 형식은?
## 결정 사항
없음
## 리뷰 기록
### 1회차
범위가 적절하다.
"""


def test_example_round_trip() -> None:
    plan = parse_plan(EXAMPLE)
    assert plan.id == "20261111-153000-fix-login"
    assert plan.targets == ("src/auth/login.py", "tests/test_login.py")
    assert plan.review_round == 1
    assert plan.created_at == "2026-11-11T15:30:00+09:00"
    assert list(plan.sections)[:5] == [
        "요구사항",
        "작업 범위",
        "완료 조건",
        "작업 순서",
        "참고한 Memory",
    ]
    assert "### 1회차" in plan.sections["리뷰 기록"]
    assert parse_plan(plan.to_markdown()) == plan
    assert validate_plan(plan) == []


def test_open_questions() -> None:
    plan = parse_plan(EXAMPLE)
    assert plan.open_questions() == ("토큰 만료도 401인가?", "로그 형식은?")
    sections = dict(plan.sections)
    sections["미결 질문"] = "없음"
    assert plan.with_updates(sections=sections).open_questions() == ()
    del sections["미결 질문"]
    assert plan.with_updates(sections=sections).open_questions() == ()


@pytest.mark.parametrize(
    "text",
    [
        "id: a\n",
        EXAMPLE.replace("status: draft", "status: maybe"),
        EXAMPLE.replace("test_command: uv run pytest tests/test_login.py -q\n", ""),
        EXAMPLE.replace("review_round: 1", "review_round: one"),
        EXAMPLE.replace('"2026-11-11T15:30:00+09:00"', "2026-11-11T15:30:00+09:00"),
    ],
)
def test_parse_rejects(text: str) -> None:
    with pytest.raises(PlanFormatError):
        parse_plan(text)


def _sections(**overrides: str) -> dict[str, str]:
    sections = dict(parse_plan(EXAMPLE).sections)
    sections.update(overrides)
    return sections


@pytest.mark.parametrize(
    ("changes", "needle"),
    [
        ({"sections": _sections(요구사항="없음")}, "요구사항"),
        ({"sections": _sections(**{"완료 조건": "  "})}, "완료 조건"),
        ({"targets": ()}, "targets가 비어"),
        ({"targets": ("/etc/passwd",)}, "상대 경로"),
        ({"targets": ("../x.py",)}, ".."),
        ({"targets": ("~/x.py",)}, "상대 경로"),
        ({"targets": (".deepagents/plans/x.md",)}, ".deepagents"),
        ({"test_command": " "}, "test_command"),
        ({"targets": ("src/*.py",)}, "glob"),
    ],
)
def test_validate_rules(changes: dict, needle: str) -> None:
    plan = parse_plan(EXAMPLE).with_updates(**changes)
    problems = validate_plan(plan)
    assert len(problems) == 1
    assert needle in problems[0]


def test_memory_section_allows_empty_mark() -> None:
    plan = parse_plan(EXAMPLE).with_updates(
        sections=_sections(**{"참고한 Memory": "없음"})
    )
    assert validate_plan(plan) == []


def test_new_plan_id() -> None:
    now = datetime(2026, 11, 11, 15, 30, 0)  # noqa: DTZ001  # 형식만 본다
    assert (
        new_plan_id(now, "Fix login 500!\n둘째 줄") == "20261111-153000-fix-login-500"
    )
    assert new_plan_id(now, "로그인 고치기") == "20261111-153000-plan"
    assert len(new_plan_id(now, "a" * 50).split("-", 2)[2]) == 30


def test_store_save_twice_is_identical(tmp_path: Path) -> None:
    store = PlanStore(tmp_path)
    plan = parse_plan(EXAMPLE)
    path = store.save(plan)
    first = path.read_bytes()
    assert store.save(plan) == path
    assert path.read_bytes() == first
    assert path == tmp_path / ".deepagents" / "plans" / f"{plan.id}.md"
    assert store.load(plan.id) == plan
    assert store.list_ids() == [plan.id]
    assert [p.name for p in store.directory.iterdir()] == [path.name]


def test_store_missing(tmp_path: Path) -> None:
    store = PlanStore(tmp_path)
    assert store.list_ids() == []
    with pytest.raises(FileNotFoundError):
        store.load("nope")


@pytest.mark.parametrize("bad", ["", "a/b", "a\\b", ".."])
def test_store_rejects_bad_id(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValueError, match="계획 id"):
        PlanStore(tmp_path).path_for(bad)
