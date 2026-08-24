# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Provisioning cleanup must never be able to delete live data (#14856).

Re-running provisioning is the natural rescue for a host broken by a partial
code-sync — and that is exactly the state where the `role_*_active` facts are
most likely to be missing or wrong. So the recovery path must not be able to
destroy the data it is being run to save.

Three fail-destructive shapes are pinned out:

  * a `state: absent` gated on `lookup('vars', ..., default=false)`, where an
    UNDEFINED fact takes the delete branch
  * an unconditional `state: absent` on a component directory, which assumes
    every host that has ever existed keeps no state there
  * any *other* component removal that spells the deletion out for itself
    instead of going through the one guarded primitive

On a deployed host these paths carry `data/` with unified_memory.db,
conversation_files.db, transcriber.db, service-keys and .slm_keys, so
`state: absent` on the parent takes them with it.

The structural checks below say the gates are SHAPED right. The behavioural
checks evaluate the real `when:` text out of the real files through Jinja2 and
assert which branch it actually takes — in BOTH directions. A guard that blocks
the destructive case while breaking the legitimate cleanup is not a fix, so
every scenario table below contains rows that must still delete.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")
jinja2 = pytest.importorskip("jinja2")

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_SHARED = _ANSIBLE / "roles" / "_shared" / "tasks"
_PRIMITIVE = _SHARED / "remove_component_dir.yml"
_WRONG_NODE = _SHARED / "clean_wrong_node_dir.yml"
_LEGACY = _SHARED / "clean_legacy_dir.yml"

# Every file that used to spell a component removal out for itself. Listed by
# name rather than rediscovered, so that deleting a call site is a test failure
# and not a silent shrink of what this file covers.
_CALL_SITES = (
    _WRONG_NODE,
    _LEGACY,
    _ANSIBLE / "playbooks" / "cleanup-nodes.yml",
    _ANSIBLE / "playbooks" / "remove-role.yml",
    _ANSIBLE / "roles" / "slm_agent" / "tasks" / "clean.yml",
)

# A component directory is a per-component install root: the unit a role deploys
# to, and the thing that carries data/. Two shapes qualify — the canonical
# /opt/autobot/<component>, and the flat pre-rename roots directly under /opt
# that predate it (/opt/slm-agent is one this file's own subject still cleans up).
#
# /opt/autobot itself is deliberately NOT one. It is the root that *contains*
# component directories, and removing it is decommissioning a node — a different,
# explicitly-named operation, not a cleanup. That is a boundary, not an
# exception: nothing here exempts a component directory from the rule.
#
# `{{ ... }}` is collapsed first so that "/opt/autobot/{{ role_target_dir }}" is
# recognised as one of these and a fully-templated "{{ some_path }}" is not.
_TEMPLATE = re.compile(r"\{\{.*?\}\}")
_INSTALL_ROOT = "/opt/autobot"


_GROUP_VARS_ALL = _ANSIBLE / "inventory" / "group_vars" / "all.yml"


def _inventory_vars() -> dict[str, Any]:
    """The facts `group_vars/all.yml` supplies to every play in this inventory.

    #14914: the playbooks build their removal paths from `{{ autobot.base_dir }}`
    rather than a `/opt/autobot` literal, so this guard has to resolve that
    variable or every target below renders with an empty install root.

    Read out of the SSOT file rather than restated here, deliberately. A copy of
    `/opt/autobot` in this test would keep resolving after the real value moved,
    and these guards would then be checking paths no playbook produces — which
    is the same shape as the literal the playbooks just stopped carrying, one
    layer up.

    Asserted on PRESENCE: if the key disappears, that is a loud failure here,
    not a silent one in a comparison that stops matching.
    """
    assert _GROUP_VARS_ALL.is_file(), f"the inventory SSOT is missing: {_GROUP_VARS_ALL}"
    loaded = yaml.safe_load(_GROUP_VARS_ALL.read_text(encoding="utf-8")) or {}
    autobot = loaded.get("autobot")
    assert isinstance(autobot, dict), (
        f"{_GROUP_VARS_ALL.name} no longer defines an `autobot` mapping, so every removal "
        "target in this file would render without its install root and the checks below "
        "would compare paths no playbook produces"
    )
    base_dir = str(autobot.get("base_dir") or "")
    assert base_dir.startswith("/"), (
        f"{_GROUP_VARS_ALL.name} defines autobot.base_dir as {base_dir!r}, which is not an "
        "absolute path; the removal targets built from it cannot be checked"
    )
    return {"autobot": autobot}


def _is_component_dir(raw: str) -> bool:
    path = _TEMPLATE.sub("TPL", raw).strip().rstrip("/")
    if not path.startswith("/opt/") or path == _INSTALL_ROOT:
        return False
    tail = path[len("/opt/") :]
    if tail.startswith("autobot/"):
        tail = tail[len("autobot/") :]
    return bool(tail) and "/" not in tail


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------
def _load(path: Path) -> Any:
    """Load a task/playbook file. Some playbooks here hold several documents."""
    assert path.is_file(), f"file under test is missing: {path}"
    docs = [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d]
    assert docs, f"{path.name} is empty — a guard reading it would pass vacuously"
    return docs[0] if len(docs) == 1 else docs


