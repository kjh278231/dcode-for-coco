"""프로젝트 Memory: 기억 파일 저장소와 모델 호출마다의 주입."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, NotRequired, get_args

from deepagents.middleware._utils import (  # noqa: PLC2701  # gate와 같은 도우미
    append_to_system_message,
)
from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    PrivateStateAttr,
    TracePolicy,
    omit_payload,
)
from langchain_core.messages import HumanMessage

from deepagents_code._paths import project_paths
from deepagents_code.assistant import frontmatter
from deepagents_code.assistant.decider import questions_j6
from deepagents_code.assistant.options import PHASE_KEY, PLAN_ID_KEY
from deepagents_code.assistant.plan import PlanFormatError, PlanStore

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping
    from datetime import datetime

    from langchain.agents.middleware.types import ModelRequest, ModelResponse
    from langgraph.runtime import Runtime

    from deepagents_code.assistant.decider import Decider
    from deepagents_code.assistant.plan import Plan

logger = logging.getLogger(__name__)

MemoryKind = Literal["rule", "work"]

INDEX_NAME = "MEMORY.md"
INDEX_HEADER = "<!-- 이 파일은 자동 생성된다. 직접 고치지 않는다. -->"
DESCRIPTION_MAX = 200
WORK_DESCRIPTION_MAX = 150
INJECT_MAX_CHARS = 20000
INDEX_MAX_CHARS = INJECT_MAX_CHARS // 4
SELECTED_KEY = "_cg_selected_memories"
HUMAN_ID_KEY = "_cg_memory_human_id"

_NAME_RE = re.compile(r"^(rule|work)-[a-z0-9]+(?:-[a-z0-9]+)*$")
_SLUG_MAX = 40
_FIELDS = ("name", "kind", "description", "created_at", "source")


class MemoryFormatError(ValueError):
    """기억 파일 형식 오류."""


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """기억 한 건."""

    name: str
    kind: MemoryKind
    description: str
    created_at: str
    source: str
    body: str


def _check(record: MemoryRecord) -> None:
    if record.kind not in get_args(MemoryKind):
        msg = f"kind는 rule 또는 work여야 한다: {record.kind!r}"
        raise MemoryFormatError(msg)
    if not _NAME_RE.match(record.name) or not record.name.startswith(f"{record.kind}-"):
        msg = (
            f"이름은 소문자 영숫자와 하이픈만 쓰고 '{record.kind}-'로 시작해야 한다: "
            f"{record.name!r}"
        )
        raise MemoryFormatError(msg)
    # "\r" 같은 줄 구분자도 막는다. 읽을 때 줄로 갈려 색인에 줄을 지어낸다
    if len(record.description.splitlines()) != 1 or not record.description.strip():
        msg = "description은 비어 있지 않은 한 줄이어야 한다."
        raise MemoryFormatError(msg)
    if len(record.description) > DESCRIPTION_MAX:
        msg = f"description은 {DESCRIPTION_MAX}자 이하여야 한다."
        raise MemoryFormatError(msg)


def _parse(text: str, stem: str) -> MemoryRecord:
    try:
        meta, body = frontmatter.parse(text)
    except frontmatter.FrontmatterError as exc:
        raise MemoryFormatError(str(exc)) from exc
    values = {key: meta.get(key) for key in _FIELDS}
    if not all(isinstance(v, str) for v in values.values()):
        msg = f"frontmatter에 문자열 {', '.join(_FIELDS)}가 모두 있어야 한다."
        raise MemoryFormatError(msg)
    record = MemoryRecord(body=body, **values)  # type: ignore[arg-type]
    _check(record)
    if record.name != stem:
        msg = f"파일 이름과 name이 다르다: {stem!r} != {record.name!r}"
        raise MemoryFormatError(msg)
    return record


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def rule_name(description: str) -> str:
    """규칙 설명에서 기억 이름을 만든다.

    같은 설명은 같은 이름이 된다(다시 저장하면 덮어쓴다). 한글만 있는 설명도
    서로 겹치지 않게 설명의 해시 6자리를 붙인다.

    Args:
        description: 규칙의 한 줄 설명.

    Returns:
        `rule-<영숫자 슬러그>-<해시>` 또는 `rule-<해시>`.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", description.lower()).strip("-")
    slug = slug[:_SLUG_MAX].strip("-")
    digest = hashlib.sha256(description.strip().encode()).hexdigest()[:6]
    return f"rule-{slug}-{digest}" if slug else f"rule-{digest}"


