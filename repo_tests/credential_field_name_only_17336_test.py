# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A caller that holds a value never asks the name-only credential question (#17336).

`secret_redaction.is_credential_field(name)` cannot see the value, so it must exempt a
quantity-shaped name (`token_count`) on the name alone -- and then a JWT stored under that name
shows in clear. `is_credential_entry(name, value, policy)` is the value-aware form, and every
caller that decides whether to mask a value uses it.

The detector reads the syntax tree: ANY reference to `is_credential_field` -- a call, a bare
name passed to `filter`/`partial`/`getattr`, an assignment to an alias, or an aliased import. The guard is an explicit allowlist of the value-free sites with a
reason each, so a NEW call anywhere fails until someone has reviewed which question it is asking.
Zero production sites exist today -- including inside `secret_redaction.py` itself, which is
held to an allowlist of 0 like everyone else; the two below are tests of the name-only classification.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_NAME = "is_credential_field"

#: Every tree that holds tracked Python. Written out, not globbed, so a tree dropped from the
#: sweep is a visible edit to this constant AND to `reach_scope_claim_17844_test`.
SCAN_ROOTS = (
    "autobot-backend",
    "autobot-slm-backend",
    "autobot_shared",
    "plugins",
    "scripts",
    "pipeline-scripts",
    "tools",
    "repo_tests",
    "autobot-infrastructure",
    "autobot-npu-worker",
    "autobot-tts-worker",
    "autobot-browser-worker",
    "libs",
)

#: path -> (number of sites, why a name-only classification is right there). Value-free only.
_VALUE_FREE: dict[str, tuple[int, str]] = {
    "autobot_shared/secret_redaction_policy_17336_test.py": (
        20,
        "tests the name-only API itself over field names; no value exists",
    ),
    "autobot_shared/tests/test_config_repr_redaction_13325.py": (
        3,
        "pins how SSOT config FIELD NAMES classify; the schema has no value",
    ),
}


def _is_source_python(rel: str) -> bool:
    return rel.endswith(".py")


def _population(root: Path) -> list[str]:
    try:
        return [p for p in tracked_paths(root, *SCAN_ROOTS) if _is_source_python(p)]
    except EmptyEnumeration:
        return []


REACH = declare(
    "credential-field-name-only-callers",
    discover=_population,
    # Mid-window, from REACH.window(); the arithmetic is on the commit, not here.
    floor=6_262,
    what="tracked python in every tree that holds any",
    roots=SCAN_ROOTS,
    growth=300,
)


def _sites(source: str) -> int:
    """How many references to the name-only classifier `source` makes.

    Counts every Name load and Attribute access (a call is one such load, so it is not counted
    twice), plus an aliased import. The `def` itself is a FunctionDef and not a reference.
    """
    count = 0
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and node.id == _NAME and isinstance(node.ctx, ast.Load):
            count += 1
        elif isinstance(node, ast.Attribute) and node.attr == _NAME:
            count += 1
        elif isinstance(node, ast.ImportFrom) and any(a.name == _NAME and a.asname for a in node.names):
            count += 1  # an alias would hide every later reference
    return count


def _unreviewed(sources: dict[str, str]) -> list[str]:
    """Sites outside the allowlist, or a different count than the allowlist recorded."""
    bad = []
    for rel, source in sorted(sources.items()):
        if _NAME not in source:
            continue
        found, allowed = _sites(source), _VALUE_FREE.get(rel, (0, ""))[0]
        if found != allowed:
            bad.append(f"{rel}: {found} site(s), reviewed {allowed}")
    return bad


