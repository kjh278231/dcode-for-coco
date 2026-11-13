#!/usr/bin/env bash
# 작업 사본 dcode가 끝까지 돌아가는지 점검한다. 모델 API를 부르지 않는다(비용 0).
#
# 사용법:
#   bash scripts/smoke_dcode.sh
#
# 하는 일
#   임시 폴더에 프로필과 작업 폴더를 만들고, dcode 저장소의 통합 테스트가 쓰는 가짜 모델
#   (deepagents_code._testing_models:DeterministicIntegrationChatModel, 받은 문장을 되돌려준다)을
#   config.toml에 등록한 뒤 `dcode -n` 을 한 번 실행한다.
#   이 한 번으로 CLI 진입 -> LangGraph 서버 기동 -> 에이전트 조립 -> 응답 -> 종료 전체가 지나간다.
#   (설정 방법은 deepagents/libs/code/tests/integration_tests/test_headless_resume.py 의 _CONFIG와 같다.)
#
# 참고: 처음 실행 때 dcode가 ripgrep을 임시 프로필에 내려받으므로 네트워크가 필요하다. 20초 안팎 걸린다.
# 사용자의 실제 프로필(~/.deepagents, ~/.deepagents-day09)과 HOME은 건드리지 않는다.
set -euo pipefail

DAY09="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DCODE="${DCODE:-$DAY09/libs/code/.venv/bin/dcode}"
if [[ ! -x "$DCODE" ]]; then
  echo "오류: 먼저 libs/code/.venv에 dcode를 설치하세요." >&2
  exit 2
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcode-assistant-smoke.XXXXXX")"
mkdir -p "$WORK/profile" "$WORK/home" "$WORK/project"
cat > "$WORK/profile/config.toml" <<'EOF'
[models]
default = "itest:fake"

[models.providers.itest]
class_path = "deepagents_code._testing_models:DeterministicIntegrationChatModel"
models = ["fake"]
EOF
git -C "$WORK/project" init -q

MESSAGE="hello from dcode assistant smoke test"
echo "점검 폴더: $WORK"
echo "dcode -n 실행 중 (가짜 모델, API 호출 없음)..."

# -n 모드는 표준 입력이 터미널이 아니면 입력을 끝까지 읽는다(main.py의 stdin 처리).
# 스크립트에서는 < /dev/null 로 닫아 주어야 멈추지 않는다.
set +e
# 가짜 모델 점검이라 계획 게이트와 Jev 키 검사를 끈다 (SPEC 3.10 끄기 스위치).
(cd "$WORK/project" && HOME="$WORK/home" DEEPAGENTS_HOME="$WORK/profile" DEEPAGENTS_CODE_PLAN_GATE=0 \
  "$DCODE" -n "$MESSAGE" --no-tracing --no-mcp < /dev/null > "$WORK/stdout.txt" 2> "$WORK/stderr.txt")
code=$?
set -e

if [[ $code -eq 0 ]] && grep -q "$MESSAGE" "$WORK/stdout.txt" && grep -q "Task completed" "$WORK/stdout.txt"; then
  echo "통과: 서버 기동부터 응답까지 끝났습니다 (종료 코드 0)."
  grep -E "Server ready|Task completed" "$WORK/stdout.txt"
  rm -rf "$WORK"
  exit 0
fi

echo "실패: 종료 코드 $code. 출력은 $WORK 에 남겨 두었습니다." >&2
tail -20 "$WORK/stderr.txt" >&2
exit 1
