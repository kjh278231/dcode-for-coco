"""Unit tests for the welcome banner widget."""

from typing import TYPE_CHECKING
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.color import Color as TColor
from textual.content import Content
from textual.style import Style as TStyle

from deepagents_code import clipboard as clipboard_module
from deepagents_code._env_vars import (
    DEBUG,
    EXPERIMENTAL,
    SPLASH_SHOW_CWD,
    SPLASH_SHOW_MODEL,
)
from deepagents_code._version import __version__
from deepagents_code.config import get_glyphs
from deepagents_code.tui.widgets import welcome as welcome_module
from deepagents_code.tui.widgets.welcome import WelcomeBanner, _local_tag_style

if TYPE_CHECKING:
    import pytest

_EDITABLE = "deepagents_code.tui.widgets.welcome._is_editable_install"
_PROJECT_NAME = "deepagents_code.tui.widgets.welcome.get_langsmith_project_name"
_REPLICA_PROJECT = "deepagents_code.tui.widgets.welcome.get_langsmith_replica_project"
_FETCH_URL = "deepagents_code.tui.widgets.welcome.fetch_langsmith_project_url"
_DEBUG_STYLE = "deepagents_code.tui.widgets.welcome._debug_tag_style"
_EXPERIMENTAL_STYLE = "deepagents_code.tui.widgets.welcome._experimental_tag_style"
_LOCAL_STYLE = "deepagents_code.tui.widgets.welcome._local_tag_style"


def _raw_style_covering(content: Content, needle: str) -> str | TStyle:
    """Return the style of the single span whose text contains `needle`.

    The style may be a `TStyle` (built from a themed style) or a raw `str` style
    string (used under the ANSI theme branch, which `Content.assemble` preserves
    verbatim — see `test_debug_tag_uses_ansi_markup_under_ansi_theme`). Use
    `_style_covering` when the style must be a `TStyle`. Indexes the public
    `content.plain` and reads the public `Span.style` field; update if Textual's
    span model changes.

    Args:
        content: Assembled banner content to inspect.
        needle: Substring identifying the span whose style to return.

    Returns:
        The style of the one span covering `needle`.
    """
    spans = [s for s in content.spans if needle in content.plain[s.start : s.end]]
    assert len(spans) == 1, f"expected exactly one span covering {needle!r}"
    return spans[0].style


def _style_covering(content: Content, needle: str) -> TStyle:
    """Return the `TStyle` of the single span whose text contains `needle`.

    Only usable for spans whose style resolves to a `TStyle` (i.e. built from a
    themed `TStyle`, not a raw `str` style string as used under the ANSI theme
    branch, which `Content.assemble` preserves as a raw `str` — see
    `test_debug_tag_uses_ansi_markup_under_ansi_theme`).

    Args:
        content: Assembled banner content to inspect.
        needle: Substring identifying the span whose style to return.

    Returns:
        The `TStyle` of the one span covering `needle`.
    """
    style = _raw_style_covering(content, needle)
    assert isinstance(style, TStyle)
    return style


def _last_style_covering(content: Content, needle: str) -> TStyle:
    """Return the `TStyle` of the last span whose text contains `needle`.

    Board rows can share needle text with other board rows (e.g. the ASCII
    body's `#######` also appears in the solid row), so callers pick the
    intended occurrence by position instead of assuming uniqueness.

    Args:
        content: Assembled banner content to inspect.
        needle: Substring identifying the span whose style to return.

    Returns:
        The `TStyle` of the last span covering `needle`.
    """
    spans = [s for s in content.spans if needle in content.plain[s.start : s.end]]
    assert spans, f"expected a span covering {needle!r}"
    style = spans[-1].style
    assert isinstance(style, TStyle)
    return style


