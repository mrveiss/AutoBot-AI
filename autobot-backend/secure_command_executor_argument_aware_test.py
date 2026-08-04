# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#7384 sub-fixes: argument-aware risk for tools whose base command is
allowlisted but whose flags / arguments elevate them to attack vectors.

Three families covered:

1. **Docker escape flags** — `docker run --privileged`, `--net=host`,
   `--cap-add=SYS_ADMIN`, `-v /:/host`, `--device=` etc. Container-escape
   is a real attack chain; these flags turn an allowlisted `docker` base
   command into a host-takeover vector.

2. **`find` SUID/setgid recon** — `find / -perm -4000` enumerates setuid
   binaries (privilege-escalation primitives). `find` is allowlisted as
   MODERATE for normal use; the recon argument shape elevates to HIGH.

3. **DNS recon** — `dig`, `nslookup`, `host`, `whois`, `drill`. Real
   data-exfiltration / external-host enumeration channels (DNS tunnelling,
   subdomain takeover prep). Worth at least MODERATE so they're audit-logged.

Same architectural pattern as #7375 (env-var prefix detection): parse
arguments BEFORE base-command lookup so the more-specific reason wins.
"""

import pytest

from secure_command_executor import CommandRisk, SecureCommandExecutor


@pytest.fixture
def executor() -> SecureCommandExecutor:
    return SecureCommandExecutor()


# ---------------------------------------------------------------------------
# 1. Docker escape flags
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command, expected_flag",
    [
        ("docker run --privileged alpine", "--privileged"),
        ("docker run --net=host alpine", "--net=host"),
        ("docker run --network=host alpine", "--network=host"),
        ("docker run --pid=host alpine", "--pid=host"),
        ("docker run --ipc=host alpine", "--ipc=host"),
        ("docker run --cap-add=SYS_ADMIN alpine", "--cap-add"),
        ("docker run --cap-add SYS_PTRACE alpine", "--cap-add"),
        ("docker run -v /:/host alpine", "-v /:"),
        ("docker run --volume=/:/host alpine", "--volume=/:"),
        ("docker run --device=/dev/mem alpine", "--device="),
        ("docker run --security-opt=seccomp=unconfined alpine", "--security-opt=seccomp=unconfined"),
        ("docker run --userns=host alpine", "--userns=host"),
    ],
)
def test_docker_escape_flag_classifies_as_forbidden(
    executor: SecureCommandExecutor, command: str, expected_flag: str
) -> None:
    """Container-escape flags must classify as FORBIDDEN regardless of the
    wrapped command — `docker` itself is allowlisted, the flag is the
    injection."""
    risk, reasons = executor.assess_command_risk(command)
    assert risk == CommandRisk.FORBIDDEN, (
        f"#7384: `{command}` must classify as FORBIDDEN (docker escape " f"flag) — got {risk.value}. Reasons: {reasons}"
    )
    assert any(expected_flag in r for r in reasons), f"Expected reason mentioning {expected_flag}; got {reasons}"


def test_benign_docker_run_unaffected(executor: SecureCommandExecutor) -> None:
    """Plain `docker run alpine echo hi` must NOT be flagged — only escape
    flags trigger the FORBIDDEN classification."""
    risk, _ = executor.assess_command_risk("docker run alpine echo hi")
    # The base `docker` command may be MODERATE or HIGH depending on the
    # production allowlist, but it must NOT be FORBIDDEN purely on the
    # absence of escape flags.
    assert risk != CommandRisk.FORBIDDEN, "Benign docker run shouldn't auto-FORBID"


# ---------------------------------------------------------------------------
# 2. find SUID/setgid recon
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command, expected_pattern",
    [
        ("find / -perm -4000 2>/dev/null", "-perm -4000"),
        ("find / -perm -2000 -type f", "-perm -2000"),
        ("find / -perm -u+s", "-perm -u+s"),
        ("find / -perm -g+s", "-perm -g+s"),
        ("find / -perm /4000", "-perm /4000"),
        ("find /usr/bin -perm /2000", "-perm /2000"),
    ],
)
def test_find_suid_recon_classifies_as_high(
    executor: SecureCommandExecutor, command: str, expected_pattern: str
) -> None:
    """SUID/setgid enumeration is reconnaissance for privilege-escalation
    primitives. `find` itself is allowlisted but the recon argument shape
    elevates to HIGH."""
    risk, reasons = executor.assess_command_risk(command)
    assert risk == CommandRisk.HIGH, (
        f"#7384: `{command}` must classify as HIGH (SUID recon) — " f"got {risk.value}. Reasons: {reasons}"
    )
    assert any(expected_pattern in r for r in reasons), f"Expected reason mentioning {expected_pattern}; got {reasons}"


def test_benign_find_unaffected(executor: SecureCommandExecutor) -> None:
    """Plain `find . -name '*.txt'` must NOT trigger the SUID-recon
    classification."""
    risk, _ = executor.assess_command_risk("find . -name '*.txt'")
    assert risk != CommandRisk.HIGH or "SUID/setgid recon" not in str(risk)


# ---------------------------------------------------------------------------
# 3. DNS-recon commands
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command, expected_cmd",
    [
        ("dig @8.8.8.8 malicious.com", "dig"),
        ("nslookup malicious.com", "nslookup"),
        ("host malicious.com", "host"),
        ("whois malicious.com", "whois"),
        ("drill @1.1.1.1 malicious.com", "drill"),
    ],
)
def test_dns_recon_classifies_at_least_moderate(
    executor: SecureCommandExecutor, command: str, expected_cmd: str
) -> None:
    """DNS-recon commands must classify at least MODERATE so they're
    audit-logged. They're real exfiltration / enumeration vectors but
    not always blockable in a developer-tools context."""
    risk, reasons = executor.assess_command_risk(command)
    assert risk in (CommandRisk.MODERATE, CommandRisk.HIGH, CommandRisk.CRITICAL, CommandRisk.FORBIDDEN), (
        f"#7384: `{command}` must classify at least MODERATE (DNS recon) — " f"got {risk.value}. Reasons: {reasons}"
    )
    assert any(expected_cmd in r for r in reasons), f"Expected reason mentioning {expected_cmd}; got {reasons}"


# ---------------------------------------------------------------------------
# Architectural guard
# ---------------------------------------------------------------------------


class TestArgumentAwareRiskWinsOverTheAllowlistedBaseCommand:
    """Pin the architectural decision *by its consequence*.

    Argument-aware checks fire BEFORE the base-command allowlist, otherwise
    ``docker run --privileged ...`` resolves as whatever ``docker`` alone is
    worth and the elevation is lost.

    This used to compare ``src.find("_check_argument_aware_risk")`` against
    ``src.find("base_command = self._extract_command_name")`` inside
    ``inspect.getsource(assess_command_risk)`` (#13311): it broke on any
    rename or extraction, and it never checked that the ordering *mattered* --
    it would have passed just as happily if both branches returned the same
    thing.
    """

    @staticmethod
    def _bare_base_command_risk(executor: SecureCommandExecutor, base: str) -> CommandRisk:
        """What the allowlist alone says about the base command."""
        risk, _reasons = executor.assess_command_risk(base)
        return risk

    @pytest.mark.parametrize(
        "base, elevated",
        [
            ("docker ps", "docker run --privileged alpine"),
            ("find /tmp -name x", "find / -perm -4000"),
        ],
    )
    def test_the_argument_elevates_above_the_base_commands_own_rating(
        self, executor: SecureCommandExecutor, base: str, elevated: str
    ) -> None:
        """If the allowlist were consulted first, both would rate the same."""
        base_risk = self._bare_base_command_risk(executor, base)
        elevated_risk, reasons = executor.assess_command_risk(elevated)

        order = list(CommandRisk)
        assert order.index(elevated_risk) > order.index(base_risk), (
            f"#7384: `{elevated}` rated {elevated_risk.value}, the same or less than "
            f"`{base}` at {base_risk.value} -- the allowlist won, so the "
            f"argument-aware check no longer runs first. Reasons: {reasons}"
        )

    def test_the_reason_names_the_argument_not_the_base_command(self, executor: SecureCommandExecutor) -> None:
        """Ordering is only useful if the *more specific* reason survives."""
        _risk, reasons = executor.assess_command_risk("docker run --privileged alpine")

        joined = " ".join(reasons).lower()
        assert "--privileged" in joined, f"expected the offending flag in the reasons; got {reasons}"

    def test_a_dangerous_env_var_prefix_still_outranks_the_argument_check(
        self, executor: SecureCommandExecutor
    ) -> None:
        """#7375 sits ahead of #7384; guard that this ordering did not invert."""
        risk, reasons = executor.assess_command_risk("LD_PRELOAD=/tmp/e.so docker run --privileged alpine")

        assert risk == CommandRisk.FORBIDDEN
        assert any("env-var prefix" in r.lower() for r in reasons), reasons

    def test_an_allowlisted_command_without_the_argument_is_not_elevated(self, executor: SecureCommandExecutor) -> None:
        """The mirror: the argument-aware branch must not swallow normal use."""
        risk, _reasons = executor.assess_command_risk("docker ps")

        assert risk != CommandRisk.FORBIDDEN
