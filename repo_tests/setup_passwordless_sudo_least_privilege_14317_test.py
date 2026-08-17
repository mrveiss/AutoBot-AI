# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025-2026 mrveiss
# Author: mrveiss
"""setup_passwordless_sudo.sh grants exactly four wrapper invocations, never a
bare binary or a wildcard (#14317, hardened in PR #14412 review round 2).

Before the first fix, the script hardcoded NOPASSWD sudo to a leftover
dev-image account ('ka' + 'li') and included `usermod -aG docker <account>`
in the grant -- docker group membership is equivalent to root.

Round 2: even scoped to the resolved account, bare `NOPASSWD: /usr/bin/kill`
and `/usr/bin/pkill` let any process that account already runs signal ANY
PID as root (`sudo pkill -f sshd`), and bare `lsof` reads every other user's
open files. Both are now routed through autobot-cleanup-port, a fixed
root-owned wrapper with no free-form argument; sudoers names only its exact
invocations. AUTOBOT_USER is also validated as a plain account name before
it reaches the sudoers content -- `visudo -c` checks grammar only, so a
multi-line value would otherwise inject a second, unrelated rule and still
pass validation.

Round 3: the wrapper's subcommand NAMES were fixed ("backend", "frontend",
...), but the PORT NUMBER each name resolved to still came from the calling
account's own environment (AUTOBOT_BACKEND_PORT). `AUTOBOT_BACKEND_PORT=22
sudo autobot-cleanup-port kill-port backend` would have killed whatever
listens on 22 -- finding 1 by another route, gated only by sudo's
(unstated, if correct) env_reset default. Ports are now hardcoded literals
in the wrapper, and the sudoers file states env_reset/secure_path
explicitly for this exact command instead of relying on the inherited
system default.

Static only: the script itself calls `sudo install`/`sudo visudo`, so it is
never executed here (or anywhere in this suite) -- it modifies real sudoers
state and installs a root-owned binary. These tests parse its source text
(and the wrapper's) and reproduce just enough of sudoers' matching semantics
(exact user + exact command; no wildcard rules exist in this fixture) to
prove an invocation OUTSIDE the allowlist is denied, not merely that the
ones inside it are permitted.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "setup" / "system"
SCRIPT = SCRIPT_DIR / "setup_passwordless_sudo.sh"
WRAPPER = SCRIPT_DIR / "autobot-cleanup-port"

WRAPPER_DEST = "/opt/autobot/bin/autobot-cleanup-port"

# The generated sudoers rule shape this script writes: an unquoted heredoc, so
# ${AUTOBOT_USER} is the only per-account expansion in it -- resolved at
# runtime from an env var, validated before use, never a literal account name
# written into the file.
_RULE_RE = re.compile(
    r"^\$\{AUTOBOT_USER\}\s+ALL=\(root\)\s+NOPASSWD:\s+\$\{WRAPPER_DEST\}\s+(.+?)\s*$",
    re.MULTILINE,
)

# The heredoc IS the actual sudoers content -- everything else in the script
# is prose (including this fix's own explanation of the bugs it replaces,
# which necessarily names the leftover account and the removed commands).
# Tests below check the artifact that is actually installed, not the
# commentary describing why it changed.
_HEREDOC_RE = re.compile(r'cat > "\$\{sudoers_tmp\}" <<EOF\n(.*?)\nEOF\n', re.DOTALL)


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _wrapper_text() -> str:
    return WRAPPER.read_text(encoding="utf-8")


def _sudoers_content() -> str:
    match = _HEREDOC_RE.search(_script_text())
    assert match, "could not locate the sudoers heredoc in the script"
    return match.group(1)


def _granted_invocations() -> set[str]:
    """The exact `<subcommand> <arg>` strings granted against the wrapper."""
    return set(_RULE_RE.findall(_sudoers_content()))


def _is_permitted(invocation: str, granted: set[str]) -> bool:
    """Sudoers matching for this fixture: no wildcards are used anywhere in
    the generated file, so an invocation is permitted iff it is EXACTLY one
    of the granted strings -- the same rule visudo would apply."""
    return invocation in granted


def _wrapper_accepted_invocations() -> set[str]:
    """Every {subcommand, port-name} combination the wrapper itself accepts,
    parsed from its own `case` statements -- used to prove sudoers grants a
    SUBSET of what the wrapper can do, never something it doesn't recognise."""
    text = _wrapper_text()
    port_names = set(re.findall(r"^\s*(backend|frontend|backend-tls)\)", text, re.MULTILINE))
    assert port_names == {"backend", "frontend", "backend-tls"}
    accepted = {f"kill-port {p}" for p in port_names}
    accepted |= {f"diagnose-port {p}" for p in port_names}
    accepted.add("kill-uvicorn")
    return accepted


