# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""frontend-test.yml's push paths must still mirror .github/filters/frontend-paths.yml (#16260).

GitHub requires event path filters to be inline, so the authoritative list in
``.github/filters/frontend-paths.yml`` cannot be shared with ``on.push.paths``
-- the workflow says so itself, and calls the copy a mirror. Nothing checked
that the mirror still matched.

It did not. #15002 added ``autobot-plugins/terminal/**`` to the filter file so
that a plugin-only edit would run the redactor drift guard, then dropped the
same entry from this mirror because the hardcoded-values hook made the workflow
file unstageable (#16260, fixed in #17329). A plugin-only push therefore did
not run the frontend suite after merge, for months, while the PR gate -- fed by
the authoritative file -- looked correct. Drift in this direction is silent by
construction: both files parse, both workflows run, and the only symptom is a
suite that quietly does not execute.

Scope, deliberately: this pins the copy that DECLARES itself a mirror. The
inline ``frontend`` filter in ci.yml is a different and much narrower list
(3 of these 8 entries) gating that workflow's own frontend-tests job; whether
it should mirror this list is a coverage decision, not a drift, and is filed
separately rather than asserted here.
"""

from pathlib import Path

import yaml
from repo_tests._paths import repo_root

REPO = repo_root()
FILTER_FILE = REPO / ".github" / "filters" / "frontend-paths.yml"
WORKFLOW = REPO / ".github" / "workflows" / "frontend-test.yml"


def _push_paths(workflow: Path) -> list[str]:
    """``on.push.paths``, tolerating YAML 1.1 parsing ``on:`` as the boolean True."""
    loaded = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    triggers = loaded.get("on", loaded.get(True))
    assert triggers is not None, f"{workflow.name} declares no triggers at all"
    return list(triggers["push"]["paths"])


def test_the_push_mirror_matches_the_authoritative_filter_exactly():
    assert FILTER_FILE.exists(), f"the authoritative filter file is missing: {FILTER_FILE}"
    authoritative = set(yaml.safe_load(FILTER_FILE.read_text(encoding="utf-8"))["frontend"])
    assert authoritative, "the authoritative `frontend` list is empty — that is not a passing state"

    mirror = set(_push_paths(WORKFLOW))

    missing = sorted(authoritative - mirror)
    extra = sorted(mirror - authoritative)
    assert not missing, (
        "frontend-test.yml's on.push.paths no longer mirrors .github/filters/frontend-paths.yml. "
        f"A change matching these patterns would NOT run the suite after merge: {missing}. "
        "This is exactly how #15002's autobot-plugins/terminal/** entry went missing (#16260)."
    )
    assert not extra, (
        "frontend-test.yml's on.push.paths carries patterns the authoritative filter does not: "
        f"{extra}. The filter file is authoritative (#13405) — add them there, or drop them here."
    )
