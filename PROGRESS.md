# 진행 기록

명세는 `docs/SPEC.md` 10장. 기존 테스트 기준선은 `BASELINE.md`. 작업 순서는 `AGENTS.md`, 검사는 `scripts/check.sh`.

## M0. 작업 사본과 기준선 — 완료 (2026-11-11)

- 커밋 `679a464`(원본 사본), `1b81051`(환경과 기준선).
- 검사 통과: `dcode --version`이 `~/workspace/dcode-assistant/libs/code` editable 설치를 보여준다. `scripts/smoke_dcode.sh` 종료 코드 0. `BASELINE.md` 있음.
- langfuse 4.15.1 고정, `uv lock --check --no-sources` 통과. lock에서 빠진 줄은 `--no-sources`로 로컬 `../deepagents`, `../acp` 대신 PyPI 패키지를 쓴 결과다.
- 알려진 기준선 실패: 기본 조건 테스트 수집 실패(langsmith 경고), 경고 제외 시 71 failed / 16 errors, `ty`는 없는 `../deepagents` 경로로 실패.

## M1. 순수 모듈 — 완료 (2026-11-11, 커밋 `8f26eba`)

- 추가: `deepagents_code/assistant/{__init__,options,frontmatter,plan,policy}.py`, `tests/unit_tests/assistant/test_{frontmatter,plan,policy}.py`.
- 수정: `_paths.py`의 `ProjectPaths`에 `plans_dir`, `memory_dir`, `improvements_dir`.
- 검사: `tests/unit_tests/assistant` + `ProjectPaths`를 쓰는 기존 테스트(`test_agent`, `test_mcp_tools`, `test_mcp_login_service`) 554 passed. 새 파일과 `_paths.py`에 `ruff check`, `ruff format --diff` 통과, `check_process_cwd.py` 통과. 테스트는 기준선과 같이 langsmith 경고 하나를 `-W ignore`로 끄고 돌렸다.
- 명세와 다른 점 (SPEC 본문에 반영함):
  - `PlanGateOptions`는 `Decider`, `PlanReviewer`가 생기는 M2로 미뤘다. 지금 넣으면 없는 모듈을 import한다.
  - `options.py`에 `PROTECTED_DIRS`와 `Phase` 리터럴을 더했다. `policy`와 이후 `gate`가 같이 쓴다.
  - `normalize_tool_path(raw)`는 `project_root` 인자를 뺐다. 정규화에 쓰지 않는다.
  - `mentions_protected`는 보호 폴더 셋 외에 상위 `.deepagents` 자체(`rm -rf .deepagents`, `.deepagents/*`)도 잡는다. `is_protected`의 상위 폴더 규칙과 맞췄다.
  - 계획 본문의 알 수 없는 `##` 절은 버리지 않고 정해진 절 뒤에 둔다. 첫 `##` 앞의 글은 버린다.
- `scripts/check.sh baseline`: 71 failed, 10392 passed(기준선 10316 + 새 테스트 76), 26 skipped, 16 errors. 실패 목록이 기준선과 같다. 경고가 1건 늘었는데 업스트림 `test_server.py::TestServerProcess::test_after_spawn_cancellation_reaps_subprocess`의 임시 파일 `ResourceWarning`이다.
- 확인 못 한 것: `ty`는 기준선부터 깨져 있어 돌리지 않았다.

## 하네스 (2026-11-11)

- `AGENTS.md`(+ `CLAUDE.md`): 마일스톤 루프와 완료 기준.
- `scripts/check.sh`: `unit`, `lint`, `baseline`, `smoke`, `all`. `scripts/baseline_failures.txt`는 `BASELINE.md`의 실패 87건(71 failed + 16 errors)이다.

## M2. 판정기와 리뷰어 — 완료 (2026-11-11)

- 추가: `deepagents_code/assistant/{decider,reviewer,prompts}.py`, `options.py`의 `PlanGateOptions`, `tests/unit_tests/assistant/{fakes,test_decider,test_reviewer}.py`, `scripts/jev_probe.py`(실제 Jev 응답 형태 확인용).
- 수정(업스트림): `_env_vars.py`에 `PLAN_GATE_JEV_THRESHOLD`.
- 검사: `check.sh unit` 119 passed(새 테스트 43). `check.sh lint` 통과. `check.sh baseline` 71 failed, 10434 passed(기준선 10316 + assistant 118), 26 skipped, 16 errors, 2 warnings(M1과 같음). 실패 목록이 기준선과 같다. 그 뒤로는 `assistant/` 안만 고쳤다(테스트 1개 추가).
- 실제 Jev 호출 (OpenRouter 경유, `typesafe/jev-1.13`, 키는 `.env`의 `OPENROUTER_API_KEY`): `scripts/jev_probe.py` HTTP 200. 최상위 키 `answers, id, model, provider, usage`, `answers.J1 = {"type": "noul", "noul": 0.98}`(float). SPEC 3.3의 형태와 같다. 호출당 약 $0.000015.
  - 실제 `question_j1` 문구로 두 계획: 완료 조건 "잘 동작하면 된다" 0.11(통과 못 함), "pytest ... 통과, /health 200" 0.95(통과).
  - 프로브의 짧은 기준 문구로는 모호한 완료 조건이 0.52로 0.5를 넘었다. 기준 문구가 결과를 크게 바꾼다. M9 보정의 근거로 남긴다.
- 명세와 다른 점 (SPEC 본문에 반영함):
  - `questions_j6`는 `MemoryRecord`가 생기는 M5로, `record_judgment`와 `cg.plan.review` 구간은 `tracing.py`가 생기는 M6로 미뤘다.
  - `PLAN_GATE_JEV_THRESHOLD` 상수를 M3에서 M2로 당겼다. `from_environment`가 읽는다. 값이 수가 아니거나 (0, 1] 밖이면 `DeciderError`.
  - `JevDecider`가 OpenRouter 경유를 지원한다. `TYPESAFE_API_KEY`가 없고 `OPENROUTER_API_KEY`가 있으면 `https://openrouter.ai/api/alpha/decisions`, 모델 `typesafe/jev-1.13`. 이 모델 id는 수업 코드에서 미확인이었고 이번 호출로 동작을 확인했다. 저장소 `.gitignore`에 `.env`를 더했다.
  - `FakeDecider` 대본 값에 `None`(= transport_error)을 허용했다. G16용.
  - Jev 응답에서 `noul`이 bool이거나 문자열이면 invalid, 응답이 JSON이 아니거나 `answers`가 사전이 아니면 그 묶음 전체가 transport_error다.
  - 리뷰어의 구조화 출력이 없거나(`None`) 필드가 빠지면 `error`를 채운다. 빈 의견으로 세지 않는다.
  - 판정 state가 4,000자를 넘으면 각 부분을 같은 몫으로 자른다. 긴 절 하나가 targets나 테스트 명령을 밀어내지 않게 한다.
- SPEC 3.10의 [확인]과 다른 사실: 이 사본의 `tests/unit_tests/test_env_vars.py`에는 테스트 함수가 없다. `DEEPAGENTS_CODE_*` 문자열 직접 사용을 막는 검사가 실제로는 돌지 않는다. 규칙은 그대로 지킨다.
- 확인 못 한 것: 질문 문구는 보정 전 초안이다 (M9). `ty`는 돌리지 않았다.

## M3. 게이트와 계획 도구 — 완료 (2026-11-11)

- 추가: `deepagents_code/assistant/{gate,tools,subagents}.py`, `tests/unit_tests/assistant/test_gate.py`.
- 수정(assistant): `options.py`(상태 키 상수, `plan_gate_enabled`), `plan.py`(`record_answers`), `decider.py`(`question_j4`의 `request` 인자).
- 수정(업스트림): `_env_vars.py`(`PLAN_GATE`), `_server_config.py`(`plan_gate` 필드, env, payload, `SESSION_WORKSPACE_FIELDS`), `client/launch/server_manager.py`, `client/non_interactive.py`, `main.py`(`_require_typesafe_key`, `server_kwargs`), `server_graph.py`(`_build_plan_gate_options`), `agent.py`(`plan_gate` 인자, 게이트와 탐색 서브에이전트 등록, `precheck_denies`, `--allow-fs-tools` 주입에서 explorer 제외).
- 수정(검사 자료와 스크립트): `libs/code/scripts/check_process_cwd.py` 허용 항목 토큰 `99c1d085` → `86fa45ed`(사유 문구 그대로, 사용자 승인). `scripts/smoke_dcode.sh`와 `tests/integration_tests/test_headless_resume.py`에 `DEEPAGENTS_CODE_PLAN_GATE=0`(9.4 허용).
- 먼저 확인한 [미확인]:
  - ask_user 모양 멈춤을 다른 도구 이름(`request_plan_approval`)으로 내도 TUI가 질문 화면을 띄운다. `test_textual_adapter`의 가짜 스트림으로 먼저 확인했고(재개 값 `{"answers": ["승인"]}`, 행 상태 success), 아래 실제 TUI에서 다시 확인했다.
  - `CompositeBackend.aexecute(cmd, timeout=600)` → `ExecuteResponse(output, exit_code, truncated)`. 셸 없는 백엔드는 `NotImplementedError`.
  - 모델 객체는 `server_graph`의 `result.model`로 `create_cli_agent` 밖에서 얻는다.
