# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every nginx site that gets templated into sites-available/ must also be
enabled in the SAME task file (#16979).

Root cause: roles/slm_manager/tasks/nginx_site.yml rendered
sites-available/{{ slm_nginx_config }} but the steps that made it live (stat
sites-enabled for a non-symlink, replace it, link it) lived only in
roles/slm_manager/tasks/main.yml -- reachable on a full provision, but NOT
from playbooks/update-all-nodes.yml or playbooks/update-node.yml, which
include ONLY nginx_site.yml via `tasks_from`. A node whose sites-enabled
entry was a stale regular file kept serving that frozen config forever: every
self-update re-rendered sites-available and nginx never noticed.
roles/frontend/tasks/code_only.yml had the identical shape (#16979 AC5).

This guard encodes the invariant those two fixes both restored: *the file
that renders a site into sites-available/ also contains the task that links
it into sites-enabled/*. Ansible split into role task files precisely so
self-update playbooks can include a narrow slice of a role (the `tasks_from`
/ #12959 delivery contract) -- so if the render and the enable live in
different files, the render is the only slice guaranteed to run on every
path, and a second render site can reintroduce this exact gap without either
of the two fixes above catching it.

Static analysis only: reads the YAML, never runs ansible. Covers every
roles/*/tasks/*.yml and playbooks/*.yml file in the ansible tree, not just
the two known sites -- a THIRD role adding a nginx site the same way is
caught by the same scan, not by remembering to update a hardcoded list.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from repo_tests._paths import repo_root

_REPO_ROOT = repo_root()
_ANSIBLE_ROOT = _REPO_ROOT / "autobot-slm-backend" / "ansible"

_SITES_AVAILABLE_PREFIX = "/etc/nginx/sites-available/"
_SITES_ENABLED_PREFIX = "/etc/nginx/sites-enabled/"
# "Renders" means any task that WRITES a file at that dest -- not only the
# `template` module. playbooks/deploy-native-services.yml writes its nginx
# vhost via `copy: content: |...` (a Jinja-templated inline block, same
# effect as `template:`), so a scan keyed on the `template` module alone
# would silently skip it rather than confirm it is linked.
_RENDER_KEYS = ("ansible.builtin.template", "template", "ansible.builtin.copy", "copy")
_FILE_KEYS = ("ansible.builtin.file", "file")

# Known render sites as of #16979: roles/slm_manager/tasks/nginx_site.yml,
# roles/frontend/tasks/code_only.yml, playbooks/provision-fleet-roles.yml
# (Phase 4c co-located re-render) -- all three fixed by this issue -- plus
# the pre-existing roles/backend/tasks/main.yml and the two standalone
# one-off playbooks (deploy-nginx-proxy.yml, deploy-native-services.yml)
# that already co-located render+enable. The floor below only asserts the
# scan still reaches at least this many -- it is not the source of truth for
# which files exist; `_render_sites` is.
_KNOWN_RENDER_SITE_FLOOR = 6


def _flatten(entries: object) -> list[dict]:
    """Recurse into play task lists (`hosts:`/`tasks:`/`pre_tasks:`/
    `post_tasks:`) and `block:`/`rescue:`/`always:` bodies, mirroring
    repo_tests/sync_deletions_ansible_wiring_16310_test.py's `_flatten` --
    both a role's tasks/main.yml (a flat list) and a playbook (a list of
    plays) need to resolve to one flat task list."""
    flat: list[dict] = []
    if not isinstance(entries, list):
        return flat
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if "hosts" in entry:
            for key in ("pre_tasks", "tasks", "post_tasks"):
                if key in entry:
                    flat.extend(_flatten(entry[key]))
        elif "block" in entry:
            flat.append(entry)
            flat.extend(_flatten(entry.get("block")))
            flat.extend(_flatten(entry.get("rescue")))
            flat.extend(_flatten(entry.get("always")))
        else:
            flat.append(entry)
    return flat


def _module_args(task: dict, keys: tuple[str, ...]) -> dict | None:
    for key in keys:
        args = task.get(key)
        if isinstance(args, dict):
            return args
    return None


def _basename(dest: str) -> str:
    return dest.rstrip("/").rsplit("/", 1)[-1]


def _load_tasks(path: Path) -> list[dict]:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return []
    return _flatten(doc)


def _render_dests_in_file(path: Path) -> list[str]:
    """Every ``dest`` rendered into sites-available/ by *path*, in file order."""
    return [
        dest
        for task in _load_tasks(path)
        if (args := _module_args(task, _RENDER_KEYS)) is not None
        and (dest := str(args.get("dest", ""))).startswith(_SITES_AVAILABLE_PREFIX)
    ]


def _enable_link_dests_in_file(path: Path) -> list[str]:
    """Every ``dest`` an ``ansible.builtin.file: state: link`` task in *path*
    points into sites-enabled/, in file order."""
    dests = []
    for task in _load_tasks(path):
        args = _module_args(task, _FILE_KEYS)
        if not args or args.get("state") != "link":
            continue
        dest = str(args.get("dest", ""))
        if dest.startswith(_SITES_ENABLED_PREFIX):
            dests.append(dest)
    return dests


def _has_matching_enable_link(path: Path, sites_available_dest: str) -> bool:
    """True iff *path* also links a sites-enabled/ entry with the same final
    path segment as *sites_available_dest* -- e.g. both sides spelled
    ``{{ slm_nginx_config }}``, or both spelled the literal ``autobot-frontend``.
    Matching on the raw Jinja/literal basename (not a resolved value) is
    deliberate: this is static analysis over YAML, not a templating engine."""
    target = _basename(sites_available_dest)
    return any(_basename(d) == target for d in _enable_link_dests_in_file(path))


def _candidate_files(ansible_root: Path) -> list[Path]:
    """roles/*/tasks/*.yml and playbooks/*.yml -- the two directories every
    real nginx site render lives under (confirmed by grepping the whole
    ansible tree for `dest:.*sites-available` while writing this guard).

    Deliberately excludes loose top-level ansible/*.yml one-off scripts:
    migrate-grafana-to-vm.yml writes
    `sites-available/autobot-slm.backup-{{ ansible_facts['date_time'].epoch }}`
    -- an explicit backup snapshot, not the live config nginx serves -- and
    including it would need extra logic just to tell that dest apart from a
    real site, for a directory the `tasks_from` self-update seam this issue
    is about does not operate on in the first place."""
    return sorted((ansible_root / "roles").glob("*/tasks/*.yml")) + sorted((ansible_root / "playbooks").glob("*.yml"))


def _render_sites(ansible_root: Path) -> list[tuple[Path, str]]:
    """(file, dest) for every sites-available/ render found under
    roles/*/tasks/*.yml and playbooks/*.yml."""
    found: list[tuple[Path, str]] = []
    for path in _candidate_files(ansible_root):
        for dest in _render_dests_in_file(path):
            found.append((path, dest))
    return found


# --------------------------------------------------------------------------
# Vacuity floor (#16979 AC4): the scan must actually reach the ansible tree,
# not silently return zero because a glob pattern or the root moved.
# --------------------------------------------------------------------------


def test_render_sites_vacuity_floor() -> None:
    sites = _render_sites(_ANSIBLE_ROOT)
    assert len(sites) >= _KNOWN_RENDER_SITE_FLOOR, (
        f"only {len(sites)} nginx sites-available render(s) found under "
        f"{_ANSIBLE_ROOT} -- expected at least {_KNOWN_RENDER_SITE_FLOOR} "
        "(roles/slm_manager/tasks/nginx_site.yml, roles/frontend/tasks/code_only.yml, "
        "playbooks/provision-fleet-roles.yml, roles/backend/tasks/main.yml, and the two "
        "standalone deploy-*.yml playbooks). The scan did not reach the ansible tree -- "
        "this is 'did not look', not 'found nothing to fix'."
    )


# --------------------------------------------------------------------------
# The actual guard: every render site enforces its own sites-enabled link.
# --------------------------------------------------------------------------


def test_every_sites_available_render_enforces_its_sites_enabled_link_in_the_same_file() -> None:
    sites = _render_sites(_ANSIBLE_ROOT)
    assert len(sites) >= _KNOWN_RENDER_SITE_FLOOR, "vacuity floor failed -- see test_render_sites_vacuity_floor"

    gaps = [
        f"{path.relative_to(_ANSIBLE_ROOT)}: renders {dest!r} with no matching "
        f"state:link task into sites-enabled/ in the same file"
        for path, dest in sites
        if not _has_matching_enable_link(path, dest)
    ]
    assert gaps == [], "sites-available render(s) with no matching sites-enabled link:\n" + "\n".join(gaps)


# --------------------------------------------------------------------------
# Negative control: a synthetic render-without-link file must be caught by
# the same checker -- proving the guard has teeth, not just that today's
# real files happen to pass.
# --------------------------------------------------------------------------


def test_negative_control_a_render_without_a_link_is_flagged(tmp_path) -> None:
    synthetic = tmp_path / "synthetic_unlinked_site.yml"
    synthetic.write_text(
        """\
- name: "Render a site with no enable step (negative control)"
  ansible.builtin.template:
    src: fake.conf.j2
    dest: /etc/nginx/sites-available/synthetic-site
    mode: "0644"
""",
        encoding="utf-8",
    )

    dests = _render_dests_in_file(synthetic)
    assert dests == ["/etc/nginx/sites-available/synthetic-site"], "negative control fixture did not parse as expected"
    assert not _has_matching_enable_link(synthetic, dests[0]), (
        "negative control: a render with no matching sites-enabled link must be reported as unlinked -- "
        "the checker is vacuously passing everything"
    )


def test_positive_control_a_render_with_a_matching_link_passes(tmp_path) -> None:
    synthetic = tmp_path / "synthetic_linked_site.yml"
    synthetic.write_text(
        """\
- name: "Render a site (positive control)"
  ansible.builtin.template:
    src: fake.conf.j2
    dest: /etc/nginx/sites-available/synthetic-site
    mode: "0644"

- name: "Enable the site (positive control)"
  ansible.builtin.file:
    src: /etc/nginx/sites-available/synthetic-site
    dest: /etc/nginx/sites-enabled/synthetic-site
    state: link
""",
        encoding="utf-8",
    )

    dests = _render_dests_in_file(synthetic)
    assert dests == ["/etc/nginx/sites-available/synthetic-site"], "positive control fixture did not parse as expected"
    assert _has_matching_enable_link(synthetic, dests[0]), (
        "positive control: a render WITH a matching sites-enabled link must pass -- "
        "the checker is rejecting everything, not discriminating"
    )
