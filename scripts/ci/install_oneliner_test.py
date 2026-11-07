# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""scripts/ci/install_oneliner.py extracts the documented installer command (#19403)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_HERE = Path(__file__).parent
_SPEC = importlib.util.spec_from_file_location("install_oneliner_19403", _HERE / "install_oneliner.py")
io1 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(io1)


def test_install_md_documents_the_pinned_oneliner():
    """A doc change to the command fails here until the fixture is changed with it."""
    pinned = (_HERE / "install_oneliner.expected").read_text(encoding="utf-8").strip()
    assert io1.extract_oneliner((io1.ROOT / "INSTALL.md").read_text(encoding="utf-8")) == pinned


def test_the_first_fenced_oneliner_is_taken_and_prose_is_ignored():
    md = (
        "Run curl -fsSL https://x.example/install.sh | sudo bash in prose.\n\n"
        "```bash\n# comment\ncurl -fsSL https://a.example/install.sh | sudo bash\n```\n"
        "```bash\ncurl -fsSL https://b.example/install.sh | sudo bash\n```\n"
    )
    assert io1.extract_oneliner(md) == "curl -fsSL https://a.example/install.sh | sudo bash"


def test_a_doc_without_the_oneliner_fails_loudly():
    with pytest.raises(SystemExit, match="no `curl"):
        io1.extract_oneliner("```bash\nsudo ./install.sh\n```\n")
