# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Normalisation applied to every OpenAPI spec this repo publishes.

Both backends dump `app.openapi()` to a checked-in spec that the frontends
generate types from, and CI regenerates the same spec to prove the committed one
is fresh. Anything pydantic changes about its JSON-Schema output therefore lands
directly in a published contract — which is how `\\z` got there.
"""

from __future__ import annotations

from typing import Any

__all__ = ["normalize_pattern_anchors"]

#: pydantic >= 2.12 emits the Rust-regex end anchor for a `Field(pattern=...)`
#: that was authored with `$`.
_RUST_END_ANCHOR = "\\z"


def normalize_pattern_anchors(node: Any) -> Any:
    """Rewrite the Rust end anchor back to `$` in JSON-Schema ``pattern`` values.

    JSON Schema's regex dialect is ECMA-262, which has no ``\\z``. Consumers do
    not reject it — they misread it, which is worse:

        JS   /^(hour|day)\\z/.test("hour")  -> false     (the valid value fails)
        JS   /^(hour|day)\\z/.test("hourz") -> true      (an invalid value passes)
        Py   re.match(r"^(hour|day)\\z", …) -> re.error: bad escape \\z

    So a spec carrying it silently inverts validation for every JS client and
    breaks every Python one. Field authors write ``$``; this restores what they
    wrote, at the one point where the spec becomes a published artifact.

    Only a *trailing* anchor is rewritten. A ``\\z`` anywhere else is not
    something pydantic produces, and rewriting it would corrupt a pattern that
    genuinely means a literal backslash followed by ``z``.
    """
    if isinstance(node, dict):
        return {
            key: (
                value[: -len(_RUST_END_ANCHOR)] + "$"
                if key == "pattern" and isinstance(value, str) and value.endswith(_RUST_END_ANCHOR)
                else normalize_pattern_anchors(value)
            )
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [normalize_pattern_anchors(item) for item in node]
    return node
