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
under ``.github/codeql/`` must be the value of a ``config-file:`` key in
``.github/workflows/codeql.yml``, a ``uses:`` key under a ``codeql-config.yml``
``queries:`` entry, or a value under its ``packs:`` key (#16302). Both files are
parsed with ``yaml.safe_load`` rather than scanned for the filename as a
substring, so a name that only appears in a comment -- never loaded by CodeQL --
is flagged instead of sitting there unread.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from repo_tests._paths import repo_root

_CODEQL_DIR = repo_root() / ".github" / "codeql"
_WORKFLOW = repo_root() / ".github" / "workflows" / "codeql.yml"
_CONFIG = _CODEQL_DIR / "codeql-config.yml"


def _normalize(value: object) -> str | None:
    """A YAML path value, with a leading ``./`` stripped -- or None if it isn't a string."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[2:] if value.startswith("./") else value


def _flatten(node: object) -> list[object]:
    """Every leaf value under *node*, however deep -- ``packs:`` nests by language."""
    if isinstance(node, dict):
        return [leaf for value in node.values() for leaf in _flatten(value)]
    if isinstance(node, list):
        return [leaf for value in node for leaf in _flatten(value)]
    return [node]


def _init_steps(workflow: dict) -> list[dict]:
    """Every step across every job whose ``uses:`` is a ``codeql-action/init`` call."""
    return [
        step
        for job in (workflow.get("jobs") or {}).values()
        if isinstance(job, dict)
        for step in (job.get("steps") or [])
        if isinstance(step, dict) and "codeql-action/init" in str(step.get("uses", ""))
    ]


def referenced_codeql_paths(workflow_path: Path, config_path: Path) -> set[str]:
    """Paths named as a ``config-file:``, a ``queries: - uses:``, or a ``packs:`` value.

    Not a filename substring search: a step's own ``uses:`` (the action reference,
    e.g. ``github/codeql-action/init@...``) is deliberately not a source -- only a
    ``uses:`` nested under a CodeQL config's ``queries:`` list counts.
    """
    referenced: set[str] = set()

    if workflow_path.is_file():
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8")) or {}
        for step in _init_steps(workflow):
            normalized = _normalize((step.get("with") or {}).get("config-file"))
            if normalized:
                referenced.add(normalized)

    if config_path.is_file():
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        for query in config.get("queries") or []:
            if isinstance(query, dict):
                normalized = _normalize(query.get("uses"))
                if normalized:
                    referenced.add(normalized)
        for leaf in _flatten(config.get("packs")):
            normalized = _normalize(leaf)
            if normalized:
                referenced.add(normalized)

    return referenced


def unreferenced_codeql_files(codeql_dir: Path, workflow_path: Path, config_path: Path) -> list[str]:
    """Every file under *codeql_dir* whose path is nowhere in :func:`referenced_codeql_paths`."""
    if not codeql_dir.is_dir():
        return [f"{codeql_dir} is missing -- no CodeQL config directory was checked"]
    files = sorted(p for p in codeql_dir.rglob("*") if p.is_file())
    if not files:
        return [f"{codeql_dir} has no files -- nothing was checked, which is not a clean pass"]
    referenced = referenced_codeql_paths(workflow_path, config_path)
    root = codeql_dir.parent.parent
    return [
        f"{path} is not a config-file/uses/packs value in {workflow_path.name} or {config_path.name}"
        for path in files
        if path.relative_to(root).as_posix() not in referenced
    ]


# --------------------------------------------------------------------------
# The live tree
# --------------------------------------------------------------------------


def test_the_config_file_exists_and_is_referenced_by_the_workflow() -> None:
    """The population floor: the workflow's init step must point config-file at the real config."""
    assert _CONFIG.is_file(), f"{_CONFIG} is missing"
    assert _WORKFLOW.is_file(), f"{_WORKFLOW} is missing"
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8")) or {}
    init_steps = _init_steps(workflow)
    assert init_steps, f"{_WORKFLOW.name} has no github/codeql-action/init step"
    config_file = _normalize((init_steps[0].get("with") or {}).get("config-file"))
    expected = _CONFIG.relative_to(repo_root()).as_posix()
    assert config_file == expected, f"init step's config-file ({config_file!r}) does not point at {expected}"


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
    workflow.write_text(
        "jobs:\n"
        "  analyze:\n"
        "    steps:\n"
        "      - uses: actions/checkout@v7\n"
        "      - name: Initialize CodeQL\n"
        "        uses: github/codeql-action/init@deadbeef\n"
        "        with:\n"
        "          languages: python\n"
        "          config-file: ./.github/codeql/codeql-config.yml\n",
        encoding="utf-8",
    )
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


def test_a_file_named_under_packs_is_not_flagged(tmp_path: Path) -> None:
    codeql_dir, workflow, config = _plant_referenced_pair(tmp_path)
    config.write_text(
        'name: "x"\npacks:\n  python:\n    - .github/codeql/extra-pack.qls\n',
        encoding="utf-8",
    )
    extra_pack = codeql_dir / "extra-pack.qls"
    extra_pack.write_text("- query: py/full-ssrf\n", encoding="utf-8")

    assert unreferenced_codeql_files(codeql_dir, workflow, config) == []


def test_a_name_only_in_a_comment_is_unreferenced(tmp_path: Path) -> None:
    """A filename mentioned only in a YAML comment was never loaded by anything -- flag it."""
    codeql_dir, workflow, config = _plant_referenced_pair(tmp_path)
    workflow.write_text(
        workflow.read_text(encoding="utf-8") + "# ghost.qls used to be referenced here too\n",
        encoding="utf-8",
    )
    ghost = codeql_dir / "ghost.qls"
    ghost.write_text("- query: py/full-ssrf\n", encoding="utf-8")

    problems = unreferenced_codeql_files(codeql_dir, workflow, config)
    assert len(problems) == 1, problems
    assert "ghost.qls" in problems[0]


def test_a_missing_codeql_dir_is_a_failure(tmp_path: Path) -> None:
    problems = unreferenced_codeql_files(tmp_path / "nope", tmp_path / "codeql.yml", tmp_path / "codeql-config.yml")
    assert len(problems) == 1 and "missing" in problems[0], problems


def test_an_empty_codeql_dir_is_a_failure(tmp_path: Path) -> None:
    codeql_dir = tmp_path / ".github" / "codeql"
    codeql_dir.mkdir(parents=True)
    problems = unreferenced_codeql_files(codeql_dir, tmp_path / "codeql.yml", codeql_dir / "codeql-config.yml")
    assert len(problems) == 1 and "no files" in problems[0], problems
