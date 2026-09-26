# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One Redis config path, named once, and actually passed to the daemon (#17434).

`roles/redis` rendered a 2933-byte config and **the running server never read
it.** The drop-in the role installs sets `User`, `Group`, limits, `MemoryLimit`
and two `Environment=` lines -- and no `ExecStart`, so the packaged unit's
argument-less `ExecStart` stood, and the packaged wrapper then chose the file
itself:

    CMD=${BASEDIR}/bin/redis-server
    if [ -f "${1}" ]; then CONFFILE="${1}"; shift
    elif [ -f ${BASEDIR}/etc/redis-stack.conf ]; then CONFFILE=${BASEDIR}/etc/...

With no argument the `elif` is guaranteed, so the daemon read the package's own
23-byte default. On the `database`-role node `maxmemory 6gb` read back as `0`,
`appendonly yes` as `no` and `requirepass` as empty.

Four spellings of one path existed. Two were pure fiction -- neither
`/etc/redis-stack/` nor `/etc/redis/` exists on a provisioned node -- so every
write to them landed in nothing:

* `/opt/redis-stack/etc/redis-stack.conf` -- what the daemon actually read, and
  referenced by no code at all.
* `/etc/redis-stack.conf` -- rendered, never passed. **Canonical.**
* `/etc/redis-stack/redis-stack.conf` -- `pki/configurator.py`, the unit
  template, `mtls-migrate.py`'s write side.
* `/etc/redis/redis.conf` -- the plain-redis path, on the role's public
  interface and in nine `roles/redis-replication` tasks.

Why guard this rather than trust the edits. #16060 and #16071 already pinned the
*unit* name and the *package* name against the same plain-redis premise. The
premise survived one field over, in the config path, because each guard covered
the symbol next to the defect instead of the belief behind it. This one covers
the belief.

What these assertions can and cannot see, stated because the gap matters:

* The sweep skips `#`-comment lines. That is deliberate -- #16060's first draft
  flagged its own explanation of the bug -- but in Markdown a leading `#` is a
  heading, so a non-canonical path inside one would be missed. No heading
  contains one today; a path in prose or a code fence IS caught.
* It reads literals only. A path assembled at runtime is invisible, which is
  why `test_the_declarations_agree` pins the two declarations directly.
* It skips its own file (`_SELF`), which has to name every spelling it forbids.
  So it does not guard itself -- see the note on `_SELF`.

Mutation check: delete the `ExecStart=` pair from
`roles/redis/templates/redis-stack-override.conf.j2` and
`test_the_drop_in_passes_the_config_to_the_daemon` goes red -- that is the one
assertion standing between a correct config and an ignored one. Change either
declaration and `test_the_declarations_agree` names both values.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ANSIBLE = "autobot-slm-backend/ansible"

#: The expected answer, asserted against BOTH declarations below rather than
#: trusted from here.
_CANONICAL = "/etc/redis-stack.conf"

#: Every spelling that is not canonical. `/opt/...` is the packaged default the
#: daemon falls back to: correct as a description, wrong as a target, so it is
#: swept like the rest and exempted where it is being described.
_WRONG = (
    "/etc/redis-stack/redis-stack.conf",
    "/etc/redis/redis.conf",
    "/opt/redis-stack/etc/redis-stack.conf",
)

#: `file:line` -> why this non-canonical literal is allowed to stay.
#:
#: The two `docs/api/redis-documentation.md` entries that were here are gone:
#: #17438 deleted the compose example they covered (a fictitious `redis.conf`
#: mount and `command:` override that this repo never ran), so the container
#: path they excused no longer exists. `test_every_exemption_is_still_live`
#: caught them on the rebase, which is what it is for -- a stranded exemption
#: is a stale claim that silently covers whatever later occupies that line.
#:
#: Every entry is prose ABOUT the defect or a genuinely different namespace. No
#: entry is a live path a process resolves; an exemption that covered one would
#: be this guard reporting a clean sweep over the bug it exists to catch.
_EXEMPT = {
    "autobot-slm-backend/services/backup.py:524": (
        "docstring prose recording #16625's finding -- it names the path to say "
        "roles/redis never renders it. Not a `#` comment, so the sweep sees it."
    ),
}

#: This file, skipped by the sweep below. A guard that forbids three spellings
#: has to write all three down -- in `_WRONG`, in its docstring and in its
#: failure messages -- so sweeping itself makes it its own largest offender.
#: (It passed until the commit that tracked it: `tracked_paths` reads git, so an
#: untracked new guard is invisible to its own sweep.) The cost is stated rather
#: than hidden: a non-canonical path used for real INSIDE this file would not be
#: caught here. Nothing in it resolves a path -- it only compares strings.
_SELF = "repo_tests/redis_config_path_is_canonical_17434_test.py"

