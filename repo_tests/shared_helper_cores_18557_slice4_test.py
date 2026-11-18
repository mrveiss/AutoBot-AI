# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18557 slice 4: the native-vm scripts share one configuration block.

Kept separate on purpose: the two `index_documentation.py` shims differ only in their depth,
and each keeps a documented command working (#18129).
"""

import re

import pytest
from repo_tests._paths import repo_root

NATIVE_VM = repo_root() / "autobot-infrastructure/shared/scripts/native-vm"
SCRIPTS = ("start_autobot_native.sh", "stop_autobot_native.sh", "status_autobot_native.sh")
_OWN_BLOCK = re.compile(r"^\s*(?:declare -A (?:VMS|SERVICES)\b|RED=|SSH_USER=)", re.MULTILINE)


@pytest.mark.parametrize("script", SCRIPTS)
def test_each_script_reads_the_common_block(script: str) -> None:
    text = (NATIVE_VM / script).read_text("utf-8")
    assert '/_native_common.sh"' in text
    assert not _OWN_BLOCK.search(text), f"{script} restates a block that lives in _native_common.sh"


def test_the_common_block_defines_what_the_scripts_read() -> None:
    assert len(_OWN_BLOCK.findall((NATIVE_VM / "_native_common.sh").read_text("utf-8"))) == 4


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ("declare -A VMS\n", True),
        ("RED='\\033[0;31m'\n", True),
        ('SSH_USER="${AUTOBOT_SSH_USER:-autobot}"\n', True),
        ('echo -e "${RED}failed${NC}"\n', False),
        ("declare -A OTHER\n", False),
    ],
)
def test_the_detector_has_both_sides(source: str, flagged: bool) -> None:
    assert bool(_OWN_BLOCK.search(source)) is flagged
