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

## M5. Memory — 다음
