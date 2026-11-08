# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The uninstaller drops every database and role provisioning creates (#19409).

``scripts/uninstall.sh`` listed only ``slm_app`` in ``DB_ROLES``, but fleet provisioning also
creates the backend's ``autobot_app``. ``--purge-data`` then counted ``autobot_app`` as a
foreign role, kept PostgreSQL, and never dropped it. #19320's guard checks that each entry is
a known value; this one checks the lists are complete against ``autobot_shared/postgres_identity.py``.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

from autobot_shared import postgres_identity as pg

_UNINSTALL = "scripts/uninstall.sh"

#: What fleet provisioning creates (the table's "Fleet" column). Compose values are not here:
#: the uninstaller removes a fleet or single-box install, not a compose stack.
PROVISIONED_ROLES = frozenset({pg.USERS_DB_ROLE, pg.SLM_DB_ROLE})
PROVISIONED_DATABASES = frozenset({pg.USERS_DB_NAME, pg.SLM_DB_NAME, pg.SLM_USERS_DB_NAME})


def shell_list(text: str, name: str) -> frozenset[str]:
    """The members of ``readonly NAME=(...)`` in *text*."""
    match = re.search(rf"^readonly {name}=\(([^)]*)\)", text, re.M)
    assert match, f"{_UNINSTALL} no longer declares {name}"
    return frozenset(match.group(1).split())


def test_the_uninstaller_drops_every_provisioned_role() -> None:
    text = (repo_root() / _UNINSTALL).read_text(encoding="utf-8")
    assert shell_list(text, "DB_ROLES") == PROVISIONED_ROLES


def test_the_uninstaller_drops_every_provisioned_database() -> None:
    text = (repo_root() / _UNINSTALL).read_text(encoding="utf-8")
    assert shell_list(text, "DATABASES") == PROVISIONED_DATABASES


def test_a_missing_role_is_caught() -> None:
    assert shell_list("readonly DB_ROLES=(slm_app)  # note\n", "DB_ROLES") != PROVISIONED_ROLES
