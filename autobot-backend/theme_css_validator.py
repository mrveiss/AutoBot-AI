# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Strict validator for uploaded theme CSS (#10472).

Untrusted CSS may only style its own variant and must not fetch anything
external. Rejects on the first violation with an HTTPException(400).
"""

from __future__ import annotations

import re

from fastapi import HTTPException, status

MAX_CSS_BYTES = 512 * 1024
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_FORBIDDEN = ("@import", "expression(", "behavior:", "javascript:", "@charset")
_URL = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", re.IGNORECASE)
_BLOCK = re.compile(r"([^{}]+)\{[^{}]*\}", re.DOTALL)
# CSS escapes: "\26 " == '&', "\69" == 'i', "\@" == '@'. The browser decodes these,
# so substring/regex checks must run on the DECODED text or an attacker bypasses them
# (e.g. "@\69mport", "url(\68ttp://evil)"). #10472 security review.
_HEX_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6})[ \t\n\r\f]?")
_CHAR_ESCAPE = re.compile(r"\\(.)", re.DOTALL)


def _reject(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Theme CSS rejected: {detail}")


def _decode_css_escapes(text: str) -> str:
    """Resolve CSS escape sequences to the characters the browser will render."""

    def _hex(match: re.Match[str]) -> str:
        try:
            return chr(int(match.group(1), 16))
        except (ValueError, OverflowError):
            return ""

    return _CHAR_ESCAPE.sub(lambda m: m.group(1), _HEX_ESCAPE.sub(_hex, text))


def validate_theme_css(css: str, variant_id: str) -> None:
    if len(css.encode("utf-8")) > MAX_CSS_BYTES:
        _reject(f"exceeds {MAX_CSS_BYTES // 1024}KB")
    stripped = _COMMENT.sub(" ", css)
    # Escapes have no legitimate use in a relative asset path — reject before decoding.
    for ref in _URL.findall(stripped):
        if "\\" in ref:
            _reject(f"escaped url() not allowed: {ref.strip()[:60]}")
    decoded = _decode_css_escapes(stripped)
    lowered = decoded.lower()
    for tok in _FORBIDDEN:
        if tok in lowered:
            _reject(f"forbidden token {tok!r}")
    for ref in _URL.findall(decoded):
        target = ref.strip()
        if target.startswith("data:"):
            continue
        if re.match(r"^(https?:)?//", target, re.IGNORECASE) or "\\" in target or ":" in target.split("/")[0]:
            _reject(f"external url() not allowed: {target}")
    scope = f'[data-theme-variant="{variant_id}"]'
    blocks = _BLOCK.findall(decoded)
    if not blocks:
        _reject("no style rules found")
    for selector_list in blocks:
        for selector in selector_list.split(","):
            sel = selector.strip()
            if not sel or sel.startswith("@"):  # @font-face/@media handled below
                continue
            if not sel.startswith(scope):
                _reject(f"selector not scoped to {scope}: {sel[:60]}")
