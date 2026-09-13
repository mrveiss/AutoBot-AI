# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14070 AC2: the audit-log default derives from one definition.

Kept out of ``security_layer_test.py`` so that file stays within its recorded
size ceiling — the ratchet only turns down.
"""

from __future__ import annotations

import importlib

import security_layer


class TestAuditLogFileDerivesFromOneDefinition:
    """#14070 AC2: derivation, not coincidental equality.

    The previous test asserted ``_AUDIT_LOG_FILE_DEFAULT == config.audit_log_file``
    — true of two independent formulas that happen to agree, and it stays true
    if someone "fixes" a failure by editing both copies, which is exactly how
    the divergence #14050 repaired would come back.

    This instead **moves the canonical formula** and asserts every consumer
    moved with it. Two hand-copied formulas cannot pass this: monkeypatching one
    of them leaves the other where it was.
    """

    SENTINEL = "/sentinel/audit-path/audit.log"

    def test_moving_the_canonical_formula_moves_the_resolved_value(self, monkeypatch) -> None:
        from autobot_shared import ssot_config

        monkeypatch.delenv("AUTOBOT_AUDIT_LOG_FILE", raising=False)
        monkeypatch.setattr(ssot_config, "default_audit_log_file", lambda: self.SENTINEL)
        ssot_config.reload_config()

        try:
            reloaded = importlib.reload(security_layer)
            # The SSOT field picked up the redirected formula...
            assert ssot_config.config.audit_log_file == self.SENTINEL
            # ...and so did the value security_layer actually writes through.
            assert reloaded._AUDIT_LOG_FILE == self.SENTINEL
        finally:
            monkeypatch.undo()
            ssot_config.reload_config()
            importlib.reload(security_layer)

    def test_the_empty_env_fallback_also_derives_from_it(self, monkeypatch) -> None:
        """The fallback branch is reachable (an explicitly empty env var) and
        must use the same one definition rather than a local copy."""
        from autobot_shared import ssot_config

        monkeypatch.setenv("AUTOBOT_AUDIT_LOG_FILE", "")
        monkeypatch.setattr(ssot_config, "default_audit_log_file", lambda: self.SENTINEL)
        ssot_config.reload_config()

        try:
            assert not ssot_config.config.audit_log_file, "precondition: the field must be falsy here"
            reloaded = importlib.reload(security_layer)
            assert reloaded._AUDIT_LOG_FILE == self.SENTINEL
        finally:
            monkeypatch.undo()
            ssot_config.reload_config()
            importlib.reload(security_layer)