- 검사:
  - `check.sh unit` 142 passed. `test_gate.py` 23개: G1~G11, G14~G19, `create_cli_agent`에 게이트가 설치되는지, `complete_plan` 성공과 실패, `precheck_denies`, 둘째 계획의 리뷰 회차, 실패한 쓰기의 대상 미추가.
  - `check.sh lint` 통과.
  - `check.sh baseline` (리뷰 수정 뒤) 71 failed, 10458 passed(10316 + assistant 142), 26 skipped, 16 errors, 2 warnings. 실패 목록이 기준선과 같다. 토큰을 바꾸기 전 실행에서는 `test_process_cwd_check.py::test_current_package_matches_allowlist`가 새로 실패했다.
  - 가짜 echo 모델로 게이트를 켠 `dcode -n`: 키가 있으면 종료 코드 0이고 시스템 프롬프트에 게이트 지침이 들어간다. 키가 없으면 종료 코드 1이고 안내만 나온다(키 값 없음).
  - 실제 모델 TUI(`opengateway:z-ai/glm-5.3-flash-ultrafast`, Jev는 OpenRouter, 임시 저장소 `calc.py` 빼기 버그): 탐색 → 제출(리뷰 2회차) → 승인 화면 → "승인" → 수정 → 계획 재제출과 재승인 → `complete_plan` 테스트 통과, 계획 status done. 모델 비용 표시 $0.00, 캐시 읽기 약 663K 토큰. 승인 화면 pane 캡처(끝부분):

    ```
    │    형식 문제: 없음                                    │
    │    의견: 없음                                         │
    │    이 계획을 승인하시겠습니까? (required)              │
    │   › 승인                                              │
    │   • 거부                                              │
    │   • Other (type your answer)                          │
    │ ↑/↓ move • Enter to continue • Ctrl+J newline • Esc to cancel │
    ```
- 명세와 다른 점 (SPEC 본문에 반영함):
  - 탐색 서브에이전트(`subagents.py`, 등록, `_inject_fs_tools_into_subagents` 제외)를 M4에서 M3로 당겼다(사용자 승인). 없으면 `task(explorer)`의 "does not exist" 문자열이 탐색 결과로 통한다.
  - `precheck_denies`는 `classify_call`을 부르지 않는다. 승인 술어에서 프로젝트 루트를 알 수 없어서, 승인 전의 경로 쓰기 도구와 OTHER_MUTATING만 True다. `execute`, MCP, 승인 뒤 보호 경로는 dcode 승인 화면을 거친 뒤 게이트가 거부한다.
  - `_cg_counters`, 카운터 갱신, `aafter_agent`는 소비자인 `tracing.py`와 함께 M6로 미뤘다. `propose_rule`(M5), `propose_improvement`(M7)도 그대로 뒤에 둔다.
  - `build_plan_tools(options, backend)`. `submit_plan`, `complete_plan`은 비동기만 있다(리뷰어가 async만 있다).
  - idle에서 제출하면 새 plan id를 만든다(끝났거나 거부된 계획을 덮어쓰지 않는다). executing에서 다시 제출하면 review_round를 0으로 되돌린다.
  - 비대화에서 미결 질문이 여럿이면 사람 메시지 하나를 질문 전부의 답으로 한 줄에 적는다.
  - `question_j4`에 선택 인자 `request`. 승인 뒤 새 요청일 때 J4 state에 넣는다.
- 리뷰 뒤 수정 (2026-11-11):
  - idle에서 새 계획을 내면 review_round를 0부터 센다. 전에는 앞 계획의 회차를 물려받아 둘째 계획이 수정 회차를 건너뛰었다. 테스트 `test_second_plan_in_thread_gets_its_own_review_rounds`.
  - `submit_plan`이 리뷰 의견으로 draft를 돌려줄 때 status는 success다. error는 형식 문제와 거부에만 쓴다 (M6의 tool_errors가 정상 리뷰를 실패로 세지 않게).
  - J4가 통과시킨 대상 추가는 handler가 성공한 뒤에 한다. 계획을 다시 읽고 잠금 안에서 저장한다. 테스트 `test_failed_write_does_not_extend_targets`.
  - 게이트가 켜졌는데 사용자 서브에이전트 이름이 `explorer`이면 `ValueError`로 기동을 멈추고 이름 변경이나 `DEEPAGENTS_CODE_PLAN_GATE=0`을 안내한다 (`agent.py`).
  - 테스트 `approved()` 도우미가 승인 결과("승인됐다")를 단언하고, G6과 G16은 phase가 executing인지도 단언한다.
  - 프로젝트 루트는 `project_context`가 없으면 `config.cwd`로 물러선다 (`server_graph.py`). SPEC 3.10에 적었다.
- 확인한 문제(고치지 않음):
  - 승인 화면에서 frontmatter가 마크다운으로 한 문단에 붙어 보인다.
  - 리뷰어의 구조화 출력(`{ "comments": [], "questions": [] }`)이 TUI 대화에 한 줄 나온다. 리뷰어 모델 호출이 그래프 스트림 안에서 돌기 때문이다.
  - 승인 뒤 모델이 `execute`로 임시 저장소에 `.venv`를 만들고 pytest를 설치했다. J4가 통과시켰다.
- 확인된 열린 길 (M4에서 닫는다): 승인 뒤 게이트는 `task`를 `targets`와 J4 없이 통과시킨다. 사용자 선언형 서브에이전트와 `DEEPAGENTS_CODE_FORKED_SUBAGENTS=0`일 때의 `general-purpose`는 범위 밖 파일을 쓸 수 있다.
- 확인 못 한 것: 탐색 서브에이전트의 실제 도구 목록(M4 검사). `ty`는 돌리지 않았다.

## M4. 서브에이전트 — 완료 (2026-11-11)

- 추가: `gate.py`의 `SubagentWriteBlockMiddleware`, `tests/unit_tests/assistant/test_subagents.py`. `test_gate.py`에 G12와 승인 뒤 `task` 통과 테스트.
- 수정(업스트림): `agent.py`의 `_subagent_cli_middleware` 끝에 `plan_gate`가 있으면 `SubagentWriteBlockMiddleware`를 더한다. 사용자 선언형, `general-purpose`(fork와 fork 아님), 탐색 서브에이전트가 모두 이 목록을 쓴다.
- 먼저 확인한 [미확인] (fork 서브에이전트의 최종 도구 목록, SDK `create_agent`를 감싸 열거):
  - 고치기 전: fork `general-purpose`가 `PlanGateMiddleware`를 이름 그대로 물려받아 `submit_plan`, `request_plan_approval`, `complete_plan`이 도구 노드에 있었다. 리뷰어가 본 것과 같다. SPEC의 가정(같은 이름이면 사양 쪽이 대신한다, `SDK/graph.py:774`)과 어긋나지 않는다.
  - 고친 뒤: 그 자리가 `SubagentWriteBlockMiddleware`로 바뀌고 계획 도구가 빠졌다. `write_file, edit_file, delete, execute, task`는 도구 노드에 남는다(등록됨, 모델 목록에서 빠짐, 호출 거부).
- 검사:
  - `check.sh unit` 149 passed. G12, G13, 세 구성(fork `general-purpose`, `DEEPAGENTS_CODE_FORKED_SUBAGENTS=0`의 `general-purpose`, 사용자 선언형) 각각 실제 조립된 서브에이전트 그래프에 `write_file`을 돌려 파일이 생기지 않고 계획 도구가 없는지, 탐색 서브에이전트 도구가 `ls, read_file, glob, grep`뿐인지.
  - `check.sh lint` 통과.
  - `check.sh baseline` 71 failed, 10465 passed(10316 + assistant 149), 26 skipped, 16 errors, 2 warnings. 실패 목록이 기준선과 같다.
- 리뷰 뒤 수정 (2026-11-11):
  - 원격 비동기 서브에이전트 `start_async_task`, `update_async_task`를 단계와 관계없이 거부한다(`policy.classify_call` 규칙 1a, 사유 `async_subagent`, `precheck_denies`도 True). 전에는 승인 뒤 J4로 갔는데 J4는 도구 이름만 받고 원격에는 쓰기 차단이 없다. P3에 맞췄다. `cancel_async_task`는 J4에 남는다.
  - `SubagentWriteBlockMiddleware`를 허용 목록으로 바꿨다: `ls, read_file, glob, grep`, 읽기 전용 `execute`, `ask_user, compact_conversation, fetch_url, web_search, get_current_thread_id`, 읽기 전용 주석이 맞는 MCP 도구. 생성자 둘째 인자는 `read_only_tool_names`. 그 밖(확장 도구, fork의 `update_goal`, 읽기 전용이 아닌 MCP)은 거부된다.
  - 사용자 결정: 확장 도구 이름을 주 게이트에서 쓰기 계열로 본다. `create_cli_agent` 첫머리에서 `plan_gate.mcp_mutating_tool_names`에 더한다. 승인 전 거부, 승인 뒤 J4.
  - 테스트: 정책 규칙 1a(2), 승인 뒤 `start_async_task` 거부(가짜 도구 본문이 돌지 않음), 확장 도구 승인 전 거부(실제 `create_cli_agent`와 `ExtensionRegistry`), 주 에이전트 `task` → SDK 서브에이전트 → `write_file` 거부, 세 구성 테스트에 거부 문구 단언. 차단기와 확장 이름 연결을 일부러 끈 변이에서 새 테스트 5개가 실패하는 것을 확인했다.
  - 검사: `check.sh unit` 154 passed. `check.sh lint` 통과. `check.sh baseline` 71 failed, 10470 passed(10316 + assistant 154), 26 skipped, 16 errors, 2 warnings. 실패 목록이 기준선과 같다.
