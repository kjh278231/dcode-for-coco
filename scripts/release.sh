#!/usr/bin/env bash
# 커밋 시점의 libs/code를 editable이 아닌 별도 venv에 설치하고 ~/.local/bin/dcode-a로 실행하게 한다.
# 작업 사본을 고쳐도 dcode-a는 바뀌지 않는다. 전역 dcode(업스트림 uv tool)는 건드리지 않는다.
#
# 사용법: bash scripts/release.sh [커밋, 기본 HEAD]
# 되돌리기: bash scripts/release.sh <이전 커밋>
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${DCODE_RELEASE_DIR:-$HOME/.local/share/dcode-assistant-release}"
LINK="$HOME/.local/bin/dcode-a"
SHA="$(git -C "$REPO" rev-parse --short "${1:-HEAD}^{commit}")"
VENV="$DEST/$SHA"

SRC="$(mktemp -d)"
trap 'rm -rf "$SRC"' EXIT
git -C "$REPO" archive "$SHA" libs/code | tar -x -C "$SRC"

# venv는 절대 경로가 박히므로 커밋별 폴더에 바로 만든다. 실패하면 링크는 그대로다.
rm -rf "$VENV"
uv venv -q --python 3.14 "$VENV"
DEEPAGENTS_CODE_BUILD_COMMIT="$(git -C "$REPO" rev-parse "$SHA")" \
  uv pip install -q --no-config --no-sources --python "$VENV/bin/python" "$SRC/libs/code"

# 링크 대신 감싸기 스크립트. 자동 업데이트가 성공하면 고정한 릴리스본이 업스트림으로 바뀐다 (FOLLOWUPS F3).
# 예전 링크를 먼저 지운다. 링크 위에 쓰면 venv의 dcode를 덮어쓴다.
mkdir -p "$(dirname "$LINK")"
rm -f "$LINK"
printf '#!/bin/sh\nDEEPAGENTS_CODE_AUTO_UPDATE=0 exec "%s" "$@"\n' "$VENV/bin/dcode" > "$LINK"
chmod +x "$LINK"
echo "dcode-a -> $SHA ($VENV)"