def _walk(node: Any):
    """Every mapping in a document, including tasks nested in blocks and plays."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _module(task: dict, *names: str) -> dict | None:
    for name in names:
        spec = task.get(name)
        if isinstance(spec, dict):
            return spec
        if isinstance(spec, str):
            return {"_raw": spec}
    return None


def _deletions(doc: Any) -> list[dict]:
    out = []
    for task in _walk(doc):
        spec = _module(task, "ansible.builtin.file", "file")
        if spec and spec.get("state") == "absent":
            out.append(task)
    return out


def _includes_of(doc: Any, target: str) -> list[dict]:
    out = []
    for task in _walk(doc):
        inc = _include_path(task)
        if inc and Path(inc).name == target:
            out.append(task)
    return out


def _include_path(task: dict) -> str | None:
    inc = task.get("ansible.builtin.include_tasks") or task.get("include_tasks")
    return inc if isinstance(inc, str) else None


def _delegations(doc: Any) -> list[dict]:
    """Tasks that hand a directory to something for removal.

    Keyed on the CONTRACT (a `remove_dir_path` is passed) rather than on the
    include target, so that a call site repointed at some other file is still
    recognised as a removal and still has to answer for itself. Keying on the
    target instead is how the first version of this guard let exactly that
    mutation through.
    """
    return [t for t in _walk(doc) if _include_path(t) and "remove_dir_path" in (t.get("vars") or {})]


def _when_list(task: dict) -> list[str]:
    """The `when:` as Ansible sees it — a list of expressions ANDed together.

    Joining them into one string would produce nonsense like
    `x is not none not (y | bool)`, which Jinja2 happens to reject loudly here
    but would otherwise have quietly become a guard that evaluates something
    other than the file it claims to check.
    """
    cond = task.get("when")
    if cond is None:
        return []
    if isinstance(cond, list):
        return [str(c) for c in cond]
    return [str(cond)]


def _when_text(task: dict) -> str:
    """Flattened, for substring checks only — never for evaluation."""
    return " ".join(_when_list(task))


# --------------------------------------------------------------------------
# a tiny Ansible-flavoured Jinja2, enough to execute a `when:`
# --------------------------------------------------------------------------
_TRUTHY = {"true", "yes", "on", "1", "y", "t"}


def _ansible_bool(value: Any) -> bool:
    """Ansible's `| bool`. group_vars spells these facts as folded STRINGS."""
    if isinstance(value, jinja2.Undefined):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY
    return bool(value)


class _FactUndefined(Exception):
    """`lookup('vars', x)` with no default is a hard error in Ansible too."""


def _evaluate(conditions: str, scope: dict[str, Any]) -> bool:
    """Render a real `when:` string against a scenario and return the branch taken."""
    env = jinja2.Environment(undefined=jinja2.ChainableUndefined, autoescape=False)
    env.filters["bool"] = _ansible_bool

    def _lookup(kind: str, *terms: str, **kwargs: Any) -> Any:
        assert kind == "vars", f"only the vars lookup is modelled here, got {kind!r}"
        name = terms[0]
        if name in scope:
            return scope[name]
        if "default" in kwargs:
            return kwargs["default"]
        raise _FactUndefined(name)

    env.globals["lookup"] = _lookup
    # `when:` is an implicit expression; each list item is ANDed. Rendering
    # through an {% if %} gives us the branch rather than a stringified value.
    rendered = env.from_string("{%% if %s %%}TAKEN{%% else %%}SKIPPED{%% endif %%}" % conditions).render(**scope)
    assert rendered in ("TAKEN", "SKIPPED"), f"unexpected render {rendered!r} for {conditions!r}"
    return rendered == "TAKEN"


def _render_value(value: Any, scope: dict[str, Any]) -> Any:
    """Render a `set_fact` value the way Ansible would, keeping non-templates as-is."""
    if not isinstance(value, str) or "{{" not in value:
        return value
    env = jinja2.Environment(undefined=jinja2.ChainableUndefined, autoescape=False)
    env.filters["bool"] = _ansible_bool

    def _lookup(kind: str, *terms: str, **kwargs: Any) -> Any:
        assert kind == "vars", f"only the vars lookup is modelled here, got {kind!r}"
        name = terms[0]
        if name in scope:
            return scope[name]
        if "default" in kwargs:
            return kwargs["default"]
        raise _FactUndefined(name)

    env.globals["lookup"] = _lookup
    return env.from_string(value).render(**scope)


def _apply_set_fact(task: dict, scope: dict[str, Any]) -> dict[str, Any]:
    """Run a real set_fact task against a scenario, so the gate reads what the
    playbook would actually have put in front of it."""
    spec = _module(task, "ansible.builtin.set_fact", "set_fact")
    assert spec, f"'{task.get('name')}' is not a set_fact task"
    for key, value in spec.items():
        scope[key] = _render_value(value, scope)
    return scope


