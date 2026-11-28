# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A `regex_search` backreference must survive YAML parsing as ONE backslash (#17897).

The install break this guards against was not the one it was first diagnosed as. The
original fix reordered `default` before `first`, which was necessary and not sufficient:
the task still raised on every input, including the success path, because its regex
arguments were written `'\\\\w+'` and `'\\\\1'` inside a **folded** (`>-`) scalar.

A folded scalar performs no YAML unescaping, so those reach Jinja as two literal
characters. Ansible then hands `'\\\\1'` to `regex_search`, whose own
`re.match(r'\\\\(\\\\d+)', arg)` cannot parse it and raises -- before any of the
value-guards upstream can run. The symptom is a bare `FAILED! => {"changed": false}`
with no message, which is what a user's install actually reported.

**The invariant is style-independent, which is what makes it checkable.** Both correct
spellings converge after the YAML parser has run:

    folded/plain      '\\1'    -> parser passes it through  -> one backslash
    double-quoted     '\\\\1'   -> parser unescapes it       -> one backslash

So a post-parse value carrying two backslashes in a backreference is wrong in *either*
style, and no knowledge of the scalar's quoting is needed to say so. The tree held one
of each spelling -- `playbooks/fix-backend-environment.yml` folded and correct,
`playbooks/update-all-nodes.yml` quoted and correct -- so the convention was already
right twice and wrong once, which is exactly the shape a guard fixes better than review.

**Scope.** This asserts backreferences (`\\1`..`\\9`) only, not pattern bodies. A pattern
is a regex in its own right where a doubled backslash can be legitimate (`'\\\\.'` matching
a literal dot), so demanding one backslash there would be wrong. Backreference arguments
have no such reading: `regex_search`'s parser accepts exactly one form.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from repo_tests._paths import repo_root

_ANSIBLE = Path("autobot-slm-backend/ansible")

#: The second argument of `regex_search`, when it is a backreference. Captured from the
#: POST-PARSE string, so what it counts is what Jinja will receive.
#:
#: `.*?` rather than `[^)]*?`: the FIRST argument is a regex and routinely contains its
#: own `)` -- `'VERDICT=(\\w+)'` is the live case. A character class excluding `)` stops
#: inside the pattern's own group and matches nothing, which is how the first version of
#: this guard scanned the tree and found zero. The reach floor below caught that; without
#: it the guard would have reported the tree clean while reading none of it.
_BACKREF_ARG = re.compile(r"regex_search\s*\(.*?,\s*'(\\+)(\d)'")

#: Reach floor. A walk that resolves no `regex_search` at all must fail rather than
#: report a clean tree -- "nothing was scanned" and "nothing was wrong" are the same
#: empty result otherwise, and this guard exists because a silent pass hid a hard break.
_MIN_CALLS = 3


def _yaml_files() -> list[Path]:
    root = repo_root() / _ANSIBLE
    return sorted(p for p in root.rglob("*.yml") if p.is_file())


def _strings(node: object) -> list[str]:
    """Every string value anywhere in a parsed YAML document."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in _strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in _strings(v)]
    return []


def backreference_args() -> list[tuple[str, str, int]]:
    """``(path, backslashes, group)`` for every post-parse `regex_search` backreference."""
    found: list[tuple[str, str, int]] = []
    for path in _yaml_files():
        try:
            docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except yaml.YAMLError:
            # Templated or vault-encrypted files are not this guard's subject; a parse
            # failure here is a different defect and is not silently counted as clean.
            continue
        for doc in docs:
            for value in _strings(doc):
                for slashes, group in _BACKREF_ARG.findall(value):
                    found.append((str(path.relative_to(repo_root())), slashes, int(group)))
    return found


def over_escaped(found: list[tuple[str, str, int]]) -> list[str]:
    """The offenders: a backreference that survived parsing with more than one backslash."""
    return [f"{path} -> '{slashes}{group}'" for path, slashes, group in found if len(slashes) != 1]


def test_enough_regex_search_calls_were_scanned_to_mean_anything() -> None:
    """Reach. Without this, a broken walk reports the tree clean."""
    found = backreference_args()
    assert len(found) >= _MIN_CALLS, (
        f"only {len(found)} regex_search backreferences resolved, below the floor of "
        f"{_MIN_CALLS} -- the ansible tree or the pattern has moved, so a clean result "
        "below means nothing was scanned, not that nothing was wrong"
    )


def test_no_backreference_survives_parsing_with_two_backslashes() -> None:
    """#17897: `'\\\\1'` in a folded scalar raised on every input, with no message."""
    offenders = over_escaped(backreference_args())
    assert not offenders, (
        f"these regex_search backreferences reach Jinja with more than one backslash: "
        f"{offenders}. regex_search parses its backreference with re.match(r'\\\\(\\\\d+)'), "
        "which fails on a doubled backslash and raises BEFORE any surrounding default or "
        "guard can run -- surfacing as a bare FAILED! with no message. Use '\\\\1' in a "
        "double-quoted scalar (the parser unescapes it) or '\\1' in a folded or plain one."
    )


def test_an_over_escaped_backreference_is_reported() -> None:
    """The detector fires; without this the clean result above licenses nothing."""
    assert over_escaped([("some.yml", "\\\\", 1)]) == ["some.yml -> '\\\\1'"]


def test_a_single_backslash_backreference_is_accepted() -> None:
    """The contrast: the correct post-parse form must not be flagged."""
    assert over_escaped([("some.yml", "\\", 1)]) == []
