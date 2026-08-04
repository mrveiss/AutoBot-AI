# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The builtin updater must reconcile the DB credential store (#12907, #12959).

#12907's fix — strip the pre-#12224 unmarked duplicate keys, retire the
superseded ``autobot-db-credentials.env`` — landed in
``roles/postgresql/tasks/databases.yml``. ``update-all-nodes.yml`` applies
neither that role nor an inline copy, so the fix was merged, the issue closed,
and five full self-update runs (``ok=108 changed=32``) left both credential
files byte-identical. The duplicate ``AUTOBOT_DB_PASSWORD`` that caused the
#12883 outage was still there afterwards.

These tests pin the three properties that close it:

1. the reconciliation is applied by the updater, for both credential prefixes;
2. it exists exactly once — extracted to its own task file and *included* by
   ``databases.yml``, not copied into the playbook, because inline-vs-role
   duplication is the root cause #12959 is about;
3. it actually runs and actually reconciles: the shell tasks declare
   ``executable: /bin/bash``, and the collapse leaves exactly one assignment per
   key carrying the value every consumer already resolves to.

#13454 shipped 1 and 2 and still delivered nothing, because ``shell`` runs under
``/bin/sh`` -- dash on the deployed hosts -- where ``set -o pipefail`` is an
illegal option in a special builtin. Every task aborted on line 1 with rc=2,
``failed_when: false`` made that a green ``ok``, and the tasks gated on
``rc == 0`` were skipped on every host. Hence the behavioural tests below:
asserting the task's *shape* is what let a fix that could not execute look
delivered twice.

