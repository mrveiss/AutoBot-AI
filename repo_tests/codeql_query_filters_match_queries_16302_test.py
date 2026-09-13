# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A CodeQL ``query-filters`` entry must filter on something a query carries (#16302).

``.github/codeql/codeql-config.yml`` carried three "reviewed exclusions" that
paired a query id with a source file through ``files:`` or ``paths:`` inside an
``exclude:`` block. A query filter is a query-suite include/exclude
instruction: its keys are matched against each QUERY's metadata, never against
the files being analysed. No query carries a ``files`` or ``paths`` property, so
none of the three scoped anything. The ``py/full-ssrf`` alert on
``external_importer.py`` stayed open under advanced setup with its entry in
place. They read as suppressions and did nothing, and nothing failed. They are
now applied as code-scanning alert dismissals, and their reasons are comments.

This guard fails on any ``query-filters`` key CodeQL does not match on, so the
next file-scoped entry is a red build instead of a silent no-op. It also fails
when the config is missing or empty, so it cannot read clean on nothing.

The allowlist, and where it comes from
--------------------------------------
* An entry is ``exclude:`` or ``include:`` -- GitHub Docs, "Customizing your
  advanced setup for code scanning", the section on excluding specific queries,
  which sends the reader to query metadata for what a filter can match.
* Inside it, the keys a query-suite constraint accepts -- GitHub Docs,
  "Creating CodeQL query suites" (CodeQL CLI), filtering section: the standard
  metadata keys ``description``, ``id``, ``kind``, ``name``, ``tags``,
  ``precision`` and ``problem.severity``, and the constraints ``query filename``,
  ``query path``, ``tags contain`` and ``tags contain all``.
* ``security-severity`` -- that page says a constraint key "is typically a query
  metadata property", and "Metadata for CodeQL queries" documents
  ``@security-severity``.

``query path`` and ``query filename`` match the path of the QUERY file inside
its pack, not a source file; they are allowed because CodeQL supports them.
``previous-id`` is documented metadata too, left out until a filter needs it:
adding it is one entry here, with its source.

A reason beside an instruction (``reason:``) is not an entry key CodeQL
documents, so it is rejected as well; a reason belongs in a YAML comment.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

_CONFIG = repo_root() / ".github" / "codeql" / "codeql-config.yml"

_ENTRY_KEYS = frozenset({"exclude", "include"})

_CONSTRAINT_KEYS = frozenset(
    {
        "description",
        "id",
        "kind",
        "name",
        "tags",
        "precision",
        "problem.severity",
        "security-severity",
        "query filename",
        "query path",
        "tags contain",
        "tags contain all",
    }
)

_NOT_A_FILE_SCOPE = (
    "a query filter matches query metadata, never a source file, so this entry filters nothing "
    "(#16302). Suppress one query on one file by dismissing the alert; drop a path from every "
    "query with `paths-ignore`."
)


def _load(path: Path) -> tuple[dict | None, list[str]]:
    """The parsed config, or why there is nothing to check -- never an empty pass."""
    if not path.is_file():
        return None, [f"{path} is missing -- no config was checked, which is not a clean config"]
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not document:
        return None, [f"{path} parsed to {document!r}, not a non-empty mapping -- nothing was checked"]
    return document, []


def _constraint_problems(index: int, instruction: str, constraint: object) -> list[str]:
    where = f"query-filters[{index}].{instruction}"
    if not isinstance(constraint, dict) or not constraint:
        return [f"{where} is {constraint!r}, not a non-empty mapping of query-metadata keys"]
    unknown = sorted(set(constraint) - _CONSTRAINT_KEYS, key=str)
    return [f"{where} uses `{key}`, which no CodeQL query carries: {_NOT_A_FILE_SCOPE}" for key in unknown]


def _entry_problems(index: int, entry: object) -> list[str]:
    if not isinstance(entry, dict) or not set(entry) & _ENTRY_KEYS:
        return [f"query-filters[{index}] is {entry!r}, not a mapping with `exclude:` or `include:`"]
    problems = [
        f"query-filters[{index}] has `{key}` beside its instruction -- an entry is `exclude:` or "
        "`include:` only; keep a reason in a YAML comment above it"
        for key in sorted(set(entry) - _ENTRY_KEYS, key=str)
    ]
    for instruction in sorted(set(entry) & _ENTRY_KEYS):
        problems += _constraint_problems(index, instruction, entry[instruction])
    return problems


