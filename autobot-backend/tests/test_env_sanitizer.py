# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the execution env-var sanitizer (subprocess env-injection fix).

Verifies the AUTOBOT_* allowlist + credential/loader/shell denylist and that every
execution backend routes task env vars through the shared ``safe_task_env`` helper.
"""

from services.execution.env_sanitizer import (
    PROTECTED_ENV_KEYS,
    is_protected_env_key,
    safe_task_env,
)


def test_preserves_base_env():
    base = {"PATH": "/usr/bin", "HOME": "/home/x", "ANTHROPIC_API_KEY": "secret"}
    result = safe_task_env(base, {})
    assert result == base
    # A new dict is returned; the base is not mutated.
    result["AUTOBOT_X"] = "1"
    assert "AUTOBOT_X" not in base


def test_keeps_allowlisted_autobot_var():
    result = safe_task_env({"PATH": "/usr/bin"}, {"AUTOBOT_TASK_ID": "t-42"})
    assert result["AUTOBOT_TASK_ID"] == "t-42"
    assert result["PATH"] == "/usr/bin"


def test_drops_runtime_hijack_vars():
    hijack = {
        "NODE_OPTIONS": "--require /tmp/evil.js",
        "BASH_ENV": "/tmp/evil.sh",
        "GIT_SSH_COMMAND": "sh -c evil",
        "PERL5OPT": "-Mevil",
        "RUBYOPT": "-revil",
        "GCONV_PATH": "/tmp/evil",
        "IFS": " ",
    }
    result = safe_task_env({"PATH": "/usr/bin"}, hijack)
    for key in hijack:
        assert key not in result
    assert result == {"PATH": "/usr/bin"}


def test_drops_ld_and_dyld_prefix_variants():
    # Not just LD_PRELOAD — ANY LD_*/DYLD_* variant must be rejected.
    for key in ("LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES", "DYLD_FRAMEWORK_PATH"):
        assert is_protected_env_key(key)
        result = safe_task_env({}, {key: "/tmp/evil"})
        assert key not in result


def test_drops_random_non_allowlisted_key():
    result = safe_task_env({}, {"TEST_VAR": "x", "FOO": "y", "MY_SECRET": "z"})
    assert result == {}


def test_denylist_covers_all_expected_hijack_vars():
    for key in (
        "NODE_OPTIONS",
        "NODE_PATH",
        "BASH_ENV",
        "ENV",
        "PERL5OPT",
        "PERL5LIB",
        "RUBYOPT",
        "RUBYLIB",
        "GIT_SSH_COMMAND",
        "GIT_EXEC_PATH",
        "GCONV_PATH",
        "IFS",
        "ANTHROPIC_API_KEY",
        "PATH",
        "PYTHONPATH",
    ):
        assert key in PROTECTED_ENV_KEYS


def test_protected_autobot_named_hijack_still_dropped():
    # Defense-in-depth: even if a hijack var were AUTOBOT_-shaped it stays blocked
    # via the denylist. (LD_ prefix beats the allowlist regardless.)
    assert is_protected_env_key("LD_PRELOAD")
    assert not is_protected_env_key("AUTOBOT_MODEL")


def test_backends_use_safe_task_env():
    """Each backend's env-building path must reference the shared sanitizer."""
    import services.execution.claude_code_backend as ccb
    import services.execution.docker_backend as db
    import services.execution.local_backend as lb
    import services.execution.modal_backend as mb

    for mod in (ccb, db, lb, mb):
        src = open(mod.__file__, encoding="utf-8").read()
        assert "safe_task_env" in src, f"{mod.__name__} does not use safe_task_env"