#: Measured, not guessed: of the tracked extensions, exactly four carry a Redis
#: config-path literal today -- 10 `.md`, 8 `.yml`, 6 `.py` and 2 `.j2`.
#:
#: `.j2` is deliberately NOT swept. Both templates that carry one are asserted by
#: name below, which is the stronger check -- a sweep only says "no wrong literal
#: appears", while those say "the right one is passed to the daemon". Dropping it
#: also returns a #15900 record entry, and that record only shrinks.
#:
#: `*.yaml`, `*.sh`, `*.conf` and `*.service` are dropped for the opposite reason:
#: each matches no such literal AND sits outside the python path filter, so
#: declaring one buys a record entry -- a standing note that this guard does not
#: re-run when that tree changes -- for coverage that does not exist. Stated
#: plainly: a `.yaml`, `.sh`, `.conf` or literal `.service` file naming a
#: non-canonical path is NOT caught here.
_EXTENSIONS = ("*.py", "*.yml", "*.md")

#: A sweep that stops reaching the tree would report a clean repository.
#:
#: Measured, not estimated: the first floor here was 9000, taken from a shell
#: count over a DIFFERENT extension list, and the declaration caught it at 8400.
#: `floor + growth` must cover the population, so the pair leaves room in both
#: directions -- the sweep may reach 9500 files before the ceiling binds, and the
#: floor fires if it ever drops below 6500. A floor pinned at `population -
#: growth` is red on the next file anyone adds.
REACH = declare(
    "redis-config-path-census",
    discover=lambda root: _files(root),
    floor=6500,
    what="tracked text files swept for a Redis config-path literal",
    growth=3000,
)


def _files(root: Path) -> list[str]:
    try:
        # No "*.min.js": #15900 refuses an exclusion glob for a tree the extension
        # filter never reaches, because a dead exclusion reads as coverage.
        return tracked_paths(root, *_EXTENSIONS, exclude=("node_modules",))
    except EmptyEnumeration:
        return []