class MemoryStore:
    """기억 파일과 색인의 읽기와 쓰기. 기억 폴더에 쓰는 코드는 이 클래스뿐이다."""

    def __init__(self, project_root: Path) -> None:
        """기억 저장소를 만든다.

        Args:
            project_root: 프로젝트 루트의 절대 경로.
        """
        self.project_root = project_root
        self._directory = project_paths(project_root).memory_dir

    @property
    def directory(self) -> Path:
        """`<project_root>/.deepagents/memory`."""
        return self._directory

    def _writable(self) -> None:
        # 신뢰할 수 없는 저장소의 심볼릭 링크로 프로젝트 밖에 쓰지 않는다
        if not self.directory.resolve().is_relative_to(self.project_root.resolve()):
            msg = f"기억 폴더가 프로젝트 밖을 가리킨다: {self.directory}"
            raise PermissionError(msg)

    def exists(self, name: str) -> bool:
        """같은 이름의 기억 파일이 있는가.

        Args:
            name: 기억 이름.

        Returns:
            파일이 있으면 True.
        """
        return self._path(name).is_file()

    def _path(self, name: str) -> Path:
        if not _NAME_RE.match(name):
            msg = f"기억 이름이 잘못됐다: {name!r}"
            raise ValueError(msg)
        return self.directory / f"{name}.md"

    def _files(self) -> list[Path]:
        if not self.directory.is_dir():
            return []
        return sorted(
            p
            for p in self.directory.glob("*.md")
            if p.name != INDEX_NAME and not p.name.startswith(".")
        )

    def list_records(self, kind: MemoryKind | None = None) -> list[MemoryRecord]:
        """기억을 이름순으로 돌려준다.

        Args:
            kind: 주면 그 종류만.

        Returns:
            기억 목록. 형식이 깨진 파일은 건너뛰고 경고를 남긴다. 폴더가 없으면 빈 목록.
        """
        records = []
        for path in self._files():
            try:
                record = _parse(path.read_text(encoding="utf-8"), path.stem)
            except (OSError, MemoryFormatError) as exc:
                logger.warning("기억 파일을 건너뛴다 %s: %s", path.name, exc)
                continue
            if kind is None or record.kind == kind:
                records.append(record)
        return records

    def load(self, name: str) -> MemoryRecord:
        """기억 하나를 읽는다.

        Args:
            name: 기억 이름.

        Returns:
            읽은 기억.

        Raises:
            FileNotFoundError: 파일이 없을 때.
            MemoryFormatError: 형식이 잘못됐을 때.
        """  # noqa: DOC502  # 두 예외 모두 아래 호출에서 그대로 올라온다
        try:
            path = self._path(name)
        except ValueError as exc:
            raise FileNotFoundError(name) from exc
        return _parse(path.read_text(encoding="utf-8"), name)

    def save(self, record: MemoryRecord) -> Path:
        """기억을 쓰고 색인을 다시 만든다. 같은 이름이 있으면 덮어쓴다.

        Args:
            record: 저장할 기억.

        Returns:
            쓴 파일 경로.
        """
        _check(record)
        self._writable()
        path = self._path(record.name)
        meta = {key: getattr(record, key) for key in _FIELDS}
        _atomic_write(path, frontmatter.render(meta, record.body))
        self.rebuild_index()
        return path

    def delete(self, name: str) -> None:
        """기억을 지우고 색인을 다시 만든다. 없으면 아무 일도 하지 않는다.

        Args:
            name: 기억 이름.
        """
        path = self._path(name)
        self._writable()
        if path.exists():
            path.unlink()
            self.rebuild_index()

    def rebuild_index(self) -> Path:
        """모든 기억의 frontmatter를 읽어 MEMORY.md를 다시 쓴다.

        Returns:
            색인 파일 경로.
        """
        self._writable()
        records = self.list_records()
        lines = [INDEX_HEADER]
        for title, kind in (("프로젝트 규칙", "rule"), ("작업 기록", "work")):
            lines.append(f"## {title}")
            lines.extend(
                f"- {r.name}: {r.description}" for r in records if r.kind == kind
            )
        path = self.directory / INDEX_NAME
        _atomic_write(path, "\n".join(lines) + "\n")
        return path

    def read_index(self) -> str:
        """MEMORY.md 내용에서 첫 줄 주석을 뺀 문자열.

        Returns:
            색인 본문. 파일이 없으면 빈 문자열.
        """
        path = self.directory / INDEX_NAME
        if not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8")
        first, _, rest = text.partition("\n")
        return rest if first.startswith("<!--") else text

    def save_rule(
        self, description: str, body: str, *, source: str, now: datetime
    ) -> MemoryRecord:
        """프로젝트 규칙을 저장한다.

        Args:
            description: 한 줄 설명.
            body: 규칙 본문.
            source: `user`, `agent-approved` 등.
            now: 저장 시각.

        Returns:
            저장한 기억.
        """
        description = description.strip()
        record = MemoryRecord(
            name=rule_name(description),
            kind="rule",
            description=description,
            created_at=now.isoformat(),
            source=source,
            body=body.strip() + "\n",
        )
        self.save(record)
        return record

    def save_work_record(
        self, plan: Plan, summary: str, *, now: datetime
    ) -> MemoryRecord:
        """끝난 계획에서 작업 기록을 만든다. 모델을 부르지 않는다.

        Args:
            plan: 끝난 계획.
            summary: complete_plan에 모델이 넘긴 요약.
            now: 저장 시각.

        Returns:
            저장한 기억.
        """
        sections = plan.sections
        requirements = sections.get("요구사항", "").strip()
        first = (requirements.splitlines() or [""])[0].strip() or plan.id
        body = (
            f"## 요청\n{requirements}\n"
            f"## 사용자 결정\n{sections.get('결정 사항', '').strip()}\n"
            f"## 최종 설계\n{sections.get('작업 범위', '').strip()}\n"
            f"{sections.get('작업 순서', '').strip()}\n"
            f"수정 대상: {', '.join(plan.targets)}\n"
            f"## 결과\n{summary.strip()}\n"
            f"계획: .deepagents/plans/{plan.id}.md\n"
        )
        record = MemoryRecord(
            name=f"work-{plan.id}",
            kind="work",
            description=first[:WORK_DESCRIPTION_MAX],
            created_at=now.isoformat(),
            source=f"plan:{plan.id}",
            body=body,
        )
        self.save(record)
        return record


