"""The desktop header must never be empty.

The header shows either the inline navigation or the burger button.  Those two
are driven by separate media queries, so if the navigation appears *later* than
the burger disappears, there is a band of viewport widths with neither: the
header then holds only the logo and the profile button.  That is exactly what
happened — the navigation started at 1024px while the burger stopped at 900px.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

LAYOUT_CSS = (
    Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "layout.css"
)


def _min_width_for(selector_block: str) -> int:
    """The ``min-width`` of the media query wrapping ``selector_block``."""
    source = LAYOUT_CSS.read_text(encoding="utf-8")
    index = source.index(selector_block)
    # Walk back to the nearest media query, which is what guards the block.
    prefix = source[:index]
    matches = list(re.finditer(r"@media\s*\(min-width:\s*(\d+)px\)", prefix))
    assert matches, f"no min-width media query guards {selector_block!r}"
    return int(matches[-1].group(1))


@pytest.fixture(scope="module")
def nav_and_burger_breakpoints() -> tuple[int, int]:
    return (
        _min_width_for(".header__nav { display: flex; }"),
        _min_width_for(".burger { display: none; }"),
    )


def test_navigation_and_burger_switch_at_the_same_width(
    nav_and_burger_breakpoints,
):
    """No gap: the moment the burger goes, the inline navigation arrives."""
    nav_min, burger_min = nav_and_burger_breakpoints
    assert nav_min == burger_min, (
        "the inline navigation and the burger must swap at the same width, "
        f"otherwise {min(nav_min, burger_min)}–{max(nav_min, burger_min)}px "
        "has neither and the header looks empty"
    )


def test_the_header_is_never_without_a_way_to_navigate(
    nav_and_burger_breakpoints,
):
    """Below the switch width the burger must still be visible."""
    nav_min, burger_min = nav_and_burger_breakpoints
    assert nav_min <= burger_min
