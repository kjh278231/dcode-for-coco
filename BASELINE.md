# M0 기준선

- 원본: 수업 저장소 커밋 `08a7e5a1`, `Day09/deepagents/libs/code/`.
- 환경: Python 3.14.10, `uv pip install --no-config --no-sources -e . --group pyproject.toml:test`.
- 기본 테스트 조건은 경고를 오류로 취급한다. 첫 실행은 수집 전에 실패했다.
- 단위 테스트 전체의 추가 관찰은 `-W "ignore:'asyncio.iscoroutinefunction' is deprecated:DeprecationWarning"`를 명시했다. 이 결과는 기본 조건의 통과가 아니다. 실행 중 Langfuse와 의존성 세 패키지가 환경에 추가됐다.
- 가짜 모델 실행과 버전 확인은 API 호출 없이 통과했다.

## 기본 조건의 테스트

명령: `.venv/bin/pytest -n 4 --benchmark-disable --disable-socket --allow-unix-socket tests/unit_tests/ --cov=deepagents_code --cov-report=term-missing`

종료 코드 3, 출력 원문:

```text
Error while loading plugin "pytest11".
.venv/lib/python3.14/site-packages/langsmith/pytest_plugin.py:15: in <module>
    from langsmith.testing._internal import _get_test_suite_name
.venv/lib/python3.14/site-packages/langsmith/testing/__init__.py:3: in <module>
    from langsmith.testing._internal import (
.venv/lib/python3.14/site-packages/langsmith/testing/_internal.py:32: in <module>
    from langsmith import client as ls_client
.venv/lib/python3.14/site-packages/langsmith/client.py:946: in <module>
    class Client:
.venv/lib/python3.14/site-packages/langsmith/client.py:4062: in Client
    @_deprecated(
.venv/lib/python3.14/site-packages/langsmith/_internal/_beta_decorator.py:92: in decorator
    if asyncio.iscoroutinefunction(func):
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/home/sds/.local/share/uv/python/cpython-3.14.10-linux-x86_64-gnu/lib/python3.14/asyncio/coroutines.py:23: in iscoroutinefunction
    warnings._deprecated("asyncio.iscoroutinefunction",
/home/sds/.local/share/uv/python/cpython-3.14.10-linux-x86_64-gnu/lib/python3.14/_py_warnings.py:833: in _deprecated
    _wm.warn(msg, DeprecationWarning, stacklevel=3)
E   DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
```

## 경고 하나를 제외한 추가 관찰

명령: 위 명령에 `-W "ignore:'asyncio.iscoroutinefunction' is deprecated:DeprecationWarning"` 추가.

종료 코드 1. 전체 출력은 실행 당시 `/tmp/dcode-m0-test-warning.log`에 남겼다. 아래는 원문의 실패 목록과 요약이다. `skipped`는 업스트림 테스트 자체의 실행 결과이며 새로 skip 처리한 것이 아니다.

