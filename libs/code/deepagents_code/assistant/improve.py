"""자기 개선: 신호 집계, 개선안 저장, `/improve` 화면 (SPEC 7장)."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from deepagents_code._paths import project_paths
from deepagents_code.assistant import frontmatter
from deepagents_code.assistant.memory import MemoryRecord
from deepagents_code.assistant.runs import NO_KEYS_TEXT, RunsClient

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime
    from pathlib import Path

    from deepagents_code.assistant.memory import MemoryStore

Kind = Literal["rule", "skill"]
STATUSES = ("proposed", "validated", "failed", "applied", "rejected")
RECENT_RUNS = 20
"""`/improve`가 신호를 읽는 최근 작업 수."""
DESCRIPTION_MAX = 200
NAME_MAX = 64
_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MEMORY_FIELDS = ("name", "kind", "description", "created_at", "source")
RELOAD_NOTICE = "새 스킬은 /reload나 새 대화부터 보입니다."


@dataclass(frozen=True, slots=True)
class Threshold:
    """신호 하나의 임계값."""

    signal: str
    per_run: float
    """한 작업에서 이 값 이상이면 "해당"으로 센다."""
    min_runs: int
    """해당 작업이 이 수 이상이면 관찰로 올린다."""


# 근거 없이 정한 시작값이다 (SPEC 7.2)
THRESHOLDS: tuple[Threshold, ...] = (
    Threshold("cg.repeat_failures", per_run=2, min_runs=2),
    Threshold("cg.tool_errors", per_run=5, min_runs=2),
    Threshold("cg.test_failures", per_run=2, min_runs=2),
    Threshold("cg.review_rounds", per_run=2, min_runs=3),
    Threshold("cg.jev_denies", per_run=2, min_runs=2),
    Threshold("cg.gate_denies", per_run=3, min_runs=2),
)


@dataclass(frozen=True, slots=True)
class Observation:
    """임계값을 넘은 신호 하나."""

    signal: str
    run_count: int
    total_runs: int
    worst_trace_ids: tuple[str, ...]


def find_observations(
    signals: Mapping[str, Mapping[str, float]],
    thresholds: Sequence[Threshold] = THRESHOLDS,
) -> list[Observation]:
    """Trace별 신호에서 임계값을 넘은 관찰을 찾는다. 순수 함수다.

    Args:
        signals: trace id -> 점수 이름 -> 값.
        thresholds: 임계값 목록.

    Returns:
        관찰 목록. 임계값 순서대로.
    """
    found = []
    for t in thresholds:
        hits = sorted(
            (
                (scores[t.signal], trace_id)
                for trace_id, scores in signals.items()
                if scores.get(t.signal, 0) >= t.per_run
            ),
            reverse=True,
        )
        if len(hits) >= t.min_runs:
            found.append(
                Observation(
                    signal=t.signal,
                    run_count=len(hits),
                    total_runs=len(signals),
                    worst_trace_ids=tuple(trace_id for _, trace_id in hits[:3]),
                )
            )
    return found


class ImprovementStateError(RuntimeError):
    """개선안의 상태가 요청한 동작을 허락하지 않는다."""


@dataclass(frozen=True, slots=True)
class Improvement:
    """개선안 하나."""

    id: str
    kind: Kind
    name: str
    description: str
    status: str
    created_at: str
    observations: tuple[str, ...]
    body: str
    """proposal.md 본문 (근거)."""
    path: Path
    validation: Mapping[str, Any] | None

    @property
    def payload(self) -> Path:
        """반영할 파일. 규칙은 `rule-<name>.md`, 스킬은 `<name>/` 폴더."""
        if self.kind == "rule":
            return self.path / "payload" / f"rule-{self.name}.md"
        return self.path / "payload" / self.name


def _observation_line(o: Observation) -> str:
    worst = ", ".join(t[:8] for t in o.worst_trace_ids)
    return f"{o.signal}: {o.run_count}/{o.total_runs}건 (가장 나쁜 작업 {worst})"


def _inside(path: Path, root: Path) -> None:
    # 신뢰할 수 없는 저장소의 심볼릭 링크로 프로젝트 밖에 쓰지 않는다
    if not path.resolve().is_relative_to(root.resolve()):
        msg = f"프로젝트 밖을 가리킨다: {path}"
        raise PermissionError(msg)


class ImprovementStore:
    """개선안 폴더의 읽기와 쓰기."""

    def __init__(self, project_root: Path) -> None:
        """개선안 저장소를 만든다.

        Args:
            project_root: 프로젝트 루트의 절대 경로.
        """
        self.project_root = project_root
        self.directory = project_paths(project_root).improvements_dir

    def _dir(self, improvement_id: str) -> Path:
        if not re.fullmatch(r"\d{8}-\d{6}-[a-z0-9-]+", improvement_id):
            raise FileNotFoundError(improvement_id)
        return self.directory / improvement_id

    def create(
        self,
        *,
        kind: Kind,
        name: str,
        description: str,
        body: str,
        rationale: str,
        observations: Sequence[Observation],
        now: datetime,
    ) -> str:
        """개선안을 저장하고 id를 돌려준다. status는 proposed.

        Args:
            kind: `rule` 또는 `skill`.
            name: 영소문자, 숫자, `-`로 된 이름.
            description: 한 줄 설명.
            body: 규칙 본문 또는 SKILL.md 본문.
            rationale: 근거와 기대 효과.
            observations: 근거가 된 관찰.
            now: 만든 시각.

        Returns:
            개선안 id.

        Raises:
            ValueError: kind, name, description이 잘못됐을 때.
        """
        description = description.strip()
        if kind not in {"rule", "skill"}:
            msg = f"kind는 rule 또는 skill이어야 한다: {kind!r}"
            raise ValueError(msg)
        if not _NAME_RE.match(name) or len(name) > NAME_MAX:
            msg = f"name은 영소문자, 숫자, '-'로 {NAME_MAX}자 이하여야 한다: {name!r}"
            raise ValueError(msg)
        if not description or "\n" in description or len(description) > DESCRIPTION_MAX:
            msg = f"description은 {DESCRIPTION_MAX}자 이하의 한 줄이어야 한다."
            raise ValueError(msg)
        improvement_id = f"{now:%Y%m%d-%H%M%S}-{name}"
        path = self._dir(improvement_id)
        _inside(self.directory, self.project_root)
        (path / "payload").mkdir(parents=True)
        source = f"improvement:{improvement_id}"
        if kind == "rule":
            record = MemoryRecord(
                f"rule-{name}", "rule", description, now.isoformat(), source,
                body.strip() + "\n",
            )  # fmt: skip
            meta = {k: getattr(record, k) for k in _MEMORY_FIELDS}
            text = frontmatter.render(meta, record.body)
            (path / "payload" / f"{record.name}.md").write_text(text, encoding="utf-8")
        else:
            skill = path / "payload" / name
            skill.mkdir()
            meta = {"name": name, "description": description}
            text = frontmatter.render(meta, body.strip() + "\n")
            (skill / "SKILL.md").write_text(text, encoding="utf-8")
        meta = {
            "id": improvement_id,
            "kind": kind,
            "name": name,
            "description": description,
            "status": "proposed",
            "created_at": now.isoformat(),
            "observations": [_observation_line(o) for o in observations],
        }
        text = frontmatter.render(meta, f"## 근거\n{rationale.strip()}\n")
        (path / "proposal.md").write_text(text, encoding="utf-8")
        return improvement_id

    def load(self, improvement_id: str) -> Improvement:
        """개선안 하나를 읽는다.

        Args:
            improvement_id: 개선안 id.

        Returns:
            읽은 개선안.

        Raises:
            FileNotFoundError: 없을 때.
            ValueError: proposal.md의 kind나 name이 잘못됐을 때.
        """
        path = self._dir(improvement_id)
        proposal = path / "proposal.md"
        if not proposal.is_file():
            raise FileNotFoundError(improvement_id)
        meta, body = frontmatter.parse(proposal.read_text(encoding="utf-8"))
        # 파일은 손으로 고칠 수 있다. 반영이 이 이름으로 경로를 만들므로 다시 검사한다
        if meta.get("kind") not in {"rule", "skill"} or not _NAME_RE.match(
            str(meta.get("name", ""))
        ):
            msg = f"proposal.md의 kind나 name이 잘못됐다: {improvement_id}"
            raise ValueError(msg)
        validation_file = path / "validation.json"
        validation = (
            json.loads(validation_file.read_text(encoding="utf-8"))
            if validation_file.is_file()
            else None
        )
        return Improvement(
            id=improvement_id,
            kind=meta["kind"],
            name=meta["name"],
            description=meta.get("description", ""),
            status=meta["status"],
            created_at=meta.get("created_at", ""),
            observations=tuple(meta.get("observations") or ()),
            body=body,
            path=path,
            validation=validation,
        )

    def list_ids(self) -> list[str]:
        """개선안 id를 오래된 것부터 돌려준다.

        Returns:
            id 목록. 폴더가 없으면 빈 목록.
        """
        if not self.directory.is_dir():
            return []
        return sorted(p.parent.name for p in self.directory.glob("*/proposal.md"))

    def _set_status(self, improvement_id: str, status: str) -> None:
        proposal = self._dir(improvement_id) / "proposal.md"
        meta, body = frontmatter.parse(proposal.read_text(encoding="utf-8"))
        meta["status"] = status
        proposal.write_text(frontmatter.render(meta, body), encoding="utf-8")

    def record_validation(self, improvement_id: str, result: Mapping[str, Any]) -> None:
        """validation.json을 쓰고 status를 validated 또는 failed로 바꾼다.

        Args:
            improvement_id: 개선안 id.
            result: 평가 실행기의 판정. `passed`가 참이면 validated.
        """
        self.load(improvement_id)
        path = self._dir(improvement_id) / "validation.json"
        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._set_status(
            improvement_id, "validated" if result.get("passed") else "failed"
        )

    def apply(self, improvement_id: str, memory: MemoryStore, skills_dir: Path) -> None:
        """개선안을 반영한다.

        Args:
            improvement_id: 개선안 id.
            memory: 규칙을 저장할 기억 저장소.
            skills_dir: 스킬을 복사할 폴더.

        Raises:
            ImprovementStateError: status가 validated가 아닐 때.
        """
        improvement = self.load(improvement_id)
        if improvement.status != "validated":
            msg = f"검증을 통과한 개선안만 반영한다. 지금 상태: {improvement.status}"
            raise ImprovementStateError(msg)
        if improvement.kind == "rule":
            meta, body = frontmatter.parse(
                improvement.payload.read_text(encoding="utf-8")
            )
            fields = {k: str(meta[k]) for k in _MEMORY_FIELDS}
            memory.save(MemoryRecord(body=body, **fields))  # type: ignore[arg-type]
        else:
            _inside(skills_dir, self.project_root)
            shutil.copytree(
                improvement.payload, skills_dir / improvement.name, dirs_exist_ok=True
            )
        self._set_status(improvement_id, "applied")

    def reject(self, improvement_id: str) -> None:
        """Status를 rejected로 바꾼다. 폴더는 지우지 않는다.

        Args:
            improvement_id: 개선안 id.

        Raises:
            ImprovementStateError: 이미 반영된 개선안일 때.
        """
        if self.load(improvement_id).status == "applied":
            msg = "이미 반영된 개선안은 거절할 수 없다."
            raise ImprovementStateError(msg)
        self._set_status(improvement_id, "rejected")


# ----- /improve 화면. 처리기는 아래 함수의 결과만 띄운다 -----


def observe(client: RunsClient, *, limit: int = RECENT_RUNS) -> list[Observation]:
    """최근 작업의 점수로 관찰을 만든다.

    Args:
        client: 조회 클라이언트.
        limit: 읽을 최근 작업 수.

    Returns:
        관찰 목록.
    """
    runs = client.list_runs(limit=limit)
    return find_observations({r.trace_id: r.scores for r in runs})


def pending_observation_count(environ: Mapping[str, str]) -> int:
    """TUI 시작 알림용. 키가 없으면 0.

    Args:
        environ: 환경변수 사전.

    Returns:
        관찰 수.
    """
    from deepagents_code.assistant import tracing

    if not tracing.is_enabled(environ):
        return 0
    return len(observe(RunsClient(environ)))


def instruction(observations: Sequence[Observation]) -> str:
    """에이전트에게 보낼 지시문.

    Args:
        observations: 관찰 목록.

    Returns:
        지시문.
    """
    rows = "\n".join(
        f"- {o.signal}: {o.run_count}/{o.total_runs}건, "
        f"가장 나빴던 작업 {', '.join(o.worst_trace_ids)}"
        for o in observations
    )
    return (
        "최근 작업의 신호에서 임계값을 넘은 관찰이다.\n"
        f"{rows}\n\n"
        "원인을 추정하고 프로젝트 규칙이나 스킬 하나로 고칠 수 있는 것만 "
        "propose_improvement로 제안하라. 근거가 약하면 제안하지 마라. "
        "코드는 고치지 마라."
    )


def _observation_table(observations: Sequence[Observation]) -> str:
    return "\n".join(_observation_line(o) for o in observations)


def _validation_text(improvement: Improvement) -> str:
    if improvement.validation is None:
        return (
            "검증 전입니다. 실행할 명령:\n"
            "python -m deepagents_code.assistant.evalsuite run "
            f"--improvement {improvement.id}"
        )
    return "검증 결과:\n" + json.dumps(
        improvement.validation, ensure_ascii=False, indent=2
    )


def _show(improvement: Improvement) -> str:
    payload = improvement.payload
    if improvement.kind == "skill":
        payload /= "SKILL.md"
    imp = improvement
    lines = [
        f"{imp.id} [{imp.status}] {imp.kind} {imp.name}",
        improvement.description,
        "관찰: " + ("; ".join(improvement.observations) or "없음"),
        improvement.body.strip(),
        f"--- {payload.relative_to(improvement.path)}",
        payload.read_text(encoding="utf-8").strip(),
        "---",
        _validation_text(improvement),
    ]
    return "\n".join(lines)


def _list(store: ImprovementStore) -> str:
    rows = []
    for improvement_id in store.list_ids():
        try:
            imp = store.load(improvement_id)
        except (ValueError, KeyError, OSError) as exc:
            rows.append(f"{improvement_id}  읽을 수 없음: {exc}")
            continue
        rows.append(f"{imp.id}  {imp.status}  {imp.kind}  {imp.description}")
    return "\n".join(rows) or "개선안이 없습니다"


def _observe_text(
    environ: Mapping[str, str], client: RunsClient | None
) -> tuple[str, str | None]:
    from deepagents_code.assistant.runs import TracingUnavailableError

    try:
        observations = observe(client or RunsClient(environ))
    except TracingUnavailableError:
        return NO_KEYS_TEXT, None
    except Exception as exc:  # noqa: BLE001  # 네트워크 오류도 화면에 한 줄로
        return f"Langfuse 조회에 실패했습니다: {type(exc).__name__}", None
    if not observations:
        return f"최근 작업 {RECENT_RUNS}건에서 임계값을 넘은 관찰이 없습니다", None
    calls = 1 + 2 * len(observations)  # 관찰마다 제안 하나와 그 결과, 마지막 답
    text = (
        f"관찰 {len(observations)}건\n{_observation_table(observations)}\n\n"
        f"에이전트에게 개선안을 요청합니다. 예상 규모: 모델 호출 약 {calls}회"
    )
    return text, instruction(observations)


def improve_command(
    args: str,
    project_root: Path,
    environ: Mapping[str, str],
    *,
    client: RunsClient | None = None,
) -> tuple[str, str | None]:
    """`/improve [list|show|apply|reject] [id]`를 처리한다.

    Args:
        args: 명령 뒤의 인자.
        project_root: 프로젝트 루트.
        environ: 환경변수 사전.
        client: 조회 클라이언트. 없으면 환경의 키로 만든다.

    Returns:
        (화면에 띄울 글, 에이전트에게 보낼 지시문 또는 None).
    """
    from deepagents_code.assistant.memory import MemoryStore

    sub, _, improvement_id = args.strip().partition(" ")
    improvement_id = improvement_id.strip()
    store = ImprovementStore(project_root)
    shown = ""
    if not sub:
        return _observe_text(environ, client)
    if sub == "list":
        return _list(store), None
    if sub not in {"show", "apply", "reject"} or not improvement_id:
        return "사용법: /improve [list | show <id> | apply <id> | reject <id>]", None
    try:
        improvement = store.load(improvement_id)
        if sub == "show":
            return _show(improvement), None
        if sub == "reject":
            store.reject(improvement_id)
            return f"{improvement_id}을 거절했습니다", None
        shown = _validation_text(improvement)
        store.apply(
            improvement_id,
            MemoryStore(project_root),
            project_paths(project_root).skills_dir,
        )
    except FileNotFoundError:
        return f"개선안이 없습니다: {improvement_id}", None
    except (ImprovementStateError, OSError, ValueError, KeyError) as exc:
        return f"{shown}\n{exc}".strip(), None
    notice = f"\n{RELOAD_NOTICE}" if improvement.kind == "skill" else ""
    return f"{shown}\n\n{improvement_id}을 반영했습니다.{notice}", None
