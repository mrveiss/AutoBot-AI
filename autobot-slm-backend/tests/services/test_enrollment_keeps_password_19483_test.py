# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""No code path deletes a node's stored SSH credential on its own (#19483, #17038).

Only a human's approval may remove it. A deletion spelled as a del, pop or a filtered rebuild of
extra_data is what this reads for, across the SLM's production code.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_DELETES = re.compile(r"""(?:\bdel\s+\w+\[|\.pop\(\s*)["']ssh_password["']|!=\s*["']ssh_password["']""")


def _production_files() -> list[Path]:
    return [
        path
        for tree in ("api", "services")
        for path in (_ROOT / tree).rglob("*.py")
        if not path.name.endswith("_test.py") and not path.name.startswith("test_")
    ]


def test_no_production_code_deletes_the_stored_password() -> None:
    files = _production_files()
    assert len(files) > 50, f"read only {len(files)} files; this test reads nothing"
    found = [str(path) for path in files if _DELETES.search(path.read_text(encoding="utf-8"))]
    assert not found, found


def test_contrast_each_spelling_is_caught() -> None:
    assert _DELETES.search('del extra_data["ssh_password"]')
    assert _DELETES.search("extra.pop('ssh_password', None)")
    assert _DELETES.search('{k: v for k, v in d.items() if k != "ssh_password"}')
    assert not _DELETES.search('extra.get("ssh_password")')


def test_a_key_auth_node_never_logs_in_with_its_stored_password() -> None:
    """Before #19483 the password was gone after enrollment; keeping it must not switch deploys to sshpass."""
    source = (_ROOT / "services" / "deployment.py").read_text(encoding="utf-8")
    body = source[source.index("def _get_ssh_credentials") :].split("\n    async def ")[0]
    assert 'node.auth_method != "key"' in body
