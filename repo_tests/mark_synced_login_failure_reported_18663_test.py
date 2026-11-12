# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The mark-synced tasks survive a login result that has no ``status`` (#18663).

The login task is ``failed_when: false`` + ``no_log``: when it fails before the HTTP exchange
(templating, privilege escalation) its registered result carries ``msg`` but no ``status``. A
bare ``_slm_login.status`` then raised an opaque conditional error that hid the cause. Every
read of it must tolerate the missing key, and the localhost-delegated tasks must not escalate.
"""

from __future__ import annotations

import re

import yaml
from repo_tests._paths import repo_root

_PLAYBOOK = "autobot-slm-backend/ansible/playbooks/provision-fleet-roles.yml"
_MARK = "Mark-synced | "


def _mark_synced_tasks(text: str) -> list[dict]:
    plays = yaml.safe_load(text)
    play = next(p for p in plays if p.get("name", "").startswith("Provision Phase 6.5"))
    return [t for t in play["tasks"] if t["name"].startswith(_MARK)]


def _bare_status_reads(text: str) -> list[str]:
    """Reads of ``_slm_login.status`` that are not piped through ``default``."""
    return [m.group(0) for m in re.finditer(r"_slm_login\.status(?!\s*\|\s*default)", text)]


def _text() -> str:
    return (repo_root() / _PLAYBOOK).read_text(encoding="utf-8")


def test_every_login_status_read_tolerates_a_missing_status() -> None:
    assert not _bare_status_reads(_text())


def test_control_a_bare_status_read_is_detected() -> None:
    bare = _text().replace("(_slm_login.status | default(0)) != 200", "_slm_login.status != 200", 1)
    assert bare != _text(), "control did not change the playbook"
    assert _bare_status_reads(bare)


def test_login_and_post_do_not_escalate_on_the_install_inventory() -> None:
    by_name = {t["name"].split("{{")[0]: t for t in _mark_synced_tasks(_text())}
    for key in (_MARK + "Login to SLM API", _MARK + "POST to /api/code-sync/nodes/"):
        assert by_name[key].get("become") is False, key


def test_a_failed_login_is_reported_with_its_message() -> None:
    tasks = {t["name"]: t for t in _mark_synced_tasks(_text())}
    warn = tasks[_MARK + "Warn if login failed (skip mark-synced gracefully)"]
    assert "_slm_login.msg" in warn["debug"]["msg"]