``tasks_from`` is the intended shape, not a compromise: applying the postgresql
role in full on an update path would re-run installation, configuration and
database creation on a host that already has all three. The companion guard
``test_update_all_applies_roles_12959.py`` asserts that contract, and still
xfails for the four components that have no task file at all yet (#13460).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_ROLE_TASKS = _ANSIBLE / "roles" / "postgresql" / "tasks"
_RECONCILE = _ROLE_TASKS / "credentials_reconcile.yml"
_DATABASES = _ROLE_TASKS / "databases.yml"

#: The awk program that collapses duplicate keys. Distinctive enough that a
#: copy anywhere else in the tree is a real duplication, not a coincidence.
_STRIP_FINGERPRINT = 'sub(/=.*/, "", k); last[k] = NR'

#: Name fragment of the task that owns the collapse; extracted and executed
#: against fixtures below.
_STRIP_TASK = "Collapse duplicate"

_MARKER = "# {mark} {prefix} DB CREDENTIALS (managed by postgresql role)"


def _iter_mappings(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_mappings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_mappings(item)


def _reconcile_includes() -> list[dict]:
    """Every playbook task that applies the postgresql credential reconcile."""
    playbook = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    found = []
    for task in _iter_mappings(playbook):
        inc = task.get("ansible.builtin.include_role") or task.get("include_role")
        if (
            isinstance(inc, dict)
            and inc.get("name") == "postgresql"
            and inc.get("tasks_from") == "credentials_reconcile"
        ):
            found.append(task)
    return found


def test_reconcile_task_file_exists():
    assert _RECONCILE.is_file(), (
        f"{_RECONCILE} missing — without it the #12907 fix has no application "
        "path that does not also run the whole postgresql role"
    )


def test_no_role_task_file_is_git_ignored():
    """A .gitignore pattern must never silently swallow a role's own code.

    ``credentials*`` (a rule for credential *data*) matched
    ``roles/postgresql/tasks/credentials_reconcile.yml``. Every test here passed
    off the working copy while the file never reached the remote — a host would
    have gotten an ``include_role`` pointing at a task file that does not exist.
    That is the same "green but not delivered" shape as #12959 itself, one layer
    down, so it gets its own guard.
    """
    git = shutil.which("git")
    if git is None:
        pytest.skip("git not installed")

    roles = _ANSIBLE / "roles"
    candidates = [p for p in roles.rglob("*.yml")] + [p for p in roles.rglob("*.j2")]
    assert candidates, f"no role files found under {roles} — did the layout move?"

    # --no-index is load-bearing: without it check-ignore reports nothing for a
    # file that is already in the index, so the guard would go green the moment
    # someone ran `git add -f` locally and still ship an ignore rule that traps
    # the next role file added.
    result = subprocess.run(
        [git, "check-ignore", "--no-index", "--stdin"],
        input="\n".join(str(p) for p in candidates),
        capture_output=True,
        text=True,
        cwd=roles,
        timeout=60,
    )

    ignored = [line for line in result.stdout.splitlines() if line.strip()]
    assert not ignored, (
        "role files excluded by .gitignore — they exist locally, are absent from "
        "the remote, and every include_role pointing at them breaks on a host:\n  " + "\n  ".join(ignored)
    )


def test_updater_applies_the_reconcile_for_both_prefixes():
    """db-credentials.env is shared by the SLM_ and AUTOBOT_ prefixes.

    Reconciling only one leaves the other's stale duplicates in place, and the
    SLM migration parse takes the *first* ``DATABASE_URL=`` match.
    """
    prefixes = {(task.get("vars") or {}).get("db_env_prefix") for task in _reconcile_includes()}
    assert {"SLM", "AUTOBOT"} <= prefixes, (
        "update-all-nodes.yml must apply roles/postgresql credentials_reconcile "
        f"for both prefixes; found {sorted(p for p in prefixes if p)}"
    )


def test_reconcile_runs_with_become():
    """/etc/autobot/db-credentials.env is root-owned, mode 0600.

    ``become`` is not a valid keyword on a dynamic ``include_role`` — ansible
    rejects the whole playbook — so privilege must be handed over via ``apply``.
    """
    for task in _reconcile_includes():
        inc = task.get("ansible.builtin.include_role") or task["include_role"]
        assert (inc.get("apply") or {}).get("become") is True, (
            f"{task.get('name')!r}: reconcile needs `apply: {{become: true}}`; "
            "a bare `become` on include_role breaks every self-update"
        )


def test_reconcile_is_defined_exactly_once():
    """The strip logic must not be copied into the playbook or the role's main flow.

    Two implementations of the same deploy step, free to drift, is precisely
    the #12959 failure mode.
    """
    tree = _ANSIBLE.parent.parent
    copies = [
        path
        for path in tree.rglob("*.yml")
        if "node_modules" not in path.parts and _STRIP_FINGERPRINT in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert copies == [_RECONCILE], (
        "the credential-strip logic must live only in "
        f"{_RECONCILE.name}; also found in {[str(p) for p in copies if p != _RECONCILE]}"
    )


def test_databases_yml_includes_rather_than_repeats_it():
    tasks = yaml.safe_load(_DATABASES.read_text(encoding="utf-8"))
    includes = [(t.get("ansible.builtin.include_tasks") or t.get("include_tasks")) for t in tasks]
    assert "credentials_reconcile.yml" in includes, (
        "roles/postgresql/tasks/databases.yml must include credentials_reconcile.yml "
        "so provisioning and the updater share one implementation"
    )


def _shell_tasks_using_pipefail() -> list[tuple[Path, dict]]:
    """Every shell task in the ansible tree whose body relies on ``pipefail``."""
    found = []
    for path in sorted(_ANSIBLE.rglob("*.yml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue  # vault/templated files are not what this guard is about
        for task in _iter_mappings(doc):
            module = task.get("ansible.builtin.shell", task.get("shell"))
            body = module.get("cmd", "") if isinstance(module, dict) else module
            if isinstance(body, str) and "pipefail" in body:
                found.append((path, task))
    return found


def test_every_pipefail_shell_task_declares_bash():
    """``shell`` runs under /bin/sh, which is dash -- where pipefail is illegal.

    This is the whole of why #13454 delivered nothing: ``set -euo pipefail``
    made every reconcile task exit 2 on its first line, before any credential
    logic ran. The failure is invisible (``failed_when: false`` reports ``ok``
    and ansible.cfg sets ``display_skipped_hosts = False``), so it gets a static
    guard rather than another live deploy to re-discover it.
    """
    tasks = _shell_tasks_using_pipefail()
    assert tasks, "no pipefail shell tasks found — did the ansible tree move?"

    offenders = []
    for path, task in tasks:
        module = task.get("ansible.builtin.shell", task.get("shell"))
        executable = (task.get("args") or {}).get("executable") or (
            module.get("executable") if isinstance(module, dict) else None
        )
        if not str(executable or "").endswith("bash"):
            offenders.append(f"{path.name}: {task.get('name')!r} (executable={executable!r})")

    assert not offenders, (
        "shell tasks using `set -o pipefail` must declare `executable: /bin/bash`; "
        "under /bin/sh (dash) they abort with rc=2 before running:\n  " + "\n  ".join(offenders)
    )


def _run_collapse(tmp_path: Path, content: str, prefix: str = "AUTOBOT") -> tuple[str, str]:
    """Run the SHIPPED collapse task against a fixture credential file.

    Extracts the task body from the role instead of re-implementing it, so the
    test cannot pass against a transform the host never runs.
    """
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not installed")

    tasks = yaml.safe_load(_RECONCILE.read_text(encoding="utf-8"))
    task = next(t for t in tasks if _STRIP_TASK in t["name"])
    script = task["ansible.builtin.shell"]["cmd"]
    for placeholder, value in (
        ("{{ postgresql_credentials_dir }}", str(tmp_path)),
        ("{{ postgresql_credentials_file }}", "db-credentials.env"),
        ("{{ db_env_prefix }}", prefix),
    ):
        script = script.replace(placeholder, value)

    target = tmp_path / "db-credentials.env"
    target.write_text(content, encoding="utf-8")
    result = subprocess.run([bash, "-c", script], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"collapse refused: rc={result.returncode} {result.stderr}"
    return target.read_text(encoding="utf-8"), result.stdout


def _values(text: str, key: str) -> list[str]:
    return [line.split("=", 1)[1] for line in text.splitlines() if line.startswith(f"{key}=")]


#: The observed live shape: two full sets of AUTOBOT keys, neither inside a
#: managed block (the host predates #12224), the dead copy FIRST. Every value is
#: a fixture placeholder — the real store is mode 0600 and is never read here.
_LEGACY = """# AutoBot database credentials
SLM_DB_USER=slm_app
SLM_DB_PASSWORD=slm-value
AUTOBOT_DB_HOST=127.0.0.1
AUTOBOT_DB_USER=autobot_app
AUTOBOT_DB_PASSWORD=first-copy-dead
AUTOBOT_DATABASE_URL=postgresql+asyncpg://db-node:5432/autobot_users?copy=first
AUTOBOT_DB_HOST=127.0.0.1
AUTOBOT_DB_USER=autobot_app
AUTOBOT_DB_PASSWORD=last-copy-live
AUTOBOT_DATABASE_URL=postgresql+asyncpg://db-node:5432/autobot_users?copy=last
"""

_BEGIN_SLM = _MARKER.format(mark="BEGIN", prefix="SLM")
_END_SLM = _MARKER.format(mark="END", prefix="SLM")
_BEGIN_AUTOBOT = _MARKER.format(mark="BEGIN", prefix="AUTOBOT")
_END_AUTOBOT = _MARKER.format(mark="END", prefix="AUTOBOT")

#: A migrated host: residue above, both managed blocks below. The SLM block
#: carries AUTOBOT_USERS_DATABASE_URL (#12297) — an AUTOBOT_-prefixed key that
#: lives inside the *other* prefix's block.
_WITH_BLOCKS = f"""AUTOBOT_DB_PASSWORD=first-copy-dead
{_BEGIN_SLM}
SLM_DB_PASSWORD=slm-value
AUTOBOT_USERS_DATABASE_URL=postgresql+asyncpg://db-node:5432/autobot_users?owner=slm-block
{_END_SLM}
{_BEGIN_AUTOBOT}
AUTOBOT_DB_PASSWORD=last-copy-live
AUTOBOT_DATABASE_URL=postgresql+asyncpg://db-node:5432/autobot_users?copy=managed
{_END_AUTOBOT}
"""


def test_collapse_keeps_the_current_value_on_a_legacy_host(tmp_path):
    """The whole point: duplicates outside any managed block must be reconciled.

    The gate #13454 used — "only strip when this prefix's marker exists" —
    skipped precisely this host, because the marker is what a pre-#12224 host
    does not have.
    """
    after, stdout = _run_collapse(tmp_path, _LEGACY)

    assert "CHANGED" in stdout
    assert _values(after, "AUTOBOT_DB_PASSWORD") == ["last-copy-live"], (
        "must keep the LAST assignment: the dead copy is first, and retaining "
        "it locks the deployment out of PostgreSQL"
    )
    assert _values(after, "AUTOBOT_DATABASE_URL") == [
        "postgresql+asyncpg://db-node:5432/autobot_users?copy=last"
    ]
    assert _values(after, "SLM_DB_PASSWORD") == ["slm-value"], "the other prefix must not be touched"
    assert after.startswith("# AutoBot database credentials\n"), "comments must survive"


def test_collapse_is_idempotent(tmp_path):
    """A second application must be a byte-for-byte no-op."""
    once, _ = _run_collapse(tmp_path, _LEGACY)
    twice, stdout = _run_collapse(tmp_path, once)

    assert twice == once
    assert "CHANGED" not in stdout, "a reconciled file must not be rewritten again"


def test_collapse_does_not_damage_a_clean_file(tmp_path):
    """One assignment per key: nothing to do, and nothing done."""
    clean = "AUTOBOT_DB_PASSWORD=last-copy-live\nAUTOBOT_DB_HOST=127.0.0.1\n"
    after, stdout = _run_collapse(tmp_path, clean)

    assert after == clean
    assert "CHANGED" not in stdout
    assert not (tmp_path / "db-credentials.env.pre-12907.bak").exists(), "an untouched file must not be backed up"


def test_collapse_preserves_a_managed_block_and_the_other_prefixs_key(tmp_path):
    """Regression guard for the #12297 landmine the previous strip re-armed.

    That awk dropped every ``AUTOBOT_*`` line outside the *AUTOBOT* block —
    which includes ``AUTOBOT_USERS_DATABASE_URL``, deliberately emitted inside
    the **SLM** block. Collapsing by last assignment has no such blind spot: a
    key that appears once is its own last assignment.
    """
    after, stdout = _run_collapse(tmp_path, _WITH_BLOCKS)

    assert "CHANGED" in stdout
    assert _values(after, "AUTOBOT_DB_PASSWORD") == ["last-copy-live"]
    assert _values(after, "AUTOBOT_USERS_DATABASE_URL") == [
        "postgresql+asyncpg://db-node:5432/autobot_users?owner=slm-block"
    ], "the SLM block's AUTOBOT_-prefixed key must survive an AUTOBOT reconcile"
    for marker in (_BEGIN_SLM, _END_SLM, _BEGIN_AUTOBOT, _END_AUTOBOT):
        assert marker in after, f"blockinfile marker lost: {marker}"
    assert after.count("AUTOBOT_DB_PASSWORD=") == 1


def test_collapse_backs_the_file_up_before_mutating_it(tmp_path):
    """The store holds live DB passwords; a wrong rewrite is an outage."""
    _run_collapse(tmp_path, _LEGACY)
    backup = tmp_path / "db-credentials.env.pre-12907.bak"

    assert backup.is_file(), "no recovery copy taken before rewriting the credential store"
    assert backup.read_text(encoding="utf-8") == _LEGACY


def test_updater_asserts_delivery_instead_of_reporting_success_blindly():
    """A green run that delivered nothing is the outcome #12959 is about."""
    text = _PLAYBOOK.read_text(encoding="utf-8")
    playbook = yaml.safe_load(text)
    asserts = [
        task
        for task in _iter_mappings(playbook)
        if (task.get("ansible.builtin.assert") or task.get("assert")) and "12959" in str(task.get("name", ""))
    ]
    assert asserts, "update-all-nodes.yml has no post-update delivery assertion (#12959)"

    covered = " ".join(str((t.get("ansible.builtin.assert") or t["assert"]).get("that")) for t in asserts)
    for invariant, issue in (
        ("faulthandler", "#12777"),
        ("dup_cred_keys", "#12907 Defect 1"),
        ("legacy_store", "#12907 Defect 2"),
    ):
        assert invariant in covered, f"no delivery assertion for {issue} ({invariant})"
