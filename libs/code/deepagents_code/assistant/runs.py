"""Langfuse에서 작업 기록을 읽는다. `/runs`, `/improve`, 평가 실행기가 함께 쓴다.

[M6] 이 계정에서는 v1 `trace.list`, `trace.get`, `scores.get_many`가 410이다
(2026-09-16 뒤 만든 조직. Cloud 전체는 2026-11-16에 없어진다). v2
`observations.get_many`, `scores_v3.get_many_v3`, `get_trace_url`만 쓴다.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from deepagents_code.assistant import tracing

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

NO_KEYS_TEXT = "Langfuse 키가 없어 기록이 없습니다"
WINDOW_DAYS = 30
"""조회 창. v2 API는 시작 시각 범위로 읽는다."""
PAGE_LIMIT = 100
MAX_PAGES = 20
"""한 조회에서 읽는 쪽 수의 상한. 공유 프로젝트에서 끝없이 읽지 않는다."""


class TracingUnavailableError(RuntimeError):
    """Langfuse 키가 없다."""


@dataclass(frozen=True, slots=True)
class RunSummary:
    """작업 한 건(trace 하나)의 요약."""

    trace_id: str
    timestamp: str
    name: str
    session_id: str | None
    latency_s: float | None
    scores: Mapping[str, float]
    error_count: int
    url: str | None


@dataclass(frozen=True, slots=True)
class Failure:
    """실패나 경고로 남은 구간 하나."""

    span_name: str
    level: str
    status_message: str
    start_time: str


def _since() -> datetime:
    return datetime.now(UTC) - timedelta(days=WINDOW_DAYS)


def _iso(value: object) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value or "")


class RunsClient:
    """Langfuse에서 작업 기록을 읽는다."""

    def __init__(
        self,
        environ: Mapping[str, str],
        *,
        client: Any = None,  # noqa: ANN401  # 테스트가 가짜를 넣는다
    ) -> None:
        """조회 클라이언트를 만든다.

        Args:
            environ: 환경변수 사전.
            client: Langfuse 클라이언트. 없으면 환경의 키로 만든다.

        Raises:
            TracingUnavailableError: 키가 없을 때.
        """
        if client is None:
            if not tracing.is_enabled(environ):
                raise TracingUnavailableError(NO_KEYS_TEXT)
            client = tracing.api_client(environ)
        self._client = client

    def _observations(self, **query: Any) -> Iterator[Any]:
        cursor = None
        for _ in range(MAX_PAGES):
            page = self._client.api.observations.get_many(
                limit=PAGE_LIMIT, cursor=cursor, **query
            )
            yield from page.data
            cursor = getattr(page.meta, "cursor", None)
            if not cursor or not page.data:
                return

    def _scores(self, trace_id: str) -> dict[str, float]:
        page = self._client.api.scores_v3.get_many_v3(trace_id=trace_id, limit=100)
        return {
            s.name: float(s.value)
            for s in page.data
            if s.name.startswith("cg.") and isinstance(s.value, (int, float))
        }

    def list_runs(
        self, *, limit: int = 10, session_id: str | None = None
    ) -> list[RunSummary]:
        """최근 작업을 새것부터 돌려준다. `dcode-assistant` 태그가 붙은 trace만 본다.

        Args:
            limit: 최대 건수.
            session_id: 이 세션(대화)의 것만.

        Returns:
            작업 요약 목록.
        """
        since = _since()
        filters: list[dict[str, Any]] = [
            {
                "type": "arrayOptions",
                "column": "traceTags",
                "operator": "any of",
                "value": [tracing.TAG],
            },
            {
                "type": "datetime",
                "column": "startTime",
                "operator": ">=",
                "value": since.isoformat(),
            },
        ]
        if session_id:
            filters.append(
                {
                    "type": "string",
                    "column": "sessionId",
                    "operator": "=",
                    "value": session_id,
                }
            )
        roots: dict[str, Any] = {}
        for row in self._observations(fields="core,basic", filter=json.dumps(filters)):
            if row.trace_id not in roots or row.parent_observation_id is None:
                roots[row.trace_id] = row  # 태그가 붙은 행 중 최상위를 대표로
            if len(roots) > limit:
                break
        picked = sorted(roots.values(), key=lambda r: r.start_time, reverse=True)
        return [self._summary(row, since) for row in picked[:limit]]

    def _summary(self, row: Any, since: datetime) -> RunSummary:  # noqa: ANN401
        # 한 요청은 여러 조각(make_graph 호출, 재개)으로 오므로 trace 전체에서 잰다
        rows = list(
            self._observations(
                fields="core,basic", trace_id=row.trace_id, from_start_time=since
            )
        ) or [row]
        start = min(o.start_time for o in rows)
        ends = [o.end_time for o in rows if getattr(o, "end_time", None)]
        return RunSummary(
            trace_id=row.trace_id,
            timestamp=_iso(start),
            name=row.name or "",
            session_id=row.session_id or None,
            latency_s=(max(ends) - start).total_seconds() if ends else None,
            scores=self._scores(row.trace_id),
            error_count=sum(1 for o in rows if o.level == "ERROR"),
            url=self._client.get_trace_url(trace_id=row.trace_id),
        )

    def failures(self, trace_id: str) -> list[Failure]:
        """Trace 하나의 ERROR, WARNING 구간과 `cg.gate.deny`를 시간순으로 돌려준다.

        Args:
            trace_id: trace id.

        Returns:
            실패 구간 목록.
        """
        rows = [
            o
            for o in self._observations(
                fields="core,basic", trace_id=trace_id, from_start_time=_since()
            )
            if o.level in {"ERROR", "WARNING"} or o.name == "cg.gate.deny"
        ]
        rows.sort(key=lambda o: o.start_time)
        return [
            Failure(
                span_name=o.name or "",
                level=o.level or "",
                status_message=o.status_message or "",
                start_time=_iso(o.start_time),
            )
            for o in rows
        ]

    def signals(self, trace_ids: Sequence[str]) -> dict[str, dict[str, float]]:
        """Trace별 `cg.*` 점수를 돌려준다.

        Args:
            trace_ids: trace id 목록.

        Returns:
            trace id -> 점수 이름 -> 값.
        """
        return {trace_id: self._scores(trace_id) for trace_id in trace_ids}

    def wait_for(
        self, trace_id: str, *, attempts: int = 6, delay_s: float = 5.0
    ) -> bool:
        """Trace가 조회될 때까지 기다린다. 쓰기는 비동기라 늦게 보인다.

        Args:
            trace_id: trace id.
            attempts: 조회 횟수.
            delay_s: 조회 사이 대기 초.

        Returns:
            보이면 True, 끝내 안 보이면 False.
        """
        for attempt in range(attempts):
            page = self._client.api.observations.get_many(
                limit=1, fields="core", trace_id=trace_id, from_start_time=_since()
            )
            if page.data:
                return True
            if attempt + 1 < attempts:
                time.sleep(delay_s)
        return False


def _score_text(scores: Mapping[str, float]) -> str:
    keys = ("cg.llm_calls", "cg.tool_calls", "cg.tool_errors", "cg.gate_denies")
    parts = [f"{k[3:]}={scores[k]:g}" for k in keys if k in scores]
    return " ".join(parts) or "지표 없음"


def format_run_list(runs: Sequence[RunSummary]) -> str:
    """`/runs` 목록 화면의 문자열.

    Args:
        runs: 작업 요약 목록.

    Returns:
        한 줄에 한 건. 시각, 상태, 지표 요약, trace id 앞 8자.
    """
    if not runs:
        return "기록된 작업이 없습니다"
    lines = []
    for run in runs:
        status = f"오류 {run.error_count}" if run.error_count else "정상"
        lines.append(
            f"{run.timestamp[:19]}  {status}  {_score_text(run.scores)}  "
            f"{run.trace_id[:8]}"
        )
    return "\n".join(lines)


def format_run_detail(run: RunSummary, failures: Sequence[Failure]) -> str:
    """`/runs <id>` 화면의 문자열. 실패 구간과 원인, 지표, Langfuse 주소.

    Args:
        run: 작업 요약.
        failures: 그 작업의 실패 구간.

    Returns:
        여러 줄 문자열.
    """
    lines = [f"작업 {run.trace_id}", f"시각: {run.timestamp}"]
    if run.latency_s is not None:
        lines.append(f"소요: {run.latency_s:.1f}초")
    lines.append("실패 구간:")
    lines.extend(
        f"- {f.start_time[:19]} {f.level} {f.span_name}: {f.status_message or '-'}"
        for f in failures
    )
    if not failures:
        lines.append("- 없음")
    lines.append("지표:")
    lines.extend(f"- {k}: {v:g}" for k, v in sorted(run.scores.items()))
    if not run.scores:
        lines.append("- 없음")
    lines.append(f"주소: {run.url or '알 수 없음'}")
    return "\n".join(lines)


# ----- 슬래시 명령. 처리기는 아래 함수의 결과만 띄운다 -----

FIND_LIMIT = 50
"""`/runs <id 앞부분>`이 찾아보는 최근 작업 수."""


def runs_command(
    args: str, environ: Mapping[str, str], *, client: RunsClient | None = None
) -> str:
    """`/runs`와 `/runs <id 앞부분>`의 화면 문자열.

    Args:
        args: 명령 뒤의 인자.
        environ: 환경변수 사전.
        client: 조회 클라이언트. 없으면 환경의 키로 만든다.

    Returns:
        화면에 띄울 글.
    """
    prefix = args.strip()
    try:
        client = client or RunsClient(environ)
        if not prefix:
            return format_run_list(client.list_runs())
        recent = client.list_runs(limit=FIND_LIMIT)
        matches = [r for r in recent if r.trace_id.startswith(prefix)]
        if len(matches) != 1:
            head = (
                f"{prefix}로 시작하는 작업이 여러 건입니다. 더 길게 적어 주세요."
                if matches
                else f"최근 {FIND_LIMIT}건에 {prefix}로 시작하는 작업이 없습니다"
            )
            return f"{head}\n{format_run_list(matches)}" if matches else head
        return format_run_detail(matches[0], client.failures(matches[0].trace_id))
    except TracingUnavailableError:
        return NO_KEYS_TEXT
    except Exception as exc:  # noqa: BLE001  # 네트워크 오류도 화면에 한 줄로
        return f"Langfuse 조회에 실패했습니다: {type(exc).__name__}"


def latest_trace(
    environ: Mapping[str, str],
    session_id: str,
    *,
    client: RunsClient | None = None,
) -> tuple[str | None, str]:
    """`/trace`. 이 대화(세션)의 가장 최근 trace 주소.

    Args:
        environ: 환경변수 사전.
        session_id: 대화의 thread id. Langfuse 세션 id와 같다.
        client: 조회 클라이언트. 없으면 환경의 키로 만든다.

    Returns:
        (주소 또는 None, 화면에 띄울 글).
    """
    try:
        runs = (client or RunsClient(environ)).list_runs(limit=1, session_id=session_id)
    except TracingUnavailableError:
        return None, NO_KEYS_TEXT
    except Exception as exc:  # noqa: BLE001
        return None, f"Langfuse 조회에 실패했습니다: {type(exc).__name__}"
    if not runs or not runs[0].url:
        return None, (
            "이 대화의 기록이 아직 Langfuse에 없습니다. "
            "반영까지 수십 초 걸릴 수 있으니 잠시 뒤 다시 시도하세요."
        )
    return runs[0].url, f"Langfuse trace를 엽니다:\n{runs[0].url}"
