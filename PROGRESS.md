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

## M3. 게이트와 계획 도구 — 다음