- 고친 M3 버그: 게이트 `_decide`의 `task` 분기가 값 둘을 돌려줘 explorer가 아닌 `task`는 승인 전후 모두 `ValueError`로 죽었다. G12가 찾았다.
- 명세와 다른 점 (SPEC 본문에 반영함):
  - 차단기는 거부 목록이 아니라 허용 목록이다(리뷰 뒤 수정). `execute`는 모델 목록에 남고 읽기 전용 명령만 통과한다(주 게이트와 같다).
  - 원격 비동기 서브에이전트 시작과 지시 변경은 승인 뒤에도 거부한다. 확장 도구는 주 게이트에서 쓰기 계열이다(사용자 결정).
- 확인한 문제(고치지 않음): 서브에이전트에는 phase가 없어 `precheck_denies`가 False다. 자동 승인이 아니면 서브에이전트의 쓰기 호출에 dcode 승인 화면이 먼저 뜨고 그 뒤에 거부된다. 쓰기 도구는 모델 목록에서 빠져 있어 모델이 이름을 지어낼 때만 생긴다.
- 확인 못 한 것: 실제 모델 TUI는 돌리지 않았다. 허용 목록 때문에 서브에이전트에서 읽기 전용 주석이 없는 MCP 도구와 확장 도구, fork의 `update_goal`이 막힌다. 그런 도구에 기대는 사용자 서브에이전트는 실제로 확인하지 않았다. `ty`는 돌리지 않았다.

## M5. Memory — 완료 (2026-11-11)

- 추가: `deepagents_code/assistant/memory.py`(`MemoryRecord`, `MemoryStore`, `MemoryInjectionMiddleware`), `tests/unit_tests/assistant/test_memory.py`.
- 수정(assistant): `decider.py`(`questions_j6`), `tools.py`(`propose_rule`, `complete_plan` 성공 시 `save_work_record`), `prompts.py`(`GATE_BASE` 8번: `propose_rule`).
- 수정(업스트림): `agent.py`(게이트가 있으면 `MemoryMiddleware`를 읽기 전용 프롬프트로, `if enable_memory:` 끝에 `MemoryInjectionMiddleware`), `app.py`(`/remember` → `_save_remembered_rule`, 확인 없이 `save_rule(source="user")`), `command_registry.py`(`/remember` 설명과 인자 표시, `_STATIC_SKILL_ALIASES`에서 `remember` 제거), `COMMANDS.md` 재생성, `_env_vars.py`·`agent.py` docstring 문구. `built_in_skills/remember/` 삭제.
- 먼저 확인할 [미확인]: M5에는 없다.
- 고친 업스트림 테스트 (9.4 "삭제한 remember 스킬을 직접 검사하는 테스트", README에 옮길 것):
  - `tests/unit_tests/smoke_tests/snapshots/system_prompt_interactive_local.md`, `system_prompt_headless_local.md`: 스킬 목록의 remember 두 줄씩 삭제. `--update-snapshots`로 다시 만든 diff가 정확히 그 4줄뿐임을 확인했다. 테스트 코드는 그대로다.
  - `tests/unit_tests/test_app.py::TestRememberRequiresMessages` 두 테스트: `/skill:remember`로 넘기는지 단언하던 것을 새 동작(규칙 파일이 `cwd=tmp_path` 아래 저장되는지, 빈 인자면 안내 문구와 저장 없음)으로 바꿨다. 이름은 그대로 두었다.
- 검사:
  - `check.sh unit` 167 passed (새 테스트 13). `test_memory.py`: 저장/읽기/색인/삭제, 한글 설명 이름 충돌 없음, 잘못된 기록 거부, 깨진 파일 건너뜀(경고), `questions_j6`, 그래프 테스트(`create_cli_agent(plan_gate=...)` 실제 조립): 작업 기록 둘 중 J6가 고른 하나만 시스템 프롬프트에 들어감(규칙은 항상, 색인은 전부), `propose_rule` → "저장" → 같은 thread의 다음 모델 호출에 규칙 본문이 들어감(첫 호출에는 없음), "버림"과 비대화는 저장 안 함, 기억 없으면 주입 없음, 20,000자 상한. `test_gate.py`: `complete_plan` 성공 시 작업 기록, 실패 시 없음.
  - `check.sh lint` 통과 (명령 목록 최신).
  - `check.sh baseline` 71 failed, 10483 passed(10316 + assistant 167), 26 skipped, 16 errors, 2 warnings. 실패 목록이 기준선과 같다.
  - 실제 Jev(OpenRouter) J6 한 번: 요청 "로그인 ... 에러 코드가 이상해요", 기록 둘 → `J6:work-...-fix-login` 0.84 통과, `J6:work-...-css-cleanup` 0.02. `J6:<이름>` 키를 받는다. 호출 비용 약 $0.00002.
- 명세와 다른 점 (SPEC 본문에 반영함):
  - 규칙 이름은 `rule-<영숫자 슬러그>-<설명 sha256 6자리>`(슬러그가 비면 `rule-<해시>`). 한글만 있는 설명이 모두 `rule-`가 되어 서로 덮어쓰는 것을 막는다. 같은 설명은 같은 이름이라 덮어쓰기는 유지.
  - `cg.memory.inject` 구간과 상한으로 뺀 사실의 기록은 `tracing.py`가 생기는 M6로 미뤘다.
  - 기억이 하나도 없으면(규칙이 없고 색인에 항목이 없으면) 주입하지 않는다. 동기 훅도 둔다.
  - `/remember`는 게이트가 꺼진 세션에서도 저장한다(주입은 안 됨). 설명은 첫 줄 200자에서 자른다. 루트는 `hooks.trust.project_root_for`.
