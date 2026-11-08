# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The security layer's file grants come from the canonical role map (#15738)."""

from unittest.mock import patch

import pytest

from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role
from security_layer import SecurityLayer


@pytest.fixture
def layer():
    with patch("security_layer.get_config_manager") as get_cm, patch("security_layer.emit_security"):
        get_cm.return_value.get.return_value = {"enable_auth": True, "roles": {}}
        yield SecurityLayer()


def _canonical_files(role: Role) -> set[str]:
    return {p.value for p in ROLE_PERMISSIONS[role] if p.value.startswith("files.")}


@pytest.mark.parametrize("role", [Role.ADMIN, Role.OPERATOR])
def test_default_file_grants_match_the_canonical_map(layer, role):
    defaults = {p for p in layer._get_default_role_permissions(role.value) if p.startswith("files.")}
    assert defaults == _canonical_files(role)


def test_a_role_unknown_to_the_canonical_map_holds_no_file_default(layer):
    assert not [p for p in layer._get_default_role_permissions("developer") if p.startswith("files.")]


def test_operator_can_upload_but_not_delete(layer):
    assert Permission.FILES_DELETE.value not in _canonical_files(Role.OPERATOR)
    assert layer.check_permission("operator", Permission.FILES_UPLOAD.value) is True
    assert layer.check_permission("operator", Permission.FILES_DELETE.value) is False
