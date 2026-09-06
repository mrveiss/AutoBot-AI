#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The doc-sync hook must resolve to an indexer that exists (#15845).

`post-commit-doc-sync` referenced `tools/index_documentation.py`, which was
never created. Every documentation commit printed the sync banner, listed the
changed files, and exited 0 without indexing anything. Nothing failed, so
nothing was noticed -- `docs/research/_index.md` had drifted five documents
away from the tree by the time anyone looked.

The test that matters here is the path resolution one: it reads the path out of
the hook rather than restating it, so moving the entry point without moving the
hook fails, which is exactly the mistake that was made.
"""

import importlib.util
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "autobot-infrastructure/shared/scripts/hooks/post-commit-doc-sync"
RESEARCH_DIR = REPO_ROOT / "docs/research"


def _hook_text() -> str:
    return HOOK.read_text(encoding="utf-8")


def _referenced_indexer() -> Path:
    """Resolve INDEX_SCRIPT from the hook itself, not from a copy of the string."""
    match = re.search(r'^INDEX_SCRIPT="\$PROJECT_ROOT/(.+)"$', _hook_text(), re.MULTILINE)
    assert match, "hook no longer assigns INDEX_SCRIPT from PROJECT_ROOT"
    return REPO_ROOT / match.group(1)


def test_hook_references_an_indexer_that_exists():
    """The defect itself: the hook pointed at a file nobody had created."""
    indexer = _referenced_indexer()
    assert indexer.is_file(), f"hook references {indexer.relative_to(REPO_ROOT)}, which does not exist"


def test_the_referenced_indexer_is_executable_as_a_script():
    """A service class with no `__main__` is not something a hook can run.

    The indexer existed all along as `DocIndexerService`; what was missing was
    an entry point. Asserting the file exists would have passed on a module
    that `python3 file.py --incremental` does nothing with.
    """
    source = _referenced_indexer().read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in source
    assert "--incremental" in source, "hook invokes --incremental; the entry point must accept it"


def test_not_found_branch_names_the_path_it_looked_for():
    """The old message named no path, so the skip read as 'nothing to do'."""
    text = _hook_text()
    match = re.search(r"Documentation indexer not found[^\"]*", text)
    assert match, "the not-found branch no longer exists"
    assert "$INDEX_SCRIPT" in match.group(0), "the failure message must name the path it looked for"


def _load_entry_point():
    spec = importlib.util.spec_from_file_location("index_documentation", _referenced_indexer())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_incremental_and_force_are_opposite_ends_of_one_knob():
    """`--incremental` is `force=False`; they must not both be settable."""
    module = _load_entry_point()

    assert module.parse_args(["--incremental"]).force is False
    assert module.parse_args(["--force"]).force is True
    # No flag at all is the hook's mode, not a full re-embed.
    assert module.parse_args([]).force is False

    with pytest.raises(SystemExit):
        module.parse_args(["--incremental", "--force"])


def test_entry_point_imports_without_a_backend_or_a_database():
    """Importing must not drag in Chroma, embeddings or config.

    The backend imports live inside `run_index` deliberately: a hook entry point
    that cannot be imported cannot be tested without standing up the stack.
    """
    module = _load_entry_point()
    assert callable(module.main)


def test_every_research_document_is_reachable_from_its_index():
    """The visible symptom: documents present in the tree but in no index.

    Generalised past the five found in #15845 -- a rule that listed those five
    by name would go quiet on the sixth.
    """
    index = (RESEARCH_DIR / "_index.md").read_text(encoding="utf-8")
    linked = set(re.findall(r"^\| \[\[([^\]|]+)\]\]", index, re.MULTILINE))
    on_disk = {p.stem for p in RESEARCH_DIR.glob("*.md")} - {"_index"}

    assert not (on_disk - linked), f"present but unindexed: {sorted(on_disk - linked)}"
    assert not (linked - on_disk), f"indexed but missing from the tree: {sorted(linked - on_disk)}"