def _port_mapping() -> dict[str, str]:
    """Parse port_for()'s case arms into {port_name: resolved_value}."""
    text = _wrapper_text()
    match = re.search(r"port_for\(\) \{\n(.*?)\n\}\n", text, re.DOTALL)
    assert match, "port_for() function not found in the wrapper"
    body = match.group(1)
    return dict(re.findall(r'(backend|frontend|backend-tls)\)\s+echo "([^"]+)"', body))


def test_ports_are_compile_time_literals_not_environment_reads():
    """PR #14412 review round 3: a fixed subcommand NAME is not enough if the
    VALUE it resolves to still comes from the caller's environment. Every
    resolved value must be a bare digit literal -- no `$`, no expansion, no
    reference to anything a caller could set before invoking sudo."""
    mapping = _port_mapping()
    assert mapping == {"backend": "8001", "frontend": "5173", "backend-tls": "8443"}
    for name, value in mapping.items():
        assert value.isdigit(), f"port_for({name!r}) must resolve to a literal, not an expression: {value!r}"


def test_wrapper_never_reads_port_environment_variables():
    """The regression this guards: reintroducing an env-var read for any of
    these names silently reopens finding 1 by another route."""
    text = _wrapper_text()
    for env_var in ("AUTOBOT_BACKEND_PORT", "AUTOBOT_FRONTEND_PORT", "AUTOBOT_BACKEND_TLS_PORT"):
        assert env_var not in text, (
            f"{env_var} must not appear in the wrapper -- the calling account's "
            "environment must never influence which port root acts on"
        )


def test_sudoers_states_env_reset_and_secure_path_for_the_wrapper():
    """Belt and braces (#14412 review round 3): even with round 3's fix, the
    file that grants the privilege should say so explicitly rather than
    depend on an unwritten system default. The heredoc is unquoted, so the
    SOURCE literally spells ${WRAPPER_DEST} -- the same placeholder shape
    _RULE_RE matches elsewhere in this file -- not the expanded path."""
    content = _sudoers_content()
    assert "Defaults!${WRAPPER_DEST} env_reset" in content
    assert re.search(r'Defaults!\$\{WRAPPER_DEST\} secure_path="[^"]+"', content)


def test_grants_exactly_the_wrapper_allowlist():
    granted = _granted_invocations()
    assert granted == {
        "kill-port backend",
        "kill-port frontend",
        "diagnose-port backend-tls",
        "kill-uvicorn",
    }


def test_granted_invocations_are_a_subset_of_what_the_wrapper_accepts():
    granted = _granted_invocations()
    accepted = _wrapper_accepted_invocations()
    assert granted <= accepted
    # and a real subset -- proving sudoers is narrower than the wrapper's own
    # capability (e.g. it can kill-port backend-tls; sudoers does not grant it)
    assert granted != accepted


def test_denies_docker_group_escalation():
    """The #14317 regression: usermod -aG docker must never be NOPASSWD."""
    content = _sudoers_content()
    assert "usermod" not in content
    assert "docker" not in content