def _and(conditions: list[str], scope: dict[str, Any]) -> bool:
    """Ansible ANDs an inherited include `when:` with the child task's own."""
    assert conditions, "nothing to evaluate — an empty condition list would read as a pass"
    return all(_evaluate(c, scope) for c in conditions)


def _stat(exists: bool | None) -> dict[str, Any]:
    """A registered stat result. None models 'the probe did not produce a verdict'."""
    return {"stat": {} if exists is None else {"exists": exists}}


# --------------------------------------------------------------------------
# the primitive exists and is the only place a component removal happens
# --------------------------------------------------------------------------
def test_the_guarded_primitive_exists_and_deletes_exactly_once() -> None:
    """Assert the target before asserting on its behaviour.

    Every other test in this file follows the primitive one hop or more. If it
    were missing or had stopped deleting anything, those tests would report a
    cheerful PASS while nothing was guarded.
    """
    deletions = _deletions(_load(_PRIMITIVE))
    assert len(deletions) == 1, (
        f"{_PRIMITIVE.name} must contain exactly one state=absent task — the single "
        f"place provisioning removes a component directory. Found {len(deletions)}."
    )
    spec = _module(deletions[0], "ansible.builtin.file", "file")
    assert spec and spec.get("path") == "{{ remove_dir_path }}", (
        "the primitive does not remove the path its callers pass it; callers would be "
        "delegating to something that deletes a different directory"
    )
    probes = [
        t
        for t in _walk(_load(_PRIMITIVE))
        if (_module(t, "ansible.builtin.stat", "stat") or {}).get("path") == "{{ remove_dir_path }}/data"
    ]
    assert probes, "the primitive never probes for data/ — its whole reason to exist"


def test_no_component_directory_is_removed_outside_the_primitive() -> None:
    """The class, not the one task.

    #14856's named defect was one `when:` in one shared file. The same delete
    was ALSO hand-copied, unguarded, into cleanup-nodes.yml (59 of them) and
    slm_agent/clean.yml — the triplication #13148 and #14678 describe. Fixing
    the shared file alone would have left the worse copies live, so the rule is
    stated over the whole tree and carries no exception list.
    """
    files_scanned = 0
    deletions_seen = 0
    offenders: list[str] = []

    for path in sorted(_ANSIBLE.rglob("*.yml")) + sorted(_ANSIBLE.rglob("*.yaml")):
        try:
            docs = [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d]
        except yaml.YAMLError as exc:  # a file we cannot read is not a file we can clear
            pytest.fail(f"{path.relative_to(_ANSIBLE)} does not parse, so it cannot be checked: {exc}")
        files_scanned += 1
        if not docs:
            continue
        for task in _deletions(docs):
            deletions_seen += 1
            spec = _module(task, "ansible.builtin.file", "file") or {}
            raw = str(spec.get("path") or spec.get("dest") or "")
            if _is_component_dir(raw):
                offenders.append(f"{path.relative_to(_ANSIBLE)}: {task.get('name')} -> {raw}")

    # Presence, not absence of failure: an empty scan reads as a clean scan.
    assert files_scanned > 100, f"only {files_scanned} ansible files scanned — the sweep is not reaching the tree"
    assert deletions_seen > 50, f"only {deletions_seen} state=absent tasks found — the sweep is not finding deletions"
    assert not offenders, (
        "these tasks remove a whole component directory themselves instead of delegating to "
        f"{_PRIMITIVE.name}, so nothing checks whether the directory holds data/:\n  " + "\n  ".join(offenders)
    )


def _delegated_targets(task: dict) -> list[str]:
    """The concrete paths one delegation can remove, loop expanded.

    Callers pass `remove_dir_path: "{{ autobot.base_dir }}/{{ _cleanup_target.dir }}"`
    over a loop, so the raw string says nothing about what is actually scheduled.
    Expanding it — the install root from the inventory SSOT, the component from
    the loop — is the difference between a guard that reads the code and one that
    reads what the code will do.
    """
    spec = str((task.get("vars") or {}).get("remove_dir_path", ""))
    if not spec:
        return []
    # #14914: the inventory facts belong in EVERY render scope here, including
    # the loop-less one. Without them `{{ autobot.base_dir }}/{{ x }}` renders
    # as `/x`, which is not a `/opt/` path and never equals the protected
    # directory — so the caller's check keeps passing with nothing left to
    # match. That is not a hypothetical: it is how the first attempt at #14914
    # disarmed the protected-config guard while every test stayed green.
    scope = _inventory_vars()
    items = task.get("loop")
    if not isinstance(items, list):
        return [str(_render_value(spec, dict(scope)))]
    loop_var = ((task.get("loop_control") or {}).get("loop_var")) or "item"
    return [str(_render_value(spec, {**scope, loop_var: item})) for item in items]


