# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard test for the second session_configs writer stamping owner
(#14989, #14960).

api.terminal.create_terminal_session (the Tools Terminal REST endpoint) was
the only writer of the shared, process-local ``session_manager.session_configs``
dict updated by the original #14989 PR. The Chat Terminal path -- agent
sessions created through POST /api/agent-terminal/sessions -- writes the same
dict via SessionManager._register_pty_with_terminal_manager, and had no
owner stamp at all, so the WebSocket ownership gate denied even the
session's own creator. This drives that write path directly (not a helper
in isolation reimplementing it) and asserts the shared dict entry it
produces.
"""

from services.agent_terminal.session_manager import SessionManager


class TestRegisterPtyWithTerminalManagerStampsOwner:
    def test_owner_is_stamped_into_shared_session_configs(self):
        from api.terminal import session_manager as terminal_session_manager

        mgr = SessionManager()
        pty_session_id = "test-pty-owner-stamp"
        try:
            mgr._register_pty_with_terminal_manager(pty_session_id, "conv-1", "alice")
            assert terminal_session_manager.session_configs[pty_session_id]["owner"] == "alice"
        finally:
            terminal_session_manager.session_configs.pop(pty_session_id, None)

    def test_missing_owner_is_stamped_explicitly_not_omitted(self):
        """An unresolved owner must still be an explicit ``None`` key, not an
        omitted one -- api.terminal._lookup_terminal_session's deny-by-default
        check (#14960/#14961) treats a missing "owner" key the same as an
        unowned session either way, but an explicit key here proves this
        writer was actually updated for #14989 rather than coincidentally
        still matching the old shape.
        """
        from api.terminal import session_manager as terminal_session_manager

        mgr = SessionManager()
        pty_session_id = "test-pty-no-owner"
        try:
            mgr._register_pty_with_terminal_manager(pty_session_id, "conv-1", None)
            config = terminal_session_manager.session_configs[pty_session_id]
            assert "owner" in config
            assert config["owner"] is None
        finally:
            terminal_session_manager.session_configs.pop(pty_session_id, None)
