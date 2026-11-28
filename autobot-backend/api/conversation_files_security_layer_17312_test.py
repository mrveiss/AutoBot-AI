# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#17312: ``conversation_files`` reuses the ``api.files`` security-layer accessor.

Two byte-identical ``get_security_layer(request)`` accessors read
``request.app.state.security_layer``. One definition keeps the lookup (and any
future fail-closed change to it) in a single place.
"""

from unittest.mock import MagicMock, patch

from api import conversation_files, files
from testkit.canonical_gate import HUMAN_PRINCIPAL


def test_conversation_files_uses_the_files_accessor():
    assert conversation_files.get_security_layer is files.get_security_layer


def test_accessor_reads_the_app_state_layer():
    sentinel = object()

    class _State:
        security_layer = sentinel

    class _App:
        state = _State()

    class _Request:
        app = _App()

    assert conversation_files.get_security_layer(_Request()) is sentinel


def test_file_operation_audit_user_is_the_principal_id():
    """#22338: the audited user is the id, never the mutable username."""
    layer = MagicMock()
    with patch("api.conversation_files.get_security_layer", return_value=layer):
        conversation_files._audit_file_operation(MagicMock(client=None), "upload", HUMAN_PRINCIPAL, "s1", {})
    assert layer.audit_log.call_args.kwargs["user"] == "u-123"
