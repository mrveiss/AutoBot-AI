# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Render strings as YAML double-quoted scalars that load back exactly (#18606)."""

import json
import re

# One JSON escape, scanned left to right so an escaped backslash is consumed whole:
# group 1/2 are the halves of a surrogate pair, anything else is left untouched.
_JSON_ESCAPE = re.compile(r"\\(?:u(d[89ab][0-9a-f]{2})\\u(d[c-f][0-9a-f]{2})|.)", re.IGNORECASE | re.DOTALL)


def yaml_double_quoted(value: str) -> str:
    """Render `value` as a YAML double-quoted scalar that loads back byte-exact.

    JSON escapes non-ASCII as \\uXXXX, which YAML reads too, except that a non-BMP
    character comes out as a surrogate pair YAML cannot join; those become \\UXXXXXXXX.
    Raw non-ASCII is avoided: U+0085, U+2028, U+2029 are line breaks that fold to a space.
    """

    def join(match: "re.Match[str]") -> str:
        if match.group(1) is None:
            return match.group(0)
        high, low = int(match.group(1), 16), int(match.group(2), 16)
        return "\\U%08x" % (0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00))

    return _JSON_ESCAPE.sub(join, json.dumps(value))
