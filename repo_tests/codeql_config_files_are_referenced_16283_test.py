# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A file under ``.github/codeql/`` that nothing loads is not a scan (#16283 AC3).

``.github/codeql/python-exclusions.qls`` sat in the tree describing a Python
query-suite exclusion in its header, and was loaded by nothing: neither
``.github/workflows/codeql.yml`` nor ``.github/codeql/codeql-config.yml`` named
it, and CodeQL never read it (``git grep python-exclusions.qls`` found 0 hits).
Nothing failed -- the file just described a suppression the analysis never
applied, the same "config claims a scan that doesn't run" shape as #16302. It
was retired once its one exclusion pair was shown to already live in
``codeql-config.yml``.

This guard is the standing check for the next such file: every file directly
under ``.github/codeql/`` must be named -- by its filename -- somewhere in
``.github/workflows/codeql.yml`` (for example a ``config-file:`` value) or in
``.github/codeql/codeql-config.yml`` (for example a ``queries: - uses:`` entry
or a ``packs:`` entry). A file named in neither is flagged instead of sitting
there unread.
"""

from __future__ import annotations

from pathlib import Path

from repo_tests._paths import repo_root

_CODEQL_DIR = repo_root() / ".github" / "codeql"
_WORKFLOW = repo_root() / ".github" / "workflows" / "codeql.yml"
_CONFIG = _CODEQL_DIR / "codeql-config.yml"


def _haystack(workflow_path: Path, config_path: Path) -> str:
    """The text a reference must show up in: the workflow plus the CodeQL config."""
    texts = [p.read_text(encoding="utf-8") for p in (workflow_path, config_path) if p.is_file()]
    return "\n".join(texts)


def unreferenced_codeql_files(codeql_dir: Path, workflow_path: Path, config_path: Path) -> list[str]:
    """Every file under *codeql_dir* whose filename names nowhere in the haystack."""
    if not codeql_dir.is_dir():
        return [f"{codeql_dir} is missing -- no CodeQL config directory was checked"]
    files = sorted(p for p in codeql_dir.rglob("*") if p.is_file())
    if not files:
        return [f"{codeql_dir} has no files -- nothing was checked, which is not a clean pass"]
    haystack = _haystack(workflow_path, config_path)
    return [
        f"{path} is named by nothing in {workflow_path.name} or {config_path.name}"
        for path in files
        if path.name not in haystack
    ]


# --------------------------------------------------------------------------
# The live tree
# --------------------------------------------------------------------------


def test_the_config_file_exists_and_is_referenced_by_the_workflow() -> None:
    """The population floor: a missing config, or one the workflow never names, is not a clean pass."""
    assert _CONFIG.is_file(), f"{_CONFIG} is missing"
    assert _WORKFLOW.is_file(), f"{_WORKFLOW} is missing"
    assert _CONFIG.name in _WORKFLOW.read_text(
        encoding="utf-8"
    ), f"{_CONFIG.name} is not referenced from {_WORKFLOW.name}"


def test_every_live_codeql_file_is_referenced() -> None:
    """An empty result means the directory was read: missing or unreferenced is a problem, not a pass."""
    assert unreferenced_codeql_files(_CODEQL_DIR, _WORKFLOW, _CONFIG) == []


# --------------------------------------------------------------------------
# Discrimination -- planted trees
# --------------------------------------------------------------------------


def _plant_referenced_pair(tmp_path: Path) -> tuple[Path, Path, Path]:
    codeql_dir = tmp_path / ".github" / "codeql"
    codeql_dir.mkdir(parents=True)
    workflow = tmp_path / "codeql.yml"
    workflow.write_text("config-file: ./.github/codeql/codeql-config.yml\n", encoding="utf-8")
    config = codeql_dir / "codeql-config.yml"
    config.write_text('name: "x"\n', encoding="utf-8")
    return codeql_dir, workflow, config


def test_an_unreferenced_file_is_flagged(tmp_path: Path) -> None:
    codeql_dir, workflow, config = _plant_referenced_pair(tmp_path)
    orphan = codeql_dir / "python-exclusions.qls"
    orphan.write_text("- query: py/full-ssrf\n", encoding="utf-8")

    problems = unreferenced_codeql_files(codeql_dir, workflow, config)
    assert len(problems) == 1, problems
    assert "python-exclusions.qls" in problems[0]


def test_a_file_named_in_the_config_is_not_flagged(tmp_path: Path) -> None:
    codeql_dir, workflow, config = _plant_referenced_pair(tmp_path)
    config.write_text(
        'name: "x"\nqueries:\n  - uses: ./.github/codeql/queries/extra.ql\n',
        encoding="utf-8",
    )
    extra = codeql_dir / "queries" / "extra.ql"
    extra.parent.mkdir()
    extra.write_text("import python\n", encoding="utf-8")

    assert unreferenced_codeql_files(codeql_dir, workflow, config) == []


def test_a_missing_codeql_dir_is_a_failure(tmp_path: Path) -> None:
    problems = unreferenced_codeql_files(tmp_path / "nope", tmp_path / "codeql.yml", tmp_path / "codeql-config.yml")
    assert len(problems) == 1 and "missing" in problems[0], problems


def test_an_empty_codeql_dir_is_a_failure(tmp_path: Path) -> None:
    codeql_dir = tmp_path / ".github" / "codeql"
    codeql_dir.mkdir(parents=True)
    problems = unreferenced_codeql_files(codeql_dir, tmp_path / "codeql.yml", codeql_dir / "codeql-config.yml")
    assert len(problems) == 1 and "no files" in problems[0], problems
