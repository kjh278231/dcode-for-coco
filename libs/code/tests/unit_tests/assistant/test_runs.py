"""Langfuse 작업 기록 조회 (SPEC 6.4). v2 관측 API와 v3 점수 API의 가짜로 돌린다."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from deepagents_code.assistant.runs import (
    Failure,
    RunsClient,
    RunSummary,
    TracingUnavailableError,
    format_run_detail,
    format_run_list,
)

T0 = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)


def obs(
    trace_id: str,
    name: str,
    minute: int,
    *,
    level: str = "DEFAULT",
    parent: str | None = "p",
    status: str = "",
    seconds: float = 1.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        trace_id=trace_id,
        name=name,
        start_time=T0 + timedelta(minutes=minute),
        end_time=T0 + timedelta(minutes=minute, seconds=seconds),
        level=level,
        parent_observation_id=parent,
        status_message=status,
        session_id="s1",
    )


class FakeApi:
    """관측은 쪽 크기 2로 나눠 주고, 점수는 trace별 대본으로 준다."""

    def __init__(
        self, rows: list[SimpleNamespace], scores: dict[str, dict[str, Any]]
    ) -> None:
        self.rows = rows
        self.score_map = scores
        self.queries: list[dict[str, Any]] = []
        self.observations = SimpleNamespace(get_many=self.get_many)
        self.scores_v3 = SimpleNamespace(get_many_v3=self.get_scores)

    def get_many(self, **query: Any) -> SimpleNamespace:
        self.queries.append(query)
        rows = self.rows
        if query.get("trace_id"):
            rows = [r for r in rows if r.trace_id == query["trace_id"]]
        if query.get("filter"):  # 태그가 붙은 행: 이름이 LangGraph인 행
            rows = [r for r in rows if r.name == "LangGraph"]
        rows = sorted(rows, key=lambda r: r.start_time, reverse=True)
        start = int(query.get("cursor") or 0)
        limit = min(query["limit"], 2)
        page = rows[start : start + limit]
        more = start + limit < len(rows)
        return SimpleNamespace(
            data=page, meta=SimpleNamespace(cursor=str(start + limit) if more else None)
        )

    def get_scores(self, **query: Any) -> SimpleNamespace:
        values = self.score_map.get(query["trace_id"], {})
        return SimpleNamespace(
            data=[SimpleNamespace(name=k, value=v) for k, v in values.items()]
        )


def client(rows: list[SimpleNamespace], scores: dict[str, Any] | None = None) -> Any:  # noqa: ANN401
    api = FakeApi(rows, scores or {})
    return SimpleNamespace(
        api=api, get_trace_url=lambda *, trace_id: f"https://lf/trace/{trace_id}"
    )


ROWS = [
    obs("t1", "LangGraph", 0, parent=None),
    obs("t1", "cg.gate.deny", 1, level="WARNING", status="no_approved_plan"),
    obs("t1", "cg.test.run", 2, level="ERROR", status="exit 3"),
    obs("t1", "model", 3, seconds=30),
    obs("t2", "LangGraph", 5, parent=None),
    obs("t3", "LangGraph", 9, parent=None),
    obs("other", "Conversational Turn", 10, parent=None),  # 다른 도구의 trace
]


def test_no_keys_raises_with_user_text() -> None:
    with pytest.raises(TracingUnavailableError, match="Langfuse 키가 없어"):
        RunsClient({})


def test_list_runs_groups_tagged_traces_newest_first() -> None:
    fake = client(ROWS, {"t1": {"cg.tool_calls": 4, "cg.llm_calls": 2, "other": 9}})
    runs = RunsClient({}, client=fake).list_runs(limit=2)
    assert [r.trace_id for r in runs] == ["t3", "t2"]
    runs = RunsClient({}, client=fake).list_runs(limit=10)
    assert [r.trace_id for r in runs] == ["t3", "t2", "t1"]
    t1 = runs[2]
    assert t1.scores == {"cg.tool_calls": 4.0, "cg.llm_calls": 2.0}
    assert t1.error_count == 1
    assert t1.latency_s == pytest.approx(210.0)  # 첫 시작부터 마지막 끝까지
    assert t1.timestamp.startswith("2026-11-11T10:00")
    assert t1.url == "https://lf/trace/t1"
    assert t1.session_id == "s1"
    first = fake.api.queries[0]
    filters = json.loads(first["filter"])
    assert filters[0] == {
        "type": "arrayOptions",
        "column": "traceTags",
        "operator": "any of",
        "value": ["dcode-assistant"],
    }
    assert filters[1]["column"] == "startTime"


def test_list_runs_can_filter_by_session() -> None:
    fake = client(ROWS)
    RunsClient({}, client=fake).list_runs(session_id="s9")
    filters = json.loads(fake.api.queries[0]["filter"])
    assert filters[-1] == {
        "type": "string",
        "column": "sessionId",
        "operator": "=",
        "value": "s9",
    }


def test_failures_reads_every_page_in_time_order() -> None:
    failures = RunsClient({}, client=client(ROWS)).failures("t1")
    assert [(f.span_name, f.level, f.status_message) for f in failures] == [
        ("cg.gate.deny", "WARNING", "no_approved_plan"),
        ("cg.test.run", "ERROR", "exit 3"),
    ]


def test_signals_returns_cg_scores_per_trace() -> None:
    fake = client(ROWS, {"t1": {"cg.tool_errors": 1}, "t2": {}})
    assert RunsClient({}, client=fake).signals(["t1", "t2"]) == {
        "t1": {"cg.tool_errors": 1.0},
        "t2": {},
    }


def test_wait_for_polls_until_visible() -> None:
    fake = client([])
    runs = RunsClient({}, client=fake)
    assert not runs.wait_for("t1", attempts=3, delay_s=0)
    assert len(fake.api.queries) == 3
    fake.api.rows.append(obs("t1", "LangGraph", 0))
    assert runs.wait_for("t1", attempts=3, delay_s=0)


def test_formatters() -> None:
    run = RunSummary(
        trace_id="a1b2c3d4e5f60718",
        timestamp="2026-11-11T10:00:00+00:00",
        name="LangGraph",
        session_id="s1",
        latency_s=12.5,
        scores={"cg.tool_calls": 4.0, "cg.llm_calls": 2.0},
        error_count=1,
        url="https://lf/trace/0123",
    )
    listing = format_run_list([run])
    assert "a1b2c3d4" in listing
    assert "e5f60718" not in listing
    assert "오류 1" in listing
    assert "llm_calls=2" in listing
    assert format_run_list([]) == "기록된 작업이 없습니다"
    detail = format_run_detail(
        run, [Failure("cg.test.run", "ERROR", "exit 3", "2026-11-11T10:02:00")]
    )
    assert "cg.test.run: exit 3" in detail
    assert "cg.tool_calls: 4" in detail
    assert "https://lf/trace/0123" in detail
    assert "- 없음" in format_run_detail(run, [])
