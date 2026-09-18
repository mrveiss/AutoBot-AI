# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every nginx site that gets templated into sites-available/ must also be
enabled in the SAME task file (#16979).

PR review (#16980) found a second, related gap this file now also guards:
roles/frontend/handlers/main.yml defined `restart nginx` (a reload) BEFORE
`test nginx config`. Ansible runs notified handlers in DEFINITION order, not
notify order, so a task that notifies both -- as roles/frontend/tasks/
code_only.yml's enable task now does -- reloaded nginx before `nginx -t` ever
ran. roles/slm_manager/handlers/main.yml already had this right (test, then
reload); frontend did not.

A follow-up review round found that first guard only swept
roles/*/handlers/main.yml, so a PLAY-level `handlers:` block (embedded
directly in a playbook, not a role) was invisible to it --
autobot-slm-backend/ansible/migrate-grafana-to-vm.yml defines its own
`reload nginx` handler with no paired test handler in that same list. It is
safe today only because an ordinary `nginx -t` task runs earlier in the same
play, outside the handlers: block entirely -- a shape the role-scoped guard
had no way to recognize as safe OR unsafe. This file's second guard sweeps
every `*.yml` under the ansible tree for a play-level `handlers:` block with
its own nginx reload/restart handler, and accepts either safety mechanism:
a preceding test handler, or an ordinary task-based `nginx -t` in the same
play.

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

import re
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


# --------------------------------------------------------------------------
# Handler order (#16980 review): in any role whose handlers include BOTH a
# `nginx -t` test handler and an nginx reload/restart handler, the test
# handler must be defined FIRST. Ansible runs notified handlers in
# DEFINITION order (the order they appear in handlers/main.yml), not notify
# order, so a task notifying both -- as this issue's own fix now does in
# roles/slm_manager/tasks/nginx_site.yml and roles/frontend/tasks/
# code_only.yml -- would reload nginx before validating it if the reload
# handler were listed first. A role with only one of the two (e.g.
# roles/backend, which validates via an ordinary task before its handlers
# ever flush, not via a handler) has nothing to check and is skipped.
# --------------------------------------------------------------------------

_NGINX_TEST_COMMAND_RE = re.compile(r"nginx\s+-t\b")
_COMMAND_KEYS = ("ansible.builtin.command", "command", "ansible.builtin.shell", "shell")
_SYSTEMD_KEYS = ("ansible.builtin.systemd", "systemd", "ansible.builtin.service", "service")
_RELOAD_STATES = ("reloaded", "restarted")

_HANDLER_VACUITY_FLOOR = 20  # 27 roles/*/handlers/main.yml files as of #16979/#16980


def _command_text(task: dict) -> str:
    """The free-form command string of a command/shell task, whichever of
    the two shapes it was written in: ``command: nginx -t`` (a bare string)
    or ``ansible.builtin.command: {cmd: nginx -t}`` (a dict)."""
    for key in _COMMAND_KEYS:
        value = task.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            cmd = value.get("cmd", "")
            if isinstance(cmd, str):
                return cmd
    return ""


def _is_nginx_test_handler(task: dict) -> bool:
    return bool(_NGINX_TEST_COMMAND_RE.search(_command_text(task)))


def _is_nginx_reload_handler(task: dict) -> bool:
    args = _module_args(task, _SYSTEMD_KEYS)
    return bool(args) and args.get("name") == "nginx" and args.get("state") in _RELOAD_STATES


def _handler_order_gap(handlers: list[dict]) -> str | None:
    """None when *handlers* has no ordering problem (including when it
    defines neither or only one of the two handler kinds -- nothing to
    check). Otherwise a description of the violation: the reload/restart
    handler nearest the top is not preceded by every test handler."""
    test_indices = [i for i, h in enumerate(handlers) if _is_nginx_test_handler(h)]
    reload_indices = [i for i, h in enumerate(handlers) if _is_nginx_reload_handler(h)]
    if not test_indices or not reload_indices:
        return None
    if max(test_indices) < min(reload_indices):
        return None
    return (
        f"a reload/restart nginx handler is defined at index {min(reload_indices)}, "
        f"at or before a test-nginx-config handler at index {max(test_indices)} -- "
        "ansible runs notified handlers in DEFINITION order, so the reload could fire "
        "before nginx -t validates the config"
    )


def _handler_files(ansible_root: Path) -> list[Path]:
    return sorted((ansible_root / "roles").glob("*/handlers/main.yml"))


def test_handler_files_vacuity_floor() -> None:
    files = _handler_files(_ANSIBLE_ROOT)
    assert len(files) >= _HANDLER_VACUITY_FLOOR, (
        f"only {len(files)} roles/*/handlers/main.yml found under {_ANSIBLE_ROOT} -- "
        f"expected at least {_HANDLER_VACUITY_FLOOR}. The scan did not reach the ansible "
        "tree -- this is 'did not look', not 'found nothing to fix'."
    )


def test_nginx_test_handler_precedes_reload_in_every_role() -> None:
    files = _handler_files(_ANSIBLE_ROOT)
    assert len(files) >= _HANDLER_VACUITY_FLOOR, "vacuity floor failed -- see test_handler_files_vacuity_floor"

    gaps = []
    roles_with_both = []
    for path in files:
        handlers = _load_tasks(path)
        if any(_is_nginx_test_handler(h) for h in handlers) and any(_is_nginx_reload_handler(h) for h in handlers):
            roles_with_both.append(path)
        gap = _handler_order_gap(handlers)
        if gap is not None:
            gaps.append(f"{path.relative_to(_ANSIBLE_ROOT)}: {gap}")

    # At least slm_manager, frontend and nginx must actually be exercised by
    # this check, or a filter regression would pass by finding nothing to
    # flag. roles/nginx's Test nginx config handler (#16980 review) has
    # nothing notifying it today -- included anyway, per the same no-debris
    # reasoning that added it.
    assert len(roles_with_both) >= 3, (
        f"only {len(roles_with_both)} role(s) with both a test and a reload/restart nginx "
        "handler found -- expected at least 3 (roles/slm_manager, roles/frontend, roles/nginx). "
        "This is 'did not look', not 'nothing to fix'."
    )
    assert gaps == [], "nginx reload/restart handler(s) not preceded by test nginx config:\n" + "\n".join(gaps)


def test_negative_control_reload_before_test_is_flagged() -> None:
    handlers = [
        {"name": "restart nginx", "systemd": {"name": "nginx", "state": "reloaded"}},
        {"name": "test nginx config", "command": "nginx -t"},
    ]
    assert _handler_order_gap(handlers) is not None, (
        "negative control: a reload handler defined before the test handler must be flagged -- "
        "the checker is vacuously passing everything"
    )


def test_positive_control_test_before_reload_passes() -> None:
    handlers = [
        {"name": "test nginx config", "command": "nginx -t"},
        {"name": "restart nginx", "systemd": {"name": "nginx", "state": "reloaded"}},
    ]
    assert (
        _handler_order_gap(handlers) is None
    ), "positive control: test defined BEFORE reload must pass -- the checker is rejecting everything"


def test_role_with_only_a_reload_handler_is_not_flagged() -> None:
    """roles/backend validates nginx config via an ordinary task that runs
    before its handlers ever flush, not via a `test nginx config` handler --
    its handlers file has a reload handler with nothing to order it against,
    and must not be flagged."""
    handlers = [{"name": "reload nginx backend", "ansible.builtin.systemd": {"name": "nginx", "state": "reloaded"}}]
    assert (
        _handler_order_gap(handlers) is None
    ), "a role with only a reload handler (no test handler) has nothing to check and must not be flagged"


# --------------------------------------------------------------------------
# Play-level handlers (#16980 review, round 2): a `handlers:` block embedded
# directly in a playbook play -- not a role's handlers/main.yml, which the
# section above already covers -- was invisible to that guard entirely.
# autobot-slm-backend/ansible/migrate-grafana-to-vm.yml defines its own
# `reload nginx` handler with no test handler in the same list; it is safe
# today only because an ordinary `nginx -t` TASK runs earlier in the play,
# outside handlers: altogether. That is a second, independently valid way to
# be safe -- handlers fire only after every task in the play has been
# visited (no explicit `meta: flush_handlers` in any file this guard
# covers), so an unconditional nginx -t task anywhere in the play's own task
# list always runs before the reload/restart handler could fire, regardless
# of its position relative to whichever task notified that handler.
# --------------------------------------------------------------------------

_PLAY_YML_VACUITY_FLOOR = 100  # *.yml files anywhere under the ansible tree


def _all_ansible_yml_files(ansible_root: Path) -> list[Path]:
    return sorted(ansible_root.rglob("*.yml"))


def _plays_with_own_handlers(path: Path) -> list[dict]:
    """Every play in *path* that defines its own play-level `handlers:`
    list. A role's handlers/main.yml is a flat list with no `hosts:` key and
    never matches here -- that shape is test_nginx_test_handler_precedes_
    reload_in_every_role's job, not this one's."""
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return []
    if not isinstance(doc, list):
        return []
    return [
        entry
        for entry in doc
        if isinstance(entry, dict) and "hosts" in entry and isinstance(entry.get("handlers"), list)
    ]


def _play_tasks(play: dict) -> list[dict]:
    """pre_tasks + tasks + post_tasks of a single play, flattened."""
    combined: list[dict] = []
    for key in ("pre_tasks", "tasks", "post_tasks"):
        value = play.get(key)
        if isinstance(value, list):
            combined.extend(value)
    return _flatten(combined)


def _handlers_have_ordered_test(handlers: list[dict]) -> bool:
    """True iff *handlers* defines a test handler that precedes every nginx
    reload/restart handler in the same list. Deliberately NOT
    `_handler_order_gap(handlers) is None` -- that returns None both when
    ordered correctly AND when no test handler exists at all (the right
    call for the role-level guard above, where a reload-only role like
    roles/backend is legitimately safe via a mechanism that guard doesn't
    model). Here "no test handler in handlers:" must fall through to the
    task-based escape hatch instead of being treated as already safe."""
    test_indices = [i for i, h in enumerate(handlers) if _is_nginx_test_handler(h)]
    reload_indices = [i for i, h in enumerate(handlers) if _is_nginx_reload_handler(h)]
    if not test_indices or not reload_indices:
        return False
    return max(test_indices) < min(reload_indices)


def _play_reload_gap(play: dict) -> str | None:
    """None when *play* has nothing to reload, or its nginx reload/restart
    handler is safe by either mechanism described above. Otherwise a
    description of the violation."""
    handlers = _flatten(play.get("handlers"))
    if not any(_is_nginx_reload_handler(h) for h in handlers):
        return None  # nothing to reload in this play

    if _handlers_have_ordered_test(handlers):
        return None  # (a): a test handler already precedes reload in handlers:

    if any(_is_nginx_test_handler(t) for t in _play_tasks(play)):
        return None  # (b): an ordinary task-based nginx -t covers it instead

    gap = _handler_order_gap(handlers)
    if gap is not None:
        return f"{gap} -- and no ordinary `nginx -t` task exists in the play's own task list either"
    return (
        "a reload/restart nginx handler is defined with no preceding test handler in the play's "
        "handlers: list, and no ordinary `nginx -t` task exists in the play's own task list either"
    )


def test_play_level_yml_files_vacuity_floor() -> None:
    files = _all_ansible_yml_files(_ANSIBLE_ROOT)
    assert len(files) >= _PLAY_YML_VACUITY_FLOOR, (
        f"only {len(files)} *.yml files found under {_ANSIBLE_ROOT} -- expected at least "
        f"{_PLAY_YML_VACUITY_FLOOR}. The scan did not reach the ansible tree -- this is "
        "'did not look', not 'found nothing to fix'."
    )


def test_play_level_nginx_reload_handlers_are_safely_ordered() -> None:
    files = _all_ansible_yml_files(_ANSIBLE_ROOT)
    assert len(files) >= _PLAY_YML_VACUITY_FLOOR, "vacuity floor failed -- see test_play_level_yml_files_vacuity_floor"

    reload_plays = []
    gaps = []
    for path in files:
        for play in _plays_with_own_handlers(path):
            handlers = _flatten(play.get("handlers"))
            if not any(_is_nginx_reload_handler(h) for h in handlers):
                continue
            reload_plays.append((path, play.get("name")))
            gap = _play_reload_gap(play)
            if gap is not None:
                gaps.append(f"{path.relative_to(_ANSIBLE_ROOT)} (play {play.get('name')!r}): {gap}")

    # migrate-grafana-to-vm.yml and playbooks/deploy-nginx-proxy.yml both
    # define their own nginx reload handler -- a filter regression that
    # matched nothing would otherwise pass by finding nothing to flag.
    assert len(reload_plays) >= 2, (
        f"only {len(reload_plays)} play(s) with their own nginx reload/restart handler found -- "
        "expected at least 2 (migrate-grafana-to-vm.yml, playbooks/deploy-nginx-proxy.yml). "
        "This is 'did not look', not 'nothing to fix'."
    )
    assert gaps == [], "play-level nginx reload/restart handler(s) not safely ordered:\n" + "\n".join(gaps)


def test_negative_control_play_level_reload_with_no_test_handler_or_task_is_flagged() -> None:
    play = {
        "hosts": "all",
        "tasks": [{"name": "do something unrelated", "ansible.builtin.debug": {"msg": "hi"}}],
        "handlers": [{"name": "reload nginx", "ansible.builtin.systemd": {"name": "nginx", "state": "reloaded"}}],
    }
    gap = _play_reload_gap(play)
    assert gap is not None, (
        "negative control: a play-level reload handler with neither a preceding test handler nor an "
        "ordinary nginx -t task must be flagged -- the checker is vacuously passing everything"
    )


def test_positive_control_play_level_reload_safe_via_handler_order() -> None:
    play = {
        "hosts": "all",
        "tasks": [],
        "handlers": [
            {"name": "test nginx config", "command": "nginx -t"},
            {"name": "reload nginx", "systemd": {"name": "nginx", "state": "reloaded"}},
        ],
    }
    assert (
        _play_reload_gap(play) is None
    ), "positive control: a play-level handlers: list ordered test-before-reload must pass"


def test_positive_control_play_level_reload_safe_via_ordinary_task() -> None:
    play = {
        "hosts": "all",
        "tasks": [{"name": "Validate config", "ansible.builtin.command": "nginx -t"}],
        "handlers": [{"name": "reload nginx", "ansible.builtin.systemd": {"name": "nginx", "state": "reloaded"}}],
    }
    assert _play_reload_gap(play) is None, (
        "positive control: an ordinary task-based nginx -t in the play must pass, same as "
        "migrate-grafana-to-vm.yml and playbooks/deploy-nginx-proxy.yml today"
    )