class MemoryInjectionState(AgentState):
    """Memory 주입이 그래프 상태에 두는 값."""

    _cg_selected_memories: NotRequired[Annotated[list[str], PrivateStateAttr]]
    _cg_memory_human_id: NotRequired[Annotated[str | None, PrivateStateAttr]]


def _last_human(messages: list[Any]) -> HumanMessage | None:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message
    return None


_GUIDE = (
    "색인에 있지만 여기 없는 기억은 read_file로 .deepagents/memory/<이름>.md를 "
    "열 수 있다. 사용한 기억은 계획의 '참고한 Memory' 절에 적는다."
)


_FRAME_TAG_RE = re.compile(r"<(/?)project_memory", re.IGNORECASE)


def _neutral(text: str) -> str:
    # 기억 본문이 주입 틀의 여닫는 태그를 흉내 내지 못하게 한다
    return _FRAME_TAG_RE.sub(r"&lt;\1project_memory", text)


def _tail_index(index: str) -> str:
    # 색인이 길면 오래된(앞쪽) 항목을 빼고 최근 항목을 남긴다
    if len(index) <= INDEX_MAX_CHARS:
        return index
    lines = index.splitlines()
    kept: list[str] = []
    size = 0
    for line in reversed(lines):
        size += len(line) + 1
        if size > INDEX_MAX_CHARS:
            break
        kept.append(line)
    dropped = len(lines) - len(kept)
    return f"(오래된 색인 {dropped}줄 생략)\n" + "\n".join(reversed(kept))


def _fit(records: list[MemoryRecord], budget: int) -> list[str]:
    # 합이 budget을 넘으면 뒤의 것부터 본문을 빼고 이름과 설명만 남긴다
    full = [f"### {r.name}\n{r.body.strip()}" for r in records]
    short = [f"### {r.name}\n(본문 생략: {r.description})" for r in records]
    keep = len(records)
    while keep and sum(map(len, full[:keep])) + sum(map(len, short[keep:])) > budget:
        keep -= 1
    return full[:keep] + short[keep:]


def _inject(request: ModelRequest, block: str | None) -> ModelRequest:
    if block is None:
        return request
    system = append_to_system_message(request.system_message, block)
    return request.override(system_message=system)