def _make_banner(
    *,
    model_provider: str = "anthropic",
    model_name: str = "claude-opus-4-8",
    cwd: str | None = "/work/project",
    thread_id: str | None = None,
    mcp_tool_count: int = 0,
    mcp_unauthenticated: int = 0,
    mcp_errored: int = 0,
    mcp_awaiting_reconnect: int = 0,
    project_name: str | None = None,
    replica_project: str | None = None,
    project_urls: dict[str, str] | None = None,
    show_model: bool = True,
    show_cwd: bool = False,
    env: dict[str, str] | None = None,
) -> WelcomeBanner:
    """Create a `WelcomeBanner` with a controlled environment.

    Args:
        model_provider: Model provider to display.
        model_name: Model name to display.
        cwd: Working directory to display (only shown when `show_cwd`).
        thread_id: Thread ID to display (only shown in debug mode).
        mcp_tool_count: MCP tool count to display.
        mcp_unauthenticated: Number of MCP servers awaiting login.
        mcp_errored: Number of MCP servers that failed to load.
        mcp_awaiting_reconnect: Number of MCP servers awaiting reconnect.
        project_name: LangSmith project name to inject (or `None`).
        replica_project: Replica LangSmith project name to inject (or `None`).
        project_urls: LangSmith project URLs keyed by project name.
        show_model: Set `SPLASH_SHOW_MODEL` so the model row renders. Defaults to
            `True` so model tests exercise the row; the real default is off.
        show_cwd: Set `SPLASH_SHOW_CWD` so the directory row renders.
        env: Additional environment variables to set while constructing.

    Returns:
        A `WelcomeBanner` instance ready for testing.
    """
    resolved_env: dict[str, str] = {}
    if show_model:
        resolved_env[SPLASH_SHOW_MODEL] = "1"
    if show_cwd:
        resolved_env[SPLASH_SHOW_CWD] = "1"
    if env:
        resolved_env.update(env)
    with (
        patch(_PROJECT_NAME, return_value=project_name),
        patch(_REPLICA_PROJECT, return_value=replica_project),
        patch.dict("os.environ", resolved_env, clear=True),
    ):
        widget = WelcomeBanner(
            model_provider=model_provider,
            model_name=model_name,
            cwd=cwd,
            thread_id=thread_id,
            mcp_tool_count=mcp_tool_count,
            mcp_unauthenticated=mcp_unauthenticated,
            mcp_errored=mcp_errored,
            mcp_awaiting_reconnect=mcp_awaiting_reconnect,
        )
        if project_urls:
            widget._project_urls = project_urls
        return widget


class TestHomePrefixed:
    """Tests for the `_home_prefixed` helper."""


class TestLangsmithLinkHelpers:
    """Tests for the LangSmith link helper functions."""


class TestLocalTagStyle:
    """Tests for the editable-install `(local)` tag style."""

    def test_ansi_uses_bold_markup(self) -> None:
        """Under ANSI themes the tag stays visible via bold terminal text."""
        from deepagents_code.theme import DARK_COLORS

        assert _local_tag_style(ansi=True, colors=DARK_COLORS) == "bold"

    def test_non_ansi_uses_themed_color(self) -> None:
        """Non-ANSI themes color the tag with the theme's tool color."""
        from textual.color import Color as TColor

        from deepagents_code.theme import DARK_COLORS

        style = _local_tag_style(ansi=False, colors=DARK_COLORS)
        assert isinstance(style, TStyle)
        assert style.bold is True
        assert style.foreground == TColor.parse(DARK_COLORS.tool)


class TestDebugTagStyle:
    """Tests for the `(debug enabled)` tag style."""


class TestExperimentalTagStyle:
    """Tests for the `(experimental)` tag style."""


