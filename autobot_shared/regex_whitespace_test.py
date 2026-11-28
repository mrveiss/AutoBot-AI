# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21987: the spelled-out whitespace classes are exactly ``\\s`` / ``\\S``."""

import re
import sys

from autobot_shared.regex_whitespace import HSPACE, NOT_WS, WS, WS_CHARS


def test_class_body_composes_into_exact_and_negated_classes():
    positive, negated = re.compile(f"[{WS_CHARS}]"), re.compile(f"[^{WS_CHARS}x]")
    shorthand = re.compile(r"\s")
    for cp in range(sys.maxunicode + 1):
        ch = chr(cp)
        assert bool(positive.fullmatch(ch)) == bool(shorthand.fullmatch(ch)), hex(cp)
        if shorthand.fullmatch(ch):
            assert not negated.fullmatch(ch), hex(cp)
    assert not negated.fullmatch("x") and negated.fullmatch("y")


def test_classes_equal_the_shorthands_for_every_code_point():
    ws, not_ws, hspace = re.compile(WS), re.compile(NOT_WS), re.compile(HSPACE)
    shorthand_ws, shorthand_not_ws = re.compile(r"\s"), re.compile(r"\S")
    for cp in range(sys.maxunicode + 1):
        ch = chr(cp)
        assert bool(ws.fullmatch(ch)) == bool(shorthand_ws.fullmatch(ch)), hex(cp)
        assert bool(not_ws.fullmatch(ch)) == bool(shorthand_not_ws.fullmatch(ch)), hex(cp)
        assert bool(hspace.fullmatch(ch)) == (bool(shorthand_ws.fullmatch(ch)) and ch != "\n"), hex(cp)
