"""YAML frontmatter가 붙은 마크다운을 읽고 쓴다."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Mapping

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)\Z", re.DOTALL)


class FrontmatterError(ValueError):
    """frontmatter 형식 오류."""


def parse(text: str) -> tuple[dict[str, Any], str]:
    """마크다운 문자열을 frontmatter 사전과 본문으로 나눈다.

    Args:
        text: `---`로 시작하는 마크다운 문자열.

    Returns:
        (frontmatter 사전, 본문). 본문 앞의 빈 줄 하나는 지운다.

    Raises:
        FrontmatterError: `---`로 시작하지 않거나, YAML이 잘못됐거나,
            최상위가 사전이 아닐 때.
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        msg = "frontmatter가 없다. 파일은 '---' 줄로 시작하고 닫아야 한다."
        raise FrontmatterError(msg)
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        msg = f"frontmatter YAML이 잘못됐다: {exc}"
        raise FrontmatterError(msg) from exc
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        msg = f"frontmatter 최상위는 사전이어야 한다: {type(meta).__name__}"
        raise FrontmatterError(msg)
    body = match.group(2)
    body = body.removeprefix("\n")
    return meta, body


def render(meta: Mapping[str, Any], body: str) -> str:
    """Frontmatter 사전과 본문을 마크다운 문자열로 만든다.

    `parse(render(m, b)) == (m, b)`가 성립한다.

    Args:
        meta: frontmatter 값.
        body: 본문.

    Returns:
        `---`로 감싼 YAML과 빈 줄 하나, 본문을 이은 문자열.
    """
    dumped = yaml.safe_dump(dict(meta), sort_keys=False, allow_unicode=True)
    return f"---\n{dumped}---\n\n{body}"
