# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#17312: ``conversation_files`` reuses the ``api.files`` security-layer accessor.

Two byte-identical ``get_security_layer(request)`` accessors read
``request.app.state.security_layer``. One definition keeps the lookup (and any
future fail-closed change to it) in a single place.
"""

from api import conversation_files, files


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
