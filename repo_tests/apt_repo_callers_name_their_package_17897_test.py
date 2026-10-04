# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every caller of the shared apt repo-add names the package it needs (#17897).

Two defects, one cause, both guarded here.

**The cause: presence detection counted files apt does not read.** A clean-machine
install died at step 4 of 7 with ``No package matching 'grafana' is available``.
The node carried ``/etc/apt/sources.list.d/grafana.list.distUpgrade`` -- correct
content, correct keyring, and *inert*: ``sources.list(5)`` has apt parse only
names ending ``.list`` or ``.sources``. ``do-release-upgrade`` renames third-party
sources to ``.list.distUpgrade`` and the suffix had been baked into the device
image. The helper's recursive grep found the match in that inert file, reported
``PRESENT``, and preserved a repository apt had never read. The same host showed
the contrast: ``nodesource.list.distUpgrade`` was equally inert but
``nodesource.sources`` sat beside it, and nodesource installed fine.

**The detector that would have caught it: ``apt_repo_verify_package``.** The
helper's verdict short-circuits to ``usable`` when no package is named --
defensible per call site, since a caller with nothing to probe for cannot do
better, and wrong as a fleet property. Six of the seven call sites inherited that
untested trust; only ``postgresql`` named a package. With one named, the probe
finds no candidate, the verdict becomes ``unusable``, the inert file is moved
aside and the canonical source is written.

The guard below is what converts "defensible default" into "declared decision":
omitting the argument is now a test failure, not a silence.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import jinja2
import pytest
import yaml
from repo_tests._ansible_tasks import load_tasks, named
from repo_tests._paths import repo_root

ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
ROLES = ANSIBLE / "roles"
HELPER = ROLES / "_shared" / "tasks" / "add_apt_repository_idempotent.yml"
HELPER_STEM = "add_apt_repository_idempotent"

VERIFY_VAR = "apt_repo_verify_package"
SOURCES_DIR = "/etc/apt/sources.list.d/"

#: Call sites resolved on a healthy tree. A FLOOR, not a ceiling: a new role that
#: adds a repo pushes the count up and is checked like the rest, while deleting a
#: call site drops below the floor and reddens, so the set can only shrink
#: deliberately. It is also the reach floor -- a resolver that finds nothing
#: fails here rather than reporting "all compliant".
EXPECTED_CALL_SITES = 7

#: Documented, shrink-only exemptions: ``"<role>/tasks/<file>.yml": "<reason>"``.
#: A site belongs here only when no package can be named *from the role itself* --
#: a wrong name makes the verdict ``unusable`` and moves a working repo aside,
#: which is worse than the trust it replaces. Empty, and the ratchet below keeps
#: it that way: adding an entry requires raising ``MAX_EXEMPTIONS`` in the same
#: diff, which is the declaration.
EXEMPTIONS: dict[str, str] = {}

#: Never raised to admit a site that merely looked awkward. Lower it when an
#: exemption is retired; raising it is a reviewed decision, not a fix.
MAX_EXEMPTIONS = 0


def _call_sites() -> list[tuple[str, dict]]:
    """Every ``include_tasks`` of the helper, as ``(role-relative path, task)``."""
    found: list[tuple[str, dict]] = []
    for path in sorted(ROLES.glob("*/tasks/*.yml")):
        try:
            tasks = load_tasks(path)
        except (AssertionError, yaml.YAMLError):
            continue
        for task in tasks:
            include = str(task.get("ansible.builtin.include_tasks", task.get("include_tasks", "")))
            if HELPER_STEM in include:
                found.append((path.relative_to(ROLES).as_posix(), task))
    return found


def _names_a_package(task: dict) -> bool:
    """The predicate the guard enforces: a non-empty ``apt_repo_verify_package``.

    ``or ""`` rather than ``get(VERIFY_VAR, "")``: a bare ``apt_repo_verify_package:``
    with no value parses as ``None``, and ``str(None)`` is the truthy ``"None"`` --
    which would have passed a call site that names nothing. Ansible reads that same
    key as empty (``None | default('', true)`` yields ``''``), so the helper
    short-circuits on it exactly as it does on an absent key.
    """
    value = (task.get("vars") or {}).get(VERIFY_VAR) or ""
    return bool(str(value).strip())


@pytest.fixture(scope="module")
def call_sites() -> list[tuple[str, dict]]:
    return _call_sites()


# ── Reach floor ──────────────────────────────────────────────────────────────


