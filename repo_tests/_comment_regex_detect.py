# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The regex shape of a hand-rolled comment stripper (#21569), for `one_comment_stripper_17941_test`.

Split out of the guard to keep it under the file-size ceiling; the guard owns the policy (the
pending list, the ratchet) and this module owns only the question "does this call strip comments".
"""

from __future__ import annotations

import ast
import re

#: `re` functions whose first argument is a pattern (#21569).
_RE_FUNCTIONS = frozenset({"compile", "sub", "subn", "finditer", "findall", "match", "search", "split"})
#: Shapes of a constant regex pattern that removes or blanks a comment construct, as regexes over the
#: pattern text (an escaped slash is normalised first). Each is anchored on what follows the marker,
#: so a URL scheme (`://`), a division and a CSS id selector are not read as comments.
_COMMENT_PATTERN_SHAPES = (
    r"(?<![:\w/])//(?=\.|\[\^|\\N)",  # `//` line comment, then a run of anything
    r"/\\\*(?!\\\*\\Z)",  # `/\*` block comment opener
    r"<!--(?=\.|\[\^|\[\\s\\S)",  # HTML comment opener
    r"\^\\s\*\\?#",  # `^\s*#` line comment
    r"(?<!\\)#(?=\.[*+]|\[\^\\n)",  # `#` then a run to end of line
)
_COMMENT_PATTERN = re.compile("|".join(_COMMENT_PATTERN_SHAPES))


def _is_re_call(node: ast.AST) -> bool:
    """`re.<function>(...)` for a pattern-taking function of the `re` module."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _RE_FUNCTIONS
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "re"
    )


def _constant_pattern(call: ast.Call, consts: dict[str, ast.expr]) -> str | None:
    """The call's first argument when it is a string literal or a module string constant."""
    if not call.args:
        return None
    arg = call.args[0]
    arg = consts.get(arg.id, arg) if isinstance(arg, ast.Name) else arg
    return arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None


def strips_comments_by_regex(tree: ast.AST, asserted: set[int], consts: dict[str, ast.expr]) -> bool:
    """True if a `re` call takes a constant pattern that removes or blanks a comment construct (#21569).

    `asserted` is the node ids under an `assert` (a control, not logic) and `consts` the module
    constants. Reads call nodes and their constant argument. A pattern built at run time (concatenated,
    formatted, passed in) is not followed, and neither is a `from re import sub` alias.
    """
    for node in ast.walk(tree):
        if _is_re_call(node) and id(node) not in asserted:
            pattern = _constant_pattern(node, consts)
            if pattern is not None and _COMMENT_PATTERN.search(pattern.replace("\\/", "/")):
                return True
    return False