- 확인한 문제(DECISIONS O3로 그대로 둠, (c)): fork `general-purpose`가 `MemoryInjectionMiddleware`를 물려받는다(조립된 스택 열거로 확인, fork 아님·사용자 선언형·explorer는 없음). SDK fork는 부모의 프롬프트 생성 미들웨어를 이름으로 물려받는 설계다. 영향: fork 작업마다 Jev J6 호출 1회(작업 기록이 있을 때), fork 프롬프트에 기억 주입. 쓰기는 `SubagentWriteBlockMiddleware`로 막혀 있다. 선택지: (a) 그대로 둔다(fork는 부모 프롬프트를 재현), (b) `_subagent_cli_middleware`에 같은 이름의 통과 미들웨어를 넣어 대체, (c) SPEC 5.3 문구를 fork 예외로 고친다. SPEC 5.3에 적었다.
- `propose_rule`의 description 검증(한 줄, 200자)은 사람이 "저장"을 고른 뒤 `save_rule`에서 한다. 잘못된 설명은 승인 뒤 저장 실패(오류 ToolMessage)가 된다.
- 확인 못 한 것: 실제 모델 TUI에서 `propose_rule` 질문 화면과 `/remember`는 돌리지 않았다(질문 화면은 M3의 `request_plan_approval`과 같은 ask_user 모양). `tui/widgets/history.py:198`의 `/remember` 주석이 낡았지만 `DC/tui/`라 두었다. `ty`는 돌리지 않았다.
- 리뷰 뒤 수정 (2026-11-11):
  - description은 `splitlines()`가 한 줄이어야 한다. 전에는 "\n"만 막아 "\r"이 저장된 뒤 색인에 줄을 지어냈다. 작업 기록 설명과 `/remember` 설명도 `splitlines()`로 첫 줄을 뗀다.
  - 주입 글의 `<project_memory`, `</project_memory`를 `&lt;`로 바꾼다(본문이 틀을 닫지 못하게).
  - J6: 계획이 진행 중이면(phase가 idle 아님, 계획 있음) 요청문을 "계획 요구사항 + 새 메시지"로 판정한다. 요구사항만 쓰는 것보다 새 메시지도 넣는 쪽이 작은 변경이라 둘 다 넣었다. SPEC 5.3에 적었다.
  - 같은 설명의 규칙: `propose_rule` 질문이 "기존 규칙 <이름>을 바꿀까요?"가 되고, `/remember`는 "덮어썼다"로 알린다. `MemoryStore.exists` 추가.
  - 상한을 틀 안 전체에 건다. 색인 5,000자 초과분은 오래된 줄부터 뺀다. 최종 20,000자 자르기.
  - 기억 폴더가 resolve 뒤 프로젝트 밖이면 쓰기를 `PermissionError`로 거부. `rebuild_index` 경합은 SPEC 14장 알려진 한계로 적었다.
  - `propose_rule`은 답을 strip해서 "저장"을 본다. MEMORY.md가 없고 규칙이 없어도 선택된 작업 기록은 주입한다. 폴더 경로는 `ProjectPaths.memory_dir`.
  - fork 상속은 그대로 둔다 (DECISIONS O3). SPEC 5.3에 예외로 적었다.
  - 테스트 9개 추가: "\r"·U+2028 설명 거부, 작업 기록 설명 첫 줄, 심볼릭 링크 거부, 틀 태그 무력화, 전체 상한과 최근 색인 유지, 색인 없을 때 선택 기록 유지, 계획 요구사항으로 J6·전송 실패·재개 가드(직접 `before_agent`), 동기 그래프(동기 `before_agent`, `wrap_model_call`, 동기 `propose_rule`, 덮어쓰기 질문, " 저장 " strip). 상한 테스트 여유를 600자로 넓혔다. 재개 가드와 태그 무력화를 일부러 끈 변이에서 각각 해당 테스트가 실패하는 것을 확인했다.
  - 검사: `check.sh unit` 176 passed. `check.sh lint` 통과. `check.sh baseline` 88 failed, 10475 passed, 26 skipped, 16 errors. 새 실패 17건이 모두 `test_main.py::TestStartupAutoUpdate`이고 기준선과 다르다 (SPEC 13장 2번, 아래 O5로 해결). 원인은 M3의 `_require_typesafe_key`: `os.environ`에 Jev 키가 없으면 종료 코드 1. 같은 테스트가 M5 변경을 stash한 HEAD(M4)에서도 따로 돌리면 2건 실패하고, `OPENROUTER_API_KEY=dummy`로는 37개 모두 통과한다. 같은 날 M5 첫 baseline은 기준선과 같았다. 테스트 순서나 `.env` 로드 여부에 따라 달라지는 기존 문제로 보이며 M5 변경 때문은 아니다.
  - 순서 의존의 원인: `.env`는 `config.py`의 부트스트랩(`_bootstrap_state`, 프로세스당 한 번)이 `os.environ`에 넣는데, `tests/unit_tests/conftest.py`의 autouse `_restore_os_environ`이 테스트마다 환경을 되돌린다. 그래서 워커에서 부트스트랩을 처음 일으킨 테스트만 저장소 `.env`의 키를 보고, 그 뒤 테스트는 키가 없다. xdist 배분에 따라 결과가 바뀐다.
  - O5 첫안(호출 위치를 `cli_main` 안에서 옮김)은 두 테스트(`test_yolo_acknowledgement_interrupt_aborts_before_tui`, `test_project_mcp_server_selection_cancel_aborts_before_tui`)를 고치지 못했다. 둘은 `_resolve_agent_arg` 뒤의 프롬프트에서 130을 기대한다.
  - O5 개정안 적용: `main.py`의 `_require_typesafe_key`와 호출을 지우고, `decider.require_jev_key`(`MissingJevKeyError(ValueError)`)를 `client/launch/server_manager.start_server_and_get_agent` 첫머리(`plan_gate`일 때, MCP 사전 검사 앞)에서 부른다. TUI와 `-n`이 모두 지나는 곳이고 시작 프롬프트 뒤, 서버와 그래프 전이다. 테스트 `assistant/test_launch_key.py` 5개(키 없음 → 오류이고 메시지에 키 값 없음, 키 둘 각각 통과, 기동 경로에서 키 없음 → 서버 전에 오류, 게이트 끔 → 건너뜀, 키 있음 → 통과). 업스트림 테스트와 `check.sh`는 고치지 않았다.
  - 실행 확인: 임시 프로필과 가짜 모델로 키 없이 `dcode -n` → 종료 코드 1, "Error: 계획 게이트에는 Jev 판정 키가 필요하다 ..."(키 값 없음). `OPENROUTER_API_KEY=dummy` → 종료 코드 0, Task completed.
  - `test_main.py` 전체: 키 둘을 지운 환경 200 passed, 가짜 키 200 passed.
  - 최종 검사: `check.sh unit` 182 passed. `check.sh lint` 통과. `check.sh baseline` 88 failed, 10481 passed, 16 errors. 새 실패 17건은 그대로 `TestStartupAutoUpdate`이지만 원인은 키가 아니다(`upgrade` 미호출, `_run_startup_auto_update`를 직접 부르는 테스트).
  - 해결(DECISIONS.md O6): 업스트림 테스트끼리의 상태 누수다. M0 원본 코드에서도 `test_auth_web_search_restart.py` 다음에 돌리면 같은 17건이 실패한다. `check.sh baseline`이 새 실패를 xdist 없이 따로 다시 돌리게 했다. 다시 돌린 결과: 순서 의존 17건, 따로 돌려도 실패하는 새 실패 0건, 통과.
  - 재현: `test_auth_web_search_restart.py` 전체(기준선의 16 errors, `Credentials`에 `tavily_api_key` 없음) 뒤에 같은 프로세스에서 `TestStartupAutoUpdate`를 돌리면 17건 실패. HEAD(M4, M5 변경 stash)에서도 같은 순서로 20건 실패(17 + 키 2 + 1). 두 파일 단독은 모두 통과. 업스트림 테스트끼리의 상태 누수이고, M5에서 테스트 수가 바뀌어 xdist가 두 파일을 같은 워커에 놓게 된 것으로 보인다. 누수 지점은 찾지 못했다.

## M6. 추적 — 완료 (2026-11-11)

- 추가: `deepagents_code/assistant/{tracing,runs}.py`, `tests/unit_tests/assistant/{test_tracing,test_runs}.py`.
- 수정(assistant): `gate.py`(`_cg_counters` 리듀서, `_cg_last_error`, 카운터 갱신을 `Command`로 싣기, `after_agent`/`aafter_agent` → `end_request`, `cg.gate.deny`·`cg.scope.extend`·`cg.explore`·비대화 `cg.plan.approval`), `tools.py`(`cg.plan.submit`, `cg.judge.mismatch`, `cg.human.question`, `cg.plan.approval`, `cg.test.run`, `cg.result`, 테스트 실패 `test_failures`), `decider.py`(`JevDecider.judge`의 `record_judgment`, M2에서 미룸), `reviewer.py`(`cg.plan.review`, M2에서 미룸), `memory.py`(`cg.memory.inject`와 상한으로 뺀 기억, M5에서 미룸), `options.py`(`COUNTERS_KEY`, `LAST_ERROR_KEY`).
- 수정(업스트림): `_env_vars.py`(`LANGFUSE_TRACING = "DEEPAGENTS_CODE_LANGFUSE_TRACING"`, SPEC 1.4는 M3라 했지만 없었다), `server_graph.py`(`tracing.init(workspace_env)`, `make_graph`의 `tracing.run_config(config)`), `config.py`(`build_stream_config`에 `langfuse_session_id`, `langfuse_tags`), `main.py`(LangSmith 기본 끄기, `--no-tracing`이 Langfuse도 끔).
- 먼저 확인한 [미확인] (가짜 모델 + 실제 Langfuse 스크립트, 그다음 실제 서버):
  - 같은 trace: 아니었다. 훅에서 연 구간이 각각 새 trace, `aafter_agent`의 `score_current_trace`는 "No active span". SPEC 대안(같은 trace id를 콜백과 구간 `trace_context`에)으로 한 trace에 모였다. 점수는 `create_score(trace_id=...)`.
  - 실제 서버에서 하나 더: 서버가 한 요청에 `make_graph`를 여러 번 부른다(`-n` 한 번에 같은 `turn_id`, 다른 `run_id` 둘). 부를 때마다 새 id면 요청 하나가 trace 19개로 쪼개졌다. id를 `create_trace_id(seed=f"{thread_id}:{turn_id}")`로 바꿔 trace 하나로 모았다(SPEC 6.2).
  - `mask` 범위: 일부만. LangGraph `model` 노드 입출력에 가짜 키 원문이 올라갔다(메시지 객체를 못 들여다봄). SPEC 대안 `mask_otel_spans`로 바꿔 전부 가려졌다.
  - 서버 환경의 키: 워크스페이스 `.env`의 가짜 `LANGFUSE_*`가 `workspace_env`에 들어간다. `init(workspace_env)`로 받는다. 실제 서버 서브프로세스 `os.environ`은 확인 안 함.
- Langfuse 조회 API: v1 `trace.list`, `trace.get`, `sessions.list`, `scores.get_many`가 이 계정에서 HTTP 410 `LEGACY_API_UNAVAILABLE_FOR_NEW_ORGANIZATION`(2026-09-16 뒤 만든 조직, Cloud 전체는 2026-11-16 종료). SPEC 13장으로 멈췄고 DECISIONS O7로 v2 `observations.get_many`(태그 `dcode-assistant` + 시작 시각 창, trace id로 묶음), `scores_v3.get_many_v3`, `get_trace_url`로 다시 짰다. `RunSummary.html_path` → `url`.
- 검사:
  - `check.sh unit` 206 passed (새 테스트 24: `test_tracing.py` 17, `test_runs.py` 7). 훅과 `to_thread` 안 구간이 실행 설정의 trace id를 쓰는지 실제 그래프로, 같은 요청은 같은 id, 거부 카운터와 연속 실패, 새 요청의 0 초기화, `complete_plan` 실패의 `test_failures`와 `cg.test.run` ERROR, `mask_otel_spans`, 리뷰어·Jev·Memory 구간, 꺼졌을 때 무동작, 클라이언트 예외 삼킴, `list_runs` 묶음과 쪽 넘김과 태그·세션 필터, `failures` 순서, `wait_for`, 화면 문자열.
  - `check.sh lint` 통과.
  - `check.sh baseline` 86 failed, 10507 passed(10316 + assistant 206 - 순서 의존 15), 26 skipped, 16 errors, 2 warnings. 새 실패 15건은 모두 `test_main.py::TestStartupAutoUpdate`이고 따로 돌리면 통과(O6 순서 의존). 따로 돌려도 실패하는 새 실패 0건.
  - 실제 요청 (임시 저장소, `opengateway:z-ai/glm-5.3-flash-ultrafast`, Jev는 OpenRouter, 프롬프트에 가짜 키 `AKIAIOSFODNN7EXAMPLE`, "계획 없이 execute로 rm -f scratch.txt"): 게이트가 거부했다. 40초 뒤 `RunsClient.list_runs(session_id=...)` 1건(trace 하나, 관측 35, 3.6초), `failures` = `WARNING cg.gate.deny: no_approved_plan`, 점수 8개(`cg.tool_calls 1`, `cg.tool_errors 1`, `cg.gate_denies 1`, `cg.llm_calls 2`, 나머지 0), 주소 있음. trace와 그 시간대 모든 관측에 가짜 키 원문 없음(`[SECRET_DETECTED]`로 올라감).
  - 그 전 실제 요청 1회(trace id 고치기 전, 탐색·계획 제출 2회·승인 요청)는 쪼개진 trace로 문제를 찾는 데 썼다.
