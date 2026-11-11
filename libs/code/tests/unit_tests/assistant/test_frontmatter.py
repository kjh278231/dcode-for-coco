"""frontmatter 읽기와 쓰기 테스트."""

from __future__ import annotations

import pytest

from deepagents_code.assistant.frontmatter import FrontmatterError, parse, render


def test_round_trip() -> None:
    meta = {"id": "a", "targets": ["x.py", "y.py"], "review_round": 2}
    body = "## 제목\n본문\n"
    assert parse(render(meta, body)) == (meta, body)


def test_round_trip_keeps_leading_blank_line_in_body() -> None:
    assert parse(render({"a": 1}, "\n본문")) == ({"a": 1}, "\n본문")


def test_korean_value() -> None:
    text = render({"요구사항": "로그인 고치기"}, "")
    assert "로그인 고치기" in text
    assert parse(text) == ({"요구사항": "로그인 고치기"}, "")


def test_missing_delimiter() -> None:
    with pytest.raises(FrontmatterError):
        parse("id: a\n\n본문")


def test_unclosed_delimiter() -> None:
    with pytest.raises(FrontmatterError):
        parse("---\nid: a\n본문")


def test_invalid_yaml() -> None:
    with pytest.raises(FrontmatterError):
        parse("---\nid: [a\n---\n본문")


def test_top_level_list() -> None:
    with pytest.raises(FrontmatterError):
        parse("---\n- a\n- b\n---\n본문")
