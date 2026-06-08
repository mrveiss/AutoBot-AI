# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""#7406: extends #7375/#7384 argument-aware risk pattern with two more
shapes that the prefix-form / first-token-only rules missed:

1. ``export VAR=value`` shell-builtin form. Sibling of the prefix-form
   #7375 check (`PATH=/x ls`) — same dangerous-var list, different
   syntax. Persists the var in the current shell so subsequent commands
   inherit it. Real chain: ``export PATH=/x:$PATH; ls`` shadows ``ls``
   with attacker-controlled PATH.

2. ``cmd1; cmd2`` chained-command separator. Recurses
   `_check_argument_aware_risk` on each sub-command and takes the
   strictest risk. Without this, ``benign_cmd; sudo cmd`` was masked by
   the LHS classification.

3. ``SHELL`` added to the dangerous-env-var list — sudo's `-E` flag
   preserves SHELL, so ``export SHELL=/bin/sh; sudo -E sh`` runs sudo's
   target with attacker-controlled $SHELL.
"""

import pytest

from secure_command_executor import CommandRisk, SecureCommandExecutor


@pytest.fixture
def executor() -> SecureCommandExecutor:
    return SecureCommandExecutor()


# ---------------------------------------------------------------------------
# 1. export VAR= form (sibling of prefix-form #7375)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command, expected_var",
    [
        ("export PATH=/malicious:$PATH", "PATH"),
        ("export LD_PRELOAD=/x.so", "LD_PRELOAD"),
        ("export LD_LIBRARY_PATH=/x", "LD_LIBRARY_PATH"),
        ("export PYTHONPATH=/malicious", "PYTHONPATH"),
        ("export PERL5LIB=/x", "PERL5LIB"),
        ("export IFS=.", "IFS"),
        ("export BASH_ENV=/malicious", "BASH_ENV"),
        ("export ENV=/malicious", "ENV"),
        ("export SHELL=/bin/sh", "SHELL"),
        ("export DYLD_INSERT_LIBRARIES=/x.dylib", "DYLD_INSERT_LIBRARIES"),
    ],
)
def test_export_dangerous_var_classifies_as_forbidden(
    executor: SecureCommandExecutor, command: str, expected_var: str
) -> None:
    """`export DANGEROUS_VAR=value` must classify as FORBIDDEN —
    attacker can persist linker/path/shell-startup hijacks for the
    rest of the shell session."""
    risk, reasons = executor.assess_command_risk(command)
    assert risk == CommandRisk.FORBIDDEN, (
        f"#7406: `{command}` must be FORBIDDEN (export of dangerous env-var) — " f"got {risk.value}. Reasons: {reasons}"
    )
    assert any(expected_var in r for r in reasons), f"Expected reason to mention {expected_var}; got {reasons}"


def test_export_benign_var_unaffected(executor: SecureCommandExecutor) -> None:
    """`export FOO=bar` must NOT auto-FORBID — only dangerous vars."""
    risk, _ = executor.assess_command_risk("export FOO=bar")
    assert risk != CommandRisk.FORBIDDEN, "Generic export shouldn't auto-FORBID"


# ---------------------------------------------------------------------------
# 2. Chained-command separator (`;`)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command, expected_risk",
    [
        # LHS benign, RHS escalates via dangerous export → FORBIDDEN
        ("ls; export LD_PRELOAD=/x.so", CommandRisk.FORBIDDEN),
        # LHS dangerous export, RHS benign → FORBIDDEN (LHS dominates)
        ("export PATH=/x:$PATH; ls", CommandRisk.FORBIDDEN),
        # LHS benign, RHS docker escape → FORBIDDEN
        ("ls; docker run --privileged alpine", CommandRisk.FORBIDDEN),
        # LHS DNS recon, RHS benign → MODERATE (DNS recon is the strictest)
        ("dig @8.8.8.8 example.com; echo done", CommandRisk.MODERATE),
        # The original #7406 reproducer
        ("export SHELL=/bin/sh; sudo -E sh", CommandRisk.FORBIDDEN),
    ],
)
def test_chained_command_takes_strictest_risk(
    executor: SecureCommandExecutor, command: str, expected_risk: CommandRisk
) -> None:
    """`cmd1; cmd2` must classify at the strictest risk seen across
    sub-commands — otherwise an attacker prepends a benign command to
    bypass risk assessment."""
    risk, reasons = executor.assess_command_risk(command)
    assert risk == expected_risk, (
        f"#7406: `{command}` chained-command must classify {expected_risk.value} — "
        f"got {risk.value}. Reasons: {reasons}"
    )


def test_single_command_with_no_separator_unaffected(executor: SecureCommandExecutor) -> None:
    """Plain `ls -la /tmp` (no `;`) must not enter the chained-command
    code path — pin against accidental over-eager `;` matching."""
    risk, _ = executor.assess_command_risk("ls -la /tmp")
    assert risk == CommandRisk.SAFE


# ---------------------------------------------------------------------------
# 3. SHELL var added to _DANGEROUS_ENV_VARS (prefix form)
# ---------------------------------------------------------------------------


def test_shell_var_in_prefix_form_classifies_as_forbidden(executor: SecureCommandExecutor) -> None:
    """Prefix form `SHELL=/bin/sh sudo cmd` must classify FORBIDDEN —
    sudo's `-E` flag preserves SHELL into the privileged environment."""
    risk, reasons = executor.assess_command_risk("SHELL=/bin/sh sudo -E cmd")
    assert risk == CommandRisk.FORBIDDEN, (
        f"#7406: SHELL var in prefix form must be FORBIDDEN — got {risk.value}. " f"Reasons: {reasons}"
    )
    assert any("SHELL" in r for r in reasons), f"Expected reason to mention SHELL; got {reasons}"
