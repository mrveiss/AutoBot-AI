# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Published OpenAPI specs must not carry the Rust regex end anchor.

pydantic >= 2.12 emits ``\\z`` in JSON Schema for a ``Field(pattern=...)`` the
author wrote with ``$``. JSON Schema's regex dialect is ECMA-262, which has no
``\\z`` — so consumers do not reject the spec, they misread it:

    JS   /^(hour|day)\\z/.test("hour")  -> False   the valid value fails
    JS   /^(hour|day)\\z/.test("hourz") -> True    an invalid value passes
    Py   re.match(r"^(hour|day)\\z", …) -> re.error: bad escape \\z

Both measured. Validation is inverted for every JS client and impossible for
every Python one, from a spec that looks fine in review.

Surfaced by `verify-generated-types-slm` failing on a PR that touched no schema:
the committed spec had ``$`` and a fresh dump produced ``\\z``, so CI reported
"generated types are stale". Regenerating would have made CI green by publishing
the broken contract. Normalising at the dump instead keeps the artifact portable
and the check meaningful.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from autobot_shared.openapi_schema import normalize_pattern_anchors

_REPO = Path(__file__).resolve().parents[2]
_SLM_SPEC = _REPO / "autobot-slm-frontend" / "openapi.json"


def test_trailing_rust_anchor_becomes_dollar():
    assert normalize_pattern_anchors({"pattern": "^(hour|day)\\z"}) == {"pattern": "^(hour|day)$"}


def test_nested_and_listed_schemas_are_reached():
    spec = {
        "components": {
            "schemas": {
                "A": {"properties": {"x": {"pattern": "^a\\z"}}},
                "B": {"anyOf": [{"pattern": "^b\\z"}, {"pattern": "^c$"}]},
            }
        }
    }
    out = normalize_pattern_anchors(spec)
    assert out["components"]["schemas"]["A"]["properties"]["x"]["pattern"] == "^a$"
    assert [s["pattern"] for s in out["components"]["schemas"]["B"]["anyOf"]] == ["^b$", "^c$"]


def test_already_normalized_patterns_are_untouched():
    """Idempotence matters: CI regenerates and diffs, so a second pass must be a no-op."""
    spec = {"pattern": "^(hour|day)$"}
    assert normalize_pattern_anchors(normalize_pattern_anchors(spec)) == spec


def test_non_pattern_keys_and_values_are_untouched():
    spec = {"description": "ends with \\z", "default": 10, "enum": ["a\\z"]}
    assert normalize_pattern_anchors(spec) == spec


def test_a_literal_backslash_z_mid_pattern_survives():
    """Only a trailing anchor is rewritten — pydantic never emits one elsewhere.

    Rewriting a mid-pattern occurrence would corrupt a pattern that genuinely
    means a literal backslash followed by ``z``.
    """
    spec = {"pattern": "^a\\zb$"}
    assert normalize_pattern_anchors(spec) == spec


def test_committed_slm_spec_carries_no_rust_anchor():
    """The published artifact itself, not just the helper."""
    if not _SLM_SPEC.is_file():
        pytest.skip(f"{_SLM_SPEC} not present")

    offending = [
        (path, value)
        for path, value in _iter_patterns(json.loads(_SLM_SPEC.read_text(encoding="utf-8")))
        if value.endswith("\\z")
    ]
    assert not offending, (
        "the committed SLM OpenAPI spec publishes Rust end anchors, which every JS "
        "consumer misreads and every Python one refuses to compile:\n  "
        + "\n  ".join(f"{p}: {v}" for p, v in offending)
    )


def test_every_committed_pattern_compiles_as_a_python_regex():
    """A pattern no consumer can compile is not a constraint, it is a landmine."""
    if not _SLM_SPEC.is_file():
        pytest.skip(f"{_SLM_SPEC} not present")

    broken = []
    for path, value in _iter_patterns(json.loads(_SLM_SPEC.read_text(encoding="utf-8"))):
        try:
            re.compile(value)
        except re.error as exc:
            broken.append(f"{path}: {value!r} -> {exc}")

    assert not broken, "uncompilable patterns in the published spec:\n  " + "\n  ".join(broken)


def test_both_dump_paths_normalize():
    """CI regenerates via audit_api_wiring.py and diffs against dump_openapi.py output.

    If only one normalises, every PR touching the SLM backend is reported as
    having stale generated types — which is exactly how this was found.
    """
    for script in ("autobot-slm-backend/scripts/dump_openapi.py", "scripts/audit_api_wiring.py"):
        text = (_REPO / script).read_text(encoding="utf-8")
        assert "normalize_pattern_anchors(app.openapi())" in text, (
            f"{script} dumps app.openapi() without normalising; the two dump paths "
            "must produce byte-identical specs or the freshness check is meaningless"
        )


def test_rust_anchor_is_genuinely_unusable_in_python():
    """Pins the premise, so nobody 'simplifies' this away as cosmetic."""
    with pytest.raises(re.error):
        re.compile("^(hour|day)\\z")


def test_node_reads_the_rust_anchor_as_a_literal_z():
    """The JS half of the premise — silent, which is why it matters more."""
    node = subprocess.run(["node", "--version"], capture_output=True)
    if node.returncode != 0:
        pytest.skip("node not available")

    script = 'const r=/^(hour|day)\\z/;console.log(r.test("hour"),r.test("hourz"))'
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == "false true", (
        "expected the valid value to fail and the invalid one to pass; got " + out.stdout.strip()
    )


def _iter_patterns(node, path="$"):
    """Yield ``(json_path, pattern)`` for every ``pattern`` string in the spec."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "pattern" and isinstance(value, str):
                yield f"{path}.{key}", value
            else:
                yield from _iter_patterns(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _iter_patterns(item, f"{path}[{index}]")
