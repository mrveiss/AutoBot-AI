# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No path pattern was lost when change detection moved into ci.yml's one job (#18208).

`fixtures/pre_15360_changes_jobs.json` freezes what sixteen workflows' `changes` jobs
read before #15360 (generated from `origin/main` at the time). It was the baseline for
`changes_job_equivalence_15360_test.py`, which proved a reusable-workflow refactor
changed nothing -- a refactor #18208 replaced wholesale, so that test went with it.
The question that survives is the one about the DATA: every pattern those jobs read is
still read, under the key's new home.

Allowed differences, and only these:

* a key was renamed so it is unique across `.github/filters/` (`python` -> `static_analysis`
  and `backend` -> `startup_smoke` in backend-python-paths.yml);
* an inline filter moved into `.github/filters/gate-paths.yml` (`browser_worker` ->
  `npm_browser_worker`, and so on);
* a `.github/workflows/<x>.yml` self-reference to a workflow file that NO LONGER EXISTS
  was dropped; ci.yml's `self` filter (`ci.yml`, `_gate-*.yml`, the gate-verdict action)
  forces every gate instead. A dropped reference to a file that still exists fails.

Anything else missing is a gate that stopped running on a path it used to run on, and
that is the silent direction.
"""

import json
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

REPO = repo_root()
FIXTURE = Path(__file__).parent / "fixtures" / "pre_15360_changes_jobs.json"
FILTERS = REPO / ".github" / "filters"

#: (old file, old key) -> new key, for the renames that made every key unique.
FILE_KEY_RENAMES = {
    ("backend-python-paths.yml", "python"): "static_analysis",
    ("backend-python-paths.yml", "backend"): "startup_smoke",
}
#: inline key in the pre-#15360 workflow -> its key in gate-paths.yml.
INLINE_KEY_MOVES = {
    "migrations": "migrations",
    "types": "types",
    "slm_types": "slm_types",
    "slm_frontend": "slm_frontend",
    "browser_worker": "npm_browser_worker",
    "mcp": "npm_mcp",
    "sdk_ts": "npm_sdk_ts",
    "structured_thinking": "npm_structured_thinking",
}


def _flat(value) -> set:
    """Flatten the nested lists a YAML anchor produces into a set of strings."""
    if isinstance(value, str):
        return {value}
    out: set = set()
    for item in value or []:
        out |= _flat(item)
    return out


def _new_keys(name: str) -> dict:
    return yaml.safe_load((FILTERS / name).read_text(encoding="utf-8"))


def _records():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for workflow, rec in sorted(data.items()):
        src = rec["filters"]
        if "file" in src:
            fname = Path(src["file"]).name
            for key, patterns in src["content"].items():
                yield workflow, fname, key, FILE_KEY_RENAMES.get((fname, key), key), _flat(patterns), "file"
        else:
            for key, patterns in src["inline"].items():
                yield workflow, "gate-paths.yml", key, INLINE_KEY_MOVES[key], _flat(patterns), "inline"


_CASES = list(_records())


def test_the_fixture_is_read_in_full():
    """A fixture that parsed to nothing would pass every case below vacuously."""
    assert len(_CASES) >= 25
    assert {c[0] for c in _CASES} >= {
        "api-wiring",
        "code-quality",
        "docker-smoke-test",
        "migration-gate",
        "npm-package-tests",
    }


@pytest.mark.parametrize("case", _CASES, ids=[f"{c[0]}:{c[2]}" for c in _CASES])
def test_every_pattern_a_changes_job_read_is_still_read(case):
    workflow, new_file, old_key, new_key, old_patterns, _ = case
    new = _new_keys(new_file)
    assert new_key in new, f"{new_file} has no key {new_key!r} (was {old_key!r} in {workflow})"
    lost = old_patterns - _flat(new[new_key])
    stale_self_refs = {p for p in lost if p.startswith(".github/workflows/") and not (REPO / p).exists()}
    assert lost - stale_self_refs == set(), (
        f"{workflow}:{old_key} read {sorted(lost - stale_self_refs)} before #15360; {new_file}:{new_key} no longer does. "
        "Only a self-reference to a workflow file that is gone may be dropped (ci.yml's `self` covers it)."
    )


#: #17822 widened the Migration Gate on purpose: its filter used to list where its tests live, not the
#: code they import. The pinned set is DATA (`fixtures/issue_17822_migration_gate_entries.json`),
#: separate from the regenerable pre-#15360 fixture, so removing an entry from gate-paths.yml still
#: fails here. It was held by changes_job_equivalence_15360_test.py until #18208 retired that test.
ISSUE_17822_FIXTURE = Path(__file__).parent / "fixtures" / "issue_17822_migration_gate_entries.json"
#: 14 = the eleven #17822 entries plus `services/__init__.py`, `services/approval_gate_service.py` and
#: `llc/services/workspace_lease.py` (#17996), which the migration tests import.
ISSUE_17822_COUNT = 14


def test_the_issue_17822_migration_entries_are_still_read():
    entries = json.loads(ISSUE_17822_FIXTURE.read_text(encoding="utf-8"))
    assert len(entries) == ISSUE_17822_COUNT, "an emptied fixture would pin nothing"
    migrations = _flat(_new_keys("gate-paths.yml")["migrations"])
    missing = sorted(set(entries) - migrations)
    assert not missing, f"gate-paths.yml `migrations` no longer reads the #17822 entries {missing}"
