"""자기 개선: 관찰, 개선안 저장, `/improve`, `/runs`, `/trace` (SPEC 6.5, 7장)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deepagents_code.app import DeepAgentsApp
from deepagents_code.assistant import improve
from deepagents_code.assistant.frontmatter import parse
from deepagents_code.assistant.improve import (
    ImprovementStateError,
    ImprovementStore,
    Observation,
    Threshold,
    find_observations,
    improve_command,
)
from deepagents_code.assistant.memory import MemoryStore
from deepagents_code.assistant.runs import (
    NO_KEYS_TEXT,
    Failure,
    RunSummary,
    latest_trace,
    runs_command,
)
from deepagents_code.hooks.manager import HooksManager
from deepagents_code.tui.widgets.messages import AppMessage
from tests.unit_tests.assistant.fakes import tool_call
from tests.unit_tests.assistant.test_memory import build
from tests.unit_tests.test_end_to_end import FixedGenericFakeChatModel, mock_settings

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 11, 11, 15, 30, tzinfo=UTC)
NO_KEYS: dict[str, str] = {}


def summary(trace_id: str, **scores: float) -> RunSummary:
    return RunSummary(
        trace_id=trace_id,
        timestamp="2026-11-11T10:00:00",
        name="LangGraph",
        session_id="s1",
        latency_s=1.0,
        scores={f"cg.{k}": v for k, v in scores.items()},
        error_count=0,
        url=f"https://lf/trace/{trace_id}",
    )


class FakeRuns:
    def __init__(self, runs: list[RunSummary]) -> None:
        self.runs = runs
        self.calls: list[dict[str, Any]] = []

    def list_runs(self, **kwargs: Any) -> list[RunSummary]:
        self.calls.append(kwargs)
        return self.runs[: kwargs.get("limit", 10)]

    def failures(self, trace_id: str) -> list[Failure]:
        return [Failure("cg.gate.deny", "WARNING", f"deny {trace_id}", "2026-11-11")]


# ----- find_observations -----


def test_find_observations_counts_runs_over_threshold() -> None:
    signals = {
        "a": {"cg.tool_errors": 9, "cg.gate_denies": 3},
        "b": {"cg.tool_errors": 5},
        "c": {"cg.tool_errors": 7, "cg.gate_denies": 1},
        "d": {"cg.tool_errors": 4},
        "e": {},
    }
    (obs,) = find_observations(signals)
    assert obs == Observation("cg.tool_errors", 3, 5, ("a", "c", "b"))
    # gate_denies: 해당 1건 < min_runs 2
    assert find_observations({}, improve.THRESHOLDS) == []
    custom = (Threshold("cg.x", per_run=1, min_runs=1),)
    assert find_observations({"a": {"cg.x": 1}}, custom)[0].run_count == 1


# ----- ImprovementStore -----


def create(store: ImprovementStore, kind: Any = "rule", name: str = "use-uv") -> str:  # noqa: ANN401
    return store.create(
        kind=kind,
        name=name,
        description="테스트는 uv run pytest로 돌린다",
        body="uv run pytest -q",
        rationale="반복 실패 3건",
        observations=[Observation("cg.repeat_failures", 2, 5, ("abcdef1234",))],
        now=NOW,
    )


def test_rule_lifecycle(tmp_path: Path) -> None:
    store = ImprovementStore(tmp_path)
    imp_id = create(store)
    assert imp_id == "20261111-153000-use-uv"
    imp = store.load(imp_id)
    assert (imp.status, imp.kind, imp.validation) == ("proposed", "rule", None)
    assert imp.observations == ("cg.repeat_failures: 2/5건 (가장 나쁜 작업 abcdef12)",)
    assert store.list_ids() == [imp_id]

    memory = MemoryStore(tmp_path)
    with pytest.raises(ImprovementStateError):
        store.apply(imp_id, memory, tmp_path / "skills")
    assert memory.list_records() == []

    store.record_validation(imp_id, {"passed": False, "limits": "x"})
    assert store.load(imp_id).status == "failed"
    with pytest.raises(ImprovementStateError):
        store.apply(imp_id, memory, tmp_path / "skills")

    store.record_validation(imp_id, {"passed": True})
    assert store.load(imp_id).validation == {"passed": True}
    store.apply(imp_id, memory, tmp_path / "skills")
    (rule,) = memory.list_records("rule")
    assert rule.name == "rule-use-uv"
    assert rule.source == f"improvement:{imp_id}"
    assert rule.body == "uv run pytest -q\n"
    assert store.load(imp_id).status == "applied"
    with pytest.raises(ImprovementStateError):
        store.reject(imp_id)


def test_skill_apply_copies_payload(tmp_path: Path) -> None:
    store = ImprovementStore(tmp_path)
    imp_id = create(store, kind="skill", name="run-tests")
    store.record_validation(imp_id, {"passed": True})
    skills = tmp_path / ".deepagents" / "skills"
    store.apply(imp_id, MemoryStore(tmp_path), skills)
    meta, body = parse((skills / "run-tests" / "SKILL.md").read_text())
    assert meta == {
        "name": "run-tests",
        "description": "테스트는 uv run pytest로 돌린다",
    }
    assert body == "uv run pytest -q\n"


def test_reject_keeps_folder(tmp_path: Path) -> None:
    store = ImprovementStore(tmp_path)
    imp_id = create(store)
    store.reject(imp_id)
    assert store.load(imp_id).status == "rejected"
    assert (store.directory / imp_id / "payload").is_dir()


@pytest.mark.parametrize(
    ("kind", "name"),
    [("prompt", "x"), ("rule", "../escape"), ("rule", "Bad Name"), ("skill", "")],
)
def test_create_rejects_bad_kind_or_name(tmp_path: Path, kind: str, name: str) -> None:
    with pytest.raises(ValueError, match=r"kind|name"):
        create(ImprovementStore(tmp_path), kind=kind, name=name)
    assert not (tmp_path / ".deepagents").exists()


def test_create_refuses_symlink_out_of_project(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    project = tmp_path / "project"
    (project / ".deepagents").mkdir(parents=True)
    (project / ".deepagents" / "improvements").symlink_to(outside)
    with pytest.raises(PermissionError):
        create(ImprovementStore(project))
    assert list(outside.iterdir()) == []


def test_hand_edited_proposal_cannot_escape(tmp_path: Path) -> None:
    store = ImprovementStore(tmp_path)
    imp_id = create(store, kind="skill", name="run-tests")
    store.record_validation(imp_id, {"passed": True})
    proposal = store.directory / imp_id / "proposal.md"
    proposal.write_text(
        proposal.read_text().replace("name: run-tests", "name: ../../x")
    )
    text, _ = improve_command(f"apply {imp_id}", tmp_path, NO_KEYS)
    assert "kind나 name이 잘못됐다" in text
    assert "읽을 수 없음" in improve_command("list", tmp_path, NO_KEYS)[0]
    assert not (tmp_path / ".deepagents" / "skills").exists()
    assert not (tmp_path / "x").exists()


def test_load_rejects_bad_id(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ImprovementStore(tmp_path).load("../../etc")


# ----- /improve -----


def test_improve_without_keys(tmp_path: Path) -> None:
    assert improve_command("", tmp_path, NO_KEYS) == (NO_KEYS_TEXT, None)


def test_improve_sends_instruction_when_observed(tmp_path: Path) -> None:
    runs = FakeRuns(
        [summary("t1", tool_errors=6), summary("t2", tool_errors=8), summary("t3")]
    )
    text, prompt = improve_command("", tmp_path, NO_KEYS, client=runs)  # type: ignore[arg-type]
    assert runs.calls == [{"limit": improve.RECENT_RUNS}]
    assert "cg.tool_errors: 2/3건" in text
    assert "모델 호출 약 3회" in text
    assert prompt is not None
    assert "t2, t1" in prompt
    assert "propose_improvement" in prompt


def test_improve_nothing_observed(tmp_path: Path) -> None:
    text, prompt = improve_command(
        "",
        tmp_path,
        NO_KEYS,
        client=FakeRuns([summary("t1")]),  # type: ignore[arg-type]
    )
    assert prompt is None
    assert "관찰이 없습니다" in text


def test_improve_subcommands(tmp_path: Path) -> None:
    assert improve_command("list", tmp_path, NO_KEYS) == ("개선안이 없습니다", None)
    store = ImprovementStore(tmp_path)
    imp_id = create(store, kind="skill", name="run-tests")

    listed, _ = improve_command("list", tmp_path, NO_KEYS)
    assert listed.startswith(f"{imp_id}  proposed  skill")
    shown, _ = improve_command(f"show {imp_id}", tmp_path, NO_KEYS)
    assert "--- payload/run-tests/SKILL.md" in shown
    assert f"evalsuite run --improvement {imp_id}" in shown

    refused, _ = improve_command(f"apply {imp_id}", tmp_path, NO_KEYS)
    assert "검증을 통과한 개선안만" in refused
    store.record_validation(imp_id, {"passed": True})
    applied, _ = improve_command(f"apply {imp_id}", tmp_path, NO_KEYS)
    assert '"passed": true' in applied
    assert improve.RELOAD_NOTICE in applied
    assert (tmp_path / ".deepagents" / "skills" / "run-tests" / "SKILL.md").is_file()

    other = create(store, name="other")
    assert improve_command(f"reject {other}", tmp_path, NO_KEYS)[0].endswith(
        "거절했습니다"
    )
    assert "개선안이 없습니다" in improve_command("show nope", tmp_path, NO_KEYS)[0]
    assert improve_command("apply", tmp_path, NO_KEYS)[0].startswith("사용법")


# ----- /runs, /trace 문자열 -----


def test_runs_command() -> None:
    runs = FakeRuns([summary("abc111"), summary("abc222"), summary("def333")])
    assert runs_command("", NO_KEYS) == NO_KEYS_TEXT
    assert "def333"[:8] in runs_command("", NO_KEYS, client=runs)  # type: ignore[arg-type]
    detail = runs_command(" def", NO_KEYS, client=runs)  # type: ignore[arg-type]
    assert "deny def333" in detail
    assert "https://lf/trace/def333" in detail
    assert "여러 건" in runs_command("abc", NO_KEYS, client=runs)  # type: ignore[arg-type]
    assert "없습니다" in runs_command("zzz", NO_KEYS, client=runs)  # type: ignore[arg-type]


def test_latest_trace() -> None:
    runs = FakeRuns([summary("t9")])
    url, text = latest_trace(NO_KEYS, "thread-1", client=runs)  # type: ignore[arg-type]
    assert url == "https://lf/trace/t9"
    assert runs.calls == [{"limit": 1, "session_id": "thread-1"}]
    assert url in text
    assert latest_trace(NO_KEYS, "thread-1") == (None, NO_KEYS_TEXT)
    url, text = latest_trace(NO_KEYS, "t", client=FakeRuns([]))  # type: ignore[arg-type]
    assert url is None
    assert "아직" in text


# ----- propose_improvement (실제 그래프) -----


async def test_propose_improvement_saves_without_applying(tmp_path: Path) -> None:
    model = FixedGenericFakeChatModel(
        messages=iter(
            [
                tool_call(
                    "propose_improvement",
                    {
                        "kind": "rule",
                        "name": "use-uv",
                        "description": "uv로 테스트",
                        "body": "uv run pytest",
                        "rationale": "반복 실패",
                    },
                    "p",
                ),
                AIMessage(content="끝"),
            ]
        )
    )
    with mock_settings(tmp_path):
        agent = build(tmp_path, model, interactive=False)
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content="개선해")]},
            {"configurable": {"thread_id": str(uuid.uuid4())}},
        )
    assert "__interrupt__" not in result
    reply = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    assert reply.status == "success"
    (imp_id,) = ImprovementStore(tmp_path).list_ids()
    assert imp_id in str(reply.content)
    assert ImprovementStore(tmp_path).load(imp_id).status == "proposed"
    assert MemoryStore(tmp_path).list_records() == []


# ----- TUI 처리기 -----


def _configured_app(tmp_path: Path) -> DeepAgentsApp:
    app = DeepAgentsApp(cwd=tmp_path)
    app._agent = MagicMock()
    app._agent.aupdate_state = AsyncMock()
    app._ui_adapter = MagicMock()
    app._session_state = MagicMock()
    app._session_state.hooks = HooksManager.inert()
    return app


async def test_improve_handler_sends_instruction_to_agent(tmp_path: Path) -> None:
    """SPEC 7.4 [미확인]: 처리기의 지시문이 에이전트 실행까지 간다."""
    app = _configured_app(tmp_path)
    sent: list[str] = []

    async def run_task(message: str, **_: Any) -> None:
        sent.append(message)
        await app._cleanup_agent_task()

    app._run_agent_task = run_task  # type: ignore[method-assign]
    async with app.run_test() as pilot:
        await pilot.pause()
        with patch(
            "deepagents_code.assistant.improve.improve_command",
            return_value=("관찰 1건", "INSTRUCTION"),
        ) as handler:
            await app._handle_command("/improve")
            for _ in range(10):
                await pilot.pause()
        assert handler.call_args.args[0] == ""
        assert sent == ["INSTRUCTION"]
        assert not app._agent_running
        assert any("관찰 1건" in str(w._content) for w in app.query(AppMessage))


async def test_runs_and_trace_handlers(tmp_path: Path) -> None:
    app = DeepAgentsApp(cwd=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._session_state = MagicMock(thread_id="thread-1")
        with (
            patch(
                "deepagents_code.assistant.runs.runs_command", return_value="RUNS-TEXT"
            ) as runs,
            patch(
                "deepagents_code.assistant.runs.latest_trace",
                return_value=("https://lf/t", "TRACE-TEXT"),
            ) as trace,
            patch("deepagents_code.app.webbrowser.open") as opened,
            patch.dict(
                "os.environ", {"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"}
            ),
        ):
            await app._handle_command("/runs AbC")
            await app._handle_command("/trace")
            for _ in range(5):
                await pilot.pause()
        assert runs.call_args.args[0] == " AbC"
        assert trace.call_args.args[1] == "thread-1"
        opened.assert_called_once_with("https://lf/t")
        rendered = "\n".join(str(w._content) for w in app.query(AppMessage))
        assert "RUNS-TEXT" in rendered
        assert "TRACE-TEXT" in rendered


@pytest.mark.parametrize(("count", "fails"), [(2, False), (0, False), (5, True)])
async def test_startup_notice_once_per_launch(
    tmp_path: Path, count: int, *, fails: bool
) -> None:
    app = DeepAgentsApp(cwd=tmp_path)
    app._improvement_notice_pending = True  # run_textual_app가 켠다
    scan = MagicMock(
        side_effect=RuntimeError("down") if fails else None, return_value=count
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        with (
            patch("deepagents_code.assistant.improve.pending_observation_count", scan),
            patch.object(app, "notify") as notify,
            patch.object(app, "_run_session_start_sequence", new_callable=AsyncMock),
        ):
            for _ in range(2):  # 재연결에도 한 번만
                app.on_deep_agents_app_server_ready(
                    app.ServerReady(
                        agent=MagicMock(), server_proc=None, mcp_server_info=[]
                    )
                )
                for _ in range(10):
                    await pilot.pause()
        hints = [c for c in notify.call_args_list if "/improve" in str(c.args[0])]
    assert scan.call_count == 1
    assert len(hints) == (1 if count and not fails else 0)
    if hints:
        assert "관찰이 2건" in hints[0].args[0]
