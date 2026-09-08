# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`redis-server` is never operated as a systemd unit or installed by apt (#16071).

The fleet runs Redis Stack. `roles/redis` installs `redis-stack-server`, and
`systemctl show -p LoadState` reports `not-found` for both `redis` and
`redis-server` on a provisioned node. `autobot-database/README.md` states it
plainly: *"Standard `redis-server` from apt is NOT the same."*

#16060 fixed five sites that had drifted to the absent names. It did not fix
all of them, and the ones it missed were the ones that act rather than report:

* `services/blue_green.py` purged the `redis` role by stopping `redis-server`
  and `redis`, leaving Redis Stack serving data on a node that had released
  the role -- under `ignore_errors: true`, so a wrong unit name and a right
  one produced identical output.
* `ansible/upgrade-backend-agent.yml` gave the agent a discovery list of two
  absent units and no present one.
* Two installers -- `install-bare-metal.sh` and `code_analysis/install.sh` --
  `apt-get install`ed plain Redis, which starts cleanly and then fails on the
  first module command.

**The scope is deliberately narrow, and the narrowness is the design.** The
string `redis-server` is correct in a dozen places and a blanket rename would
break them: it is the binary Redis Stack ships at `/opt/redis-stack/bin/`, the
name in `/var/log/redis-stack/redis-server.log`, the process `pgrep` matches,
one half of every conflict table that exists to say the two collide, and the
example in a docstring explaining the difference. Counting mentions would
report a large number and mean nothing.

So this guard matches only the three constructs where the name is an
instruction to the system: a `systemctl` verb, a unit dependency, and an apt
install target. Prose is excluded by stripping backtick-quoted spans first --
`services/role_units.py` documents this very defect by quoting
`systemctl stop redis-server`, and a guard that flagged its own explanation
would be #16011 repeated inside the fix for #16060.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from repo_tests._paths import repo_root

_ROOT = repo_root()

#: Documentation, tests and generated artefacts. A `.md` file naming the apt
#: package is usually contrasting it with Redis Stack, which is the point.
_SKIP = re.compile(r"(_test\.py$|/tests?/|/test_|baseline|\.md$|\.lock$|node_modules/|openapi\.json$)")

_BACKTICKED = re.compile(r"`[^`\n]*`")
_COMMENT = re.compile(r"^\s*(#|//|--|\*|/\*)")

_VERBS = "start|stop|restart|enable|disable|status|reload|is-active|is-enabled|mask|unmask"
_OPERATES = [
    ("a systemctl verb", re.compile(rf"systemctl\s+(?:--\S+\s+)*(?:{_VERBS})\s+redis-server\b")),
    ("a unit dependency", re.compile(r"\b(?:After|Wants|Requires|BindsTo|PartOf)=[^\n]*\bredis-server\.service\b")),
    ("an apt install target", re.compile(r"\bapt(?:-get)?\s+install\b[^\n]*\bredis-server\b")),
]

_CANONICAL = "redis-stack-server"

#: One declared exemption, with its reason, rather than a list that may grow
#: quietly. `fix-architecture-issues.sh` enforces "Redis runs only on the
#: database node" and stops BOTH names, because a node provisioned before
#: #16071 may still carry the apt package `install-bare-metal.sh` used to
#: install. There, stopping an absent unit is the correct behaviour -- it is
#: cleaning up a state this change stops creating, not managing a service.
#: `test_the_declared_exemption_is_not_covering_a_real_gap` fails if that
#: file ever stops naming the canonical unit, so the exemption cannot outlive
#: its reason.
_LEGACY_CLEANUP = {
    "autobot-infrastructure/shared/scripts/vm-management/fix-architecture-issues.sh",
}


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [f for f in out if not _SKIP.search(f)]


def _offences_in(text: str) -> list[str]:
    """Lines instructing the system to operate a unit named `redis-server`."""
    found = []
    for line in text.splitlines():
        if _COMMENT.match(line):
            continue
        # Prose citing the command is not the command. Strip it before matching.
        bare = _BACKTICKED.sub("", line).replace(_CANONICAL, "")
        for label, pattern in _OPERATES:
            if pattern.search(bare):
                found.append(f"{label}: {line.strip()[:110]}")
    return found


def test_the_sweep_reaches_the_tree_it_claims() -> None:
    """A collapsed enumeration reports 'no offences' for the same reason a clean tree does."""
    files = _tracked_files()
    assert len(files) > 3000, f"only {len(files)} tracked files in scope -- the enumeration collapsed"


def test_no_code_operates_a_unit_named_redis_server() -> None:
    offences = []
    for name in _tracked_files():
        if name in _LEGACY_CLEANUP:
            continue
        path = _ROOT / name
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, IsADirectoryError):
            continue
        for offence in _offences_in(text):
            offences.append(f"{name}: {offence}")

    assert not offences, (
        "these operate a systemd unit named `redis-server`, which does not exist on a "
        f"provisioned node -- use `{_CANONICAL}` (#16071):\n  " + "\n  ".join(offences)
    )


def test_the_declared_exemption_is_not_covering_a_real_gap() -> None:
    """An exemption a reader cannot check is indistinguishable from a blind spot.

    The one exempt file is exempt because it stops BOTH units deliberately. If
    it ever stops naming the canonical one, the exemption would be hiding the
    exact defect this guard exists for, so pin the reason rather than the file.
    """
    for name in sorted(_LEGACY_CLEANUP):
        path = _ROOT / name
        assert path.is_file(), f"{name} is exempt but no longer exists -- drop the entry"
        text = path.read_text(encoding="utf-8")
        assert _CANONICAL in text, (
            f"{name} is exempt from this guard because it stops `{_CANONICAL}` as well as the "
            "legacy name. It no longer does, so the exemption is now hiding a real gap (#16071)."
        )


@pytest.mark.parametrize(
    "line",
    [
        "    systemctl start redis-server",
        "sudo systemctl --now stop redis-server",
        "After=network.target redis-server.service",
        "        apt-get install -y -qq redis-server",
    ],
)
def test_the_detector_finds_a_known_offence(line: str) -> None:
    """Known positives, one per construct.

    Without these the test above passes whenever the matcher breaks, which is
    the failure mode the whole #16060 cluster is about: a state the instrument
    cannot see reads as the good state.
    """
    assert _offences_in(line), f"the detector does not see: {line.strip()}"


@pytest.mark.parametrize(
    "line",
    [
        "ExecStart=/opt/redis-stack/bin/redis-server /opt/autobot/redis.conf",
        'logfile "/var/log/redis-stack/redis-server.log"',
        'if pgrep redis-server >/dev/null; then',
        '    ("redis-server", "redis-stack-server", "Both bind to port 6379", "port"),',
        '        systemctl enable redis-stack-server',
        '# and `services/backup.py` issued `systemctl stop redis-server` against nothing',
        'and `services/backup.py` issued `systemctl stop redis-server` against nothing',
    ],
)
def test_the_detector_leaves_the_legitimate_uses_alone(line: str) -> None:
    """The other direction, and the reason this guard is narrow.

    The binary, the log file, the process name, the conflict table that exists
    to record the collision, and prose quoting the defect are all correct. A
    guard that flagged them would be renamed away by the first person to hit it.
    """
    assert not _offences_in(line), f"false positive on: {line.strip()}"
