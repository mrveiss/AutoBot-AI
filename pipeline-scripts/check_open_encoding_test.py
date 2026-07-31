#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the ``no-open-without-encoding`` pre-commit hook.

The negative cases matter as much as the positive ones: an earlier regex-based
measurement of this rule reported 21 violations, of which 18 were false
positives (``PILImage.open``, ``os.open``, ``zf.open``, and a binary-mode
``path.open("rb")``). A hook that flags those would block correct code.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).with_name("check_open_encoding.py")
_spec = importlib.util.spec_from_file_location("check_open_encoding", _MODULE_PATH)
assert _spec and _spec.loader
check_open_encoding = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_open_encoding)


def _check(tmp_path: Path, source: str) -> list[int]:
    target = tmp_path / "sample.py"
    target.write_text(source, encoding="utf-8")
    return check_open_encoding.violations(target)


FLAGGED = [
    pytest.param("with open(p) as f:\n    pass\n", id="bare-open-no-mode"),
    pytest.param("with open(p, 'r') as f:\n    pass\n", id="bare-open-text-mode"),
    pytest.param("with open(p, mode='w') as f:\n    pass\n", id="mode-keyword"),
    pytest.param("import io\nio.open(p)\n", id="io-open"),
    pytest.param("import aiofiles\naiofiles.open(p)\n", id="aiofiles-open"),
]

CLEAN = [
    pytest.param("open(p, encoding='utf-8')\n", id="encoding-present"),
    pytest.param("open(p, 'r', encoding='utf-8')\n", id="encoding-with-mode"),
    pytest.param("open(p, 'rb')\n", id="binary-read"),
    pytest.param("open(p, 'wb')\n", id="binary-write"),
    pytest.param("open(p, mode='rb')\n", id="binary-mode-keyword"),
    # Attribute calls that are not text file I/O and take no `encoding`.
    pytest.param("from PIL import Image\nImage.open(p)\n", id="pil-image-open"),
    pytest.param("import os\nos.open(p, os.O_CREAT)\n", id="os-open-fd"),
    pytest.param("import tarfile\ntarfile.open(p, 'r:gz')\n", id="tarfile-open"),
    pytest.param("zf.open(name)\n", id="zipfile-member-open"),
    pytest.param("audio_path.open('rb')\n", id="path-open-binary"),
]


@pytest.mark.parametrize("source", FLAGGED)
def test_flags_text_open_without_encoding(tmp_path: Path, source: str) -> None:
    assert _check(tmp_path, source), f"expected a violation for: {source!r}"


@pytest.mark.parametrize("source", CLEAN)
def test_does_not_flag(tmp_path: Path, source: str) -> None:
    assert _check(tmp_path, source) == [], f"false positive for: {source!r}"


def test_reports_every_offending_line(tmp_path: Path) -> None:
    source = "open(a)\nopen(b, encoding='utf-8')\nopen(c, 'w')\n"
    assert _check(tmp_path, source) == [1, 3]


def test_unparseable_file_is_ignored(tmp_path: Path) -> None:
    # Syntax errors belong to flake8/black, not this hook.
    assert _check(tmp_path, "def broken(\n") == []


def test_main_exit_codes(tmp_path: Path) -> None:
    clean = tmp_path / "clean.py"
    clean.write_text("open(p, encoding='utf-8')\n", encoding="utf-8")
    dirty = tmp_path / "dirty.py"
    dirty.write_text("open(p)\n", encoding="utf-8")

    assert check_open_encoding.main([str(clean)]) == 0
    assert check_open_encoding.main([str(dirty)]) == 1
