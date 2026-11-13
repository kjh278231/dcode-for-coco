#!/usr/bin/env bash
# 커밋 시점의 libs/code를 editable이 아닌 별도 venv에 설치하고 ~/.local/bin/dcode-a로 링크한다.
# 작업 사본을 고쳐도 dcode-a는 바뀌지 않는다. 전역 dcode(업스트림 uv tool)는 건드리지 않는다.
#
# 사용법: bash scripts/release.sh [커밋, 기본 HEAD]
# 되돌리기: 이전 버전 폴더가 남아 있으니 ln -sfn <DEST>/<이전 sha>/bin/dcode ~/.local/bin/dcode-a
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

mkdir -p "$(dirname "$LINK")"
ln -sfn "$VENV/bin/dcode" "$LINK"
echo "dcode-a -> $SHA ($VENV)"
