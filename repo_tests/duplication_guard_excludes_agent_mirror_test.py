# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The SLM scope's jscpd run must ignore the drift-checked agent mirror (#16401).

``autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent/`` is a mandatory
Ansible-shipped mirror of ``autobot-slm-backend/slm/agent/``, kept byte-identical
by ``ansible/tests/detect_agent_code_drift_test.py``. Before #16401, the SLM
scope's jscpd invocation had no ignore for it, so every change to agent code
(made in both copies, because the drift test requires it) grew the clone count
and tripped the absolute pin (#16319) -- 4,740 duplicated lines measured against
a 4,729 pin on merge train g (#16392).

These tests read the ignore list off the real workflow step, translate its glob
to a regex, and check it against real paths -- rather than asserting a literal
substring -- so the test still catches a *widened* pattern that happens to keep
the old text as a substring (e.g. broadening to ``**/ansible/**``).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from repo_tests._paths import repo_root

WORKFLOW = Path(".github/workflows/duplication-guard.yml")

#: The path the drift test forces byte-identical to its source (#16401).
MIRROR_PATH = "autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent/health_collector.py"
#: The canonical source of that mirror -- real duplication-guard work, must stay scanned.
CANONICAL_SOURCE_PATH = "autobot-slm-backend/slm/agent/health_collector.py"
#: A different Ansible role's mirrored files -- an ignore "widened beyond that path" would
#: also start skipping this, and nothing guards ITS drift.
SIBLING_ROLE_MIRROR_PATH = "autobot-slm-backend/ansible/roles/backend/files/permission_rules.yaml"


def _slm_scope_run() -> str:
    document = yaml.safe_load((repo_root() / WORKFLOW).read_text(encoding="utf-8"))
    job = document["jobs"][next(iter(document["jobs"]))]
    for step in job["steps"]:
        if step.get("id") == "slm_scope":
            return step["run"]
    raise AssertionError("no step with id 'slm_scope' in duplication-guard.yml")


def _ignore_patterns() -> list[str]:
    """The comma-separated globs passed to jscpd's ``-i`` flag, as a list."""
    run = _slm_scope_run()
    match = re.search(r'-i "([^"]+)"', run)
    assert match, 'slm_scope step has no -i "..." ignore list'
    return match.group(1).split(",")


def _glob_to_regex(pattern: str) -> re.Pattern:
    """Minimal ``**``/``*`` glob translator, matched against real repo-relative paths.

    ``**`` becomes ``.*`` (crosses directory boundaries, jscpd/micromatch semantics);
    a bare ``*`` becomes ``[^/]*`` (stays within one path segment). Everything else is
    a literal, escaped segment-by-segment so a literal ``/`` never becomes part of a
    regex quantifier.
    """
    segments = [re.escape(part).replace(r"\*", "[^/]*") if part != "**" else ".*" for part in pattern.split("/")]
    return re.compile("^" + "/".join(segments) + "$")


def test_the_slm_scope_has_an_ignore_matching_the_drift_checked_mirror() -> None:
    """AC1: the mirror the drift test guards must be excluded, not just something near it."""
    patterns = _ignore_patterns()
    matching = [p for p in patterns if _glob_to_regex(p).match(MIRROR_PATH)]
    assert matching, (
        f"no ignore glob in the SLM scope matches {MIRROR_PATH!r} -- "
        f"the drift-checked mirror is being scanned as duplication again"
    )


def test_the_mirror_ignore_does_not_also_swallow_the_canonical_source() -> None:
    """The canonical agent tree is real code; excluding it would hide actual duplication."""
    patterns = _ignore_patterns()
    matching = [p for p in patterns if _glob_to_regex(p).match(CANONICAL_SOURCE_PATH)]
    assert not matching, (
        f"an SLM-scope ignore glob ({matching}) also matches the canonical source "
        f"{CANONICAL_SOURCE_PATH!r} -- too broad, it would hide real duplication there"
    )


def test_the_mirror_ignore_does_not_widen_to_a_sibling_roles_files() -> None:
    """AC3: a widened glob (e.g. ``**/ansible/**``) must fail this test.

    A sibling role's mirrored files have no drift test of their own, so excluding
    them from jscpd would be a silent, undeclared exemption -- exactly what
    RATCHET_BASELINES.md rule 1 says a ratchet must not carry.
    """
    patterns = _ignore_patterns()
    matching = [p for p in patterns if _glob_to_regex(p).match(SIBLING_ROLE_MIRROR_PATH)]
    assert not matching, (
        f"an SLM-scope ignore glob ({matching}) also matches {SIBLING_ROLE_MIRROR_PATH!r} -- "
        f"the mirror exclusion has widened past the one path #16401 justified"
    )