def test_the_protected_config_dir_is_never_scheduled_for_removal() -> None:
    """/opt/autobot/config holds permission_rules.yaml, read at runtime (#3873).

    roles/backend/tasks/clean.yml has excluded it since then. The fleet cleanup
    playbook removed it on every node anyway — a protection decided in one copy
    of the cleanup logic and never carried to the other (#13148, #14678). An
    unpinned decision regrows, so it is pinned here rather than left as a
    comment.
    """
    # Built from the same SSOT the playbooks build their targets from (#14914).
    # Hardcoding it here would leave this comparison matching the old location
    # the moment autobot.base_dir moved — the guard would go quiet rather than
    # red, which is the failure mode this whole file exists to prevent.
    protected = f"{str(_inventory_vars()['autobot']['base_dir']).rstrip('/')}/config"
    targets_seen = 0
    offenders: list[str] = []
    for candidate in sorted(_ANSIBLE.rglob("*.yml")) + sorted(_ANSIBLE.rglob("*.yaml")):
        try:
            docs = [d for d in yaml.safe_load_all(candidate.read_text(encoding="utf-8")) if d]
        except yaml.YAMLError:
            continue
        for task in _delegations(docs):
            for target in _delegated_targets(task):
                targets_seen += 1
                if target.rstrip("/") == protected:
                    offenders.append(f"{candidate.relative_to(_ANSIBLE)}: {task.get('name')}")
        for task in _deletions(docs):
            spec = _module(task, "ansible.builtin.file", "file") or {}
            targets_seen += 1
            if str(spec.get("path") or "").rstrip("/") == protected:
                offenders.append(f"{candidate.relative_to(_ANSIBLE)}: {task.get('name')}")

    assert targets_seen > 50, f"only {targets_seen} removal targets expanded — the sweep is not reaching the tree"
    assert not offenders, (
        f"{protected} is scheduled for removal by:\n  "
        + "\n  ".join(sorted(set(offenders)))
        + "\nIt holds permission_rules.yaml, which permission_matcher.py reads at runtime (#3873)."
    )


_REMOVE_ROLE = _ANSIBLE / "playbooks" / "remove-role.yml"


def _play_tasks(path: Path) -> list[dict]:
    docs = _load(path)
    plays = docs if isinstance(docs, list) else [docs]
    for play in plays:
        if isinstance(play, dict) and isinstance(play.get("tasks"), list):
            return [t for t in play["tasks"] if isinstance(t, dict)]
    raise AssertionError(f"{path.name} has no play with a tasks list")


def test_the_removal_summary_reports_what_happened_not_what_was_asked() -> None:
    """A refusal the operator never reads is a refusal that does not protect them.

    The role-removal summary used to print "<dir> removed" whenever a target dir
    was named. Now that the removal can refuse — because the directory holds
    data/ — that line would tell an operator the directory is gone while it is
    still there, and the "REFUSING" message scrolls by hundreds of lines
    earlier. That is this issue's own defect shape, a claim in the prose the
    code does not implement, so the summary is derived from observed state and
    both directions are asserted here.
    """
    tasks = _play_tasks(_REMOVE_ROLE)

    delegate_at = next(
        (i for i, t in enumerate(tasks) if _include_path(t) and "remove_dir_path" in (t.get("vars") or {})), None
    )
    assert delegate_at is not None, "remove-role.yml no longer delegates its removal"

    decisions = [
        t for t in tasks if "_disk_cleanup_summary" in (_module(t, "ansible.builtin.set_fact", "set_fact") or {})
    ]
    assert decisions, "nothing computes _disk_cleanup_summary"
    expr = str((_module(decisions[0], "ansible.builtin.set_fact", "set_fact"))["_disk_cleanup_summary"])

    # Which stat the summary depends on is read out of the expression rather
    # than named here, so this follows the real data flow instead of a naming
    # convention that a rename would quietly break. Picking "the first stat in
    # the play" instead matched an unrelated earlier probe.
    referenced = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr))
    rechecks = [
        i
        for i, t in enumerate(tasks)
        if _module(t, "ansible.builtin.stat", "stat") and str(t.get("register", "")) in referenced
    ]
    assert rechecks, "the summary is not derived from any stat result, so it cannot know what happened"
    assert min(rechecks) > delegate_at, "the directory is re-checked BEFORE the removal, so the summary predates it"

    summaries = [t for t in tasks if "_disk_cleanup_summary" in str(_module(t, "ansible.builtin.debug", "debug") or {})]
    assert summaries, "the summary no longer reports the computed disk-cleanup result"

    # #14914: the install root moved to a task-scoped `vars:` entry, so it has to
    # be rendered into scope here too. Read out of the task rather than restated,
    # because a hardcoded copy would keep rendering after the task stopped
    # defining it — and the wording assertions below would then be judging a
    # message with the path silently missing from it.
    render_scope = {**_inventory_vars(), "role_target_dir": "autobot-backend"}
    task_vars = {k: _render_value(v, render_scope) for k, v in (decisions[0].get("vars") or {}).items()}
    assert task_vars, "the summary task defines no vars — the expression's operands cannot be resolved"

    # Removed for real -> says removed. Still there -> must NOT say removed.
    base = {**render_scope, **task_vars}
    gone = str(_render_value(expr, {**base, "_role_dir_after": _stat(False)}))
    kept = str(_render_value(expr, {**base, "_role_dir_after": _stat(True)}))
    unknown = str(_render_value(expr, base))

    # The summary must NAME the directory, in both directions. Without this the
    # wording checks below pass just as well over a message whose path rendered
    # empty, which is exactly what an unresolved operand produces.
    expected_dir = f"{str(render_scope['autobot']['base_dir']).rstrip('/')}/autobot-backend"
    for label, text in (("gone", gone), ("kept", kept)):
        assert expected_dir in text, (
            f"the {label} summary does not name the directory it is reporting on. "
            f"Expected {expected_dir!r} (built from the inventory SSOT), got: {text!r}"
        )

    assert "removed" in gone.lower(), f"a directory that IS gone is not reported as removed: {gone!r}"
    assert "removed" not in kept.lower(), f"a directory still on disk is reported as removed: {kept!r}"
    assert "removed" not in unknown.lower(), f"an unverified removal is reported as removed: {unknown!r}"
    assert (
        "skipped" in str(_render_value(expr, {"_role_dir_after": _stat(False)})).lower()
    ), "with no target directory the summary should say it was skipped"


