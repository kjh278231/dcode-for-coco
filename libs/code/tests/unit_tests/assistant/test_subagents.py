"""서브에이전트는 승인 뒤에도 읽기 전용이다 (SPEC 9.3 G13, 12장 P3)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import deepagents.middleware.subagents as sdk_subagents
import pytest
from deepagents.backends import CompositeBackend, LocalShellBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.subagents import SubAgentMiddleware
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from deepagents_code._env_vars import FORKED_SUBAGENTS
from deepagents_code.agent import create_cli_agent
from deepagents_code.assistant.gate import (
    PlanGateMiddleware,
    SubagentWriteBlockMiddleware,
)
from deepagents_code.assistant.options import EXPLORER_SUBAGENT_NAME, PLAN_TOOLS
from tests.unit_tests.assistant.fakes import make_options, scripted_model, tool_call
from tests.unit_tests.test_end_to_end import FixedGenericFakeChatModel, mock_settings

if TYPE_CHECKING:
    from pathlib import Path


def _write(path: Path) -> AIMessage:
    return tool_call("write_file", {"file_path": str(path), "content": "x"}, "w")


def _results(result: dict[str, Any]) -> dict[str, ToolMessage]:
    return {m.tool_call_id: m for m in result["messages"] if isinstance(m, ToolMessage)}


async def test_g13_subagent_stack_denies_writes(tmp_path: Path) -> None:
    backend = CompositeBackend(
        default=LocalShellBackend(root_dir=tmp_path, virtual_mode=False), routes={}
    )
    script = [
        AIMessage(
            content="",
            tool_calls=[
                *_write(tmp_path / "a.py").tool_calls,
                {"name": "execute", "args": {"command": "touch b"}, "id": "rm"},
                {"name": "execute", "args": {"command": "ls"}, "id": "ls"},
                {"name": "submit_plan", "args": {}, "id": "p"},
            ],
        ),
        AIMessage(content="끝"),
    ]
    agent = create_agent(
        model=scripted_model(script),
        middleware=[
            FilesystemMiddleware(backend=backend),
            SubagentWriteBlockMiddleware(tmp_path),
        ],
    )
    result = _results(
        await agent.ainvoke({"messages": [HumanMessage(content="고쳐줘")]})
    )
    assert not (tmp_path / "a.py").exists()
    assert not (tmp_path / "b").exists()
    assert result["w"].status == "error"
    assert result["rm"].status == "error"
    assert result["p"].status == "error"
    assert result["ls"].status != "error"


async def test_task_to_sdk_subagent_write_is_denied(tmp_path: Path) -> None:
    """주 에이전트 task → SDK가 만든 서브에이전트 → 차단기가 write_file을 거부한다."""
    backend = CompositeBackend(
        default=LocalShellBackend(root_dir=tmp_path, virtual_mode=False), routes={}
    )
    target = tmp_path / "a.py"
    model = scripted_model(
        [
            tool_call("task", {"description": "써", "subagent_type": "worker"}, "t"),
            _write(target),  # 서브에이전트의 첫 응답
            AIMessage(content="못 썼다"),  # 서브에이전트의 끝
            AIMessage(content="끝"),  # 주 에이전트의 끝
        ]
    )
    worker: Any = {
        "name": "worker",
        "description": "일꾼",
        "system_prompt": "쓴다",
        "model": model,
        "tools": [],
        "middleware": [
            FilesystemMiddleware(backend=backend),
            SubagentWriteBlockMiddleware(tmp_path),
        ],
    }
    agent = create_agent(
        model=model,
        middleware=[SubAgentMiddleware(backend=backend, subagents=[worker])],
    )
    result = await agent.ainvoke({"messages": [HumanMessage(content="고쳐줘")]})
    assert _results(result)["t"].content == "못 썼다"
    assert not target.exists()


def _build(tmp_path: Path, model: Any, user_subagent: bool) -> dict[str, Any]:  # noqa: ANN401
    """게이트를 켠 dcode 에이전트를 만들고 서브에이전트 그래프를 이름별로 모은다."""
    captured: dict[str, Any] = {}
    original = sdk_subagents.create_agent

    def spy(model: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        graph = original(model, **kwargs)
        captured[kwargs["name"]] = (kwargs["middleware"], graph)
        return graph

    metas = (
        [
            {
                "name": "writer",
                "description": "사용자 서브에이전트",
                "system_prompt": "쓴다",
                "model": None,
                "path": None,
            }
        ]
        if user_subagent
        else []
    )
    with (
        mock_settings(tmp_path),
        patch.object(sdk_subagents, "create_agent", spy),
        patch("deepagents_code.agent.list_subagents", return_value=metas),
    ):
        create_cli_agent(
            model=model,
            assistant_id="test-agent",
            tools=[],
            auto_approve=True,
            cwd=tmp_path,
            checkpointer=InMemorySaver(),
            plan_gate=make_options(tmp_path),
        )
    return captured


@pytest.mark.parametrize(
    ("name", "forked"),
    [("general-purpose", "1"), ("general-purpose", "0"), ("writer", "1")],
)
async def test_every_subagent_is_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, forked: str
) -> None:
    """fork, fork 아님, 사용자 선언형 모두 쓰기가 막히고 계획 도구가 없다."""
    monkeypatch.setenv(FORKED_SUBAGENTS, forked)
    target = tmp_path / "app.py"
    model = FixedGenericFakeChatModel(
        messages=iter([_write(target), AIMessage(content="끝")])
    )
    middleware, graph = _build(tmp_path, model, user_subagent=name == "writer")[name]
    assert any(isinstance(m, SubagentWriteBlockMiddleware) for m in middleware)
    assert not any(isinstance(m, PlanGateMiddleware) for m in middleware)
    assert not PLAN_TOOLS & set(graph.nodes["tools"].bound.tools_by_name)
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="app.py 만들어줘")]},
        {"configurable": {"thread_id": str(uuid.uuid4())}},
    )
    denial = _results(result)["w"]
    assert denial.status == "error"
    assert "서브에이전트는 읽기 전용이다" in str(denial.content)
    assert not target.exists()


def test_explorer_has_only_read_tools(tmp_path: Path) -> None:
    model = FixedGenericFakeChatModel(messages=iter([]))
    _, graph = _build(tmp_path, model, user_subagent=False)[EXPLORER_SUBAGENT_NAME]
    assert set(graph.nodes["tools"].bound.tools_by_name) == {
        "ls",
        "read_file",
        "glob",
        "grep",
    }