- 명세와 다르게 한 점 (SPEC 본문에 반영함): `mask` 대신 `mask_otel_spans`. `callback_handler()` 대신 `run_config(config)`(콜백과 trace id를 함께, seed로 요청당 하나). `begin_request` 없음. `end_request`에 `review_rounds` 인자, 끝에 `flush`. 사건 기록용 `record()` 추가, `span()`은 현재 문맥을 쓰지 않는 `start_observation`. `cg.human.question`은 대화형에서 답할 때만, `cg.judge.mismatch`는 "J5 불필요인데 제출" 쪽만. `format_*`에서 `host` 인자 뺌. `_cg_last_error` 비공개 키 추가.
- 확인 못 한 것: 승인 화면에서 멈춘 실행에는 `after_agent`가 돌지 않아 점수가 없다. 재개한 실행이 끝날 때 요청 전체 값으로 붙는다. 재개 실행이 같은 `turn_id`를 받아 같은 trace에 붙는지는 대화형 승인 흐름으로 확인하지 않았다. 서브에이전트 안의 도구 호출은 카운터에 들어가지 않는다. 실제 서버 서브프로세스의 `os.environ`, TUI 실행은 확인 안 했다. `ty`는 돌리지 않았다. Plan의 `trace_ids`는 아직 채우지 않는다.

- 리뷰 뒤 수정 (2026-11-11):
  - `_cg_last_error`에 리듀서(나중 값)가 없어 한 메시지의 도구 호출이 둘 이상이면 `InvalidUpdateError`가 났다. 고쳤고 실제 그래프로 병렬 거부 둘, 병렬 허용 둘을 테스트한다(`FilesystemMiddleware`가 같은 경로 병렬 쓰기를 먼저 막아서 경로를 달리했다).
  - `end_request`의 `flush()`가 요청 끝을 수십 초 막을 수 있었다. 데몬 스레드로 비우고 최대 2초만 기다린다. 아예 안 기다리게 했더니 비대화 실제 요청에서 점수가 사라져(서버가 먼저 내려감) 2초 대기로 바꿨고, 다시 돌려 점수 8개가 올라간 것을 확인했다.
  - 워크스페이스별 설정: `init`을 `run_config(config, runtime.model_environment)` 안에서 그 워크스페이스 환경으로 부른다. 꺼짐 스위치를 켠 워크스페이스는 콜백도 구간도 보내지 않는다(구간은 trace id가 있는 실행에서만). 처음과 다른 키·주소면 경고하고 보내지 않는다. 서버 시작 경로의 `init` 호출은 뺐다.
  - O9: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`, `LANGFUSE_HOST`를 `_PROJECT_DOTENV_DENIED_ENV_KEYS`에 더했다. 사용자 `~/.deepagents/.env`와 셸은 그대로 된다(테스트). 실제 요청: 프로젝트 `.env`에 `LANGFUSE_BASE_URL=https://evil.invalid`를 둔 저장소에서도 원래 Langfuse로 갔다. 그래서 위의 "워크스페이스 `.env`의 키가 `workspace_env`에 들어간다"는 이제 막힌다.
  - `ask_user` 결과는 `Command`로 감싸지 않는다(`AskUserMiddleware` 거절 경고 유지, 카운트 안 함). `MemoryGuardMiddleware`가 결과를 바꾸면 증가분이 사라지는 것은 SPEC 14장에 적었다.
  - `runs.py`의 `langfuse` import를 `tracing.api_client`로 옮겼다(SPEC 9.4). `cg.memory.inject`의 주입 글 재계산은 추적 중일 때만 한다.
  - 테스트 추가: 병렬 호출, 동기 그래프(거부와 허용, `after_agent`), `llm_calls` 차이(동기·비동기 `after_agent`, 시작 때 `llm_base`), run id 대체 seed, 워크스페이스 꺼짐·다른 키, 실행 밖 구간 미전송, 프로젝트 `.env` 차단. 변이 6개(`_cg_last_error` 리듀서 제거, 동기 허용·거부 경로의 `_counted` 제거, 동기 `after_agent` 무동작, `llm_calls=0`, run id 대체 제거) 모두 테스트가 실패하는 것을 확인했다.
  - 문서: SPEC 6.2에 turn id가 없을 때 실행마다 trace가 갈리는 것, 재개가 같은 trace인지는 [미확인]으로 고쳤다.
  - 검사: `check.sh unit` 210 passed, `check.sh lint` 통과, `check.sh baseline` 84 failed, 10513 passed(10316 + 210 - 순서 의존 13), 26 skipped, 16 errors, 2 warnings. 새 실패 13건 모두 `TestStartupAutoUpdate`이고 따로 돌리면 통과(O6). 따로 돌려도 실패하는 새 실패 0건. 실제 요청 2회 더(재검증).

## M7. 슬래시 명령과 개선안 — 완료 (2026-11-11)

- 추가: `deepagents_code/assistant/improve.py`(`Threshold`, `THRESHOLDS`, `Observation`, `find_observations`, `ImprovementStore`, `improve_command`, `pending_observation_count`), `tests/unit_tests/assistant/test_improve.py`(23).
- 수정(assistant): `tools.py`(`propose_improvement`, 멈추지 않고 저장만), `runs.py`(`runs_command`, `latest_trace`).
- 수정(업스트림): `command_registry.py`(`/runs`, `/improve` 추가, QUEUED. `/trace` 설명), `app.py`(`/runs`·`/improve` 분기, `_handle_improve_command`, `/trace`를 Langfuse 키 유무로 나눔, `_handle_langfuse_trace_command`, `/trace` 출력 끝부분을 `_mount_trace_output`으로 뺌, 시작 알림 `_notify_improvement_observations`), `COMMANDS.md`(재생성).
- 먼저 확인한 [미확인] (SPEC 7.4): 처리기에서 `_handle_user_message`로 지시문을 보내는 경로. pilot 실험(가짜 에이전트, `_run_agent_task` 대체)으로 처리기 안에서 부르면 지시문이 worker까지 한 번 가고 `_agent_running`이 풀린다. 바쁠 때 넣은 명령과 뒤의 메시지도 큐에서 차례로 처리됐다. 명세 가정과 같다. `/skill:`이 이미 같은 길을 쓴다. 이 확인은 `test_improve_handler_sends_instruction_to_agent`로 남겼다.
- 검사:
  - `check.sh unit` 229 passed (새 19: 관찰 계산, 규칙·스킬 개선안의 생성·검증 기록·반영·거절, 검증 전 반영 거부, 잘못된 kind·name·심볼릭 링크 거부, `/improve` 하위 명령과 지시문, `/runs`, `/trace` 문자열, 실제 그래프에서 `propose_improvement`가 저장만 하는지, TUI 처리기 둘). 변이 둘(처리기의 `_handle_user_message` 호출 제거, `apply`의 상태 검사 제거)에 테스트 3건이 실패하는 것을 확인했다.
  - `generate_commands_catalog.py` 재생성 뒤 `check.sh lint` 통과.
  - `check.sh baseline` 80 failed, 10536 passed(10316 + assistant 229 - 순서 의존 9), 26 skipped, 16 errors, 2 warnings. 새 실패 9건은 모두 `test_main.py::TestStartupAutoUpdate`이고 따로 돌리면 통과(O6). 따로 돌려도 실패하는 새 실패 0건. 업스트림 테스트는 고치지 않았다(명령 수 고정 테스트도 깨지지 않았다).
  - 눈으로 확인 (D3에 따라 pane 캡처로 대신): 임시 저장소(`scratchpad/sample`, 견본 개선안 하나를 `ImprovementStore.create`로 넣음)에서 이 사본의 `.venv/bin/dcode -M opengateway:z-ai/glm-5.3-flash-ultrafast`. Langfuse 키는 셸에 없어서 실행할 때 설정 파일에서 읽어 환경으로만 넘겼다(값은 명령줄·파일에 남기지 않음). 모델 호출 없음, 비용 $0.00.

캡처(줄임: 목록 10건 중 3건, 지표 0인 줄 생략, 주소의 프로젝트 id 가림):

```
▎/ runs
 2026-11-11T10:44:32  정상  llm_calls=2 tool_calls=1 tool_errors=1 gate_denies=1  052eee99
 2026-11-11T10:41:56  정상  지표 없음  e0fac13d
 2026-11-11T10:21:52  정상  llm_calls=2 tool_calls=1 tool_errors=1 gate_denies=1  7115ebe3
 ... (10건)
▎/ runs 052eee99
 작업 052eee992d6dfbc380237797e6adf04e
 시각: 2026-11-11T10:44:32.037000+00:00
 소요: 4.9초
 실패 구간:
 - 2026-11-11T10:44:36 WARNING cg.gate.deny: no_approved_plan
 지표:
 - cg.gate_denies: 1
 - cg.llm_calls: 2
 - cg.tool_calls: 1
 - cg.tool_errors: 1
 - (나머지 0)
 주소: https://jp.cloud.langfuse.com/project/<…>/traces/052eee992d6dfbc380237797e6adf04e
▎/ improve list
 20261111-110413-use-uv  proposed  rule  테스트는 uv run pytest로 돌린다
▎/ improve
 최근 작업 20건에서 임계값을 넘은 관찰이 없습니다
▎/ trace
 이 대화의 기록이 아직 Langfuse에 없습니다. 반영까지 수십 초 걸릴 수 있으니 잠시 뒤 다시 시도하세요.
```

  - 키가 없는 pane에서 처음 띄웠을 때 `/runs`는 "Langfuse 키가 없어 기록이 없습니다"를 띄웠다.
