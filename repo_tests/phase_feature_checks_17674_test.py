# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A feature check must read a declaration, not a filename (#17674).

Split from ``phase_validation_report_contract_17674_test.py``: adding these
there took it to 634 lines against a 600 ceiling, and that file is not
grandfathered -- a KNOWN_LARGE entry grandfathers what already existed and is
not a way in for new tests.

WHY THE MODULE IS LOADED BY PATH. ``phase_validation_system`` imports aiohttp,
psutil, requests and ``autobot_shared.redis_client`` at module scope, and the
last of those WRITES secret key material when none is configured. A guard must
not mutate the tree it guards, so the checks live in the stdlib-only
``phase_feature_checks.py`` and are loaded the same way ``phase_score`` is.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict

import pytest
from repo_tests._paths import repo_root

_SCRIPTS = Path("autobot-infrastructure/shared/scripts")
_CHECKS = _SCRIPTS / "phase_feature_checks.py"
_LOADED: Dict[str, Any] = {}


def _checks():
    """Load the stdlib-only checks by path, leaving nothing in sys.modules.

    The suite's sys.modules leak guard fails a test file that installs a key
    outside ``repo_tests/``, and it is right to.
    """
    if "phase_feature_checks" not in _LOADED:
        spec = importlib.util.spec_from_file_location("phase_feature_checks", repo_root() / _CHECKS)
        module = importlib.util.module_from_spec(spec)
        sys.modules["phase_feature_checks"] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop("phase_feature_checks", None)
        _LOADED["phase_feature_checks"] = module
    return _LOADED["phase_feature_checks"]


class TestAFeatureCheckReadsADeclarationNotAFilename:
    """`exists()` reported a capability for an empty file (CodeRabbit, #17674).

    The PR this belongs to removes an inversion one layer up: a feature with
    no validator used to count as implemented. Two of the validators it added
    then reintroduced it one layer down, by returning `path.exists()` -- so an
    empty `docker-compose.yml` reported "containerization implemented".

    These live in `phase_feature_checks.py` precisely so they can be tested.
    `phase_validation_system` imports `autobot_shared.redis_client` at module
    scope, which WRITES key material when none is configured, so a guard must
    not import it -- the same division this file already makes for the policy
    modules.
    """

    def _write(self, tmp_path, name: str, text: str):
        target = tmp_path / name
        target.write_text(text, encoding="utf-8")
        return target

    @pytest.mark.parametrize(
        "label,text,expected",
        [
            ("empty file", "", False),
            ("no services key", 'version: "3"\n', False),
            ("services declared but empty", "services:\n", False),
            ("one service", "services:\n  web:\n    image: x\n", True),
            ("services after another top-level key", 'version: "3"\nservices:\n  web:\n    image: x\n', True),
        ],
    )
    def test_compose_must_declare_a_service(self, tmp_path, label, text, expected):
        """The first four all pass a bare `exists()` check; three must not pass this one."""
        path = self._write(tmp_path, "docker-compose.yml", text)
        assert _checks().declares_compose_services(path) is expected, label

    @pytest.mark.parametrize(
        "label,text,expected",
        [
            ("empty file", "", False),
            ("does not parse", "def broken(\n", False),
            ("constants only", "X = 1\n", False),
            ("defines a function", "def deploy():\n    pass\n", True),
            ("defines an async function", "async def deploy():\n    pass\n", True),
        ],
    )
    def test_a_deploy_script_must_define_something_callable(self, tmp_path, label, text, expected):
        """A file that does not parse is not deployment automation.

        It is reported as absent rather than present: a SyntaxError here is a
        finding, and falling back to "present" is how an unreadable file reads
        as a working capability.
        """
        path = self._write(tmp_path, "zero_downtime_deploy.py", text)
        assert _checks().defines_callable(path) is expected, label

    def test_a_missing_file_is_absent_for_both(self, tmp_path):
        """The contrast that keeps the two above from being satisfied by a blanket False."""
        assert _checks().declares_compose_services(tmp_path / "nope.yml") is False
        assert _checks().defines_callable(tmp_path / "nope.py") is False
