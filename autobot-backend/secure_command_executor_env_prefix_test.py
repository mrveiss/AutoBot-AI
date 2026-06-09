# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#7375: env-var prefix injection detection in SecureCommandExecutor.

Surfaced by #7367 test rot triage: `PATH=/malicious:$PATH ls` and
`LD_PRELOAD=/x.so ls` previously classified as MODERATE because the
risk assessor anchored on the base command (`ls` — SAFE/MODERATE) and
didn't parse the env-var prefix as a distinct injection vector.

Both are real attacker techniques (PATH-shadowing of standard binaries,
linker hijack of any dynamic symbol) and must classify as FORBIDDEN.
"""

import pytest

from secure_command_executor import CommandRisk, SecureCommandExecutor


@pytest.fixture
def executor() -> SecureCommandExecutor:
    return SecureCommandExecutor()


@pytest.mark.parametrize(
    "command, flagged_var",
    [
        # Linker / loader hijack family — dominant container-escape and
        # privilege-escalation technique
        ("LD_PRELOAD=/malicious.so ls", "LD_PRELOAD"),
        ("LD_LIBRARY_PATH=/malicious /usr/bin/cat /etc/shadow", "LD_LIBRARY_PATH"),
        ("LD_AUDIT=/x.so /bin/true", "LD_AUDIT"),
        ("DYLD_INSERT_LIBRARIES=/x.dylib /usr/bin/whoami", "DYLD_INSERT_LIBRARIES"),
        ("DYLD_LIBRARY_PATH=/x /usr/bin/whoami", "DYLD_LIBRARY_PATH"),
        # PATH manipulation — shadow standard binaries (sudo helpers, cron
        # login shells) by prepending an attacker-controlled directory
        ("PATH=/malicious:$PATH ls", "PATH"),
        ("PATH=/x sudo whoami", "PATH"),
        # Shell parsing / startup manipulation — affects subshells
        ("IFS=. ls", "IFS"),
        ("BASH_ENV=/malicious bash -c ls", "BASH_ENV"),
        ("ENV=/malicious sh -c ls", "ENV"),
        ("PROMPT_COMMAND='rm -rf /' bash", "PROMPT_COMMAND"),
        # Interpreter library path injection
        ("PYTHONPATH=/malicious python3 -c 'pass'", "PYTHONPATH"),
        ("PERL5LIB=/malicious perl -e ''", "PERL5LIB"),
        ("RUBYLIB=/x ruby -e ''", "RUBYLIB"),
        ("NODE_PATH=/x node -e 'process.exit(0)'", "NODE_PATH"),
        ("GEM_PATH=/x gem list", "GEM_PATH"),
        # Process-tracing leak
        ("LD_DEBUG=all /usr/bin/ssh user@host", "LD_DEBUG"),
    ],
)
def test_dangerous_env_var_prefix_classifies_as_forbidden(
    executor: SecureCommandExecutor, command: str, flagged_var: str
) -> None:
    """All dangerous env-var families must return FORBIDDEN regardless
    of the wrapped base command — the prefix itself is the injection."""
    risk, reasons = executor.assess_command_risk(command)
    assert risk == CommandRisk.FORBIDDEN, (
        f"#7375: `{command}` must classify as FORBIDDEN (env-var prefix "
        f"injection) — got {risk.value}. Reasons: {reasons}"
    )
    assert any(flagged_var in r for r in reasons), f"Expected reason mentioning {flagged_var}; got {reasons}"


def test_benign_env_var_prefix_does_not_classify_as_forbidden(
    executor: SecureCommandExecutor,
) -> None:
    """Env-var prefixes that don't shadow linker / shell startup / interpreter
    library paths should NOT be flagged as FORBIDDEN by this check.

    `FOO=bar ls` is application-level config and is benign on its own;
    falls through to the base-command lookup (`ls` → SAFE/MODERATE)."""
    risk, _ = executor.assess_command_risk("FOO=bar ls")
    assert risk != CommandRisk.FORBIDDEN, "Generic env-var prefix shouldn't auto-FORBID"


def test_no_env_var_prefix_unaffected(executor: SecureCommandExecutor) -> None:
    """Plain commands without any env-var prefix go through the normal
    risk path — pin against accidental over-eager regex matching."""
    risk, _ = executor.assess_command_risk("ls -la /tmp")
    assert risk == CommandRisk.SAFE


def test_export_assignment_not_treated_as_prefix(executor: SecureCommandExecutor) -> None:
    """`export PATH=/x; ls` is a separate injection vector (shell
    builtin), not the prefix-form this check targets. Pin so adding it
    here later is a deliberate choice, not accidental scope creep."""
    risk, _ = executor.assess_command_risk("export PATH=/x; ls")
    # We expect this to be flagged via the existing `_check_dangerous_patterns`
    # path (`;` separator) rather than the env-var prefix path. The risk
    # itself may still be FORBIDDEN/HIGH from that side — what we care about
    # is that `_check_dangerous_env_var_prefix` does NOT match this shape.
    from secure_command_executor import _check_dangerous_env_var_prefix

    assert _check_dangerous_env_var_prefix("export PATH=/x; ls") is None