class MemoryInjectionMiddleware(AgentMiddleware):
    """색인과 프로젝트 규칙을 항상 주입하고, 작업 기록은 Jev가 고른 것만 주입한다."""

    state_schema = MemoryInjectionState
    trace_policy = TracePolicy(process_inputs=omit_payload)

    def __init__(self, store: MemoryStore, decider: Decider) -> None:
        """주입 미들웨어를 만든다.

        Args:
            store: 기억 저장소.
            decider: J6 판정기.
        """
        super().__init__()
        self._store = store
        self._decider = decider

    def _request(self, state: Mapping[str, Any], text: str) -> str:
        # 계획이 진행 중이면 "계속해" 같은 짧은 메시지 대신 계획의 요구사항으로 고른다
        if state.get(PHASE_KEY, "idle") == "idle" or not state.get(PLAN_ID_KEY):
            return text
        try:
            plan = PlanStore(self._store.project_root).load(state[PLAN_ID_KEY])
        except FileNotFoundError, PlanFormatError, ValueError:
            return text
        return f"{plan.sections.get('요구사항', '').strip()}\n\n{text}"

    def _select(self, state: Mapping[str, Any]) -> dict[str, Any] | None:
        human = _last_human(state.get("messages", []))
        if human is None or human.id == state.get(HUMAN_ID_KEY):
            return None  # 사람 메시지가 없거나 멈춤 뒤 재개된 실행이다
        records = self._store.list_records("work")
        selected: list[str] = []
        if records:
            request = self._request(state, human.text)
            text, questions = questions_j6(request, records)
            verdicts = self._decider.judge(text, questions)
            # J6는 통과 못 하면 주입하지 않을 뿐 흐름을 막지 않는다
            selected = [
                r.name for r, v in zip(records, verdicts, strict=True) if v.passed
            ]
        return {SELECTED_KEY: selected, HUMAN_ID_KEY: human.id}

    def before_agent(
        self, state: MemoryInjectionState, runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        """새 요청이면 J6로 이번 요청과 관련된 작업 기록을 고른다.

        Returns:
            상태 갱신. 재개된 실행이면 None.
        """
        del runtime
        return self._select(state)

    async def abefore_agent(
        self, state: MemoryInjectionState, runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        """새 요청이면 J6로 이번 요청과 관련된 작업 기록을 고른다.

        Returns:
            상태 갱신. 재개된 실행이면 None.
        """
        del runtime
        return await asyncio.to_thread(self._select, state)

    def _block(self, state: Mapping[str, Any]) -> str | None:
        index = self._store.read_index().strip()
        rules = self._store.list_records("rule")
        works = []
        for name in state.get(SELECTED_KEY) or []:
            try:
                works.append(self._store.load(name))
            except (FileNotFoundError, MemoryFormatError) as exc:
                logger.warning("선택된 작업 기록을 읽지 못했다 %s: %s", name, exc)
        if not (rules or works or "\n- " in f"\n{index}"):
            return None  # 기억이 하나도 없다
        index = _tail_index(index)
        parts = _fit([*rules, *works], INJECT_MAX_CHARS - len(index))
        rule_parts, work_parts = parts[: len(rules)], parts[len(rules) :]
        sections = [f"## 색인\n{index}"]
        if rule_parts:
            sections.append("## 프로젝트 규칙 (항상 적용)\n" + "\n".join(rule_parts))
        if work_parts:
            sections.append("## 이번 요청과 관련된 작업 기록\n" + "\n".join(work_parts))
        inner = _neutral("\n\n".join(sections))
        if len(inner) > INJECT_MAX_CHARS:  # 생략 줄이 많아도 전체를 상한 안에 둔다
            inner = inner[:INJECT_MAX_CHARS] + "\n(상한을 넘어 잘림)"
        return f"<project_memory>\n\n{inner}\n\n</project_memory>\n\n{_GUIDE}"

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """색인, 규칙, 고른 작업 기록을 디스크에서 다시 읽어 붙인다.

        Returns:
            모델 응답.
        """
        return handler(_inject(request, self._block(request.state)))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """색인, 규칙, 고른 작업 기록을 디스크에서 다시 읽어 붙인다.

        Returns:
            모델 응답.
        """
        block = await asyncio.to_thread(self._block, request.state)
        return await handler(_inject(request, block))
