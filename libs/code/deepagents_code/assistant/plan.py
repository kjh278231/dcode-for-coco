"""계획 파일의 형식, 검사, 저장."""

from __future__ import annotations

import dataclasses
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal, get_args

from deepagents_code.assistant import frontmatter

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

PlanStatus = Literal["draft", "reviewed", "approved", "done", "failed", "rejected"]

REQUIRED_SECTIONS: tuple[str, ...] = (
    "요구사항",
    "작업 범위",
    "완료 조건",
    "작업 순서",
    "참고한 Memory",
)
OPTIONAL_SECTIONS: tuple[str, ...] = ("미결 질문", "결정 사항", "리뷰 기록")
EMPTY_MARK: str = "없음"

_EMPTY_ALLOWED_SECTION = "참고한 Memory"
_OPEN_QUESTIONS_SECTION = "미결 질문"
_SECTION_RE = re.compile(r"^## (.+?)[ \t]*$", re.MULTILINE)
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+?)\s*$")
_GLOB_CHARS = frozenset("*?[")
_SLUG_MAX = 30


class PlanFormatError(ValueError):
    """계획 파일 형식 오류."""


@dataclass(frozen=True, slots=True)
class Plan:
    """계획 한 건. 파일 하나와 일대일로 대응한다."""

    id: str
    status: PlanStatus
    targets: tuple[str, ...]
    test_command: str
    review_round: int
    trace_ids: tuple[str, ...]
    created_at: str
    sections: Mapping[str, str]
    """제목에서 본문으로. REQUIRED, OPTIONAL, 그 밖의 절 순서다."""

    def open_questions(self) -> tuple[str, ...]:
        """미결 질문 절의 목록 항목을 돌려준다.

        Returns:
            항목 문자열. 절이 없거나 "없음"이면 빈 튜플.
        """
        body = self.sections.get(_OPEN_QUESTIONS_SECTION, "").strip()
        if not body or body == EMPTY_MARK:
            return ()
        items = []
        for line in body.splitlines():
            match = _LIST_ITEM_RE.match(line)
            if match:
                items.append(match.group(1))
        return tuple(items)

    def to_markdown(self) -> str:
        """파일에 쓸 문자열을 만든다.

        Returns:
            frontmatter와 절 본문을 이은 마크다운.
        """
        meta = {
            "id": self.id,
            "status": self.status,
            "targets": list(self.targets),
            "test_command": self.test_command,
            "review_round": self.review_round,
            "trace_ids": list(self.trace_ids),
            "created_at": self.created_at,
        }
        body = "\n".join(
            f"## {title}\n{text}\n" for title, text in self.sections.items()
        )
        return frontmatter.render(meta, body)

    def with_updates(self, **changes: Any) -> Plan:  # replace와 같은 계약
        """바뀐 필드만 갈아 끼운 새 Plan을 돌려준다.

        Args:
            **changes: 바꿀 필드와 값.

        Returns:
            새 Plan.
        """
        return dataclasses.replace(self, **changes)


def _order_sections(found: Mapping[str, str]) -> dict[str, str]:
    known = REQUIRED_SECTIONS + OPTIONAL_SECTIONS
    ordered = {title: found[title] for title in known if title in found}
    ordered.update((t, b) for t, b in found.items() if t not in ordered)
    return ordered


def _split_sections(body: str) -> dict[str, str]:
    matches = list(_SECTION_RE.finditer(body))
    found: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        title = match.group(1)
        if title in found:
            msg = f"절 '{title}'이 두 번 나온다."
            raise PlanFormatError(msg)
        found[title] = body[match.end() : end].strip()
    return _order_sections(found)


