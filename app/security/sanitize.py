"""HTML sanitisation for any content a user can influence.

Two policies:

* :func:`clean_plain_text` — for chat messages, support tickets and anything
  that should be inert text.  All markup is removed, not escaped, so a stored
  ``<script>`` can never be re-enabled by a later change to a template.
* :func:`clean_rich_text` — for admin-authored news bodies, which may use a
  small allowlist of formatting tags.

Belt and braces: Jinja2 autoescape stays on, so even an unexpected value is
escaped again on output.
"""

from __future__ import annotations

import re

import bleach

# --- Plain text ------------------------------------------------------------

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


def clean_plain_text(value: str, *, max_length: int | None = None) -> str:
    """Strip all markup and control characters from a user-supplied string."""
    if not value:
        return ""

    # bleach removes tags and decodes entities, leaving readable text.
    text = bleach.clean(value, tags=[], attributes={}, strip=True, strip_comments=True)
    text = _CONTROL_CHARS.sub("", text)
    text = _EXCESS_BLANK_LINES.sub("\n\n", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()

    if max_length is not None and len(text) > max_length:
        text = text[:max_length].rstrip()
    return text


# --- Rich text (news bodies) ----------------------------------------------

RICH_TEXT_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "s",
    "ul",
    "ol",
    "li",
    "blockquote",
    "code",
    "pre",
    "h2",
    "h3",
    "h4",
    "a",
    "hr",
]

RICH_TEXT_ATTRIBUTES = {
    "a": ["href", "title", "rel"],
}

RICH_TEXT_PROTOCOLS = ["http", "https", "mailto"]


def clean_rich_text(value: str) -> str:
    """Allow a small, safe subset of HTML for editorial content."""
    if not value:
        return ""
    return bleach.clean(
        value,
        tags=RICH_TEXT_TAGS,
        attributes=RICH_TEXT_ATTRIBUTES,
        protocols=RICH_TEXT_PROTOCOLS,
        strip=True,
        strip_comments=True,
    ).strip()


# --- Helpers ---------------------------------------------------------------


def clean_slug(value: str) -> str:
    """Reduce arbitrary input to a URL-safe slug."""
    lowered = (value or "").strip().lower()
    # Keep Cyrillic letters: they are valid in slugs and expected here.
    slug = re.sub(r"[^a-z0-9\u0400-\u04ff]+", "-", lowered)
    return slug.strip("-")[:120]


def clean_email(value: str) -> str:
    return (value or "").strip().lower()[:320]
