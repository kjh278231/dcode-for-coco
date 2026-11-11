# 판단 기록

M3~M9 진행 중 SPEC 13장에 걸린 일, 명세에 없는 선택을 사용자에게 묻지 않고 정한 기록이다. 사용자가 나중에 검토한다. 각 항목: 무엇을 봤나, 고른 것, 대안, 되돌리는 법.

2026-11-11부터 사용자 지시: "이제부터는 나한테 아무것도 묻지마. 판단을 기록해둬." 그 전 항목은 사용자가 직접 답했다.

## 사용자가 직접 정한 것 (참고)

- D1 (M3): `check_process_cwd.py` 허용 토큰 `99c1d085` → `86fa45ed`. 사용자 승인.
- D2 (M3): 탐색 서브에이전트를 M4에서 M3로 당김. 사용자 승인.
- D3: 마일스톤마다 `M<n>:` 커밋. M6에서 실제 Langfuse로 trace 전송 허용. 실모델 비용은 한도 없이 SPEC 규모, 합계만 보고. 사람 검사(M7 TUI, M9 사례 훑기, README 따라하기)는 에이전트가 pane 캡처로 대신하고 끝에 목록을 준다.
- D4 (M4): 메인 게이트에서 extension_registry 도구를 쓰기 도구로 취급(승인 전 거부, 승인 뒤 J4). 내장 도구 분류는 그대로.

## 오케스트레이터가 정한 것

- O1 (M4): 원격 비동기 서브에이전트 `start_async_task`, `update_async_task`를 모든 단계에서 거부(`policy.py` 규칙 1a). 근거: P3 "서브에이전트는 항상 읽기 전용", 원격 쪽에는 쓰기 차단을 걸 수 없고 J4는 도구 이름만 본다. 대안: 승인 뒤 J4에 맡기기(이전 동작). `cancel_async_task`는 J4 그대로. 되돌리기: 규칙 1a 삭제.
- O2 (M4): 서브에이전트 쓰기 차단을 금지 목록에서 허용 목록(`SUBAGENT_ALLOWED_TOOLS`: 읽기 4종, 읽기 전용 execute, ask_user, compact_conversation, fetch_url, web_search, get_current_thread_id, 읽기 전용 주석의 MCP)으로 바꿈. 근거: P3, 미분류 도구(확장 등) 통과 방지. 영향: 서브에이전트 안에서 주석 없는 MCP, 확장 도구, fork의 `update_goal`이 막힌다. 실제 사용자 서브에이전트에 미치는 영향은 확인 안 함. 대안: 금지 목록 유지.
- O3 (M5): fork `general-purpose`가 `MemoryInjectionMiddleware`를 상속하는 것을 그대로 두고 SPEC 5.3에 예외로 적음. 근거: SDK fork는 부모 프롬프트를 일부러 그대로 재구성한다. 빼면 fork 프롬프트가 부모와 달라진다. 비용은 fork 호출마다 J6 Jev 한 번(약 $0.00002). 쓰기는 M4 차단으로 막혀 있다. 대안: 같은 이름의 통과 미들웨어로 덮기(SPEC 5.3 원문대로).
- O4 (M5): 9.4 "삭제한 remember 스킬을 직접 검사하는 테스트"에 `smoke_tests/snapshots/system_prompt_{interactive,headless}_local.md` 스냅숏 재생성을 포함시킴. diff는 remember 스킬 두 줄뿐이고 테스트 코드는 그대로. `test_app.py::TestRememberRequiresMessages` 두 테스트는 이름 유지, 새 `/remember` 동작(바로 저장, 빈 입력 안내)을 단언하도록 바꿈. README의 고친 테스트 목록에 들어간다.
- O5 (M5, M3 코드): baseline에서 `test_main.py::TestStartupAutoUpdate` 17건이 새로 실패(SPEC 13.2). 원인은 M3의 `_require_typesafe_key`가 시작 시 자동 업데이트보다 먼저 `sys.exit(1)` 하는 것, 키가 `os.environ`에 있는지가 테스트 순서에 따라 달라짐. 고른 것: 키 검사를 대화형에서는 자동 업데이트 뒤, 세션 시작 앞으로 옮김(업스트림 테스트와 check.sh는 그대로). 대안: check.sh에서 게이트 끄기(하네스가 문제를 가림), 업스트림 테스트에 `PLAN_GATE=0` 추가(9.4 밖).
  - 수정: 옮겨도 `--yolo` 확인, MCP 서버 선택 취소 테스트 2건이 키 검사에 먼저 걸렸다. 그래서 키 검사를 두 모드가 같이 쓰는 서버 시작 경로(대화형 질문들 뒤, 그래프 생성 전) 한 곳으로 옮겼다. 키 없을 때의 오류가 `--yolo` 확인 같은 질문 뒤에 나온다. 순서 의존 원인: `config.py`가 `.env`를 프로세스당 한 번 `os.environ`에 넣고, conftest의 `_restore_os_environ`가 테스트마다 되돌려서 워커의 첫 테스트만 키를 본다.
- O6 (M5): 키 검사를 옮긴 뒤에도 baseline에 `TestStartupAutoUpdate` 17건이 남았다. 원인은 업스트림 테스트끼리의 상태 누수다. `test_auth_web_search_restart.py` 뒤에 같은 프로세스에서 돌면 `upgrade`가 await되지 않는다. 원본 M0 코드(`1b81051`)에서도 같은 순서로 17 failed가 재현된다. 새는 지점은 찾지 못했다. 고른 것: `scripts/check.sh baseline`이 기준선에 없는 새 실패를 xdist 없이 따로 다시 돌린다. 모두 통과하면 "순서 의존"으로 따로 보고하고 실패로 세지 않는다. `baseline_failures.txt`와 업스트림 코드·테스트는 그대로다. 대안: 업스트림 누수 수정(업스트림 변경), `--dist loadfile`(배치가 여전히 바뀔 수 있음), 17건을 목록에 추가(규칙상 금지). 위험: 순서 의존으로 숨은 진짜 회귀를 놓칠 수 있다. 따로 돌려도 실패하는 회귀는 여전히 잡는다.