def query_filter_problems(path: Path) -> list[str]:
    """Every reason *path* is not a config whose query filters all match query metadata."""
    document, problems = _load(path)
    if document is None:
        return problems
    filters = document.get("query-filters", [])
    if not isinstance(filters, list):
        return [f"`query-filters` is {filters!r}, not a list of `exclude:` / `include:` entries"]
    for index, entry in enumerate(filters):
        problems += _entry_problems(index, entry)
    return problems


# --------------------------------------------------------------------------
# The live config
# --------------------------------------------------------------------------


def test_every_live_query_filter_matches_query_metadata() -> None:
    """An empty result here means the config was read: missing or empty is a problem, not a pass."""
    assert query_filter_problems(_CONFIG) == []


# --------------------------------------------------------------------------
# Discrimination -- planted configs, starting with the exact #16302 shapes
# --------------------------------------------------------------------------


def _plant(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "codeql-config.yml"
    path.write_text(text, encoding="utf-8")
    return path


_FILES_SCOPED = (
    "query-filters:\n"
    "  - exclude:\n"
    "      id: py/full-ssrf\n"
    "      files: autobot-backend/skills/external_importer.py\n"
)

_PATHS_SCOPED = (
    "query-filters:\n"
    "  - exclude:\n"
    "      id: py/path-injection\n"
    "      paths:\n"
    "        - autobot-backend/transcriber/upload_security.py\n"
)


@pytest.mark.parametrize(("text", "key"), [(_FILES_SCOPED, "files"), (_PATHS_SCOPED, "paths")])
def test_a_file_scoped_exclude_is_rejected(tmp_path: Path, text: str, key: str) -> None:
    problems = query_filter_problems(_plant(tmp_path, text))
    assert len(problems) == 1, problems
    assert f"`{key}`" in problems[0] and "query-filters[0].exclude" in problems[0]


def test_a_reason_beside_the_instruction_is_rejected(tmp_path: Path) -> None:
    text = "query-filters:\n  - exclude:\n      id: py/full-ssrf\n    reason: reviewed\n"
    problems = query_filter_problems(_plant(tmp_path, text))
    assert len(problems) == 1 and "`reason`" in problems[0], problems


def test_every_documented_constraint_key_is_accepted(tmp_path: Path) -> None:
    """The contrast: an allowlist that rejected a valid key would push people off query filters."""
    lines = [f"  - exclude:\n      {key}: x\n" for key in sorted(_CONSTRAINT_KEYS)]
    text = "query-filters:\n" + "".join(lines) + "  - include:\n      tags: /cwe-020/\n"
    assert query_filter_problems(_plant(tmp_path, text)) == []


def test_a_config_without_query_filters_is_clean(tmp_path: Path) -> None:
    text = 'name: "x"\npacks:\n  python:\n    - codeql/python-queries\n'
    assert query_filter_problems(_plant(tmp_path, text)) == []


@pytest.mark.parametrize("text", ["query-filters:\n", "query-filters:\n  exclude:\n    id: py/x\n"])
def test_query_filters_that_is_not_a_list_is_rejected(tmp_path: Path, text: str) -> None:
    problems = query_filter_problems(_plant(tmp_path, text))
    assert len(problems) == 1 and "not a list" in problems[0], problems


@pytest.mark.parametrize("entry", ["  - {}\n", "  - exclude: {}\n", "  - exclude:\n"])
def test_an_entry_with_no_constraint_is_rejected(tmp_path: Path, entry: str) -> None:
    assert query_filter_problems(_plant(tmp_path, "query-filters:\n" + entry))


# --------------------------------------------------------------------------
# Nothing to check is a failure, never a clean read
# --------------------------------------------------------------------------


def test_a_missing_config_is_a_failure(tmp_path: Path) -> None:
    problems = query_filter_problems(tmp_path / "codeql-config.yml")
    assert len(problems) == 1 and "missing" in problems[0], problems


@pytest.mark.parametrize("text", ["", "\n", "# only a comment\n"])
def test_an_empty_config_is_a_failure(tmp_path: Path, text: str) -> None:
    problems = query_filter_problems(_plant(tmp_path, text))
    assert len(problems) == 1 and "nothing was checked" in problems[0], problems
