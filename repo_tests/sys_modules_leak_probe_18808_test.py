# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The out-of-directory node the pre-push leak check collects last (#18808).

The sys.modules leak guard (#13337) sees a leaked stub only when a node OUTSIDE the leaking
owner's directory is checked. A pre-push selection is usually one directory's tests, so an
import-time leak there -- #18785's benchmark stubs, caught only by all 12 CI shards -- had no
such node and passed. tools/git-hooks/pre-push collects the selected backend files followed by
this module, which lives outside every backend tree.
"""

from __future__ import annotations


def test_the_leak_guard_is_loaded_in_this_session(pytestconfig):
    """Without the plugin this probe would prove nothing: the check it exists to trigger is absent."""
    assert pytestconfig.pluginmanager.has_plugin("repo_tests.sys_modules_leak_guard")
