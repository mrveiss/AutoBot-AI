# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Negative fixture: canonical names + allow-listed git 'unified diff' term."""


class Foo:
    pass


class Baz:
    pass


def condense_unified_diff(text: str) -> str:
    """'unified diff' is a git format term — allow-listed, not an era marker."""
    return text