```text
=========================== short test summary info ============================
FAILED tests/unit_tests/test_acp.py::test_auto_graph_adds_trusted_prompt_context
FAILED tests/unit_tests/test_config.py::TestWorkspaceStoredCredentials::test_stored_google_key_uses_its_endpoint_in_sdk_client[native]
FAILED tests/unit_tests/test_config.py::TestWorkspaceStoredCredentials::test_stored_google_key_uses_its_endpoint_in_sdk_client[stored]
FAILED tests/unit_tests/test_config.py::TestWorkspaceStoredCredentials::test_stored_google_key_uses_its_endpoint_in_sdk_client[client_options]
FAILED tests/unit_tests/test_config.py::TestWorkspaceStoredCredentials::test_stored_google_key_preserves_vertex_endpoint[parameter]
FAILED tests/unit_tests/test_config.py::TestWorkspaceStoredCredentials::test_stored_google_key_preserves_vertex_endpoint[environment]
FAILED tests/unit_tests/test_config.py::TestWorkspaceStoredCredentials::test_stored_google_key_preserves_vertex_endpoint[project]
FAILED tests/unit_tests/test_config.py::TestWorkspaceStoredCredentials::test_stored_key_drops_gateway_headers_only_for_native_requests[anthropic-native]
FAILED tests/unit_tests/test_btw.py::test_native_anthropic_mcp_is_absent_from_provider_request[constructor]
FAILED tests/unit_tests/test_config.py::TestWorkspaceStoredCredentials::test_stored_key_drops_gateway_headers_only_for_native_requests[anthropic-stored]
FAILED tests/unit_tests/test_btw.py::test_native_anthropic_mcp_is_absent_from_provider_request[binding]
FAILED tests/unit_tests/test_btw.py::test_native_anthropic_mcp_is_absent_from_provider_request[snapshot]
FAILED tests/unit_tests/test_btw.py::test_native_anthropic_mcp_is_absent_from_provider_request[checkpoint]
FAILED tests/unit_tests/test_btw.py::test_native_anthropic_mcp_is_absent_from_provider_request[extra_body]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-sonnet-4-20250514-False]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-opus-4-20250514-False]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-opus-4-1-20250805-False]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-opus-4.1-False]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-sonnet-4-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-sonnet-4-5-20250929-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-opus-4-5-20251101-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-haiku-4-5-20251001-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-sonnet-4-6-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-opus-4.8-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-sonnet-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-sonnet-5-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-opus-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-opus-5-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-haiku-5-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-fable-5-1-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[None-claude-mythos-5-1-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-sonnet-4-20250514-False]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-opus-4-20250514-False]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-opus-4-1-20250805-False]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-opus-4.1-False]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-sonnet-4-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-sonnet-4-5-20250929-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-opus-4-5-20251101-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-haiku-4-5-20251001-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-sonnet-4-6-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-opus-4.8-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-sonnet-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-sonnet-5-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-opus-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-opus-5-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-haiku-5-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-fable-5-1-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic/v1-claude-mythos-5-1-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-sonnet-4-20250514-False]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-opus-4-20250514-False]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-opus-4-1-20250805-False]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-opus-4.1-False]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-sonnet-4-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-sonnet-4-5-20250929-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-opus-4-5-20251101-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-haiku-4-5-20251001-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-sonnet-4-6-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-opus-4.8-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-sonnet-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-sonnet-5-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-opus-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-opus-5-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-haiku-5-5-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-fable-5-1-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_transport[https://gateway.smith.langchain.com/anthropic-claude-mythos-5-1-True]
FAILED tests/unit_tests/test_provider_tool_search_extra.py::test_anthropic_gateway_environment_transport
FAILED tests/unit_tests/test_main_acp_mode.py::test_acp_defaults_classifier_after_provider_resolution
FAILED tests/unit_tests/test_main_acp_mode.py::test_acp_sessions_use_fenced_persistence
FAILED tests/unit_tests/test_thread_titles.py::test_naming_removes_anthropic_mcp_from_provider_request[constructor]
FAILED tests/unit_tests/test_thread_titles.py::test_naming_removes_anthropic_mcp_from_provider_request[extra_body]
FAILED tests/unit_tests/test_thread_titles.py::test_naming_removes_anthropic_mcp_from_provider_request[binding]
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestNoteWebSearchRestart::test_flags_restart_when_running_server_lacks_tavily
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestNoteWebSearchRestart::test_ignores_non_tavily_service
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestNoteWebSearchRestart::test_skips_when_server_already_has_tavily
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestNoteWebSearchRestart::test_skips_when_no_owned_server
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestNoteWebSearchRestart::test_skips_when_export_produces_no_key
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestNoteWebSearchRestart::test_deleted_tavily_key_clears_env_after_offer_was_consumed
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestNoteWebSearchRestart::test_deleted_tavily_key_restores_original_env
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestOfferRestartForWebSearch::test_no_owned_server_recommends_relaunch
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestOfferRestartForWebSearch::test_busy_recommends_restart
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestOfferRestartForWebSearch::test_restart_choice_dispatches_restart
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestOfferRestartForWebSearch::test_restart_state_flip_surfaces_fallback
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestOfferRestartForWebSearch::test_skips_offer_when_tavily_already_configured
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestOfferRestartForWebSearch::test_later_choice_shows_no_followup_hint
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestOfferRestartForWebSearch::test_watchdog_timeout_falls_back_to_manual_hint
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestOfferRestartForWebSearch::test_mount_failure_falls_back_to_manual_hint
ERROR tests/unit_tests/test_auth_web_search_restart.py::TestCredentialSavedHandler::test_saved_tavily_key_arms_restart_offer
= 71 failed, 10316 passed, 26 skipped, 1 warning, 16 errors in 316.11s (0:05:16) =
```

## lint 기준선

- 처음 설치된 Ruff 0.17.4: `ruff check .` 종료 코드 1, 222건. 원본 lock의 Ruff 0.16.0으로 다시 실행: `All checks passed!`.
- `ruff format . --diff`: 종료 코드 0, `631 files already formatted`.
- `ty check .`: 종료 코드 2. 원문: `ty failed` / `Cause: /home/sds/workspace/dcode-assistant/libs/deepagents does not point to a directory`.
- `python scripts/generate_commands_catalog.py --check`: 종료 코드 0, `COMMANDS.md is up-to-date`.
- `python scripts/check_process_cwd.py deepagents_code`: 종료 코드 0, 출력 없음.

`make lint`와 `make test`는 부재한 로컬 source를 참조하는 `uv run`을 사용하므로 명세 M0에 따라 위와 같이 가상환경 명령을 직접 실행했다.
