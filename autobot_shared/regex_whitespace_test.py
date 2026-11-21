# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21987: the spelled-out whitespace classes are exactly ``\\s`` / ``\\S``."""

import re
import sys

from autobot_shared.regex_whitespace import HSPACE, NOT_WS, WS


def test_classes_equal_the_shorthands_for_every_code_point():
    ws, not_ws, hspace = re.compile(WS), re.compile(NOT_WS), re.compile(HSPACE)
    shorthand_ws, shorthand_not_ws = re.compile(r"\s"), re.compile(r"\S")
    for cp in range(sys.maxunicode + 1):
        ch = chr(cp)
        assert bool(ws.fullmatch(ch)) == bool(shorthand_ws.fullmatch(ch)), hex(cp)
        assert bool(not_ws.fullmatch(ch)) == bool(shorthand_not_ws.fullmatch(ch)), hex(cp)
        assert bool(hspace.fullmatch(ch)) == (bool(shorthand_ws.fullmatch(ch)) and ch != "\n"), hex(cp)
