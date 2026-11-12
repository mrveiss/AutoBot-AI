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
import re
from pathlib import Path

import pytest
import yaml
from repo_tests._filter_entries import doc_entries, removed_without_tombstone, uncited
from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_text

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


#: The Migration Gate's `migrations` list was widened on purpose over time (#17822 and the issues cited
#: beside each entry in gate-paths.yml): it listed where its tests live, not the code they import. It is
#: judged by the same rules as every other path filter (#21205, `repo_tests/_filter_entries.py`) -- no
#: frozen table of additions: the pre-#15360 snapshot stays in order, each entry beyond it cites its issue
#: where it is written, and no entry the merge base had goes without a `# retired #NNNN: '<entry>'`
#: tombstone. A snapshot self-reference to a workflow file that no longer exists is not an entry any more.
MIGRATIONS_KEY = "migrations"
GATE_PATHS = ".github/filters/gate-paths.yml"


def _migrations_section(text: str) -> str:
    """The `migrations:` key of gate-paths.yml with its entries and comments, up to the next top-level key."""
    match = re.search(rf"^{MIGRATIONS_KEY}:.*?(?=^[A-Za-z0-9_-]+:)", text + "\nend:", re.S | re.M)
    assert match, f"gate-paths.yml has no {MIGRATIONS_KEY!r} key"
    return match.group(0)


def _migrations_snapshot() -> list[tuple[str, str]]:
    pre = json.loads(FIXTURE.read_text(encoding="utf-8"))["migration-gate"]["filters"]["inline"]
    entries = doc_entries({MIGRATIONS_KEY: pre[MIGRATIONS_KEY]})
    return [(k, v) for k, v in entries if not (v.startswith(".github/workflows/") and not (REPO / v).exists())]


def test_the_migrations_snapshot_is_not_vacuous():
    assert len(_migrations_snapshot()) >= 9, "an emptied snapshot would judge nothing"


def test_migrations_keeps_its_snapshot_and_cites_every_addition_in_place():
    text = (REPO / GATE_PATHS).read_text(encoding="utf-8")
    section = _migrations_section(text)
    base = base_text(REPO, GATE_PATHS)
    found = uncited(section, _migrations_snapshot(), None if base is None else _migrations_section(base))
    assert not found, "; ".join(found)


def test_no_migrations_entry_the_merge_base_had_is_removed_without_a_tombstone():
    """`BaseUnavailable` is never a pass: it propagates and the test errors. A base without the file has nothing to lose."""
    base = base_text(REPO, GATE_PATHS)
    head = _migrations_section((REPO / GATE_PATHS).read_text(encoding="utf-8"))
    found = removed_without_tombstone(None if base is None else _migrations_section(base), head)
    assert not found, "; ".join(found)


# --- the filter-entry rules of #21205 for the filter FILES a converted `changes` job read -----------------
#: changes_job_equivalence_15360_test.py held rules 1-3 for these files until #18208 retired it; they move
#: here so deleting that test does not lift them. A workflow file the refactor deleted is retired with a
#: `# retired #18208: '<entry>'` tombstone in the filter that listed it.
_FILTER_FILES = sorted({c[1] for c in _CASES if c[5] == "file"})


def _file_snapshot(fname: str) -> list[tuple[str, str]]:
    """The pre-#15360 entries of one filter file under their current key names, minus deleted workflow files."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    entries: list[tuple[str, str]] = []
    for rec in data.values():
        src = rec["filters"]
        if "file" in src and Path(src["file"]).name == fname:
            renamed = {FILE_KEY_RENAMES.get((fname, k), k): v for k, v in src["content"].items()}
            entries = doc_entries(renamed)
    return [(k, v) for k, v in entries if not (v.startswith(".github/workflows/") and not (REPO / v).exists())]


def _base_with_new_key_names(fname: str) -> str | None:
    """The filter file at the merge base, its top-level keys renamed the way #18208 renamed them."""
    text = base_text(REPO, f".github/filters/{fname}")
    for (file, old), new in FILE_KEY_RENAMES.items():
        if text is not None and file == fname:
            text = re.sub(rf"^{re.escape(old)}:", f"{new}:", text, flags=re.M)
    return text


def test_the_filter_files_under_the_rules_are_not_a_vacuous_set():
    assert len(_FILTER_FILES) >= 5
    assert all(len(_file_snapshot(f)) >= 5 for f in _FILTER_FILES), "an emptied snapshot would judge nothing"


@pytest.mark.parametrize("fname", _FILTER_FILES)
def test_a_filter_file_keeps_its_snapshot_and_declares_every_addition_in_place(fname):
    text = (FILTERS / fname).read_text(encoding="utf-8")
    found = uncited(text, _file_snapshot(fname), _base_with_new_key_names(fname))
    assert not found, f"{fname}: " + "; ".join(found)


@pytest.mark.parametrize("fname", _FILTER_FILES)
def test_no_filter_file_entry_the_merge_base_had_is_removed_without_a_tombstone(fname):
    """`BaseUnavailable` is never a pass: it propagates and the test errors."""
    text = (FILTERS / fname).read_text(encoding="utf-8")
    found = removed_without_tombstone(_base_with_new_key_names(fname), text)
    assert not found, f"{fname}: " + "; ".join(found)