def test_denies_bare_binaries_and_unlisted_wrapper_invocations():
    granted = _granted_invocations()
    for invocation in (
        "kill-port backend-tls",  # the wrapper supports it; sudoers must not grant it
        "diagnose-port backend",
        "diagnose-port frontend",
        "kill-port",  # no argument
        "",
    ):
        assert not _is_permitted(invocation, granted), f"{invocation!r} must not be NOPASSWD-permitted"
    content = _sudoers_content()
    for bare_binary in ("/usr/bin/lsof", "/usr/bin/kill", "/usr/bin/pkill"):
        assert bare_binary not in content, f"{bare_binary} must never be granted directly"


def test_no_wildcard_grant():
    content = _sudoers_content()
    assert not re.search(r"NOPASSWD:\s*ALL\b", content), "a blanket ALL grant defeats least privilege"


def test_account_is_resolved_not_hardcoded():
    content = _sudoers_content()
    leftover_account = "ka" + "li"
    assert leftover_account not in content, "the leftover dev-image account must never reappear"
    text = _script_text()
    assert 'AUTOBOT_USER="${AUTOBOT_USER:-autobot}"' in text
    # every sudoers rule line names the account via the resolved variable,
    # never a bare literal
    assert re.search(r"^\$\{AUTOBOT_USER\}\s+ALL=", content, re.MULTILINE)


def test_validates_before_installing_the_sudoers_file():
    """Invalid sudoers content must never reach a live sudoers.d file."""
    text = _script_text()
    assert "sudo visudo -c -f" in text
    validate_pos = text.index("sudo visudo -c -f")
    sudoers_install_pos = text.index('sudo install -m 0440 -o root -g root "${sudoers_tmp}"')
    assert validate_pos < sudoers_install_pos, "validation must happen before the sudoers file goes live"


def test_account_name_is_validated_before_use():
    """Round 2 finding 4: visudo checks grammar only. A multi-line
    AUTOBOT_USER must be rejected before it ever reaches the heredoc."""
    text = _script_text()
    match = re.search(r'\[\[ "\$\{AUTOBOT_USER\}" =~ (\^\S+\$) \]\]', text)
    assert match, "no AUTOBOT_USER validation regex found"
    pattern = re.compile(match.group(1))

    for valid in ("autobot", "autobot-vnc", "a", "a" * 32):
        assert pattern.match(valid), f"{valid!r} should be accepted"

    injection = "autobot\nattacker ALL=(ALL) NOPASSWD: ALL"
    command_injection = "autobot; id"
    for invalid in (injection, "", command_injection, "autobot ALL=(ALL) NOPASSWD: ALL", "a" * 33, "-autobot"):
        assert not pattern.match(invalid), f"{invalid!r} must be rejected"

    # and the check must actually abort the script, not just log
    validate_pos = text.index('=~ ')
    exit_pos = text.index("exit 1", validate_pos)
    assert exit_pos - validate_pos < 200, "the validation failure must exit near where it's checked"


def test_account_name_validation_runs_before_any_sudoers_or_wrapper_action():
    text = _script_text()
    validate_pos = text.index("=~ ")
    wrapper_install_pos = text.index('sudo install -m 0755 -o root -g root "${WRAPPER_SRC}"')
    sudoers_install_pos = text.index('sudo install -m 0440 -o root -g root "${sudoers_tmp}"')
    assert validate_pos < wrapper_install_pos < sudoers_install_pos


def test_wrapper_is_deployed_root_owned_and_read_only_in_this_repo():
    text = _script_text()
    assert 'WRAPPER_DEST="/opt/autobot/bin/autobot-cleanup-port"' in text
    assert 'sudo install -m 0755 -o root -g root "${WRAPPER_SRC}" "${WRAPPER_DEST}"' in text
    assert WRAPPER.exists(), "autobot-cleanup-port must ship next to setup_passwordless_sudo.sh"
