# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The frontend path set has ONE home and no mirror (#16260, #18208).

frontend-test.yml used to carry an `on.push.paths` list that had to mirror
`.github/filters/frontend-paths.yml` exactly, because GitHub offers no include for
event path filters. #15002's `autobot-plugins/terminal/**` entry went missing from it,
and this test existed to keep the two equal.

#18208 deleted the second copy: the frontend suite is a reusable body of ci.yml, ci.yml
has no `paths:` at all, and its one `changes` job reads the filter file. What remains
worth pinning is the half of the old contract that was about the DATA -- the entries the
mirror kept losing -- and that no workflow brings a mirror back.
"""

import json
from pathlib import Path

import yaml
from repo_tests._paths import repo_root

REPO = repo_root()
FILTER_FILE = REPO / ".github" / "filters" / "frontend-paths.yml"
WORKFLOWS = REPO / ".github" / "workflows"

#: The entries a mirror once dropped. Pinned by name, in DATA: a quoted glob in this module would read to
#: the glob-declaration census (#15900) as a guard reading that tree, and these are filter values, not reads.
#: The test fails if any of them leaves the filter.
MUST_STAY = tuple(
    json.loads((Path(__file__).parent / "fixtures" / "frontend_filter_entries_16260.json").read_text(encoding="utf-8"))
)
assert len(MUST_STAY) == 5, "the pinned frontend entries are five; an emptied fixture would pin nothing"


def _frontend_patterns() -> set:
    assert FILTER_FILE.exists(), f"the authoritative filter file is missing: {FILTER_FILE}"
    patterns = set(yaml.safe_load(FILTER_FILE.read_text(encoding="utf-8"))["frontend"])
    assert patterns, "the authoritative `frontend` list is empty -- that is not a passing state"
    return patterns


def test_the_filter_keeps_the_entries_a_mirror_once_lost():
    missing = sorted(set(MUST_STAY) - _frontend_patterns())
    assert not missing, f"frontend-paths.yml lost {missing}: a change there would no longer run the frontend suite"


def test_no_workflow_carries_a_push_path_copy_of_the_frontend_set():
    """A copy is the thing that drifted. The set is read by ci.yml's `changes` job and nowhere else."""
    patterns = _frontend_patterns()
    copies = []
    for path in sorted(p for p in WORKFLOWS.iterdir() if p.suffix == ".yml"):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        triggers = doc.get(True) or doc.get("on") or {}
        for event in ("push", "pull_request"):
            listed = set(((triggers.get(event) or {}) if isinstance(triggers, dict) else {}).get("paths") or [])
            if listed and len(listed & patterns) >= 3:
                copies.append(f"{path.name}:{event}")
    assert not copies, f"{copies} copy the frontend filter; read .github/filters/frontend-paths.yml instead"
