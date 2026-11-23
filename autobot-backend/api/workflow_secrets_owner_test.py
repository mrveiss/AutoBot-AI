# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21655: an identity-less caller gets a 401 from the workflow-secret routes, never the shared "" owner."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api import workflow_secrets


def _list(user: dict):
    return asyncio.run(workflow_secrets.list_workflow_secrets(workflow_id=None, current_user=user))


def test_an_identity_less_caller_is_refused_before_the_store_is_read():
    svc = MagicMock()
    with patch.object(workflow_secrets, "_svc", return_value=svc):
        with pytest.raises(HTTPException) as exc:
            _list({"username": "alice"})
    assert exc.value.status_code == 401
    svc.list_secrets.assert_not_called()


def test_a_caller_without_a_user_id_claim_is_scoped_by_sub_not_by_the_empty_owner():
    svc = MagicMock()
    svc.list_secrets.return_value = []
    with patch.object(workflow_secrets, "_svc", return_value=svc):
        assert _list({"sub": "s-1", "username": "alice"}) == []
    assert svc.list_secrets.call_args.kwargs["owner_id"] == "s-1"