def _declared_in_ansible(root: Path) -> str | None:
    """`redis_config_file` from group_vars/all.yml -- the ansible declaration.

    Parsed with a regex rather than a YAML load: the file is full of Jinja that
    a loader would choke on, and what is being pinned is the literal as written.
    """
    text = (root / _ANSIBLE / "inventory" / "group_vars" / "all.yml").read_text(encoding="utf-8")
    match = re.search(r'^redis_config_file:\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else None


def _declared_in_python(root: Path) -> str | None:
    """`REDIS_STACK_CONFIG_PATH` from pki/config.py, read from the AST.

    Parsed, not imported: `pki.config` pulls pydantic-settings and the shared
    paths module, and what is being pinned is the declaration itself.
    """
    tree = ast.parse((root / "autobot-backend" / "pki" / "config.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "REDIS_STACK_CONFIG_PATH":
                    return node.value.value
    return None


def scan_text(rel: str, text: str) -> list[str]:
    """Findings in one file's TEXT. Pure, so it can be shown a fixture.

    Extracted from `_sweep` on review (#17444): the only test of the detector
    ran it against the live tree, which proves the tree is clean and never that
    the detector trips. A regression in the `startswith("#")` skip or the `hit`
    lookup would have passed in silence -- and a detector that fires on
    everything or on nothing is worse than none. The contrast pair lives in
    `TestTheDetectorTripsAndStaysQuiet`.
    """
    findings: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if is_comment_line(line):
            continue
        hit = next((wrong for wrong in _WRONG if wrong in line), None)
        if hit and f"{rel}:{number}" not in _EXEMPT:
            findings.append(f"{rel}:{number} -> {hit}")
    return findings


def is_comment_line(line: str) -> bool:
    """A whole-line `#` comment, which the sweep never reports.

    Named rather than inlined because `_EXEMPT`'s liveness check needs the same
    question: an exemption pointing at a line the sweep skips anyway covers
    nothing, and used to read as live because the line still contained a
    `_WRONG` literal (#17444 review).
    """
    return line.strip().startswith("#")


def _sweep(root: Path) -> list[str]:
    """Non-canonical config-path literals outside `#` comments and exemptions."""
    offenders: list[str] = []
    files = _files(root)
    for rel in files:
        if rel == _SELF:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not any(wrong in text for wrong in _WRONG):
            continue
        offenders.extend(scan_text(rel, text))
    REACH.completed(files)
    return offenders


def test_the_sweep_actually_reaches_something() -> None:
    """`nothing found` and `did not look` must not be the same green.

    Every assertion below reports a clean tree when the sweep reaches nothing,
    and a clean tree is exactly what this guard is supposed to deny.
    """
    REACH.verify_floor(repo_root())


def test_the_declarations_agree() -> None:
    """One value, two languages. The guard is what makes that one place.

    A YAML tree and a Python package cannot share a literal, so "named in one
    place" is only true while something checks it. This is that something.
    """
    root = repo_root()
    ansible, python = _declared_in_ansible(root), _declared_in_python(root)

    assert ansible == _CANONICAL, f"group_vars/all.yml declares {ansible!r}, expected {_CANONICAL!r}"
    assert python == ansible, (
        f"pki/config.py declares REDIS_STACK_CONFIG_PATH={python!r} but ansible declares "
        f"redis_config_file={ansible!r} -- the two halves of one path have drifted (#17434)"
    )


def test_the_role_defaults_follow_the_declaration() -> None:
    """The role's public interface, which other roles inherit.

    `roles/redis/defaults/main.yml` declared `/etc/redis/redis.conf` with no
    consumer inside its own role -- a false value that
    `roles/redis-replication` then inherited in nine tasks.
    """
    root = repo_root()
    for rel in ("roles/redis/defaults/main.yml", "roles/redis-replication/defaults/main.yml"):
        text = (root / _ANSIBLE / rel).read_text(encoding="utf-8")
        match = re.search(r'^redis_config_file:\s*"([^"]+)"', text, re.MULTILINE)
        assert match, f"{rel} no longer declares redis_config_file"
        assert match.group(1) == _CANONICAL, (
            f"{rel} declares {match.group(1)!r}; a role default that disagrees with "
            f"{_CANONICAL!r} is inherited by every role that does not override it (#17434)"
        )


def test_the_drop_in_passes_the_config_to_the_daemon() -> None:
    """The load-bearing assertion: a correct path nothing passes is still inert.

    Every other test here can pass while the daemon reads the packaged default,
    because that was the state of the tree before #17434 -- the path was
    *rendered* correctly to `/etc/redis-stack.conf` all along. What was missing
    was an `ExecStart` carrying it.
    """
    template = (repo_root() / _ANSIBLE / "roles" / "redis" / "templates" / "redis-stack-override.conf.j2").read_text(
        encoding="utf-8"
    )
    directives = [line.strip() for line in template.splitlines() if line.strip().startswith("ExecStart=")]

    assert "ExecStart=" in directives, (
        "the drop-in must reset ExecStart before setting it -- systemd APPENDS to the "
        "base unit's list otherwise, and redis-stack-server would be started twice (#17434)"
    )
    passing = [d for d in directives if "redis_config_file" in d]
    assert passing, (
        "the systemd drop-in sets no ExecStart that passes {{ redis_config_file }}. Without "
        "it the packaged wrapper falls back to /opt/redis-stack/etc/redis-stack.conf and every "
        "directive the role renders -- requirepass included -- is silently ignored (#17434)"
    )


def test_the_drop_in_creates_the_directories_the_config_writes_to() -> None:
    """Activating the config is not enough if it cannot start.

    `redis-stack.conf.j2` hardcodes `pidfile /var/run/redis-stack/...` and
    `logfile /var/log/redis-stack/...` (the directory database.yml's nightly
    cleanup actually sweeps), and no task in `roles/redis` creates either --
    on a provisioned node neither exists. That was free while the config was
    ignored and fatal the moment it was not: Redis exits at startup when it
    cannot open its logfile. `/run` is a tmpfs, so a one-time `file:` task would
    not survive a reboot either; systemd is the only mechanism that holds.
    """
    template = (repo_root() / _ANSIBLE / "roles" / "redis" / "templates" / "redis-stack-override.conf.j2").read_text(
        encoding="utf-8"
    )

    for directive, path in (
        ("LogsDirectory=redis-stack", "/var/log/redis-stack"),
        ("RuntimeDirectory=redis-stack", "/var/run/redis-stack"),
    ):
        assert directive in template, (
            f"the drop-in does not declare {directive}, so {path} -- which the rendered config "
            f"writes to -- would not exist when Redis starts (#17434)"
        )


def test_the_unit_template_passes_the_canonical_path() -> None:
    """The other template, asserted directly since `.j2` is not swept.

    `templates/systemd/redis-stack-server.service.j2` is the full unit
    `deploy-database.yml` renders, and it named `/etc/redis-stack/redis-stack.conf`
    -- a directory that does not exist, so the wrapper's `[ -f "${1}" ]` test
    failed and it fell back to the packaged default exactly as the drop-in path
    did. Two different mechanisms, one outcome.
    """
    template = (repo_root() / _ANSIBLE / "templates" / "systemd" / "redis-stack-server.service.j2").read_text(
        encoding="utf-8"
    )
    exec_start = [line for line in template.splitlines() if line.startswith("ExecStart=")]

    assert exec_start, "the unit template declares no ExecStart"
    assert all("redis_config_file" in line for line in exec_start), (
        f"the unit template's ExecStart does not pass {{{{ redis_config_file }}}}: {exec_start}. "
        f"A literal path here is the same defect in a second mechanism (#17434)"
    )


def test_no_site_names_a_non_canonical_config_path() -> None:
    """The sweep. Four spellings, one survivor."""
    offenders = _sweep(repo_root())

    assert not offenders, (
        "these name a Redis config path that is not the canonical "
        f"{_CANONICAL!r} (#17434):\n  " + "\n  ".join(offenders) + "\n\n"
        "Neither /etc/redis-stack/ nor /etc/redis/ exists on a provisioned node, so a write "
        "to either reaches nothing and reports success. Derive from `redis_config_file` "
        "(ansible, with `| default(...)` outside a role) or `REDIS_STACK_CONFIG_PATH` (Python). "
        "If the literal is prose about the defect, add it to _EXEMPT with its reason."
    )


def test_every_exemption_is_still_live() -> None:
    """An exemption whose line has moved is a hole nobody is watching.

    Without this, fixing an exempted site leaves its entry behind, and the entry
    then silently covers whatever later occupies that line number.
    """
    root = repo_root()
    stale = []
    for where, reason in _EXEMPT.items():
        rel, _, number = where.rpartition(":")
        path = root / rel
        if not path.exists():
            stale.append(f"{where} (file gone) -- {reason}")
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        index = int(number) - 1
        if index >= len(lines) or not any(wrong in lines[index] for wrong in _WRONG):
            stale.append(f"{where} (no longer names a non-canonical path) -- {reason}")
        elif is_comment_line(lines[index]):
            # The sweep never reports a `#` comment line, so an exemption on one
            # excuses nothing while reading as live -- the literal is still there,
            # which is all the old check asked (#17444 review). A dead entry that
            # looks authoritative is what the bidirectional contract forbids.
            stale.append(
                f"{where} points at a `#` comment line, which the sweep skips anyway -- "
                f"the exemption covers nothing. Delete it. ({reason})"
            )

    assert not stale, (
        "these exemptions no longer describe what is at that line -- delete them so the "
        "sweep covers it again (#17434):\n  " + "\n  ".join(stale)
    )


class TestTheDetectorTripsAndStaysQuiet:
    """The contrast pair `_sweep` never had (#17444 review).

    Every assertion elsewhere in this file runs the detector against the live
    tree, so all of them pass when the tree is clean -- including if the
    detector has stopped detecting. These show it on fixtures: one that must
    trip it, and four that must not.
    """

    def test_it_trips_on_a_non_canonical_literal(self) -> None:
        findings = scan_text("fake.yml", "dest: /etc/redis/redis.conf\n")
        assert findings == ["fake.yml:1 -> /etc/redis/redis.conf"]

    def test_it_reports_every_wrong_spelling(self) -> None:
        for wrong in _WRONG:
            assert scan_text("f.yml", f"path: {wrong}\n"), f"{wrong} is not detected"

    def test_it_stays_quiet_on_the_canonical_path(self) -> None:
        assert scan_text("fake.yml", f"dest: {_CANONICAL}\n") == []

    def test_it_stays_quiet_on_a_comment_line(self) -> None:
        """#16060's lesson: a guard's own explanation of the bug is not the bug."""
        assert scan_text("fake.yml", "# was /etc/redis/redis.conf until #17434\n") == []
        assert scan_text("fake.yml", "   # indented /etc/redis/redis.conf\n") == []

    def test_an_inline_comment_is_not_a_comment_line(self) -> None:
        """The trap that caught this guard's own first draft.

        `dest: X  # was /etc/redis/redis.conf` starts with `dest:`, so the line
        is code carrying prose and the literal is still published.
        """
        findings = scan_text("fake.yml", "dest: ok  # was /etc/redis/redis.conf\n")
        assert len(findings) == 1

    def test_an_exempt_line_is_not_reported(self) -> None:
        rel, number = next(iter(_EXEMPT)).rsplit(":", 1)
        text = "\n" * (int(number) - 1) + "x = '/etc/redis/redis.conf'\n"
        assert scan_text(rel, text) == []
        assert scan_text("some/other/file.py", text) != []