- 명세와 다르게 한 점 (SPEC 6.5, 7.3, 7.4, 10장 M7에 반영함):
  - `/trace`: `_handle_trace_command`의 주소 부분을 바꾸지 않고 `_handle_command`에서 나눈다. Langfuse 키가 있으면 새 처리기, 없으면 업스트림 LangSmith 처리기 그대로. 업스트림 `TestTraceCommand` 16건이 LangSmith 주소와 문구를 단언하는데 9.4가 그 수정을 허락하지 않는다. 이 셸에는 Langfuse 키가 있어 `_handle_trace_command` 안에서 나누면 그 테스트들이 Langfuse 쪽으로 간다.
  - 시작 알림은 `on_mount`가 아니라 `run_textual_app`이 켠 앱의 첫 `ServerReady` 뒤에 한 번. 처음에 `ServerReady`마다 돌게 했더니 업스트림 `test_app.py` 2건이 실제 Langfuse 조회의 재시도 대기로 teardown 시간 초과가 났다.
  - 규칙 payload 파일은 `payload/rule-<name>.md`(기억 이름 규칙 `rule-…`). proposal.md frontmatter에 `description` 추가, 본문은 `## 근거`. `record_validation`은 `result["passed"]`로 상태를 정한다(M8 `judge` 결과에 이 키를 둔다). 반영된 개선안은 거절하지 않는다.
  - `propose_improvement`는 관찰을 받지 않아 `observations=()`로 저장한다. 근거는 `rationale`에.
  - `/improve`는 최근 20건의 `RunSummary.scores`로 관찰을 만든다(`signals()`를 다시 부르지 않는다). 예상 규모는 "모델 호출 약 1 + 2×관찰 수회"(어림). `/runs <앞부분>`은 최근 50건에서 찾는다.
  - `name`(영소문자·숫자·`-`, 64자)과 `description`(200자 한 줄) 검사, 개선안·스킬 폴더의 심볼릭 링크 탈출 거부.
- 리뷰 뒤 수정:
  - 시작 알림 스캔이 종료를 막았다. 키가 있을 때 연결 4초 뒤 Ctrl+D부터 셸 복귀까지 61초(키 없으면 0.24초). `asyncio.to_thread`의 실행기를 종료가 기다리는 동안 Langfuse HTTP 클라이언트가 재시도했다. 데몬 스레드로 바꾼 뒤 키가 있어도 0.3초.
  - `ImprovementStore.load`가 손으로 고친 proposal.md의 `kind`, `name`을 다시 검사한다(`name: ../../x`로 반영하면 스킬 복사가 밖으로 나갈 수 있었다). `/improve list`는 읽을 수 없는 개선안을 한 줄로 보이고 넘어간다.
  - 테스트 추가: 손으로 고친 proposal 거부, 시작 알림(한 번만, 0건과 실패는 조용히). 변이 둘(한 번만 플래그 제거, 실패 시 0 대신 7)에 알림 테스트 3건이 실패.
  - 다시 돌린 검사: `check.sh unit` 233 passed, `check.sh lint` 통과, `check.sh baseline` 77 failed, 10543 passed(10316 + 233 - 순서 의존 6), 26 skipped, 16 errors, 2 warnings. 새 실패 6건 모두 `TestStartupAutoUpdate`이고 따로 돌리면 통과(O6). 따로 돌려도 실패하는 새 실패 0건.
  - 사용자 프로필 `.env`의 Langfuse 키: 임시 `DEEPAGENTS_HOME`에 가짜 키를 두고 `config._ensure_bootstrap()` 뒤 `os.environ`에 들어가 `tracing.is_enabled`가 참인 것을 Python에서 확인했다. TUI로는 확인하지 않았다.
- 확인 못 한 것: 실제 모델로 `/improve` → `propose_improvement`(임계값을 넘은 관찰이 없어서 지시문이 나가지 않았다. 가짜 모델 그래프 테스트와 pilot 테스트로만 확인). 시작 알림이 실제로 뜨는 화면(관찰 0건이라 안 뜸). `/trace`가 브라우저를 여는 실제 동작(새 대화라 trace 없음). `/improve apply`의 실제 TUI 실행. `ty`.
- 참고: 전역 `dcode`(`~/.local/bin/dcode`)는 지금 `~/workspace/deepagents/libs/code`를 가리킨다. 이 사본은 `libs/code/.venv/bin/dcode`로 띄웠다. Langfuse 키는 셸이 아니라 `~/.claude/settings.json`의 `env`에서 온다(이 에이전트 프로세스에만 있다). 사용자의 보통 터미널에는 없다. 단위 테스트도 이 환경에서는 실제 Langfuse에 닿았다(`--disable-socket`인데 관측 조회가 성공한 뒤 점수 조회에서 재시도 중이었다). M8에서 주의.

## M8. 평가 실행기와 과제 — 완료 (2026-11-13)

- 추가: `deepagents_code/assistant/evalsuite/{__init__,suite,__main__}.py`(`Task`, `load_task(s)`, `prepare_repo`, `run_tests`, `verify_task`, `TrialResult`, `latest_plan`, `next_reply`, `read_signals`, `run_trial`, `run_suite`, `judge`, 명령 `verify`·`run`), 과제 셋 `evalsuite/tasks/{fix-median,add-slugify,trap-test-command}/`(task.toml, instruction.md, repo/, tests_target/, tests_regression/, solution.patch), `tasks/ruff.toml`, `tests/unit_tests/assistant/test_evalsuite.py`(20).
- 수정(assistant): `improve.py`에서 payload 반영 부분을 `install()`로 뺐다(`apply`와 실행기의 candidate가 함께 쓴다). 업스트림 파일은 고치지 않았다(그래서 baseline은 돌리지 않았다).
- 과제: 버그 수정(`median` 짝수 개), 함수 추가(`slugify`), 함정(`clamp` 상한 버그 + 저장소 `AGENTS.md`의 테스트 명령 `-p "*_test.py"`가 실제 파일 `test_*.py`와 맞지 않아 0개 실행, 종료 코드 5). 테스트는 `unittest`.
- 먼저 확인한 [미확인] (SPEC 7.5):
  - thread id: `-n`에는 기계용 출력이 없다(`--json`은 하위 명령용 `add_json_output_arg`). 비대화 헤더 `Thread: <uuid7>`에서 읽는다. 실제 출력에서 Rich가 `Thread:` 앞에서 줄을 바꿨다. 정규식이 공백·줄바꿈을 허용하고 `COLUMNS=400`을 준다. `--quiet`이면 헤더가 없어 쓰지 않는다.
  - 비대화 승인: 손으로 `dcode -n <fix-median 요청>` → 계획 `reviewed`(64초), `dcode -r <thread> -n "승인"` → `executing`, `edit_file`, `complete_plan` 통과, 계획 `done`, 작업 기록 저장(12초). 게이트 코드(`_answer_headless`)와 같다. 미결 질문이 남아 있으면 "승인"도 답으로 처리되므로 실행기는 계획 파일의 질문을 먼저 본다.
  - 같이 드러난 것: `-S` 없이는 셸이 꺼져 `complete_plan`이 테스트를 못 돈다(O13). 임시 저장소에서는 Jev 키를 못 찾았다(O15). 두 번째 요청의 점수는 끝나고 약 50초 뒤 조회됐다(O12).
