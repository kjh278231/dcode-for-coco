"""계획 게이트의 Jev 키 검사 (SPEC 3.10). 서버 기동 경로에서 한 번 한다."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from deepagents_code.assistant.decider import MissingJevKeyError, require_jev_key
from deepagents_code.client.launch import server_manager

SECRET = "sk-or-secret-value-123"
PAST_CHECK = "past the key check"


def test_missing_key_message_names_variables_only() -> None:
    with pytest.raises(MissingJevKeyError) as exc_info:
        require_jev_key({"OPENROUTER_API_KEY": "  ", "OTHER": SECRET})
    message = str(exc_info.value)
    assert "OPENROUTER_API_KEY" in message
    assert "DEEPAGENTS_CODE_PLAN_GATE=0" in message
    assert SECRET not in message


@pytest.mark.parametrize("name", ["TYPESAFE_API_KEY", "OPENROUTER_API_KEY"])
def test_present_key_passes(name: str) -> None:
    require_jev_key({name: SECRET})


async def launch(*, plan_gate: bool) -> None:
    # 키 검사를 지나면 MCP 사전 검사에서 멈춰 서버를 띄우지 않는다
    with patch.object(
        server_manager,
        "_preflight_validate_mcp_config",
        side_effect=RuntimeError(PAST_CHECK),
    ):
        await server_manager.start_server_and_get_agent(
            assistant_id="agent", plan_gate=plan_gate
        )


async def test_launch_without_key_fails_before_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(MissingJevKeyError):
        await launch(plan_gate=True)


async def test_launch_with_gate_off_skips_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match=PAST_CHECK):
        await launch(plan_gate=False)


async def test_launch_with_key_passes_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    with pytest.raises(RuntimeError, match=PAST_CHECK):
        await launch(plan_gate=True)