class TestTitle:
    """Tests for the banner title line."""

    def test_no_debug_tag_when_env_falsy(self) -> None:
        """A present-but-falsy `DEEPAGENTS_CODE_DEBUG` shows no `(debug enabled)` tag.

        Locks the truthy gate (`is_env_truthy`) against a regression to a bare
        presence check (`DEBUG in os.environ`), which every other test would pass.
        """
        with patch(_EDITABLE, return_value=False):
            plain = _make_banner(env={DEBUG: "0"})._build_banner().plain
        assert "(debug enabled)" not in plain

    def test_version_debug_local_render_in_order(self) -> None:
        """Version, `(debug enabled)`, and `(local)` render in that fixed order.

        The pairwise ordering assertions each pin only two of the three segments,
        and under different editable states; this locks all three in one banner.
        """
        with patch(_EDITABLE, return_value=True):
            plain = _make_banner(env={DEBUG: "1"})._build_banner().plain
        assert (
            plain.index(f"v{__version__}")
            < plain.index("(debug enabled)")
            < plain.index("(local)")
        )

    def test_no_experimental_tag_when_env_falsy(self) -> None:
        """A present-but-falsy `DEEPAGENTS_CODE_EXPERIMENTAL` shows no tag.

        Locks the truthy gate (`is_env_truthy`) against a regression to a bare
        presence check (`EXPERIMENTAL in os.environ`), which every other test
        would pass.
        """
        with patch(_EDITABLE, return_value=False):
            plain = _make_banner(env={EXPERIMENTAL: "0"})._build_banner().plain
        assert "(experimental)" not in plain

    def test_title_tags_carry_their_own_styles(self) -> None:
        """Each title tag's span carries its own style helper's output.

        Guards against wiring regressions where a tag renders with the wrong
        helper's style or the style lands on the wrong segment; the plain-text
        assertions above cannot catch either.
        """
        from textual.color import Color as TColor

        debug_style = TStyle(foreground=TColor.parse("#010203"), bold=True)
        local_style = TStyle(foreground=TColor.parse("#040506"), bold=True)
        with (
            patch(_EDITABLE, return_value=True),
            patch(_DEBUG_STYLE, return_value=debug_style),
            patch(_LOCAL_STYLE, return_value=local_style),
        ):
            content = _make_banner(env={DEBUG: "1"})._build_banner()
        assert _style_covering(content, "(debug enabled)").foreground == TColor.parse(
            "#010203"
        )
        assert _style_covering(content, "(local)").foreground == TColor.parse("#040506")


class TestModelLine:
    """Tests for the model row."""


class TestDirectoryLine:
    """Tests for the opt-in directory row (`SPLASH_SHOW_CWD`)."""


class TestTracingLine:
    """Tests for the LangSmith tracing project row."""


class TestReplicaTracingLine:
    """Tests for the LangSmith replica tracing project row."""


class TestThreadLine:
    """Tests for the thread ID row (shown only in debug mode)."""

    def test_langsmith_link_appended_once_project_url_resolves(self) -> None:
        """A resolved project URL adds a thread trace link to the row."""
        content = _make_banner(
            thread_id="abc-123",
            project_name="proj",
            project_urls={"proj": "https://smith.langchain.com/o/org/projects/p/p1"},
            env={DEBUG: "1"},
        )._build_banner()
        assert "(open in langsmith)" in content.plain
        link = _style_covering(content, "(open in langsmith)").link
        assert link == (
            "https://smith.langchain.com/o/org/projects/p/p1/t/abc-123"
            "?utm_source=deepagents-code"
        )

    def test_no_langsmith_link_without_tracing(self) -> None:
        """No trace link when LangSmith tracing is not configured."""
        plain = (
            _make_banner(thread_id="abc-123", env={DEBUG: "1"})._build_banner().plain
        )
        assert "(open in langsmith)" not in plain


class _BannerApp(App[None]):
    """Minimal app that mounts a prebuilt `WelcomeBanner` for click tests."""

    def __init__(self, banner: WelcomeBanner) -> None:
        super().__init__()
        self._banner = banner

    def compose(self) -> ComposeResult:
        yield self._banner