def test_no_include_carries_a_keyword_ansible_rejects() -> None:
    """Only Ansible's parser knows which keywords an include accepts.

    This change moved five call sites onto `include_tasks`, and one of them
    carried `become: true` — valid on a task, rejected outright on a TaskInclude,
    and invisible to YAML parsing, to review, and to every structural check in
    this file. CI's playbook syntax-check caught it; nothing here did.

    The authority is read from Ansible itself rather than transcribed, so it
    cannot drift: `TaskInclude.VALID_INCLUDE_KEYWORDS` is the same set the
    parser enforces. This is an attribute read — no playbook is parsed or run.
    """
    task_include = pytest.importorskip("ansible.playbook.task_include")
    valid = set(task_include.TaskInclude.VALID_INCLUDE_KEYWORDS)
    assert "become" not in valid, "the keyword set no longer matches the parser behaviour this guard assumes"
    assert "when" in valid and "vars" in valid, "the keyword set looks wrong — this guard would flag everything"

    include_keys = {"include_tasks", "ansible.builtin.include_tasks"}
    seen = 0
    offenders: list[str] = []
    for candidate in sorted(_ANSIBLE.rglob("*.yml")) + sorted(_ANSIBLE.rglob("*.yaml")):
        try:
            docs = [d for d in yaml.safe_load_all(candidate.read_text(encoding="utf-8")) if d]
        except yaml.YAMLError:
            continue
        for task in _walk(docs):
            keys = set(task)
            used = include_keys & keys
            if not used:
                continue
            seen += 1
            rejected = keys - valid - include_keys
            if rejected:
                offenders.append(f"{candidate.relative_to(_ANSIBLE)}: {task.get('name')} -> {sorted(rejected)}")

    assert seen > 50, f"only {seen} include_tasks found across the tree — the sweep is not reaching it"
    assert not offenders, "Ansible rejects these keywords on an include, so the play fails to parse:\n  " + "\n  ".join(
        offenders
    )


@pytest.mark.parametrize("path", _CALL_SITES, ids=lambda p: p.name)
def test_every_delegation_path_resolves_to_the_primitive(path: Path) -> None:
    """A relative include with the wrong number of `..` fails only on a host.

    Ansible resolves a relative `include_tasks` against a search stack, and for a
    file included from inside a role the ROLE's tasks directory is on that stack
    as well as the including file's own directory. The path form used here was
    picked so that both bases land on the same file — `../../_shared/tasks/x.yml`
    resolves identically from `roles/<role>/tasks/` and from
    `roles/_shared/tasks/`. That is a property worth pinning, because the obvious
    "simplification" to a bare filename only works from one of them.
    """
    for task in _delegations(_load(path)):
        include = _include_path(task)
        assert include, f"{path.name}: '{task.get('name')}' passes remove_dir_path but includes nothing"

        resolved = (path.parent / include).resolve()
        assert resolved.is_file(), (
            f"{path.name}: '{task.get('name')}' includes {include}, which does not resolve to a file "
            f"(tried {resolved})"
        )
        assert resolved == _PRIMITIVE.resolve(), f"{path.name}: {include} resolves to {resolved}, not the primitive"

        # The role-tasks-dir base, for the files that are themselves included
        # into a role. Any role's tasks dir is an equivalent base for this form.
        if path.parent == _SHARED:
            alt = (_ANSIBLE / "roles" / "backend" / "tasks" / include).resolve()
            assert alt == _PRIMITIVE.resolve(), (
                f"{path.name}: {include} resolves to {alt} when Ansible bases it on the including role's "
                "tasks directory instead of this file's own — the two bases must agree"
            )