def test_the_resolver_reaches_every_known_call_site(
    call_sites: list[tuple[str, dict]],
) -> None:
    """ "Found nothing" must never read as "all compliant".

    If the glob, the YAML loader or the include spelling changes, every
    assertion below passes over an empty set. This is the instrument check.
    """
    assert len(call_sites) >= EXPECTED_CALL_SITES, (
        f"resolved {len(call_sites)} call sites of {HELPER_STEM}, expected at least "
        f"{EXPECTED_CALL_SITES}. Either a role stopped using the shared helper -- in "
        f"which case it is adding an apt repo by hand, unguarded -- or this test no "
        f"longer finds them and is reporting silence as compliance. "
        f"Resolved: {[p for p, _ in call_sites]}"
    )
    assert any("postgresql" in path for path, _ in call_sites), (
        "the postgresql call site, the one that already named a package before "
        "#17897, is not among the resolved sites -- the resolver is looking in the "
        "wrong place"
    )


# ── The fleet property ───────────────────────────────────────────────────────


def test_every_call_site_names_the_package_the_repo_exists_for(
    call_sites: list[tuple[str, dict]],
) -> None:
    """Without a package named, presence is trusted as usability unconditionally."""
    offenders = sorted(path for path, task in call_sites if not _names_a_package(task) and path not in EXEMPTIONS)
    assert not offenders, (
        f"these callers of {HELPER_STEM} pass no `{VERIFY_VAR}`, so the helper's "
        f"verdict short-circuits to 'usable' and a device-shipped source is trusted "
        f"without ever being asked whether it serves anything: {offenders}. Name the "
        f"package the role itself installs after adding the repo. If no package can "
        f"be named from the role, add a documented entry to EXEMPTIONS and raise "
        f"MAX_EXEMPTIONS in the same diff -- do not guess a name, a wrong one makes "
        f"the verdict 'unusable' and moves a working repo aside."
    )


def test_exemptions_are_real_sites_and_only_shrink(
    call_sites: list[tuple[str, dict]],
) -> None:
    """An exemption names a live call site, carries a reason, and is rationed."""
    known = {path for path, _ in call_sites}
    assert set(EXEMPTIONS) <= known, (
        f"EXEMPTIONS names call sites that do not exist: {sorted(set(EXEMPTIONS) - known)}. "
        f"A stale exemption silently excuses nothing and hides that the list is unread."
    )
    assert all(
        reason.strip() for reason in EXEMPTIONS.values()
    ), "every exemption states why no package can be named from the role"
    assert len(EXEMPTIONS) <= MAX_EXEMPTIONS, (
        f"{len(EXEMPTIONS)} exemptions against a ceiling of {MAX_EXEMPTIONS}. Raising "
        f"MAX_EXEMPTIONS is the declaration that this site genuinely cannot name a "
        f"package; it is not a way to land a diff."
    )


@pytest.mark.parametrize(
    ("vars_block", "compliant"),
    [
        ({VERIFY_VAR: "grafana"}, True),
        ({VERIFY_VAR: "openvino-{{ openvino_version }}"}, True),
        ({}, False),
        ({VERIFY_VAR: ""}, False),
        ({VERIFY_VAR: "   "}, False),
        ({VERIFY_VAR: None}, False),
    ],
)
def test_the_predicate_separates_a_named_package_from_an_absent_one(vars_block: dict, compliant: bool) -> None:
    """The contrast case, run against the predicate the tree is judged by.

    A guard asserted only against a passing tree cannot tell "enforces the rule"
    from "always returns true".
    """
    assert _names_a_package({"vars": vars_block}) is compliant


def test_the_helper_still_short_circuits_when_no_package_is_named() -> None:
    """The guard's premise. If the helper stopped trusting presence on its own,
    this file is guarding a rule that no longer has teeth and should be re-read
    rather than left passing.
    """
    expr = " ".join(
        str(named(load_tasks(HELPER), "Record the verdict")["ansible.builtin.set_fact"]["_apt_repo_verdict"]).split()
    )
    assert f"{VERIFY_VAR} | default('', true) | length == 0" in expr, (
        f"the verdict no longer short-circuits on an unnamed package. Either the "
        f"helper now verifies unconditionally -- in which case this guard's reason "
        f"to exist has changed -- or the expression was reworded. Reads: {expr}"
    )


# ── The cause: presence detection must ignore files apt does not read ────────


def _detect_script(tmp_dir: Path, match: str) -> str:
    """The real detect task's shell, rendered, pointed at a fixture directory."""
    body = named(load_tasks(HELPER), "Detect existing apt repo")["ansible.builtin.shell"]
    assert isinstance(body, str) and body.strip(), "the detect task carries no shell body"
    env = jinja2.Environment(autoescape=False)  # noqa: S701 - shell, not markup
    env.filters["quote"] = shlex.quote
    rendered = env.from_string(body).render(apt_repo_match=match)
    assert rendered.count(SOURCES_DIR) == 1, (
        f"expected exactly one mention of {SOURCES_DIR} to redirect at a fixture; "
        f"found {rendered.count(SOURCES_DIR)}. The substitution below would be "
        f"testing something other than the task. Script: {rendered}"
    )
    return rendered.replace(SOURCES_DIR, f"{tmp_dir}/")


