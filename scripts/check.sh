#!/usr/bin/env bash
# 마일스톤 검사를 작업 사본 가상환경으로 돌린다. `make test`, `make lint`는
# 이 사본에 없는 로컬 source를 uv run으로 찾아서 그대로는 돌지 않는다 (BASELINE.md).
#
# 사용법:
#   bash scripts/check.sh unit [pytest 인자...]   기본 대상 tests/unit_tests/assistant
#   bash scripts/check.sh lint                     libs/code 전체 ruff, 명령 목록, cwd 검사
#   bash scripts/check.sh baseline                 단위 테스트 전체(약 5분), 기준선과 실패 목록 비교
#   bash scripts/check.sh smoke                    가짜 모델로 dcode -n 한 번 (scripts/smoke_dcode.sh)
#   bash scripts/check.sh all                      lint, unit, smoke 순서
set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
REPO="$(dirname "$(dirname "$SELF")")"
CODE="$REPO/libs/code"
VENV="$CODE/.venv/bin"
BASELINE_LIST="$REPO/scripts/baseline_failures.txt"
RUFF_VERSION="0.16."
# 기준선과 같은 조건. langsmith가 import 시점에 내는 사용 중단 경고 하나만 끈다.
PYTEST_FLAGS=(
  --benchmark-disable --disable-socket --allow-unix-socket -p no:cacheprovider
  -W "ignore:'asyncio.iscoroutinefunction' is deprecated:DeprecationWarning"
)

[[ -x "$VENV/pytest" ]] || { echo "오류: $CODE/.venv가 없다. BASELINE.md의 설치 명령을 먼저 실행한다." >&2; exit 2; }
cd "$CODE"

run_unit() {
  if [[ $# -eq 0 ]]; then set -- tests/unit_tests/assistant; fi
  "$VENV/pytest" -q "${PYTEST_FLAGS[@]}" "$@"
}

run_lint() {
  local version
  version="$("$VENV/ruff" --version | awk '{print $2}')"
  if [[ "$version" != "$RUFF_VERSION"* ]]; then
    echo "오류: ruff $version. 기준선은 lock의 ${RUFF_VERSION}x에서 통과했다. 다른 버전은 가짜 실패를 낸다." >&2
    return 2
  fi
  "$VENV/ruff" check .
  "$VENV/ruff" format --diff .
  "$VENV/python" scripts/generate_commands_catalog.py --check
  "$VENV/python" scripts/check_process_cwd.py deepagents_code
  echo "lint 통과. ty는 기준선부터 깨져 있어 돌리지 않는다."
}

run_baseline() {
  local log="${TMPDIR:-/tmp}/dcode-check-baseline.log"
  local code=0
  echo "단위 테스트 전체 실행 중. 로그: $log"
  "$VENV/pytest" -n 4 -rfE "${PYTEST_FLAGS[@]}" tests/unit_tests/ >"$log" 2>&1 || code=$?

  local summary
  summary="$(grep -E '^=+ .*[0-9]+ (passed|failed).* in [0-9.]+s' "$log" | tail -1 || true)"
  # 종료 코드 0과 1만 "테스트가 끝까지 돌았다"는 뜻이다. 나머지는 수집 오류, 중단, 내부 오류.
  if [[ $code -gt 1 || -z "$summary" ]]; then
    echo "실패: pytest가 끝까지 돌지 않았다 (종료 코드 $code). 로그 끝:" >&2
    tail -30 "$log" >&2
    return 1
  fi
  echo "요약: $summary"
  echo "기준선: 71 failed, 10316 passed, 26 skipped, 16 errors"

  local current
  current="$(grep -E '^(FAILED|ERROR) tests/' "$log" | sed -E 's/^(FAILED|ERROR) //; s/ - .*$//' | sort -u)"
  local new fixed
  new="$(comm -13 "$BASELINE_LIST" <(printf '%s\n' "$current" | sed '/^$/d'))"
  fixed="$(comm -23 "$BASELINE_LIST" <(printf '%s\n' "$current" | sed '/^$/d'))"
  if [[ -n "$fixed" ]]; then
    echo "기준선에서 실패했지만 이번엔 통과 ($(wc -l <<<"$fixed")건):"
    sed 's/^/  /' <<<"$fixed"
  fi
  if [[ -n "$new" ]]; then
    echo "새 실패 ($(wc -l <<<"$new")건). docs/SPEC.md 9.4절과 13장을 따른다:" >&2
    sed 's/^/  /' <<<"$new" >&2
    return 1
  fi
  echo "통과: 기준선에 없는 실패가 없다."
}

case "${1:-}" in
  unit) shift; run_unit "$@" ;;
  lint) run_lint ;;
  baseline) run_baseline ;;
  smoke) bash "$REPO/scripts/smoke_dcode.sh" ;;
  all) run_lint && run_unit && bash "$REPO/scripts/smoke_dcode.sh" ;;
  *) sed -n "2,10p" "$SELF" >&2; exit 2 ;;
esac
