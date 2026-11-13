"""Auto 모드의 Jev 검토 (`jev_review`)."""

from typing import TYPE_CHECKING

import pytest

from deepagents_code.assistant.decider import FakeDecider
from tests.unit_tests.test_auto_mode import (
    _allow_result,
    _middleware,
    _plan,
    _request,
    _StructuredModel,
)

if TYPE_CHECKING:
    from pathlib import Path


async def _decision(
    tmp_path: Path, decider: FakeDecider | None
) -> tuple[str, str, _StructuredModel]:
    middleware = _middleware(tmp_path)
    middleware._jev_review = True
    middleware._jev_decider = decider
    model = _StructuredModel(_allow_result())
    args = {"command": "echo hi"}
    request, _store, _key = _request(
        tmp_path, model=model, tool_name="execute", args=args
    )
    plan = await _plan(middleware, request, tool_name="execute", args=args)
    decision = plan["decisions"][0]
    return decision["disposition"], decision["path"], model


@pytest.mark.parametrize(
    ("script", "disposition", "path"),
    [
        ({"call-1": 0.9}, "classifier_allow", "classifier"),
        ({"call-1": 0.1}, "policy_deny", "classifier"),
        # Jev 호출 실패는 사람 승인으로 간다.
        ({"call-1": None}, "require_human", "fallback"),
    ],
)
async def test_jev_verdict_decides_without_the_classifier_model(
    tmp_path: Path, script: dict[str, float | None], disposition: str, path: str
) -> None:
    got, got_path, model = await _decision(tmp_path, FakeDecider(script=script))

    assert (got, got_path) == (disposition, path)
    assert model.calls == []


async def test_missing_jev_key_allows_without_review(tmp_path: Path) -> None:
    got, got_path, _model = await _decision(tmp_path, None)

    assert (got, got_path) == ("classifier_allow", "classifier")
