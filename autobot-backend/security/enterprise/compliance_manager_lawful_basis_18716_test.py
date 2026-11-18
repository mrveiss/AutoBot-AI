# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18716 -- the compliance manager reads the canonical login spelling, and the legacy one.

Audit rows now carry ``auth.login``; a raw-string comparison against ``"login"`` stopped returning the
``contract`` lawful basis for logins. ``log_audit_event`` has no caller outside this class in
non-test code today, so this is a latent break, fixed anyway.
"""

import pytest

from security.enterprise.compliance_manager import ComplianceManager


@pytest.fixture
def manager() -> ComplianceManager:
    return ComplianceManager.__new__(ComplianceManager)  # the helpers under test use no instance state


@pytest.mark.parametrize("action", ["auth.login", "login", "login_success", "user.login", "authentication"])
def test_a_login_in_any_spelling_has_the_contract_basis(manager: ComplianceManager, action: str) -> None:
    assert manager._determine_lawful_basis({"action": action}) == "contract"


def test_an_unrelated_action_does_not_get_the_contract_basis(manager: ComplianceManager) -> None:
    assert manager._determine_lawful_basis({"action": "file.delete"}) != "contract"


@pytest.mark.parametrize("action", ["auth.login", "login"])
def test_login_policy_lookups_resolve_for_both_spellings(manager: ComplianceManager, action: str) -> None:
    assert manager._map_to_trust_criteria(action) == ["CC6.1", "CC6.2"]
    assert manager._get_processing_purpose(action) == "authentication_and_access_control"
    assert manager._map_to_iso_control(action) == "A.9.2.1"
    assert manager._map_to_iso_control("file.delete") == "A.18.1.1"
