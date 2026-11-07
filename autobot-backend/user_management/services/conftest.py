# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#10200: person_link_service module state never outlives the test that changed it."""

import pytest

from user_management.services import person_link_service as service


@pytest.fixture(autouse=True)
def _restore_person_link_module_state(monkeypatch):
    """Undo any rebinding of the module's globals (the startup status, the SLM fetch) after each test."""
    for name in ("last_link_status", "fetch_first_slm_admin"):
        monkeypatch.setattr(service, name, getattr(service, name))
