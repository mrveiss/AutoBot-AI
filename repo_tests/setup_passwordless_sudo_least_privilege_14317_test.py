# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025-2026 mrveiss
# Author: mrveiss
"""setup_passwordless_sudo.sh grants exactly three commands, never a wildcard (#14317).

Before this fix, the script hardcoded NOPASSWD sudo to a leftover dev-image
account ('ka' + 'li') and included `usermod -aG docker <account>` in the grant --
docker group membership is equivalent to root, so that line was a passwordless
path to root sitting beside plain process-inspection commands.

Static only: the script itself calls `sudo install`/`sudo visudo`, so it is
never executed here (or anywhere in this suite) -- it modifies real sudoers
state and system accounts. These tests parse its source text and reproduce
just enough of sudoers' matching semantics (exact user + exact command; no
wildcard rules exist in this fixture) to prove a command OUTSIDE the
allowlist is denied, not merely that the ones inside it are permitted.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO_ROOT
    / "autobot-infrastructure"
    / "shared"
    / "scripts"
    / "setup"
    / "system"
    / "setup_passwordless_sudo.sh"
)

# The generated sudoers rule shape this script writes: an unquoted heredoc, so
# ${AUTOBOT_USER} is the only shell expansion in it -- resolved at runtime
# from an env var, never a literal account name written into the file.
_RULE_RE = re.compile(r"^\$\{AUTOBOT_USER\}\s+ALL=\(ALL\)\s+NOPASSWD:\s*(\S+)\s*$", re.MULTILINE)

# The heredoc IS the actual sudoers content -- everything else in the script
# is prose (including this fix's own explanation of the bug it replaces,
# which necessarily names the leftover account and the removed command).
# Tests below check the artifact that is actually installed, not the
# commentary describing why it changed.
_HEREDOC_RE = re.compile(r'cat > "\$\{sudoers_tmp\}" <<EOF\n(.*?)\nEOF\n', re.DOTALL)


def _sudoers_content() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    match = _HEREDOC_RE.search(text)
    assert match, "could not locate the sudoers heredoc in the script"
    return match.group(1)


def _granted_commands() -> set[str]:
    return set(_RULE_RE.findall(_sudoers_content()))


def _is_permitted(command: str, granted: set[str]) -> bool:
    """Sudoers matching for this fixture: no wildcards are used anywhere in the
    generated file, so a command is permitted iff it is EXACTLY one of the
    granted absolute paths -- the same rule visudo would apply."""
    return command in granted


def test_grants_exactly_the_process_management_allowlist():
    granted = _granted_commands()
    assert granted == {"/usr/bin/lsof", "/usr/bin/kill", "/usr/bin/pkill"}


def test_denies_docker_group_escalation():
    """The #14317 regression: usermod -aG docker must never be NOPASSWD."""
    granted = _granted_commands()
    assert not _is_permitted("/usr/sbin/usermod", granted)
    content = _sudoers_content()
    assert "usermod" not in content
    assert "docker" not in content


def test_denies_arbitrary_root_commands():
    granted = _granted_commands()
    for command in ("/bin/bash", "/usr/bin/su", "/usr/sbin/visudo", "ALL"):
        assert not _is_permitted(command, granted), f"{command} must not be NOPASSWD-permitted"


def test_no_wildcard_grant():
    content = _sudoers_content()
    assert not re.search(r"NOPASSWD:\s*ALL\b", content), "a blanket ALL grant defeats least privilege"


def test_account_is_resolved_not_hardcoded():
    content = _sudoers_content()
    leftover_account = "ka" + "li"
    assert leftover_account not in content, "the leftover dev-image account must never reappear"
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'AUTOBOT_USER="${AUTOBOT_USER:-autobot}"' in text
    # every sudoers rule line names the account via the resolved variable,
    # never a bare literal
    assert re.search(r"^\$\{AUTOBOT_USER\}\s+ALL=", content, re.MULTILINE)


def test_validates_before_installing():
    """Invalid sudoers content must never reach a live sudoers.d file."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "sudo visudo -c -f" in text
    validate_pos = text.index("sudo visudo -c -f")
    install_pos = text.index("sudo install")
    assert validate_pos < install_pos, "validation must happen before the file goes live"