@pytest.mark.parametrize("path", _CALL_SITES, ids=lambda p: p.name)
def test_every_cleanup_site_delegates_to_the_primitive(path: Path) -> None:
    """A file that stopped delegating has stopped being covered."""
    includes = _includes_of(_load(path), _PRIMITIVE.name)
    assert includes, f"{path.name} no longer routes its component removals through {_PRIMITIVE.name}"
    for task in includes:
        block = task.get("vars") or {}
        assert "remove_dir_path" in block, (
            f"{path.name}: '{task.get('name')}' includes the primitive without passing remove_dir_path, "
            "so it would remove an undefined path"
        )


def test_every_delegated_removal_reaches_the_primitive() -> None:
    """`assert includes` only proves SOME removal still delegates.

    A file with several call sites can have one of them repointed elsewhere and
    still satisfy that. So every task that passes a `remove_dir_path` is checked
    individually, across the whole tree, and the file it names must be the
    primitive and must exist.
    """
    seen = 0
    offenders: list[str] = []
    for candidate in sorted(_ANSIBLE.rglob("*.yml")) + sorted(_ANSIBLE.rglob("*.yaml")):
        try:
            docs = [d for d in yaml.safe_load_all(candidate.read_text(encoding="utf-8")) if d]
        except yaml.YAMLError:
            continue
        for task in _delegations(docs):
            seen += 1
            target = Path(_include_path(task) or "")
            where = f"{candidate.relative_to(_ANSIBLE)}: {task.get('name')} -> {target}"
            if target.name != _PRIMITIVE.name:
                offenders.append(f"{where} (not the guarded primitive)")
            elif not (_SHARED / target.name).is_file():
                offenders.append(f"{where} (target file does not exist)")

    assert seen >= len(_CALL_SITES), (
        f"only {seen} delegated removals found across the tree, fewer than the {len(_CALL_SITES)} known "
        "call sites — the sweep is not seeing them"
    )
    assert not offenders, "these removals are handed to something other than the guard:\n  " + "\n  ".join(offenders)


# --------------------------------------------------------------------------
# structural: no destructive default anywhere on the path to a deletion
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", _CALL_SITES + (_PRIMITIVE,), ids=lambda p: p.name)
def test_nothing_on_the_delete_path_defaults_to_false(path: Path) -> None:
    """`default=false` on a gating fact makes UNDEFINED mean delete."""
    doc = _load(path)
    gates = _deletions(doc) + _includes_of(doc, _PRIMITIVE.name)
    assert gates, f"{path.name} has neither a deletion nor a delegation — this check would be vacuous"
    # Reach, stated rather than assumed: this check reads the gate CONDITIONS
    # only. A gating expression may legitimately be hoisted into a set_fact, and
    # a substring rule cannot judge those — `default(false)` is destructive in
    # `not (has_data | default(false))` and protective in
    # `migration_verified | default(false)`, and the text is identical. The
    # hoisted facts are covered by evaluation instead: see
    # test_legacy_data_probe_defaults_to_assuming_data and the scenario tables,
    # which assert the branch taken rather than the words used.
    for task in gates:
        flat = _when_text(task).replace(" ", "")
        # Both spellings: the lookup form `default=false` and the filter form
        # `default(false)`. Either one means "when we do not know, delete".
        #
        # No exceptions carved out: a rule with exceptions stops being checkable.
        # Where a defaulting expression is genuinely needed, compute it into a
        # named fact first and gate on that — which is what these files do.
        for bad in ("default=false", "default(false)", "default=False"):
            assert bad not in flat, (
                f"{path.name}: a removal is gated on {bad}, so an unknown value takes the delete "
                f"branch. Compute the decision into a fact with a safe default instead:\n"
                f"  {task.get('name')}"
            )


# --------------------------------------------------------------------------
# behavioural: run the real conditions, assert BOTH directions
# --------------------------------------------------------------------------
def _primitive_when() -> list[str]:
    deletions = _deletions(_load(_PRIMITIVE))
    assert deletions, "the primitive has no deletion — nothing to evaluate"
    conditions = _when_list(deletions[0])
    assert conditions, "the primitive's removal is unconditional"
    return conditions


def _wrong_node_when() -> list[str]:
    includes = _includes_of(_load(_WRONG_NODE), _PRIMITIVE.name)
    assert includes, "clean_wrong_node_dir.yml no longer delegates — nothing to evaluate"
    conditions = _when_list(includes[0])
    assert conditions, "the wrong-node delegation is unconditional"
    return conditions


def _wrong_node_normalise() -> dict:
    """The set_fact that turns the raw role fact into the token the gate reads.

    Evaluated rather than mocked: feeding the gate a hand-made token would test
    a value this repo never produces, and the interesting failures all live in
    the step that produces it.
    """
    tasks = [t for t in _load(_WRONG_NODE) if isinstance(t, dict)]
    normalisers = [t for t in tasks if _module(t, "ansible.builtin.set_fact", "set_fact")]
    assert normalisers, "clean_wrong_node_dir.yml no longer normalises the role fact"
    return normalisers[0]


