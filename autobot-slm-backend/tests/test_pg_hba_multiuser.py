# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Render tests for the postgresql role's pg_hba.conf.j2 (#10636).

Guards the single-box collapse case: provisioning one app user must never
drop the others from pg_hba (which previously would break the SLM database
when autobot_app was provisioned onto the shared instance).
"""

from pathlib import Path

import pytest

jinja2 = pytest.importorskip("jinja2")

_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "ansible" / "roles" / "postgresql" / "templates"


def _render(**ctx) -> str:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)))
    return env.get_template("pg_hba.conf.j2").render(**ctx)


def _has_user(rendered: str, user: str) -> bool:
    return (
        f"local   all             {user}" in rendered
        and f"host    all             {user}   127.0.0.1/32" in rendered
        and f"host    all             {user}   ::1/128" in rendered
    )


def test_single_user_backward_compatible():
    """Multi-VM default: only db_user is emitted (unchanged behavior)."""
    out = _render(db_user="slm_app")
    assert _has_user(out, "slm_app")
    # No HBA entry for any other user (the comment may mention examples).
    assert not _has_user(out, "autobot_app")


def test_multiuser_single_box_keeps_all_users():
    """Single-box collapse: every app user coexists; none is dropped."""
    out = _render(db_user="autobot_app", postgresql_app_users=["slm_app", "autobot_app"])
    assert _has_user(out, "slm_app"), "slm_app must survive autobot_app provisioning"
    assert _has_user(out, "autobot_app")


def test_remote_access_entries_preserved():
    out = _render(
        db_user="autobot_app",
        postgresql_app_users=["slm_app", "autobot_app"],
        pg_hba_remote_access=[{"database": "autobot_users", "user": "autobot_app", "address": "10.0.0.5/32"}],
    )
    assert "host    autobot_users    autobot_app    10.0.0.5/32" in out
