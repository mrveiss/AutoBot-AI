# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The builtin updater must reach database nodes at all (#13535).

`update-all-nodes.yml` is the playbook behind code-sync / self-update — the only
updater a GUI user can reach. Its node play targets the `infrastructure` group,
and `database` is not one of that group's children. `roles/redis` also had no
code-only task file, so even a play that did reach the node had nothing to
apply. Both halves were missing, which is why the ChromaDB authentication work
(#12513, #13462, #13537) merged green, closed, and left the host untouched — the
#12959 "merged but never applied" shape, one role further along.

The fix is a play that targets `database` directly. Adding `database` to
`infrastructure` was considered and rejected: that group is the node play's host
list, and the node play is a backend/frontend/worker update (package installs,
npm builds, alembic migrations, a backend `.env` regeneration) that was never
designed to run against a data store.

What is asserted here is the property that made the gap invisible: *some* play
reaches database hosts, and it applies `roles/redis` through a task file that
carries no provisioning. Every assertion is a regression guard for a defect that
already shipped once.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_ROLE = _ANSIBLE / "roles" / "redis"
_CODE_ONLY = _ROLE / "tasks" / "code_only.yml"

#: Host patterns that resolve to database nodes. `redis` is the inventory alias
#: whose only child is `database` (inventory/production.yml, hosts.yml).
_DATABASE_PATTERNS = {"database", "redis"}

#: Task-name substrings that mean provisioning — the same contract
#: test_update_all_applies_roles_12959.py enforces for every other role.
_PROVISIONING_MARKERS = ("venv", "pip install", "pre-download", "service account", "apt")


def _plays() -> list[dict]:
    return [p for p in yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8")) if isinstance(p, dict)]


def _tasks(path: Path) -> list:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def _iter_mappings(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_mappings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_mappings(item)


def _database_plays() -> list[dict]:
    """Plays whose host pattern reaches a database node."""
    matched = []
    for play in _plays():
        tokens = {tok.strip() for tok in str(play.get("hosts", "")).replace(",", ":").split(":")}
        if tokens & _DATABASE_PATTERNS:
            matched.append(play)
    return matched


def test_the_role_has_a_code_only_task_file():
    """Without one, no play can deliver a change to a database node."""
    assert _CODE_ONLY.is_file(), (
        f"{_CODE_ONLY} missing — roles/redis owns the Redis systemd override, the "
        "backup script and the ChromaDB unit + credential file, and none of them "
        "can reach a host without a code-only task file to apply (#13535)"
    )


def test_a_play_targets_database_hosts():
    """The gap was structural: no play in the updater named these nodes."""
    assert _database_plays(), (
        "update-all-nodes.yml has no play targeting database nodes — code-sync / "
        "self-update cannot deliver anything to the database role, exactly the "
        "state #13535 reports"
    )


def test_the_database_play_applies_the_role_through_code_only():
    """Full-role application would drag provisioning onto the update path."""
    applied = set()
    for play in _database_plays():
        for task in _iter_mappings(play.get("tasks") or []):
            include = task.get("ansible.builtin.include_role") or task.get("include_role")
            if isinstance(include, dict) and include.get("name") == "redis":
                applied.add(include.get("tasks_from"))
        for entry in play.get("roles") or []:
            name = entry.get("role") or entry.get("name") if isinstance(entry, dict) else entry
            if name == "redis":
                applied.add(None)

    assert "code_only" in applied, (
        "no play targeting database nodes applies roles/redis with "
        f"tasks_from=code_only (found: {sorted(str(a) for a in applied)}) — a fix "
        "merged into that role stays inert on every database host (#12959)"
    )
    assert None not in applied, (
        "a database play applies roles/redis in FULL — that re-runs the redis-stack "
        "package install, the service accounts, the data directory chown and the "
        "chroma venv build on every self-update"
    )


def test_delivery_does_not_depend_on_the_infrastructure_group():
    """The rejected alternative, pinned.

    Adding `database` to `infrastructure` would have routed database nodes
    through the backend/frontend/worker play. Delivery must come from a play that
    names the database nodes itself, so the route survives regardless of how the
    `infrastructure` group is composed in any given inventory.
    """
    routes = [p for p in _database_plays() if "infrastructure" not in str(p.get("hosts", ""))]
    assert routes, (
        "the only play reaching database nodes does so via the `infrastructure` "
        "group — delivery then depends on an inventory grouping that the static "
        "inventory does not have, which is how #13535 stayed invisible"
    )


def test_code_only_carries_no_provisioning():
    """A task file that re-provisions turns every self-update into a reinstall."""
    names = " ".join(str(t.get("name", "")) for t in _tasks(_CODE_ONLY) if isinstance(t, dict)).lower()
    for marker in _PROVISIONING_MARKERS:
        assert marker not in names, (
            f"roles/redis/tasks/code_only.yml: provisioning task ({marker!r}) leaked "
            "onto the update path — it must stay in main.yml"
        )


#: Jinja comment regions. Only these are safe to ignore: a ``{# ... #}`` is removed before
#: rendering, so it cannot carry a value into the output. A SHELL ``#`` comment is NOT safe --
#: Jinja does not know about shell syntax, so ``# {{ redis_password }}`` would still be
#: substituted and the credential would land in the rendered file.
_JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.S)

#: A Jinja expression or statement -- the only constructs that can put a value into the output.
_JINJA_CONSTRUCT = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)


def _emits_credential(text: str, name: str = "redis_password") -> bool:
    """Whether rendering *text* can put ``name``'s VALUE into the output.

    Asking "does the file mention the variable" is a different question, and the wrong one:
    it is satisfied by the file's own prose. ``redis-backup.sh.j2`` documents, in a shell
    comment, that the credential is deliberately NOT substituted into it -- and a substring
    check read that explanation as the violation it describes, failing CI for documenting the
    fix (the #15771 shape, catalogued as a class in #17941).

    Only a ``{{ ... }}`` or ``{% ... %}`` referencing the variable can emit it, so that is what
    this looks for. Jinja comments are stripped first because they are removed before rendering;
    shell comments deliberately are not, since Jinja substitutes inside them.
    """
    return any(name in m.group(0) for m in _JINJA_CONSTRUCT.finditer(_JINJA_COMMENT.sub("", text)))


def test_code_only_renders_nothing_that_carries_the_redis_password():
    """A code-only render must not be able to strip the data store's credential.

    ``redis_password`` resolves from ``vault_redis_password``
    (roles/redis/vars/main.yml), which no inventory in this repository defines.
    Rendering ``redis-stack.conf.j2`` or ``redis_exporter.service.j2`` on the
    update path would therefore emit both files WITHOUT the credential — silently
    removing authentication from a live data store on every update. Those two
    stay on the provisioning path until the variable has a guaranteed source.
    """
    rendered = {
        str((t.get("ansible.builtin.template") or t.get("template") or {}).get("src", ""))
        for t in _iter_mappings(_tasks(_CODE_ONLY))
    } - {""}

    offenders = {src for src in rendered if _emits_credential((_ROLE / "templates" / src).read_text(encoding="utf-8"))}
    assert not offenders, (
        f"roles/redis/tasks/code_only.yml renders {sorted(offenders)}, whose content "
        "depends on redis_password — an update-path render emits them without the "
        "credential and silently disables Redis authentication"
    )


def test_main_includes_code_only_rather_than_duplicating_it():
    """One definition, two callers — the #12886 / #12959 contract."""
    includes = [
        str(t.get("ansible.builtin.include_tasks", "")) for t in _iter_mappings(_tasks(_ROLE / "tasks" / "main.yml"))
    ]
    assert any("code_only.yml" in inc for inc in includes), (
        "roles/redis/tasks/main.yml must include code_only.yml, not repeat its "
        "tasks — an inline copy is how the provisioning and update paths drift"
    )


def test_a_comment_EXPLAINING_the_credential_is_not_an_emission():
    """The control for the bug this guard had: documenting the ruling must not trip it.

    `redis-backup.sh.j2` carries a shell comment stating that the credential is deliberately
    not substituted into it. A whole-file substring check read that sentence as the violation
    it describes and failed CI -- so the fix for #17932 could not land while explaining itself.
    This pins the distinction the guard now makes: MENTIONING the variable is not EMITTING it.
    """
    assert not _emits_credential("# the value of redis_password is NOT substituted here\n")
    assert not _emits_credential("{# redis_password is set elsewhere #}\n")


def test_a_jinja_construct_IS_an_emission():
    """The contrast. Without this the guard above is satisfiable by never firing at all."""
    assert _emits_credential("requirepass {{ redis_password }}\n")
    assert _emits_credential("{% if redis_password %}x{% endif %}\n")


def test_a_shell_comment_is_NOT_stripped_because_jinja_substitutes_inside_it():
    """Jinja has no notion of shell syntax, so a `#` line still renders.

    Stripping shell comments would have been the obvious way to fix the guard, and it would
    have opened a real hole: `# {{ redis_password }}` lands the credential in the rendered
    file, commented out but present and readable.
    """
    assert _emits_credential("# {{ redis_password }}\n")


def test_the_real_offenders_are_still_caught():
    """Narrowing must not cost the guard its actual subjects."""
    for src in ("redis-stack.conf.j2",):
        text = (_ROLE / "templates" / src).read_text(encoding="utf-8")
        assert _emits_credential(text), f"{src} emits the credential and must still be flagged"