- 검사:
  - `python -m deepagents_code.assistant.evalsuite verify`: 세 과제 모두 통과(1.3초). 시작 상태 회귀 통과, 목표 실패, 해법 적용 뒤 둘 다 통과.
  - `check.sh unit` 254 passed(새 21: `judge`의 A·B·C 갈래, 잡음 폭 안/밖, 반복 1회, 신호 빠짐, candidate 없음, 회귀 실패, 과제 읽기와 검사·문제 보고 둘, `next_reply` 상태별, 가짜 dcode 스크립트로 `run_trial`(승인 왕복과 채점과 신호 합, dcode 실패, 호출 상한, candidate 규칙 주입), `read_signals`가 일부만 보이면 포기, `main verify`, `main run`이 규모 출력과 `record_validation`, 검증 전이 아닌 개선안 거부). 테스트는 `RunsClient`를 가짜로 넣고 네트워크를 쓰지 않는다. 변이 6개(잡음 폭 제거, 질문 갈래 제거, 일부 점수 허용, 목표 통과 검사 제거, 반복 1회 갈래 제거, C가 판정에 안 들어감) 모두 테스트가 실패하는 것을 확인했다.
  - `check.sh lint` 통과(과제 코드 포함, cwd 검사 포함).
  - 실제 실행 `run --baseline-only --trials 1` (기본 모델 `opengateway:z-ai/glm-5.3-flash-ultrafast`, Jev OpenRouter, Langfuse 켬): 에이전트 실행 3회, dcode 호출 8회, 전체 702초. 세 과제 모두 통과(목표·회귀 테스트).

    | 과제 | 호출 | 시간 | 신호 (0 아닌 것) |
    |---|---|---|---|
    | add-slugify | 2 | 55초 | llm_calls 10, tool_calls 5, review_rounds 1 |
    | fix-median | 3 | 253초 | llm_calls 47, tool_calls 34, tool_errors 10, gate_denies 8, review_rounds 4(→2), repeat_failures 1 |
    | trap-test-command | 3 | 393초 | llm_calls 42, tool_calls 27, tool_errors 2, gate_denies 1, jev_denies 1, review_rounds 6(→2), test_failures 1 |

    시간에는 점수를 기다린 시간이 들어 있다. 이 실행 뒤 고친 것: `cg.review_rounds`는 요청마다의 증가분이 아니라 계획의 누적 회차라서 합하면 부풀려진다(위 4, 6). 지금은 최댓값을 쓴다(괄호 안 값). 비용: dcode 사용량 표의 비용 칸이 "—"(이 모델은 가격 정보가 없다)라 금액은 못 얻었다. 주 모델 요청 105회, 입력 약 2.78M, 출력 약 93K 토큰(Jev 호출은 따로 집계 못 함).
  - 실제 실행에서 본 것: fix-median은 리뷰어가 미결 질문을 남겨 실행기가 `answers`의 답을 보냈고, 에이전트가 다시 계획을 내 승인 대기 → "승인" → 완료(3회 왕복). 함정 과제에서 에이전트는 탐색 때 안내 명령의 패턴 불일치를 알아채고 `test_command`를 `-p "test_*.py"`로 고쳤다. 그래도 `test_failures` 1이었다. Langfuse `cg.test.run`으로 확인한 실패 명령은 `python3 -m unittest discover -s tests -p "*_test.py" && python3 -m unittest discover -s tests -p "test_*.py"`(안내 명령을 앞에 붙여 종료 코드 5). 다음 `complete_plan`은 통과. `repeat_failures`는 같은 도구 호출(같은 서명)이 연달아 실패할 때만 오른다(`gate.py`)라서 0이었다. fix-median의 `gate_denies` 8과 `tool_errors` 9는 모두 두 번째 호출(미결 질문에 일반 답을 보낸 직후, 계획 단계)의 `no_approved_plan`이었다. 일반 답이 "진행해 주세요"로 읽혀 에이전트가 승인 전에 쓰기를 시도했다. 실행기가 만든 잡음이 baseline 신호에 섞인다. 세 과제 모두 에이전트가 기존 회귀 테스트 파일에 단언을 더해 `tests_untouched`가 거짓이었다(채점은 원본으로 덮어써서 했다).
  - 작업 폴더와 로그: `/tmp/dcode-eval-4i5g5013/`(results.json, 과제별 `.log`).
- 명세와 다르게 한 점 (SPEC 7.5, 10장 M8에 `[M8]`로 반영함): thread id는 헤더에서. `-S recommended,python3`. 과제 테스트는 `unittest`, 회귀 테스트를 시작 저장소에 넣음, `answers` 키, `tasks/ruff.toml`. 승인 왕복은 계획 파일 상태로. 신호는 `wait_for(trace_id)` 대신 세션의 trace 점수 합(모두 보일 때까지 기다리고 일부면 비움). `TrialResult`에 `thread_id`, `calls`, `elapsed_s`. C가 "나빠짐"이면 떨어짐, C는 7.2 임계값 신호만, B는 baseline 전 반복 통과 과제. `--baseline-only`는 판정과 `record_validation`을 하지 않는다. `install()` 분리. 판단 기록 DECISIONS O11~O15.
- 리뷰 뒤 수정 (2026-11-13):
  - `run --improvement`가 `proposed`가 아닌 개선안을 거부한다(O16). 전에는 떨어진 개선안을 다시 돌리면 `validation.json`을 덮어썼다.
  - 채점이 에이전트가 둔 파일에 속을 수 있었다. 테스트 폴더에 `tests/__init__.py`(unittest 단언을 바꾸는 코드)를 두거나 작업 저장소에 `unittest/` 패키지를 두면 `python -m unittest`가 고치지 않은 저장소에서도 통과했다(둘 다 손으로 재현). `run_tests`는 테스트 폴더의 최상위 항목(`tests/`)을 지우고(링크면 링크만) 원본을 복사한 뒤, `python -I -B -c`로 표준 `unittest`를 먼저 읽고 작업 폴더를 경로에 넣어 돌린다. 테스트 실행 환경은 `PATH`만 넘긴다(에이전트가 쓴 코드에 키를 주지 않는다). 지운 탓에 에이전트가 테스트 폴더에 남긴 변경은 작업 폴더에 남지 않는다(`tests_untouched`는 그 전에 잰다). 테스트 `test_run_tests_ignores_agent_harness_files`.
  - dcode 시간 초과 때 `subprocess.run`이 클라이언트만 SIGKILL해서 `langgraph dev` 서버(새 세션으로 띄움)가 고아로 남을 수 있었다. `_run_dcode`가 SIGTERM을 먼저 보내고(dcode `main`이 모든 모드에서 `_install_termination_signal_handlers`로 이 신호를 `SystemExit`로 바꿔 서버 정리를 돈다) 60초 뒤 SIGKILL, 그 뒤 출력 읽기에도 60초 상한. stdout과 stderr는 한 흐름으로 합쳐 로그에 쓴다. 테스트 `test_run_trial_timeout_terminates`(가짜 dcode가 SIGTERM을 받았는지 단언. `terminate`를 `kill`로 바꾸면 실패).
  - 정책상 승인 뒤 프로젝트 밖 쓰기는 막히지 않고 J4로 간다(`policy.classify_call`의 `scope_check`, `python3` 셸도 같다). 에이전트가 패키지 안 `tasks/<과제>/tests_*`를 고치면 채점이 그 테스트로 돌았다. `run_trial`이 실행 전후로 과제의 두 테스트 폴더 파일 해시를 비교해 바뀌었으면 테스트를 돌리지 않고 실패로 기록한다(오류 "과제 폴더의 테스트가 실행 중에 바뀌었다"). 테스트 `test_run_trial_task_tests_tampered`.
  - 비밀 누출: 앞의 실제 실행 산출물(`/tmp/dcode-eval-4i5g5013/`의 results.json, 과제별 `.log`, 작업 저장소 전체)에서 환경과 저장소 `.env`의 키 값 5개를 `grep -rlF`로 찾았다. 0건. results.json에는 `TrialResult` 필드만 들어간다.
  - 변이 7개(테스트 폴더 지우기 제거, `-I` 제거, 잡음 폭 비교 `>`→`>=`, 호출 상한 `==`→`>`, thread id 재파싱, B의 "모두 통과" 조건 제거, 회귀 테스트를 시작 저장소에 넣지 않기) 모두 테스트가 실패하는 것을 확인했다.
  - 변이 2개 더(SIGTERM 대신 바로 kill, 과제 폴더 해시 비교 제거)도 테스트가 실패한다.
  - 검사: `check.sh unit` 257 passed(evalsuite 24). `check.sh lint` 통과. `evalsuite verify` 세 과제 통과. 함정 과제는 해법 적용 뒤에도 안내 명령이 종료 코드 5(PATH의 `python3` 3.12.3)인 것을 확인했다. 업스트림 파일은 고치지 않아 baseline은 돌리지 않았다.
  - 확인한 문제(고치지 않음): 에이전트가 고칠 코드(`calc/` 등) 자체가 import될 때 unittest를 바꾸는 것은 막을 수 없다(채점은 그 코드를 돌리는 일이다). `FilesystemBackend(virtual_mode=False)`라 에이전트가 절대 경로로 패키지 안 `tasks/`의 `tests_target`, `solution.patch`나 같은 작업 폴더의 다른 반복 로그를 읽을 수 있다(답 누출. 테스트 폴더를 고치면 위 해시 비교가 잡고, 그 밖의 과제 파일과 하네스 코드 쓰기는 승인 뒤 J4에만 기댄다). 함정은 `python3` 3.12 이상에서만 걸린다(3.11 이하는 0개 실행이 종료 코드 0). 개선안 payload가 망가져 `install`이 실패하면 run 전체가 예외로 끝나고 기록이 남지 않는다(이미 돈 baseline 비용은 버려진다). dcode가 오류(호출 상한, 시간 초과)로 끝나도 테스트가 통과하면 A는 통과로 본다(SPEC 7.5 A는 테스트만 본다).
- 확인 못 한 것: `run --improvement`의 실제 모델 실행(candidate 경로는 가짜 dcode로만). 반복 3회의 잡음 폭과 C 판정을 실제 신호로 본 적 없다. 함정 과제가 T8에 쓸 만큼 신호를 만드는지: 이번에는 `test_failures` 1로 7.2 임계값(per_run 2)에 못 미쳤다. 에이전트가 함정을 탐색에서 알아챘다. M9에서 T8 재현이 안 되면 함정을 더 숨기거나 임계값을 다시 봐야 한다(과제를 바꾸면 기록한다). Jev 호출 수 어림(실행당 5회)은 근거 없음. 평가 실행의 trace에도 `dcode-assistant` 태그가 붙고 `/improve`는 프로젝트 구분 없이 최근 20건을 읽는다. `--improvement` 한 번(18 실행, 호출 40회 이상)이 그 창을 채우므로 M9 T8에서 함정 과제 두 번 → `/improve` 순서가 평가 실행 뒤로 밀리지 않게 해야 한다. `ty` 안 돌림.
- 참고: 작업 중 `scripts/smoke_dcode.sh`(`DCODE` 덮어쓰기)와 `scripts/release.sh`가 다른 쪽에서 바뀌거나 생겼다. 이 마일스톤에서 만든 변경이 아니어서 손대지 않았다.

## F1–F3. dcode-a 사용 중 나온 문제 — 완료 (2026-11-13)