class TestBorder:
    """Tests for the charset-aware banner border."""

    async def test_ascii_mode_uses_ascii_border(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ASCII mode replaces the default solid border."""
        monkeypatch.setattr(welcome_module, "is_ascii_mode", lambda: True)
        banner = _make_banner(show_model=False)
        app = _BannerApp(banner)
        async with app.run_test(size=(80, 24)) as pilot:
            assert banner.styles.border_top[0] == "ascii"

            original_color = banner.styles.border_top[1]
            app.theme = "textual-light"
            await pilot.pause()

            assert banner.styles.border_top[0] == "ascii"
            assert banner.styles.border_top[1] == TColor.parse(
                welcome_module.theme.get_theme_colors(banner).primary
            )
            assert banner.styles.border_top[1] != original_color


class TestMascot:
    """Tests for the coco mascot board merged into the banner."""

    _BLOCK_CHARS = "▄▀█"
    _ROW_NEEDLES = (
        "▄▄   ▄▄",
        "▀██▄██▀",
        "     █",
        "▄█████▄",
        "███ █ ███",
        "█████████",
        "▀▀   ▀▀",
    )
    _ANSI_ROW_STYLES = (
        "green",
        "green",
        "green",
        "bold green",
        "bold green",
        "bold green",
        "green",
    )
    _ROW_HEXS = (
        "#008700",
        "#008700",
        "#008700",
        "#87d75f",
        "#87d75f",
        "#87d75f",
        "#005f00",
    )

    def test_unicode_board_renders_with_right_column(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The board sits left of the title column in Unicode mode."""
        monkeypatch.setattr(welcome_module, "is_ascii_mode", lambda: False)
        banner = _make_banner(show_model=False)
        content = banner._build_banner()
        lines = content.plain.split("\n")
        # Board rows share the title line and extend below it.
        assert welcome_module._MASCOT_UNICODE[0] in lines[0]
        assert "dcode" in lines[0]
        assert sum(ch in self._BLOCK_CHARS for ch in content.plain) > 0
        # Title starts after the board width plus the column gap plus the
        # styled cursor prefix.
        title_column = (
            welcome_module._MASCOT_WIDTH
            + welcome_module._MASCOT_COLUMN_GAP
            + len(f"{get_glyphs().cursor} ")
        )
        assert lines[0].index("dcode") == title_column
        # Default banner has one right line, so the board fills the height.
        assert len(lines) == welcome_module._MASCOT_HEIGHT
        assert lines[6].rstrip() == welcome_module._MASCOT_UNICODE[6]

    def test_unicode_board_rows_carry_design_hexes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each board row's span foreground matches the mascot design notes."""
        monkeypatch.setattr(welcome_module, "is_ascii_mode", lambda: False)
        content = _make_banner(show_model=False)._build_banner()
        for needle, hex_color in zip(self._ROW_NEEDLES, self._ROW_HEXS, strict=True):
            style = _style_covering(content, needle)
            assert style.foreground == TColor.parse(hex_color), needle

    def test_ansi_theme_rows_use_named_markup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Under ANSI themes board rows use raw named markup, not hexes.

        `_build_banner` assembles at construction time, so the ANSI theme is
        set on the active app before the banner exists and the first build
        takes the ANSI branch.
        """
        monkeypatch.setattr(welcome_module, "is_ascii_mode", lambda: False)
        from textual._context import active_app

        app = App()
        app.theme = "ansi-dark"
        token = active_app.set(app)
        try:
            # `_build_banner` assembles at construction time AND again on every
            # theme/update path; build inside the context so both share the
            # ANSI branch.
            banner = _make_banner(show_model=False)
            content = banner._build_banner()
        finally:
            active_app.reset(token)
        for needle, markup in zip(
            self._ROW_NEEDLES, self._ANSI_ROW_STYLES, strict=True
        ):
            style = _raw_style_covering(content, needle)
            assert style == markup, needle

    def test_ascii_mode_renders_ascii_board(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ASCII mode swaps the block-character board for the 7-bit sprite."""
        monkeypatch.setattr(welcome_module, "is_ascii_mode", lambda: True)
        banner = _make_banner(show_model=False)
        content = banner._build_banner()
        plain = content.plain
        assert sum(ch in self._BLOCK_CHARS for ch in plain) == 0
        # The board itself is 7-bit ASCII; the title cursor glyph stays Unicode
        # (glyph selection is orthogonal to the charset mode).
        board_text = "".join(welcome_module._MASCOT_ASCII)
        assert board_text.isascii()
        assert all(row.isascii() for row in welcome_module._MASCOT_ASCII)
        assert welcome_module._MASCOT_ASCII[0] in plain.split("\n")[0]
        # Right column alignment mirrors the Unicode layout with the ASCII
        # board's own width.
        ascii_width = max(
            Content.from_text(row).cell_length for row in welcome_module._MASCOT_ASCII
        )
        title_column = (
            ascii_width
            + welcome_module._MASCOT_COLUMN_GAP
            + len(f"{get_glyphs().cursor} ")
        )
        assert plain.split("\n")[0].index("dcode") == title_column

    def test_ascii_board_rows_use_same_color_zones(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ASCII sprite reuses the Unicode board's three color zones."""
        monkeypatch.setattr(welcome_module, "is_ascii_mode", lambda: True)
        content = _make_banner(show_model=False)._build_banner()
        for index, (row_text, hex_color) in enumerate(
            zip(welcome_module._MASCOT_ASCII, self._ROW_HEXS, strict=True)
        ):
            style = _last_style_covering(content, row_text.strip())
            assert style.foreground == TColor.parse(hex_color), index

    def test_boards_fit_the_board_width(self) -> None:
        """Both boards stay within the 10-cell width the layout pads against."""
        for row in welcome_module._MASCOT_UNICODE:
            assert Content.from_text(row).cell_length <= welcome_module._MASCOT_WIDTH
        for row in welcome_module._MASCOT_ASCII:
            assert Content.from_text(row).cell_length <= welcome_module._MASCOT_WIDTH
            assert row.isascii()

    def test_rows_beyond_the_board_continue_at_column_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Text past the board's height flows from column 0 with no prefix."""
        monkeypatch.setattr(welcome_module, "is_ascii_mode", lambda: False)
        content = _make_banner(
            model_provider="anthropic",
            model_name="claude-opus-4-8",
            cwd="/work/project",
            thread_id="abc-123",
            mcp_tool_count=3,
            project_name="proj",
            replica_project="repl",
            project_urls={"proj": "https://x/p1", "repl": "https://x/p2"},
            show_model=True,
            show_cwd=True,
            env={
                DEBUG: "1",
                "DEEPAGENTS_CODE_SPLASH_SHOW_CWD": "1",
            },
        )._build_banner()
        lines = content.plain.split("\n")
        # title + blank + model + directory + tracing + replica + thread + mcp
        assert len(lines) == 8
        assert lines[7].startswith("mcp:")

    def test_board_height_extends_past_short_right_column(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With a short right column the banner stays as tall as the board."""
        monkeypatch.setattr(welcome_module, "is_ascii_mode", lambda: False)
        content = _make_banner(show_model=False)._build_banner()
        lines = content.plain.split("\n")
        assert len(lines) == welcome_module._MASCOT_HEIGHT
        # The surplus rows carry board content with no right-column text.
        assert lines[5].rstrip() == welcome_module._MASCOT_UNICODE[5]
        assert lines[6].rstrip() == welcome_module._MASCOT_UNICODE[6]

    def test_thread_trace_link_survives_the_merge(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The trace link span still carries its URL after board merging."""
        monkeypatch.setattr(welcome_module, "is_ascii_mode", lambda: False)
        content = _make_banner(
            thread_id="abc-123",
            project_name="proj",
            project_urls={"proj": "https://smith.langchain.com/o/org/projects/p/p1"},
            env={DEBUG: "1"},
        )._build_banner()
        assert "(open in langsmith)" in content.plain
        link = _style_covering(content, "(open in langsmith)").link
        assert link == (
            "https://smith.langchain.com/o/org/projects/p/p1/t/abc-123"
            "?utm_source=deepagents-code"
        )


def _click_offset(banner: WelcomeBanner, needle: str) -> tuple[int, int]:
    """Return a click offset inside the rendered span containing `needle`.

    Derives the offset from the rendered text instead of hardcoding columns, then
    shifts it by the banner's border (1 column, 1 row) and horizontal padding
    (2 columns) so it addresses the widget's own coordinate space.

    Args:
        banner: The banner whose content is measured.
        needle: Substring identifying the target span.

    Returns:
        The `(x, y)` offset to click.
    """
    border_x, border_y, padding_x = 1, 1, 2
    for y, line in enumerate(banner._build_banner().plain.split("\n")):
        column = line.find(needle)
        if column != -1:
            return border_x + padding_x + column, border_y + y
    msg = f"{needle!r} not found in the rendered banner"
    raise AssertionError(msg)


class TestThreadIdClickToCopy:
    """Clicking the thread ID copies it; the trace link still opens."""

    async def test_clicking_trace_link_opens_it_without_copying(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The trace link opens in the browser and never copies."""
        copied: list[str] = []

        def fake_copy(_app: App[None], text: str) -> tuple[bool, str | None]:
            copied.append(text)
            return True, None

        monkeypatch.setattr(clipboard_module, "copy_text_to_clipboard", fake_copy)
        opened: list[object] = []
        monkeypatch.setattr(
            welcome_module, "open_style_link", lambda event: opened.append(event)
        )
        banner = _make_banner(
            thread_id="abc-123", show_model=False, project_name="proj", env={DEBUG: "1"}
        )
        app = _BannerApp(banner)
        project_url = "https://smith.langchain.com/o/org/projects/p/p1"
        # The mounted banner renders the link only after its startup worker
        # resolves the project URL, so patch the fetch and let the worker run.
        with patch(_FETCH_URL, return_value=project_url):
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                assert banner._project_urls == {"proj": project_url}
                await pilot.click(
                    banner, offset=_click_offset(banner, "(open in langsmith)")
                )
                await pilot.pause()

                assert len(opened) == 1
                assert copied == []


class TestMcpToolLine:
    """Tests for the MCP tool count row."""


class TestMcpWarnings:
    """Tests for MCP server warning lines."""

    def test_shows_unauthenticated_warning(self) -> None:
        """An unauthenticated-server warning line is rendered."""
        plain = _make_banner(mcp_unauthenticated=2)._build_banner().plain
        assert "2 MCP servers need login" in plain
        assert "open /mcp" in plain

    def test_singular_unauthenticated(self) -> None:
        """A single unauthenticated server uses singular wording."""
        plain = _make_banner(mcp_unauthenticated=1)._build_banner().plain
        assert "1 MCP server needs login" in plain

    def test_set_connected_updates_warnings(self) -> None:
        """`set_connected` updates warning counts and re-renders."""
        widget = _make_banner()
        with patch.object(widget, "update"):
            widget.set_connected(
                5, mcp_unauthenticated=1, mcp_errored=2, mcp_awaiting_reconnect=3
            )
        assert widget._mcp_tool_count == 5
        assert widget._mcp_unauthenticated == 1
        assert widget._mcp_errored == 2
        assert widget._mcp_awaiting_reconnect == 3
        plain = widget._build_banner().plain
        assert "1 MCP server needs login" in plain
        assert "2 MCP servers failed to load" in plain
        assert "3 MCP servers ready to load" in plain


class TestRemovedSections:
    """The banner does not show the old splash tips/footer content."""


class TestReturnType:
    """Tests for `_build_banner` return value."""


class TestThreadIdUpdates:
    """`update_thread_id` tracks the id and only re-renders in debug mode."""


class TestAutoLinksDisabled:
    """Tests that `auto_links` is disabled to prevent hover flicker."""
