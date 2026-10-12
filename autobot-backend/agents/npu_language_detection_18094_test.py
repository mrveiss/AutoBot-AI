# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One extension-to-language detector; the NPU agent's emitted names are unchanged (#18094)."""

import importlib
from pathlib import Path

import pytest

from agents import npu_code_search_patterns as patterns


@pytest.fixture
def base_analyzer(_real_base_analyzer):
    """The real module, imported after agents/conftest.py has swapped it in."""
    return importlib.import_module("code_intelligence.base_analyzer")


# The exact table npu_code_search_patterns emitted before the consolidation.
LEGACY_EMITTED = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".cs": "csharp",
    ".rb": "ruby",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".ps1": "powershell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
    ".md": "markdown",
}


# Extensions the old NPU map returned "unknown" for; they are now classified through the
# canonical map. Affects newly indexed files only; no stored data is rewritten.
NEWLY_CLASSIFIED = {
    ".pyi": "python",
    ".pyw": "python",
    ".mts": "typescript",
    ".cts": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".vue": "vue",
}


@pytest.mark.parametrize("ext,name", sorted(NEWLY_CLASSIFIED.items()))
def test_previously_unknown_extensions_follow_the_canonical_map(ext, name):
    assert patterns.detect_language(ext) == name


@pytest.mark.parametrize("ext,name", sorted(LEGACY_EMITTED.items()))
def test_emitted_names_are_unchanged(ext, name):
    assert patterns.detect_language(ext) == name
    assert patterns.detect_language(ext.upper()) == name


def test_unknown_extension_still_emits_unknown():
    assert patterns.detect_language(".zzz") == "unknown"
    assert patterns.detect_language("") == "unknown"


@pytest.mark.parametrize("ext", sorted(LEGACY_EMITTED))
def test_the_enum_detector_knows_every_extension_the_npu_map_had(base_analyzer, ext):
    assert base_analyzer.detect_language(Path(f"f{ext}")) is not base_analyzer.Language.UNKNOWN


def test_sh_maps_to_the_existing_shell_member(base_analyzer):
    assert base_analyzer.detect_language(Path("run.sh")) is base_analyzer.Language.SHELL


@pytest.mark.parametrize("alias", ["bash", "BASH", "sh", "zsh"])
def test_bash_is_accepted_as_an_input_alias(base_analyzer, alias):
    language = base_analyzer.Language
    assert language(alias) is language.SHELL
    assert language("shell") is language.SHELL


def test_unknown_names_are_still_rejected(base_analyzer):
    with pytest.raises(ValueError):
        base_analyzer.Language("cobol")


def test_the_patterns_module_no_longer_carries_its_own_extension_map():
    assert not hasattr(patterns, "_LANGUAGE_BY_EXTENSION")


def test_unanalysed_classification_only_file_is_not_an_error(base_analyzer, tmp_path):
    source = tmp_path / "Main.java"
    source.write_text("class Main {}\n", encoding="utf-8")

    assert base_analyzer.MultiLanguageAnalyzer().analyze_file(source).errors == []
