# 진행 기록

명세는 `docs/SPEC.md` 10장. 기존 테스트 기준선은 `BASELINE.md`.

## M0. 작업 사본과 기준선 — 완료 (2026-11-11)

- 커밋 `679a464`(원본 사본), `1b81051`(환경과 기준선).
- 검사 통과: `dcode --version`이 `~/workspace/dcode-assistant/libs/code` editable 설치를 보여준다. `scripts/smoke_dcode.sh` 종료 코드 0. `BASELINE.md` 있음.
- langfuse 4.15.1 고정, `uv lock --check --no-sources` 통과. lock에서 빠진 줄은 `--no-sources`로 로컬 `../deepagents`, `../acp` 대신 PyPI 패키지를 쓴 결과다.
- 알려진 기준선 실패: 기본 조건 테스트 수집 실패(langsmith 경고), 경고 제외 시 71 failed / 16 errors, `ty`는 없는 `../deepagents` 경로로 실패.

## M1. 순수 모듈 — 완료 (2026-11-11, 커밋 전)

- 추가: `deepagents_code/assistant/{__init__,options,frontmatter,plan,policy}.py`, `tests/unit_tests/assistant/test_{frontmatter,plan,policy}.py`.
- 수정: `_paths.py`의 `ProjectPaths`에 `plans_dir`, `memory_dir`, `improvements_dir`.
- 검사: `tests/unit_tests/assistant` + `ProjectPaths`를 쓰는 기존 테스트(`test_agent`, `test_mcp_tools`, `test_mcp_login_service`) 554 passed. 새 파일과 `_paths.py`에 `ruff check`, `ruff format --diff` 통과, `check_process_cwd.py` 통과. 테스트는 기준선과 같이 langsmith 경고 하나를 `-W ignore`로 끄고 돌렸다.
- 명세와 다른 점:
  - `PlanGateOptions`는 `Decider`, `PlanReviewer`가 생기는 M2로 미뤘다. 지금 넣으면 없는 모듈을 import한다.
  - `options.py`에 `PROTECTED_DIRS`와 `Phase` 리터럴을 더했다. `policy`와 이후 `gate`가 같이 쓴다.
  - `normalize_tool_path(raw)`는 `project_root` 인자를 뺐다. 정규화에 쓰지 않는다.
  - `mentions_protected`는 보호 폴더 셋 외에 상위 `.deepagents` 자체(`rm -rf .deepagents`, `.deepagents/*`)도 잡는다. `is_protected`의 상위 폴더 규칙과 맞췄다.
  - 계획 본문의 알 수 없는 `##` 절은 버리지 않고 정해진 절 뒤에 둔다. 첫 `##` 앞의 글은 버린다.
- 확인 못 한 것: `ty`는 기준선부터 깨져 있어 돌리지 않았다.

## M2. 판정기와 리뷰어 — 다음