_VALUE_BEARING = (
    "from autobot_shared.secret_redaction import MatchPolicy, is_credential_field\n"
    "def scrub(d):\n"
    "    return {k: ('***' if is_credential_field(k, MatchPolicy.BROAD) else v) for k, v in d.items()}\n"
)
_VALUE_AWARE = (
    "from autobot_shared.secret_redaction import MatchPolicy, is_credential_entry\n"
    "def scrub(d):\n"
    "    return {k: ('***' if is_credential_entry(k, v, MatchPolicy.BROAD) else v) for k, v in d.items()}\n"
)


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a value-bearing name-only call", _VALUE_BEARING, 1),
        ("the value-aware call", _VALUE_AWARE, 0),
        ("a module-qualified call", "import m\nm.secret_redaction.is_credential_field('k')\n", 1),
        ("an aliased import", "from x import is_credential_field as f\n", 1),
        ("a bare name passed to filter", "list(filter(is_credential_field, names))\n", 1),
        ("a bare name through partial", "g = functools.partial(is_credential_field, policy=p)\n", 1),
        ("an alias assignment", "f = is_credential_field\n", 1),
        ("the definition itself", "def is_credential_field(name):\n    return True\n", 0),
        ("a comment naming it", "# is_credential_field(k)\nx = 1\n", 0),
        ("a string naming it", "s = 'is_credential_field(k)'\n", 0),
    ],
)
def test_the_matcher_tells_a_name_only_call_from_a_value_aware_one(label: str, source: str, expected: int) -> None:
    assert _sites(source) == expected, label


def test_a_planted_value_bearing_call_fails_and_the_value_aware_twin_passes(tmp_path: Path) -> None:
    """Scratch copy of a production module: the contrast pair, end to end."""
    planted = tmp_path / "autobot-backend" / "services" / "scrub.py"
    planted.parent.mkdir(parents=True)
    planted.write_text(_VALUE_BEARING, encoding="utf-8")
    rel = "autobot-backend/services/scrub.py"
    assert _unreviewed({rel: planted.read_text(encoding="utf-8")}) == [f"{rel}: 1 site(s), reviewed 0"]
    planted.write_text(_VALUE_AWARE, encoding="utf-8")
    assert _unreviewed({rel: planted.read_text(encoding="utf-8")}) == []
    planted.write_text("from m import is_credential_field\nscrub = is_credential_field\n", encoding="utf-8")
    assert _unreviewed({rel: planted.read_text(encoding="utf-8")}) == [f"{rel}: 1 site(s), reviewed 0"]


def test_the_canonical_module_is_held_to_zero_references() -> None:
    """secret_redaction.py defines the classifier and may not call, alias or pass it around."""
    rel = "autobot_shared/secret_redaction.py"
    assert rel not in _VALUE_FREE
    assert _sites((repo_root() / rel).read_text(encoding="utf-8")) == 0
    assert _unreviewed({rel: "x = is_credential_field\n"}) == [f"{rel}: 1 site(s), reviewed 0"]


def test_a_second_call_in_an_allowlisted_file_is_also_unreviewed() -> None:
    rel = next(iter(_VALUE_FREE))
    extra = "\n".join(f"{_NAME}('a{i}')" for i in range(_VALUE_FREE[rel][0] + 1))
    assert _unreviewed({rel: extra}) == [f"{rel}: {_VALUE_FREE[rel][0] + 1} site(s), reviewed {_VALUE_FREE[rel][0]}"]


def test_every_name_only_call_in_the_tree_is_a_reviewed_value_free_site() -> None:
    root = repo_root()
    sources = {}
    for rel in REACH.examined(root):
        text = (root / rel).read_text(encoding="utf-8")
        if _NAME in text:
            sources[rel] = text
    assert len(sources) >= 3, f"only {len(sources)} files name the classifier; the scan is blind"
    bad = _unreviewed(sources)
    assert not bad, (
        f"#17336: {bad}. A caller holding a value must call `is_credential_entry(name, value, policy)`; "
        f"the name-only `{_NAME}` would unmask a credential stored under a quantity-shaped name. "
        "A genuinely value-free site goes in _VALUE_FREE with its reason."
    )


def test_every_allowlisted_site_still_exists() -> None:
    root = repo_root()
    for rel, (count, reason) in _VALUE_FREE.items():
        assert reason, rel
        assert _sites((root / rel).read_text(encoding="utf-8")) == count, f"{rel} no longer has {count} site(s)"
