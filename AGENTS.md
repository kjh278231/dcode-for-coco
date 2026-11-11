# dcode-assistant

dcode(`libs/code/`) 위에 계획 게이트, Memory, 추적, 자기 개선을 얹는다. 명세는 `docs/SPEC.md`이고 정답은 이 문서다. 배경은 `docs/DESIGN.md`.

## 마일스톤 루프

먼저 `PROGRESS.md`에서 다음 마일스톤을 찾는다. 마일스톤 하나는 이 순서로 진행한다.

1. SPEC 10장의 그 마일스톤과, 거기 적힌 파일의 절을 읽는다. `DC/파일:줄`은 줄 번호가 밀렸을 수 있으니 심볼 이름으로 `grep -n` 한다.
2. "먼저 확인할 [미확인]"이 있으면 구현 전에 실행해서 확인한다. 명세와 다르면 SPEC 13장대로 멈추고 묻는다.
3. 구현한다. 새 모듈은 `libs/code/deepagents_code/assistant/`, 테스트는 `libs/code/tests/unit_tests/assistant/`.
4. 검사한다. 완료는 다음이 모두 통과한 상태다.
   - 그 마일스톤의 "검사" 항목 전부
   - `bash scripts/check.sh lint`
   - 업스트림 파일(`assistant/` 밖)을 고쳤으면 `bash scripts/check.sh baseline`
5. `PROGRESS.md`에 결과, 돌린 검사와 수치, 명세와 다르게 한 점을 적는다. 다르게 한 점은 SPEC 본문에도 반영한다.
6. 사용자에게 보고한다. 커밋은 요청받으면 `M<n>: <요약>` 하나로 한다.

## 검사 명령

`scripts/check.sh`의 사용법은 파일 머리에 있다. `make test`와 `make lint`는 이 사본에서 그대로 돌지 않는다 (`BASELINE.md`). `baseline`은 5분 걸리니 Herdr pane에서 돌린다.

## 코드 규칙

업스트림 규칙은 `libs/code/AGENTS.md`. 이 작업에 더해진 규칙은 SPEC 9.4절(기존 테스트를 다루는 법)과 9.5절(lint에서 걸리는 것).