`dcode-a`(M7 `4235bca` 릴리스본)를 `~/workspace/deepagents-coco`에서 coco 배너 요청에 쓰다가 나온 문제(`FOLLOWUPS.md`). 원문 명령은 `~/.deepagents/.state/sessions.db` 체크포인트에서 꺼냈다(FOLLOWUPS의 `ls <경로> && head -60 <파일>`은 줄인 것이고 실제로는 가운데 `echo "---coco.sh---"`가 있었다. `ls && head`만이면 전부터 통과한다).

- 수정(assistant): `policy.py`(`is_read_only_shell` 끝에 `_read_only_chain`, `_cd_target`, `_READ_ONLY_COMMANDS`, `_HARMLESS_REDIRECT_RE`, `_SHELL_SPLIT_RE`), `gate.py`(`_DENY_TEXT["no_approved_plan"]` 안내 문장), 테스트 `test_policy.py`(`test_f1_read_only_chains_allowed` 7, `test_f1_write_capable_lookalikes_denied` 44), `test_gate.py`(`test_f1_observed_read_only_shell_runs_and_program_is_guided`, 가짜 모델 그래프). 업스트림 파일은 고치지 않았다(그래서 baseline은 돌리지 않았다).
- F1 판정: 넓혔다(O17). 조합 명령을 `&&`, `||`, `|`, `;`로 나눠 조각마다 업스트림 `is_shell_command_allowed`(허용 목록 + `echo`) 또는 `_fixed_repo_command_allowed`를 요구한다. 그 전에 스페이스로 떨어진 `2>&1`, `2>/dev/null` 토큰만 지우고(유니코드 공백은 bash가 나누지 않아 경계로 안 봄) 나머지는 업스트림 `contains_dangerous_patterns`가 거부한다(다른 `>`, `<`, 단독 `&`, `$`, 치환). 맨 앞의 `cd <절대 경로>`는 건너뛰되, 그 뒤의 git은 `cd` 대상이 프로젝트 루트 자체일 때만 받는다(하위 폴더의 중첩 저장소 설정이 git에서 프로그램을 돌릴 수 있다). 관찰한 네 읽기 명령은 통과, 같은 실행의 `cd mascot && python3 coco.sh …`는 계속 거부된다.
- F1 반복 거부: `repeat_failures`는 `summarize_call`(명령 포함) 서명이 같을 때만 올라 셸 변형 반복은 못 잡는다. `gate_denies`가 세고 SPEC 7.2 임계값(작업당 3, 작업 2개)이 자기 개선에서 잡는다. 실행 중 단계 올림은 SPEC에 없어 넣지 않았다. 대신 거부 문장에 "셸 명령을 바꿔 다시 시도하지 마라"와 읽기 도구, 탐색 서브에이전트를 넣었다.
- F2 원인: 거부 문구는 auto 분류기의 로컬 마감(`_ClassifierDeadlineExceededError`). 20초는 기본값 `AUTO_CLASSIFIER_TIMEOUT_SECONDS_DEFAULT`(설정 안 함), 분류기 모델은 주 모델 물려받기, 재시도 대기도 같은 20초 안. 순서: `AutoModeHITLMiddleware`가 주 모델 응답을 감싸는 `awrap_model_call`에서 먼저 분류하고, 게이트는 도구 실행 때 판단한다. 그래서 게이트가 거부할 호출도 분류기를 거친다. 시간 초과가 난 호출이 바로 게이트도 거부할 `python3` 호출이었다. 나머지 네 `execute`는 분류기가 허용한 뒤 게이트가 거부했다. 재현: 체크포인트에 남은 분류기 요청 다섯 개(성공한 것. 시간 초과 난 요청은 판정 뒤에만 상태에 저장돼 남지 않는다)를 같은 모델(`opengateway:z-ai/glm-5.3-flash-ultrafast`)로 세 번씩 0.7~4.9초, 짧은 요청 13번 1.4~6.3초. 시간 초과 난 `python3` 호출을 직전 분류기 기록과 앞선 호출 10개로 재구성한 요청은 여섯 번 3.5~7.9초(모두 거부 판정, 다른 요청보다 느림). 20초 초과는 재현 못 했다. 재구성이고 새로 만든 모델 객체라 실행 당시와 같지 않을 수 있다.
- F2 처리: 코드 변경 없음(O18). SPEC 14장에 순서와 설정(`DEEPAGENTS_CODE_AUTO_CLASSIFIER_TIMEOUT`, `[models].auto_classifier_timeout` 1~300초, `[models].auto_classifier`, `--auto-classifier-model`. 프로젝트 `.env`로는 못 정함)을 적었다. 게이트가 확실히 거부할 호출에서 분류기를 건너뛰는 업스트림 수정은 FOLLOWUPS에 남겼다.
- F3: 오케스트레이터가 처리했다. `scripts/release.sh`가 `~/.local/bin/dcode-a`를 링크 대신 `DEEPAGENTS_CODE_AUTO_UPDATE=0 exec <venv>/bin/dcode "$@"` 감싸기 스크립트로 쓴다(전의 링크를 먼저 지워 venv의 `dcode`를 덮어쓰지 않는다). 지금 설치(`4235bca`)에 적용했고 `is_auto_update_enabled()`가 그 환경에서 False, 없으면 True인 것을 확인했다. 이 작업에서는 `release.sh`와 `~/.local/bin`을 건드리지 않았다.
- 검사:
  - `check.sh unit` 309 passed(M8 257 + 새 52: 위 F1 테스트).
  - `check.sh lint` 통과.
  - 변이 7개 모두 테스트가 실패했다: 조각 검사 `all`→`any`(15건), 리다이렉트 경계 조건 제거(5건), 경계를 `\S`(유니코드 공백)로(3건), `cd` 뒤 git을 루트가 아니어도 허용(3건), `cd` 절대 경로 조건 제거(1건. 상대 경로 `tmp/…/root`는 `validate_path`가 `/`를 붙여 루트로 보이지만 bash에서는 하위 폴더다), `echo` 빼기(3건), 거부 문장에서 `read_file` 빼기(1건). 모두 되돌린 것을 diff로 확인했다.
- 명세와 다르게 한 점 (SPEC 3.4, 3.7, 14장에 `[F1]`, `[F2]`로 반영함): `is_read_only_shell` 4단계 추가. `no_approved_plan` 문장. 반복 거부와 auto 모드 순서, 분류기 설정은 14장.
- 리뷰 뒤 수정 (적대적 검토, 후보 약 60개를 `is_read_only_shell`과 이전 판정에 직접 넣어 봄):
  - 우회 1 (전부터 있던 것, `echo`로 넓어짐): 허용 이름으로 함수를 정의하면 첫 토큰 검사를 지난다. `cat () ( touch x ) && cat`, `ls () ( touch x ); ls`는 업스트림 `is_shell_command_allowed`만으로 True였고 dash(`/bin/sh`, 백엔드가 `shell=True`)에서 본문이 실행돼 파일이 생겼다. `echo () ( … ); echo`는 이번 변경으로 새로 통과했다. 수정: `policy._FUNC_DEF_RE`(`\(\s*\)`)가 있으면 맨 앞에서 거부.
  - 우회 2 (전부터 있던 것, 조합으로 넓어짐): `git diff *`는 glob이 `--output=pwned`라는 파일 이름을 옵션으로 펼쳐 파일을 쓴다(임시 저장소에서 확인). 업스트림 `_fixed_repo_command_allowed`가 True였고 `ls && git diff *`는 이번 변경으로 새로 통과했다. 수정: `policy._git_read_only`(glob 문자 `*?[`가 없을 때만 git 판정), 단독 명령과 조각 양쪽에 쓴다.
  - 막힌 것으로 확인(이전과 같음): `2>/dev/null>x`, `2>&1>x`, `2>/dev/nullx`, `1>&2`, `3>&1`, `>|`, `&>`, `2>&1&`, `|&`, 따옴표 안의 구분자, `\;`, 제어 문자(`\v`, `\f`, NUL), NBSP 경계, `$HOME`, `(rm x)`, `{ rm x; }`, `git -c`, `git -C`, `git log --output`, `--ext-diff`, `cd /tmp && git`, `cd 루트/.. && git`(`validate_path`가 `..`을 거부해 bash 논리 경로와 어긋날 일이 없다), `GIT_DIR=… git`. 통과하지만 무해: `ls ;; ls`, `ls (rm x)`(dash 문법 오류), `echo !!`(비대화형은 history 없음), `echo {a,b}`(dash는 중괄호 확장 없음).
  - 테스트: `test_f1_write_capable_lookalikes_denied`에 7개 추가(함수 정의 3, glob git 4). `check.sh unit` 316 passed(309 + 7), `check.sh lint` 통과.
  - 문서: SPEC 3.4 의사 코드 1), 3)과 검사 문단, DECISIONS O17, FOLLOWUPS(업스트림에 남은 같은 우회, `hostname <이름>`).
- 확인 못 한 것: 실제 모델이 새 거부 문장을 받고 읽기 도구로 옮겨 가는지(가짜 모델로만). 서브에이전트의 넓어진 `execute`를 실제로 돌려 보지 않았다(같은 함수라 단위 테스트로 갈음). F2의 20초 초과 원인(일시적 지연으로 추정). auto 모드에서 분류기가 시간 초과로 거부한 호출은 게이트의 안내 문장을 받지 못한다. `ty` 안 돌림.

## M9. 보정과 README — 다음

먼저 볼 것: `FOLLOWUPS.md`(F2의 남은 일: auto 분류기를 건너뛰는 업스트림 수정 검토. F4: 업스트림 읽기 전용 판정에 남은 우회). M8의 함정 과제가 T8용 신호를 만들지 못한 문제도 M8 절에 있다.