# (data/ present?, must the directory be removed?)
_PRIMITIVE_SCENARIOS = [
    pytest.param(False, True, id="no_data_dir__removes"),
    pytest.param(True, False, id="data_dir_present__refuses"),
    pytest.param(None, False, id="probe_gave_no_verdict__refuses"),
]


@pytest.mark.parametrize("data_exists, expect_removed", _PRIMITIVE_SCENARIOS)
def test_primitive_takes_the_right_branch(data_exists: bool | None, expect_removed: bool) -> None:
    """The backstop, evaluated rather than read.

    The `no_data_dir__removes` row is the one that keeps this honest: a guard
    that refused everything would satisfy the two destructive rows and quietly
    break every legitimate cleanup in the fleet.
    """
    scope: dict[str, Any] = {
        "remove_dir_path": "/opt/autobot/autobot-backend",
        "_remove_dir_data": _stat(data_exists),
    }
    assert _and(_primitive_when(), scope) is expect_removed


def test_primitive_refuses_when_the_probe_never_ran() -> None:
    """Guard order is a thing people get wrong. Unknown must still mean keep."""
    assert _and(_primitive_when(), {"remove_dir_path": "/opt/autobot/autobot-backend"}) is False


# (fact value, data/ present?, must the directory be removed?)
#
# `MISSING` is the state #14856 is named for: `services/deployment.py` runs
# playbooks with a bare `-i "<host>,"` inventory, so group_vars is never
# discovered and these facts simply are not there.
MISSING = object()

_WRONG_NODE_SCENARIOS = [
    pytest.param(MISSING, False, False, id="fact_undefined__keeps"),
    pytest.param(MISSING, True, False, id="fact_undefined_with_data__keeps"),
    pytest.param("false", False, True, id="role_inactive_string__removes"),
    pytest.param(False, False, True, id="role_inactive_bool__removes"),
    pytest.param("no", False, True, id="role_inactive_yamlish__removes"),
    pytest.param("false", True, False, id="role_inactive_but_holds_data__keeps"),
    pytest.param(False, None, False, id="role_inactive_but_probe_silent__keeps"),
    pytest.param("true", False, False, id="role_active_string__keeps"),
    pytest.param(True, False, False, id="role_active_bool__keeps"),
    pytest.param("", False, False, id="fact_empty_string__keeps"),
    pytest.param("  ", False, False, id="fact_whitespace_only__keeps"),
    pytest.param("None", False, False, id="fact_rendered_as_none__keeps"),
    pytest.param("{{ unresolved }}", False, False, id="fact_half_rendered_jinja__keeps"),
    pytest.param("FALSE", False, True, id="role_inactive_uppercase__removes"),
    pytest.param("false\n", False, True, id="role_inactive_folded_scalar__removes"),
]


@pytest.mark.parametrize("fact, data_exists, expect_removed", _WRONG_NODE_SCENARIOS)
def test_wrong_node_cleanup_takes_the_right_branch(fact: Any, data_exists: bool | None, expect_removed: bool) -> None:
    """The whole wiring: the caller's gate AND the primitive's, as Ansible ANDs them.

    Both directions are asserted. `fact_undefined__keeps` is the bug; the two
    `role_inactive_*__removes` rows are the behaviour that must survive the fix,
    and they are what makes this a guard rather than a blanket refusal.
    """
    scope: dict[str, Any] = {
        "role_check_fact": "role_backend_active",
        "dir_name": "autobot-backend",
        "_remove_dir_data": _stat(data_exists),
    }
    if fact is not MISSING:
        scope["role_backend_active"] = fact

    _apply_set_fact(_wrong_node_normalise(), scope)
    removed = _and(_wrong_node_when() + _primitive_when(), scope)
    assert removed is expect_removed, (
        f"role_backend_active={fact!r}, data/={data_exists!r} -> "
        f"{'REMOVED' if removed else 'kept'}, expected {'REMOVED' if expect_removed else 'kept'}"
    )


def test_wrong_node_undefined_fact_would_hard_error_rather_than_delete() -> None:
    """Belt and braces: the gate never reads the fact without an explicit default.

    A bare `lookup('vars', name)` on an undefined fact raises in Ansible. If the
    gate ever grew one, this surfaces it here instead of on a host.
    """
    scope: dict[str, Any] = {"role_check_fact": "role_backend_active", "_remove_dir_data": _stat(False)}
    try:
        _apply_set_fact(_wrong_node_normalise(), scope)
        removed = _and(_wrong_node_when() + _primitive_when(), scope)
    except _FactUndefined:
        return  # a hard error is an acceptable non-destructive outcome
    assert removed is False, "an undefined role fact reached the delete branch — this is #14856 itself"