def _detect(tmp_path: Path, files: dict[str, str], match: str = "apt.grafana.com") -> str:
    sources = tmp_path / "sources.list.d"
    sources.mkdir(exist_ok=True)
    for name, content in files.items():
        (sources / name).write_text(content, encoding="utf-8")
    done = subprocess.run(  # noqa: S603 - fixed argv, all paths under tmp_path
        ["/bin/bash", "-c", _detect_script(sources, match)],
        capture_output=True,
        text=True,
        timeout=60,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
    )
    assert done.returncode == 0, f"detect script failed: {done.stderr}"
    return done.stdout.strip()


#: The real `grafana.list.distUpgrade` line from the failing node, keyring path
#: and all. Not invented -- the point is that nothing about the CONTENT is wrong.
INERT_LINE = "deb [signed-by=/usr/share/keyrings/grafana.key] https://apt.grafana.com stable main\n"


def test_a_source_apt_does_not_read_is_not_present(tmp_path: Path) -> None:
    """The live failure. Correct content in an inert name is not a configured repo."""
    assert _detect(tmp_path, {"grafana.list.distUpgrade": INERT_LINE}) == "MISSING", (
        "a `.list.distUpgrade` leftover was reported PRESENT. apt parses only "
        "`.list` and `.sources` in sources.list.d, so the helper preserves a "
        "repository apt never reads and `Install Grafana` dies with "
        "'No package matching grafana is available'"
    )


@pytest.mark.parametrize("name", ["grafana.list", "grafana.sources"])
def test_a_source_apt_does_read_is_present(tmp_path: Path, name: str) -> None:
    """The contrast, and the instrument check.

    Without this, a detect step that always answered MISSING -- a typo in the
    find, a wrong directory -- would satisfy the inert case above and look fixed
    while every host re-added a repo it already had.
    """
    assert _detect(tmp_path, {name: INERT_LINE}) == "PRESENT", (
        f"a live `{name}` was reported MISSING; detection no longer sees the files " f"apt actually reads"
    )


def test_the_nodesource_shape_is_present(tmp_path: Path) -> None:
    """The same host's working repo: one inert file AND one live file beside it.

    This is why the failure is about the suffix and not the content --
    nodesource carried both and installed fine; grafana carried only the inert
    one and failed.
    """
    files = {
        "nodesource.list.distUpgrade": "deb https://deb.nodesource.com/node_20.x nodistro main\n",
        "nodesource.sources": "URIs: https://deb.nodesource.com/node_20.x\n",
    }
    assert _detect(tmp_path, files, match="deb.nodesource.com") == "PRESENT"


def test_an_empty_directory_is_missing(tmp_path: Path) -> None:
    """`find` matching nothing must answer MISSING, not fail or print both words."""
    assert _detect(tmp_path, {}) == "MISSING"


@pytest.mark.parametrize(
    "name",
    [
        "grafana.list.save",
        "grafana.list.bak",
        "grafana.list.dpkg-old",
        "grafana.sources.distUpgrade",
    ],
)
def test_the_other_inert_suffixes_are_also_ignored(tmp_path: Path, name: str) -> None:
    """`.distUpgrade` is one of several names apt skips. The rule is the suffix
    apt accepts, not a denylist of the ones seen on one host.
    """
    assert _detect(tmp_path, {name: INERT_LINE}) == "MISSING", (
        f"`{name}` was counted as a configured repo; apt reads neither it nor any "
        f"other name that does not end .list or .sources"
    )


def test_detection_does_not_recursive_grep_the_directory() -> None:
    """Anti-regression on the form that caused this.

    The executable tests above would also catch a reintroduced `grep -r`, but
    this names the defect so a future edit reads why the shape is deliberate.
    """
    body = str(named(load_tasks(HELPER), "Detect existing apt repo")["ansible.builtin.shell"])
    assert "grep -rqs" not in body and "grep -r " not in body, (
        "the detect step recursively greps sources.list.d again, which counts "
        "`.distUpgrade`, `.save` and `.bak` leftovers apt never parses"
    )
    assert "'*.list'" in body and "'*.sources'" in body, (
        "the detect step no longer restricts the scan to the two suffixes apt " "parses (sources.list(5))"
    )