def _str_tuple(meta: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = meta.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        msg = f"'{key}'는 문자열 목록이어야 한다."
        raise PlanFormatError(msg)
    return tuple(value)


def _required_str(meta: Mapping[str, Any], key: str) -> str:
    if key not in meta:
        msg = f"필수 키 '{key}'가 없다."
        raise PlanFormatError(msg)
    value = meta[key]
    if not isinstance(value, str):
        msg = f"'{key}'는 문자열이어야 한다."
        raise PlanFormatError(msg)
    return value


def parse_plan(text: str) -> Plan:
    """마크다운 문자열을 Plan으로 읽는다.

    Args:
        text: 계획 파일 내용.

    Returns:
        읽은 Plan.

    Raises:
        PlanFormatError: frontmatter 오류, 필수 키 누락, 타입 오류, status 값 오류.
    """
    try:
        meta, body = frontmatter.parse(text)
    except frontmatter.FrontmatterError as exc:
        raise PlanFormatError(str(exc)) from exc

    plan_id = _required_str(meta, "id")
    status = _required_str(meta, "status")
    if status not in get_args(PlanStatus):
        msg = f"status 값이 잘못됐다: {status}"
        raise PlanFormatError(msg)
    if "targets" not in meta:
        msg = "필수 키 'targets'가 없다."
        raise PlanFormatError(msg)
    targets = _str_tuple(meta, "targets")
    test_command = _required_str(meta, "test_command")
    review_round = meta.get("review_round", 0)
    if not isinstance(review_round, int) or isinstance(review_round, bool):
        msg = "'review_round'는 정수여야 한다."
        raise PlanFormatError(msg)
    created_at = meta.get("created_at", "")
    if not isinstance(created_at, str):
        msg = "'created_at'은 따옴표로 감싼 문자열이어야 한다."
        raise PlanFormatError(msg)

    return Plan(
        id=plan_id,
        status=status,  # ty: ignore[invalid-argument-type]  # 위에서 값 검사
        targets=targets,
        test_command=test_command,
        review_round=review_round,
        trace_ids=_str_tuple(meta, "trace_ids"),
        created_at=created_at,
        sections=_split_sections(body),
    )


def _target_problem(target: str) -> str | None:
    if not target.strip():
        return "targets에 빈 경로가 있다."
    if target.startswith(("/", "~")) or re.match(r"^[a-zA-Z]:", target):
        return f"targets는 프로젝트 루트 기준 상대 경로여야 한다: {target}"
    parts = PurePosixPath(target.replace("\\", "/")).parts
    if ".." in parts:
        return f"targets에 '..'를 쓸 수 없다: {target}"
    if parts and parts[0] == ".deepagents":
        return f"targets에 .deepagents/ 아래 경로를 넣을 수 없다: {target}"
    if _GLOB_CHARS & set(target):
        return f"targets에 glob 문자(* ? [)를 쓸 수 없다: {target}"
    return None


def validate_plan(plan: Plan) -> list[str]:
    """형식 문제를 사람이 읽는 문장 목록으로 돌려준다.

    Args:
        plan: 검사할 계획.

    Returns:
        문제 문장 목록. 빈 목록이면 통과다.
    """
    problems: list[str] = []
    for title in REQUIRED_SECTIONS:
        text = plan.sections.get(title, "").strip()
        if not text:
            problems.append(f"필수 절 '{title}'이 없거나 비어 있다.")
        elif text == EMPTY_MARK and title != _EMPTY_ALLOWED_SECTION:
            problems.append(f"필수 절 '{title}'에 '{EMPTY_MARK}'만 있다.")
    if not plan.targets:
        problems.append("targets가 비어 있다. 고칠 파일을 한 개 이상 적는다.")
    problems.extend(p for t in plan.targets if (p := _target_problem(t)))
    if not plan.test_command.strip():
        problems.append("test_command가 비어 있다.")
    return problems


def new_plan_id(now: datetime, requirements: str) -> str:
    """`YYYYMMDD-HHMMSS-<슬러그>` 형식의 id를 만든다.

    Args:
        now: 만든 시각.
        requirements: 요구사항. 첫 줄의 영숫자로 슬러그를 만든다.

    Returns:
        계획 id. 슬러그를 만들 수 없으면 `plan`을 쓴다.
    """
    first_line = requirements.strip().split("\n", 1)[0].lower()
    slug = re.sub(r"[^a-z0-9]+", "-", first_line).strip("-")
    slug = slug[:_SLUG_MAX].strip("-") or "plan"
    return f"{now:%Y%m%d-%H%M%S}-{slug}"


class PlanStore:
    """계획 파일의 읽기와 쓰기. 계획 폴더에 쓰는 코드는 이 클래스뿐이다."""

    def __init__(self, project_root: Path) -> None:
        """계획 저장소를 만든다.

        Args:
            project_root: 프로젝트 루트의 절대 경로.
        """
        self._root = project_root

    @property
    def directory(self) -> Path:
        """`<project_root>/.deepagents/plans`."""
        return self._root / ".deepagents" / "plans"

    def path_for(self, plan_id: str) -> Path:
        """계획 파일 경로를 돌려준다.

        Args:
            plan_id: 계획 id.

        Returns:
            `<directory>/<plan_id>.md`.

        Raises:
            ValueError: id가 비었거나 경로 구분자가 있을 때.
        """
        if not plan_id or "/" in plan_id or "\\" in plan_id or plan_id in {".", ".."}:
            msg = f"계획 id가 잘못됐다: {plan_id!r}"
            raise ValueError(msg)
        return self.directory / f"{plan_id}.md"

    def save(self, plan: Plan) -> Path:
        """계획을 파일에 쓴다. 같은 id가 있으면 덮어쓴다.

        Args:
            plan: 저장할 계획.

        Returns:
            쓴 파일 경로.
        """
        path = self.path_for(plan.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".md")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(plan.to_markdown())
            Path(tmp).replace(path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return path

    def load(self, plan_id: str) -> Plan:
        """계획을 읽는다.

        Args:
            plan_id: 계획 id.

        Returns:
            읽은 Plan.

        Raises:
            FileNotFoundError: 파일이 없을 때.
            PlanFormatError: 형식이 잘못됐을 때.
        """  # noqa: DOC502  # 두 예외 모두 아래 호출에서 그대로 올라온다
        return parse_plan(self.path_for(plan_id).read_text(encoding="utf-8"))

    def list_ids(self) -> list[str]:
        """id를 이름순으로 돌려준다.

        Returns:
            id 목록. 폴더가 없으면 빈 목록.
        """
        if not self.directory.is_dir():
            return []
        return sorted(
            p.stem for p in self.directory.glob("*.md") if not p.name.startswith(".")
        )


def record_answers(plan: Plan, pairs: Sequence[tuple[str, str]]) -> Plan:
    """사람의 답을 "결정 사항"에 덧붙이고 "미결 질문"을 비운다.

    Args:
        plan: 질문이 있던 계획.
        pairs: (질문, 답) 목록.

    Returns:
        갱신된 Plan.
    """
    sections = dict(plan.sections)
    decided = sections.get("결정 사항", "").strip()
    lines = [] if decided in {"", EMPTY_MARK} else [decided]
    lines.extend(f"- 질문: {q} / 답: {a}" for q, a in pairs)
    sections["결정 사항"] = "\n".join(lines)
    sections[_OPEN_QUESTIONS_SECTION] = EMPTY_MARK
    return plan.with_updates(sections=_order_sections(sections))