# --------------------------------------------------------------------------
# legacy retirement is a migration, not a deletion
# --------------------------------------------------------------------------
def test_legacy_data_probe_defaults_to_assuming_data() -> None:
    """The hoisted half of the legacy gate, checked by polarity not by spelling.

    `_legacy_has_data` is what authorises the removal, and it used to be derived
    from a stat that only ran when a canonical target happened to be mapped — so
    an unmapped legacy directory answered "no data here" without anyone having
    looked. The probe must now answer "assume data" when it has no result.
    """
    tasks = [t for t in _load(_LEGACY) if isinstance(t, dict)]
    probes = [
        t
        for t in tasks
        if (_module(t, "ansible.builtin.stat", "stat") or {}).get("path") == "/opt/autobot/{{ dir_name }}/data"
    ]
    assert probes, "nothing probes the legacy directory for data/"
    assert "when" not in probes[0], (
        "the data probe is conditional, so some other condition decides whether the question "
        "authorising a deletion gets asked at all"
    )

    recorders = [t for t in tasks if "_legacy_has_data" in (_module(t, "ansible.builtin.set_fact", "set_fact") or {})]
    assert recorders, "nothing computes _legacy_has_data"
    expr = str((_module(recorders[0], "ansible.builtin.set_fact", "set_fact"))["_legacy_has_data"])

    # No stat result at all -> must come out as "there is data", i.e. keep.
    scope: dict[str, Any] = {"dir_name": "ai-stack", "_legacy_canonical": ""}
    assert _ansible_bool(_render_value(expr, scope)) is True, (
        "with no probe result _legacy_has_data comes out false, which authorises the removal "
        "of a directory nobody looked inside"
    )
    # And the legitimate direction still works: a probe that says 'no data' means no data.
    scope["_legacy_data_stat"] = _stat(False)
    assert _ansible_bool(_render_value(expr, scope)) is False, (
        "a directory the probe found no data in is reported as holding data — legitimate "
        "legacy cleanup would never run again"
    )


def test_legacy_retirement_migrates_before_removing() -> None:
    doc = _load(_LEGACY)
    tasks = [t for t in doc if isinstance(t, dict)]
    names = [str(t.get("name", "")) for t in tasks]
    assert any("MIGRATE" in n for n in names), "legacy cleanup no longer migrates data to the canonical path"

    migrate_at = next(i for i, n in enumerate(names) if "MIGRATE" in n)
    removals = _includes_of(doc, _PRIMITIVE.name)
    assert removals, "legacy cleanup no longer delegates its removal"
    delete_at = tasks.index(removals[0])
    assert migrate_at < delete_at, "the legacy directory is removed before its data is migrated"

    assert "_legacy_safe_to_remove" in _when_text(removals[0]), "the legacy removal is not gated on the safety decision"

    decisions = [
        t for t in tasks if "_legacy_safe_to_remove" in str(_module(t, "ansible.builtin.set_fact", "set_fact") or {})
    ]
    assert decisions, "nothing computes _legacy_safe_to_remove — the gate would be undefined"
    decision = str(_module(decisions[0], "ansible.builtin.set_fact", "set_fact"))
    assert "_legacy_has_data" in decision, "the safety decision ignores whether the path held data"
    assert "default(true)" in decision.replace(" ", ""), (
        "the safety decision does not default to 'has data' when unknown, so an unreadable host "
        "could still be removed"
    )


# (legacy holds data?, migration ran?, migration verified?, safe to remove?)
_LEGACY_SCENARIOS = [
    pytest.param(False, False, False, True, id="never_held_data__removes"),
    pytest.param(True, True, True, True, id="migrated_and_verified__removes"),
    pytest.param(True, False, False, False, id="holds_data_unmigrated__keeps"),
    pytest.param(True, True, False, False, id="migration_did_not_land__keeps"),
    pytest.param(None, False, False, False, id="unknown_whether_it_holds_data__keeps"),
]


@pytest.mark.parametrize("has_data, migrated, verified, expect_removed", _LEGACY_SCENARIOS)
def test_legacy_safety_decision_takes_the_right_branch(
    has_data: bool | None, migrated: bool, verified: bool, expect_removed: bool
) -> None:
    """Evaluate the real `_legacy_safe_to_remove` expression, both directions."""
    tasks = [t for t in _load(_LEGACY) if isinstance(t, dict)]
    decisions = [
        t for t in tasks if "_legacy_safe_to_remove" in str(_module(t, "ansible.builtin.set_fact", "set_fact") or {})
    ]
    assert decisions, "nothing computes _legacy_safe_to_remove"
    expr = str((_module(decisions[0], "ansible.builtin.set_fact", "set_fact") or {})["_legacy_safe_to_remove"])
    expr = expr.strip().removeprefix("{{").removesuffix("}}").strip()

    scope: dict[str, Any] = {
        "_legacy_migrated": {"changed": migrated},
        "_legacy_migrated_check": _stat(verified),
    }
    if has_data is not None:
        scope["_legacy_has_data"] = has_data

    assert _evaluate(expr, scope) is expect_removed
