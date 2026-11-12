# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one version that decides whether a cached code-index entry is still valid (#13508, #21316).

A content hash answers "did this file change"; it cannot answer "did the thing that reads it
change". That thing is this extractor *and* the tree-sitter runtime and grammars it loads: a
grammar upgrade can change the parse of an unchanged file. ``cache_version`` therefore folds
the hand-bumped ``EXTRACTOR_VERSION`` together with the installed versions of every package
the indexer loads, read at runtime through ``importlib.metadata``. It is the single value
stored under ``code_indexer._CACHE_VERSION_KEY`` — not a second key beside it.
"""

import json
from importlib import metadata

# #13508: bump when extraction, resolution or node identity changes in a way that makes
# previously-indexed records wrong rather than merely stale. A bump invalidates the whole hash
# cache on the next run, so every file is re-extracted instead of skipped on an unchanged hash.
EXTRACTOR_VERSION = 1

# Distribution names of everything ``extract_python`` / ``extract_javascript`` import:
# ``tree_sitter``, ``tree_sitter_python`` and ``tree_sitter_javascript`` (TS and Vue are parsed
# with the JavaScript grammar). Add a grammar here in the same change that makes the indexer load it.
GRAMMAR_PACKAGES: tuple[str, ...] = ("tree-sitter", "tree-sitter-python", "tree-sitter-javascript")

NOT_INSTALLED = "not-installed"


def installed_grammar_versions() -> dict[str, str]:
    """Installed version of every grammar package, read now; a missing one reports ``not-installed``."""
    versions: dict[str, str] = {}
    for package in GRAMMAR_PACKAGES:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = NOT_INSTALLED
    return versions


def grammar_versions_json(versions: dict[str, str] | None = None) -> str:
    """Scalar (JSON string) form of *versions*, for the provenance record's metadata."""
    return json.dumps(installed_grammar_versions() if versions is None else versions, sort_keys=True)


def cache_version(versions: dict[str, str] | None = None, extractor_version: int = EXTRACTOR_VERSION) -> str:
    """``EXTRACTOR_VERSION`` combined with the grammar versions: equal only when none of them moved."""
    return f"{extractor_version}|{grammar_versions_json(versions)}"
