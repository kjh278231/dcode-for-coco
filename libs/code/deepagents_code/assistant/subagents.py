"""읽기 도구만 가진 탐색 서브에이전트 사양."""

from __future__ import annotations

from typing import TYPE_CHECKING

from deepagents.middleware.filesystem import FilesystemMiddleware

from deepagents_code.assistant import prompts
from deepagents_code.assistant.options import EXPLORER_SUBAGENT_NAME

if TYPE_CHECKING:
    from collections.abc import Sequence

    from deepagents.backends.protocol import BackendProtocol
    from deepagents.middleware.subagents import SubAgent
    from langchain.agents.middleware.types import AgentMiddleware


def build_explorer_subagent(
    backend: BackendProtocol, extra_middleware: Sequence[AgentMiddleware]
) -> SubAgent:
    """읽기 도구만 가진 탐색 서브에이전트 사양을 만든다.

    Args:
        backend: 메인 에이전트와 같은 백엔드.
        extra_middleware: 서브에이전트 공통 미들웨어.

    Returns:
        `task(subagent_type="explorer")`로 부르는 사양.
    """
    return {
        "name": EXPLORER_SUBAGENT_NAME,
        "description": prompts.EXPLORER_DESCRIPTION,
        "system_prompt": prompts.EXPLORER_SYSTEM,
        # 부모의 일반 도구(fetch_url, MCP 등)를 물려받지 않는다
        "tools": [],
        "middleware": [
            FilesystemMiddleware(
                backend=backend, tools=["ls", "read_file", "glob", "grep"]
            ),
            *extra_middleware,
        ],
        "interrupt_on": {},
    }
