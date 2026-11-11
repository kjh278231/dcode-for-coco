"""Langfuse 추적 (SPEC 6.1~6.3). 가짜 클라이언트로 돌린다. 네트워크를 쓰지 않는다."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from deepagents.backends import CompositeBackend, LocalShellBackend
from langchain.agents import create_agent
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from deepagents_code.assistant import tracing
from deepagents_code.assistant.decider import FakeDecider, JevDecider, Noul, Verdict
from deepagents_code.assistant.gate import PlanGateMiddleware
from deepagents_code.assistant.memory import MemoryInjectionMiddleware, MemoryStore
from deepagents_code.assistant.options import COUNTERS_KEY, LAST_ERROR_KEY
from deepagents_code.assistant.plan import Plan
from deepagents_code.assistant.reviewer import PlanReviewer
from deepagents_code.config import build_stream_config
from tests.unit_tests.assistant.fakes import make_options, scripted_model, tool_call
from tests.unit_tests.assistant.test_gate import (
    Harness,
    approval,
    done,
    explore,
    submit,
    write,
)

if TYPE_CHECKING:
    from pathlib import Path

FAKE_SECRET = "AKIAIOSFODNN7EXAMPLE"
TRACE_ID = "0123456789abcdef0123456789abcdef"


class FakeObservation:
    def __init__(self, log: FakeLangfuse, kwargs: dict[str, Any]) -> None:
        self.kwargs = kwargs
        self.updates: dict[str, Any] = {}
        self.ended = False
        log.observations.append(self)

    def update(self, **kwargs: Any) -> None:
        self.updates.update(kwargs)

    def end(self) -> None:
        self.ended = True


class FakeLangfuse:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.observations: list[FakeObservation] = []
        self.scores: list[dict[str, Any]] = []
        self.flushed = 0

    def start_observation(self, **kwargs: Any) -> FakeObservation:
        if self.fail:
            raise RuntimeError
        return FakeObservation(self, kwargs)

    def create_score(self, **kwargs: Any) -> None:
        if self.fail:
            raise RuntimeError
        self.scores.append(kwargs)

    def flush(self) -> None:
        self.flushed += 1

    def named(self, name: str) -> list[FakeObservation]:
        return [o for o in self.observations if o.kwargs["name"] == name]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeLangfuse:
    """가짜 클라이언트와, run_config가 붙은 실행 안인 것처럼 고정 trace id."""
    client = FakeLangfuse()
    monkeypatch.setattr(tracing, "_client", lambda: client)
    monkeypatch.setattr(tracing, "current_trace_id", lambda: TRACE_ID)
    return client


REAL_CURRENT_TRACE_ID = tracing.current_trace_id
KEYS = {"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"}


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tracing, "_state", {"enabled": False, "anonymizer": None, "settings": None}
    )


def test_is_enabled_needs_both_keys_and_no_off_switch() -> None:
    keys = {"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"}
    assert tracing.is_enabled(keys)
    assert not tracing.is_enabled({"LANGFUSE_PUBLIC_KEY": "pk"})
    assert not tracing.is_enabled({**keys, "LANGFUSE_SECRET_KEY": " "})
    off = {**keys, "DEEPAGENTS_CODE_LANGFUSE_TRACING": "false"}
    assert not tracing.is_enabled(off)


def test_init_without_keys_or_with_broken_client_stays_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert not tracing.init({})
    import langfuse

    def broken(**_: Any) -> None:
        raise ValueError

    monkeypatch.setattr(langfuse, "Langfuse", broken)
    assert not tracing.init({"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"})
    assert tracing.run_config(None, KEYS) is None


def test_init_passes_workspace_keys_and_otel_mask(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import langfuse

    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(langfuse, "Langfuse", lambda **kw: seen.append(kw))
    env = {
        "LANGFUSE_PUBLIC_KEY": "pk",
        "LANGFUSE_SECRET_KEY": "sk",
        "LANGFUSE_BASE_URL": "https://lf.example",
    }
    assert tracing.init(env)
    assert seen[0]["base_url"] == "https://lf.example"
    assert seen[0]["mask_otel_spans"] is tracing._mask_otel_spans
    assert tracing.init(env)  # 두 번째는 만들지 않는다
    assert len(seen) == 1


def test_otel_mask_hides_secrets_in_string_attributes() -> None:
    from langfuse.types import OtelSpanPatch

    spans = {
        "a": SimpleNamespace(
            attributes={
                "langfuse.observation.input": f'{{"messages": "key {FAKE_SECRET}"}}',
                "plain": "hello",
                "count": 3,
                "list": ("ok", FAKE_SECRET),
            }
        ),
        "b": SimpleNamespace(attributes={"plain": "nothing"}),
    }
    result = tracing._mask_otel_spans(params=SimpleNamespace(spans=spans))
    assert set(result.span_patches) == {"a"}
    patch = result.span_patches["a"]
    assert isinstance(patch, OtelSpanPatch)
    assert set(patch.set_attributes) == {"langfuse.observation.input", "list"}
    assert FAKE_SECRET not in str(dict(patch.set_attributes))
    assert "SECRET_DETECTED" in patch.set_attributes["langfuse.observation.input"]


def test_disabled_tracing_is_a_no_op() -> None:
    with tracing.span("cg.x") as handle:
        handle.update(output={"a": 1}, level="ERROR")
    tracing.record("cg.y", output=1)
    tracing.end_request(
        counters={}, llm_calls=0, review_rounds=0, phase="idle", plan_id=None
    )
    assert tracing.run_config(None, {}) is None


def test_client_failures_do_not_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    broken = FakeLangfuse(fail=True)
    monkeypatch.setattr(tracing, "_client", lambda: broken)
    monkeypatch.setattr(tracing, "current_trace_id", lambda: TRACE_ID)
    with tracing.span("cg.x") as handle:
        handle.update(output=1)
    tracing.end_request(
        counters={}, llm_calls=1, review_rounds=0, phase="idle", plan_id=None
    )


def test_run_config_gives_one_trace_id_per_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import langfuse.langchain

    class Handler:  # noqa: B903  # CallbackHandler 자리
        def __init__(self, *, trace_context: dict[str, str]) -> None:
            self.trace_context = trace_context

    monkeypatch.setattr(langfuse.langchain, "CallbackHandler", Handler)
    tracing._state.update(enabled=True, settings=("pk", None))  # init이 끝난 상태
    config = {"metadata": {"thread_id": "th", "turn_id": "turn-1"}}
    first = tracing.run_config(config, KEYS)
    again = tracing.run_config(config, KEYS)  # 같은 요청의 다른 make_graph 호출
    other = tracing.run_config(
        {"metadata": {"thread_id": "th", "turn_id": "turn-2"}}, KEYS
    )
    assert first is not None
    assert again is not None
    assert other is not None
    trace_id = first["metadata"][tracing.TRACE_ID_KEY]
    assert len(trace_id) == 32
    assert first["callbacks"][0].trace_context == {"trace_id": trace_id}
    assert again["metadata"][tracing.TRACE_ID_KEY] == trace_id
    assert other["metadata"][tracing.TRACE_ID_KEY] != trace_id

    # turn id가 없으면 run id로 묶는다 (TUI graph_input 실행)
    by_run = {"configurable": {"thread_id": "th", "run_id": "r1"}}
    run_a = tracing.run_config(by_run, KEYS)
    run_b = tracing.run_config(by_run, KEYS)
    assert run_a is not None
    assert run_b is not None
    assert run_a["metadata"] == run_b["metadata"]

    # 워크스페이스 설정을 따른다: 꺼짐 스위치, 처음과 다른 키
    off = {**KEYS, "DEEPAGENTS_CODE_LANGFUSE_TRACING": "0"}
    assert tracing.run_config(config, off) is None
    other_key = {**KEYS, "LANGFUSE_PUBLIC_KEY": "pk-other"}
    assert tracing.run_config(config, other_key) is None


@tool
def echo(text: str) -> str:
    """받은 글을 돌려준다.

    Returns:
        같은 글.
    """
    return text


class SpanEverywhere(AgentMiddleware):
    """훅마다 구간을 남긴다. 비동기 훅과 to_thread 안에서 trace id가 보이는지 본다."""

    async def abefore_agent(self, state: Any, runtime: Any) -> None:  # noqa: ANN401, ARG002
        tracing.record("cg.before")

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:  # noqa: ANN401
        import asyncio

        await asyncio.to_thread(tracing.record, "cg.tool")
        return await handler(request)

    async def aafter_agent(self, state: Any, runtime: Any) -> None:  # noqa: ANN401, ARG002
        tracing.record("cg.after")


async def test_spans_in_hooks_join_the_run_trace(
    fake: FakeLangfuse, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tracing, "current_trace_id", REAL_CURRENT_TRACE_ID)
    agent = create_agent(
        model=scripted_model([tool_call("echo", {"text": "x"}, "e"), done()]),
        tools=[echo],
        middleware=[SpanEverywhere()],
    )
    await agent.ainvoke(
        {"messages": [HumanMessage("hi")]},
        {"metadata": {tracing.TRACE_ID_KEY: TRACE_ID}},
    )
    names = [o.kwargs["name"] for o in fake.observations]
    assert names == ["cg.before", "cg.tool", "cg.after"]
    for observation in fake.observations:
        assert observation.kwargs["trace_context"] == {"trace_id": TRACE_ID}
        assert observation.ended


def test_span_outside_a_traced_run_is_not_sent(
    fake: FakeLangfuse, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracing.record("cg.in_run", output=1, level="WARNING")
    (observation,) = fake.observations
    assert observation.kwargs["trace_context"] == {"trace_id": TRACE_ID}
    assert observation.updates == {"output": 1, "level": "WARNING"}
    # run_config가 붙지 않은 실행(꺼진 워크스페이스)이나 그래프 밖은 보내지 않는다
    monkeypatch.setattr(tracing, "current_trace_id", REAL_CURRENT_TRACE_ID)
    tracing.record("cg.lonely")
    assert len(fake.observations) == 1


def test_record_judgment_keeps_state_text_out(fake: FakeLangfuse) -> None:
    verdict = Verdict("J6:work-a", 0.8, passed=True, reason="ok")
    tracing.record_judgment("J6:work-a", 1234, verdict)
    (observation,) = fake.observations
    assert observation.kwargs["name"] == "cg.judge.J6"
    assert observation.kwargs["as_type"] == "guardrail"
    assert observation.kwargs["input"] == {"question": "J6:work-a", "state_chars": 1234}
    assert observation.updates["output"] == {
        "probability": 0.8,
        "passed": True,
        "reason": "ok",
    }


def test_end_request_scores_every_counter(
    fake: FakeLangfuse, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tracing, "current_trace_id", lambda: None)
    tracing.end_request(
        counters={"tool_calls": 1},
        llm_calls=2,
        review_rounds=1,
        phase="x",
        plan_id=None,
    )
    assert fake.scores == []  # trace id가 없으면 붙일 곳이 없다
    monkeypatch.setattr(tracing, "current_trace_id", lambda: TRACE_ID)
    tracing.end_request(
        counters={"tool_calls": 3, "gate_denies": 1, "llm_base": 9},
        llm_calls=2,
        review_rounds=1,
        phase="executing",
        plan_id="p1",
    )
    values = {s["name"]: s["value"] for s in fake.scores}
    assert values == {
        "cg.tool_calls": 3.0,
        "cg.tool_errors": 0.0,
        "cg.repeat_failures": 0.0,
        "cg.gate_denies": 1.0,
        "cg.jev_denies": 0.0,
        "cg.test_failures": 0.0,
        "cg.llm_calls": 2.0,
        "cg.review_rounds": 1.0,
    }
    assert {s["trace_id"] for s in fake.scores} == {TRACE_ID}
    # 전송은 데몬 스레드에서 비운다. 요청 끝을 막지 않는다
    for _ in range(200):
        if fake.flushed:
            break
        time.sleep(0.01)
    assert fake.flushed == 1


def test_jev_decider_records_each_judgment(fake: FakeLangfuse) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answers": {"J1": {"noul": 0.9}}})

    decider = JevDecider(
        "k", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    questions = [Noul("J1", "i", "t", "f"), Noul("J2", "i", "t", "f")]
    decider.judge("state text", questions)
    assert [o.kwargs["name"] for o in fake.observations] == [
        "cg.judge.J1",
        "cg.judge.J2",
    ]
    assert fake.observations[1].updates["output"]["reason"] == "refused"
    assert "state text" not in str([o.kwargs for o in fake.observations])


def _plan() -> Plan:
    return Plan(
        id="p1",
        status="draft",
        targets=("a.py",),
        test_command="true",
        review_round=0,
        trace_ids=(),
        created_at="2026-11-11T00:00:00+00:00",
        sections={"요구사항": "r"},
    )


async def test_reviewer_records_review_span(fake: FakeLangfuse) -> None:
    class Broken:
        def with_structured_output(self, _schema: object) -> object:
            raise RuntimeError

    result = await PlanReviewer(Broken()).areview(_plan(), [], [])  # type: ignore[arg-type]
    assert result.error == "RuntimeError"
    (span,) = fake.named("cg.plan.review")
    assert span.updates["output"] == {
        "comments": 0,
        "questions": 0,
        "error": "RuntimeError",
    }
    assert span.updates["level"] == "ERROR"
    assert span.ended


def test_memory_inject_records_selection_and_trim(
    fake: FakeLangfuse, tmp_path: Path
) -> None:
    store = MemoryStore(tmp_path)
    store.save_rule("큰 규칙", "x" * 25_000, source="user", now=datetime.now(UTC))
    middleware = MemoryInjectionMiddleware(store, FakeDecider())
    human = HumanMessage("요청", id=str(uuid.uuid4()))
    assert middleware._select({"messages": [human]}) is not None
    (span,) = fake.named("cg.memory.inject")
    output = span.updates["output"]
    assert output["candidates"] == 0
    assert output["selected"] == []
    assert len(output["body_dropped"]) == 1  # 상한을 넘은 규칙 본문을 뺐다


def gate_scores(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(tracing, "end_request", lambda **kw: calls.append(kw))
    return calls


async def test_gate_counts_denies_and_repeats(
    tmp_path: Path, fake: FakeLangfuse, monkeypatch: pytest.MonkeyPatch
) -> None:
    ends = gate_scores(monkeypatch)
    h = Harness(
        tmp_path,
        [
            write(tmp_path, "a.py", call_id="w1"),
            write(tmp_path, "a.py", call_id="w2"),
            done(),
            done(),
        ],
    )
    await h.say("a.py 만들어줘")
    counters = (await h.state())[COUNTERS_KEY]
    assert counters["tool_calls"] == 2
    assert counters["tool_errors"] == 2
    assert counters["gate_denies"] == 2
    assert counters["repeat_failures"] == 1
    (end,) = ends
    assert end["counters"]["gate_denies"] == 2
    denies = fake.named("cg.gate.deny")
    assert len(denies) == 2
    assert denies[0].updates["level"] == "WARNING"
    assert denies[0].kwargs["input"] == {
        "tool": "write_file",
        "reason": "no_approved_plan",
    }

    # 같은 대화의 새 요청은 0부터 다시 센다
    await h.say("다시")
    assert (await h.state())[COUNTERS_KEY].get("tool_calls", 0) == 0


async def test_failed_tests_are_counted_and_traced(
    tmp_path: Path, fake: FakeLangfuse, monkeypatch: pytest.MonkeyPatch
) -> None:
    ends = gate_scores(monkeypatch)
    h = Harness(
        tmp_path,
        [
            explore(),
            submit(test_command="echo boom; exit 3"),
            approval(),
            tool_call("complete_plan", {"summary": "고침"}, "c"),
            done(),
        ],
    )
    await h.say("app.py 버그 고쳐줘")
    await h.resume("승인")
    counters = (await h.state())[COUNTERS_KEY]
    assert counters["test_failures"] == 1
    assert counters["tool_errors"] == 1
    (run,) = fake.named("cg.test.run")
    assert run.updates["level"] == "ERROR"
    assert run.updates["output"]["exit_code"] == 3
    for name in ("cg.explore", "cg.plan.submit", "cg.plan.approval"):
        assert fake.named(name), name
    assert fake.named("cg.plan.approval")[0].updates["output"] == {"result": "approved"}
    assert ends[-1]["review_rounds"] == 1
    assert ends[-1]["phase"] == "executing"


def test_stream_config_carries_langfuse_session_and_tag() -> None:
    config = build_stream_config("thread-1", None)
    assert config["metadata"]["langfuse_session_id"] == "thread-1"
    assert config["metadata"]["langfuse_tags"] == ["dcode-assistant"]


def test_project_dotenv_cannot_set_langfuse_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import deepagents_code.config as config_mod
    import deepagents_code.config_manifest as manifest

    project = tmp_path / "repo"
    project.mkdir()
    keys = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")
    (project / ".env").write_text(
        "".join(f"{k}=from-project\n" for k in (*keys, "LANGFUSE_HOST"))
    )
    global_env = tmp_path / "global.env"
    global_env.write_text("LANGFUSE_PUBLIC_KEY=from-global\n")
    monkeypatch.setattr(config_mod, "_GLOBAL_DOTENV_PATH", global_env)
    monkeypatch.setattr(manifest, "resolve_read_project_dotenv", lambda **_: True)

    env = config_mod._dotenv_environment(
        start_path=project, environ={"LANGFUSE_SECRET_KEY": "from-shell"}
    )
    assert env["LANGFUSE_PUBLIC_KEY"] == "from-global"  # 사용자 .env는 된다
    assert env["LANGFUSE_SECRET_KEY"] == "from-shell"  # 셸도 된다
    assert "LANGFUSE_BASE_URL" not in env  # 프로젝트 .env는 못 넣는다
    assert "LANGFUSE_HOST" not in env


def _calls(*calls: tuple[str, dict[str, Any], str]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": n, "args": a, "id": i, "type": "tool_call"} for n, a, i in calls
        ],
    )


async def test_parallel_tool_calls_in_one_step(
    tmp_path: Path, fake: FakeLangfuse, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate_scores(monkeypatch)
    (tmp_path / "app.py").write_text("x = 1\n")
    write_a = {"file_path": str(tmp_path / "a.py"), "content": "x"}
    write_b = {"file_path": str(tmp_path / "b.py"), "content": "x"}
    read_args = {"file_path": str(tmp_path / "app.py")}
    h = Harness(
        tmp_path,
        [
            _calls(("write_file", write_a, "w1"), ("write_file", write_b, "w2")),
            done(),
            _calls(("read_file", read_args, "r1"), ("read_file", read_args, "r2")),
            done(),
        ],
    )
    await h.say("둘 다 써줘")  # 한 단계에서 거부 둘
    counters = (await h.state())[COUNTERS_KEY]
    assert counters["tool_calls"] == 2
    assert counters["gate_denies"] == 2
    assert len(fake.named("cg.gate.deny")) == 2
    await h.say("둘 다 읽어줘")  # 한 단계에서 허용 둘
    state = await h.state()
    assert state[COUNTERS_KEY]["tool_calls"] == 2
    assert "tool_errors" not in state[COUNTERS_KEY]
    assert state[LAST_ERROR_KEY] is None


def test_sync_graph_counts_and_scores(
    tmp_path: Path, fake: FakeLangfuse, monkeypatch: pytest.MonkeyPatch
) -> None:
    ends = gate_scores(monkeypatch)
    (tmp_path / "app.py").write_text("x = 1\n")
    read = tool_call("read_file", {"file_path": str(tmp_path / "app.py")}, "r")
    h = Harness(tmp_path, [write(tmp_path, "a.py"), read, done()])
    h.agent.invoke({"messages": [HumanMessage("a.py 만들어줘")]}, h.config)
    counters = h.agent.get_state(h.config).values[COUNTERS_KEY]
    assert counters["tool_calls"] == 2  # 거부 하나, 허용 하나
    assert counters["gate_denies"] == 1
    assert counters["tool_errors"] == 1
    (end,) = ends
    assert end["counters"]["gate_denies"] == 1
    assert len(fake.named("cg.gate.deny")) == 1


async def test_llm_calls_are_the_request_difference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ends = gate_scores(monkeypatch)
    backend = CompositeBackend(
        default=LocalShellBackend(root_dir=tmp_path, virtual_mode=False), routes={}
    )
    gate = PlanGateMiddleware(make_options(tmp_path), backend)
    human = HumanMessage("요청", id="h1")
    start = gate.before_agent(
        {"messages": [human], "_session_cost_breakdown": {"request_count": 7}},
        None,  # type: ignore[arg-type]
    )
    assert start is not None
    assert start[COUNTERS_KEY] == {"__reset__": 1, "llm_base": 7}
    state = {
        COUNTERS_KEY: {"llm_base": 7, "tool_calls": 2},
        "_session_cost_breakdown": {"request_count": 10},
    }
    gate.after_agent(state, None)  # type: ignore[arg-type]
    await gate.aafter_agent(state, None)  # type: ignore[arg-type]
    assert [e["llm_calls"] for e in ends] == [3, 3]
    assert ends[0]["counters"]["tool_calls"] == 2
    assert ends[0]["phase"] == "idle"
