# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No ChromaDB unit binds a hardcoded interface (#15317).

Two of the three files that render or document the ChromaDB systemd unit had
`--host 0.0.0.0` — every interface, in front of four unpatchable advisories,
one a pre-auth RCE. The host firewall was the only remaining control. This
pins the fix (a `chromadb_bind_host` variable, defaulting to loopback) so a
future edit cannot quietly reintroduce a literal.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

_REPO_ROOT = repo_root()

# Every file that has ever rendered or documented a `chroma run` ExecStart.
_CHROMA_UNIT_FILES = (
    "autobot-slm-backend/ansible/roles/ai-stack/templates/autobot-chromadb.service.j2",
    "autobot-slm-backend/ansible/roles/redis/templates/autobot-chromadb.service.j2",
    "autobot-infrastructure/autobot-database/templates/autobot-chromadb.service",
)

# A bind literal other than loopback. 127.0.0.1 is the chosen safe default and
# is not itself a violation; a real regression looks like 0.0.0.0 or a real
# routable address typed directly into `--host`.
_HARDCODED_WIDE_BIND = re.compile(r"--host\s+0\.0\.0\.0")


def test_the_scan_finds_the_known_unit_files() -> None:
    """A path that stopped existing would make the guard below vacuous."""
    missing = [f for f in _CHROMA_UNIT_FILES if not (_REPO_ROOT / f).is_file()]
    assert not missing, f"expected these ChromaDB unit files to exist: {missing}"


def test_no_chromadb_unit_hardcodes_a_wide_bind() -> None:
    offenders = []
    for rel_path in _CHROMA_UNIT_FILES:
        text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
        if _HARDCODED_WIDE_BIND.search(text):
            offenders.append(rel_path)

    assert not offenders, (
        f"{offenders} bind ChromaDB to 0.0.0.0 literally -- in front of four unpatchable "
        "advisories (one pre-auth RCE), the host firewall becomes the only remaining "
        "control. Bind through chromadb_bind_host (group_vars/all.yml), not a literal (#15317)."
    )


def test_the_ai_stack_and_redis_templates_share_one_bind_variable() -> None:
    """The two live templates must read the SAME variable, or a value set in one
    place silently fails to narrow the unit the other role renders."""
    for rel_path in _CHROMA_UNIT_FILES[:2]:
        text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
        assert "{{ chromadb_bind_host }}" in text, f"{rel_path} does not read chromadb_bind_host"
