# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The post-add verification gate fires on every path that ADDED a repo (#17897).

Split from `pgdg_preserved_repo_is_verified_17897_test.py` at the 600-line ceiling. That
file exercises the role's embedded shell; this one is a meta-check over the role's
`when:` expressions and failure message -- so a regression here surfaces in whichever
shard holds THIS file, not the shard holding the role.

The defect: `Record the verdict` short-circuits `_apt_repo_verdict` to 'usable' whenever
presence is not `PRESENT`, and both post-add tasks were gated on `!= 'usable'`. That
excluded `MISSING` -- the fresh-install path, where nothing had been verified at all. So
a one-command install added the repo, verified nothing, and died three steps later on
apt's bare "No package matching 'postgresql-16' is available".
"""

from __future__ import annotations

import jinja2
import pytest
from repo_tests._ansible_tasks import eval_when, load_tasks, named, when_of
from repo_tests._paths import repo_root

HELPER = (
    repo_root()
    / "autobot-slm-backend"
    / "ansible"
    / "roles"
    / "_shared"
    / "tasks"
    / "add_apt_repository_idempotent.yml"
)
PKG = "postgresql-16"


@pytest.fixture(scope="module")
def helper_tasks() -> list[dict]:
    return load_tasks(HELPER)


def _verdict_template(helper_tasks: list[dict]) -> str:
    """The role's own `_apt_repo_verdict` expression, whitespace-normalised."""
    return " ".join(
        str(named(helper_tasks, "Record the verdict")["ansible.builtin.set_fact"]["_apt_repo_verdict"]).split()
    )


def _verdict_shortcircuits_to_usable(helper_tasks: list[dict], present: str) -> bool:
    r"""Does the role decide 'usable' WITHOUT consulting the probe, for this presence?

    Only the `if` condition is evaluated, never the else-branch. That is deliberate and
    is the difference between an instrument that matches its question and one that does
    not: the else-branch calls `regex_search`, which Jinja does not have, and a mock of
    it does NOT reproduce Ansible's semantics. Measured on ansible-core 2.17 -- Ansible
    delivers a string literal `'\1'` to a filter as backslash-one, where a plain Jinja
    environment applies `unicode_escape` and delivers `\x01`. So a plain-Jinja harness
    reports the opposite verdict about the group spec from the engine that runs the
    play: it accepts `'\\1'`, which Ansible rejects (#17912 was exactly that raise).

    The `if` condition uses only `default`, `trim` and `length` -- all native Jinja,
    none escape-sensitive -- so evaluating THAT is faithful. The reachability fact the
    gate test needs lives entirely in it.
    """
    template = _verdict_template(helper_tasks)
    parts = template.split(" else ")
    assert len(parts) == 2, (
        f"expected exactly one top-level ' else ' in the verdict expression, found "
        f"{len(parts) - 1}: the slice below would be the wrong half of the expression. "
        f"Expression: {template}"
    )
    condition = parts[0].split(" if ", 1)[1]
    env = jinja2.Environment(autoescape=False)  # noqa: S701 - a condition, not markup
    return bool(
        env.compile_expression(condition, undefined_to_none=True)(
            _apt_repo_present={"stdout": present},
            apt_repo_verify_package=PKG,
        )
    )


def test_a_missing_repo_derives_usable_without_ever_probing(
    helper_tasks: list[dict],
) -> None:
    """The reachability fact that created the defect, pinned on its own.

    `Record the verdict` short-circuits to 'usable' whenever presence is not `PRESENT`.
    So on a fresh host -- nothing configured, nothing probed, nothing verified -- the
    verdict reads exactly like a repo that was probed and found working. Any gate
    written as `verdict != 'usable'` is therefore OPEN on the fresh-install path, which
    is the one path where no verification has happened at all.
    """
    assert _verdict_shortcircuits_to_usable(helper_tasks, "MISSING"), (
        "MISSING no longer short-circuits to 'usable'. If that is intentional the gate "
        "predicates below can be simplified -- but check them, do not assume: the whole "
        "point of #17897 is that 'usable' and 'verified' were not the same thing"
    )
    assert not _verdict_shortcircuits_to_usable(helper_tasks, "PRESENT"), (
        "PRESENT now short-circuits too, so the probe's verdict is never consulted and "
        "the preserve path trusts presence again -- the original #17897 defect"
    )


#: (presence, verdict) -> whether the two post-add tasks must fire. An add happens when
#: the repo was MISSING or the configured one was found unusable, so verification must
#: happen in exactly those cases.
#:
#: `undetermined` must not fire because the play never reaches the add: "Stop: could not
#: determine whether the configured repo serves the package" fails first. The row is
#: here so that turning the stop into a warning shows up as a gap in this table rather
#: than as a silent skip.
_GATE_MATRIX = [
    ("MISSING", "usable", True),
    ("PRESENT", "usable", False),
    ("PRESENT", "unusable", True),
    ("PRESENT", "undetermined", False),
]

_POST_ADD_TASKS = (
    "Confirm the package is available after the add",
    "Fail with the real cause when the repo still cannot serve the package",
)


@pytest.mark.parametrize(("present", "verdict", "gates_fire"), _GATE_MATRIX)
@pytest.mark.parametrize("task_name", _POST_ADD_TASKS)
def test_the_post_add_gates_fire_on_every_path_that_added_a_repo(
    helper_tasks: list[dict],
    task_name: str,
    present: str,
    verdict: str,
    gates_fire: bool,
) -> None:
    """A path that ADDS a repo must verify it, and `MISSING` is such a path.

    The defect this pins: both post-add tasks were gated on `_apt_repo_verdict !=
    'usable'`, and a MISSING repo derives 'usable' -- so a fresh add verified nothing
    and the play died much later at `Install PostgreSQL packages` with apt's bare "No
    package matching 'postgresql-16' is available". The gates now MIRROR the add's own
    predicate, which states "an add happened" instead of negating a fact about
    preservation. An earlier revision was told this about `not preserve_ok` and replaced
    it with `!= 'usable'`, which is true in the same case: the variable changed and the
    hole did not.

    WHERE A REGRESSION HERE SURFACES: this is a meta-check over another file's `when:`
    expressions, so it fails in whichever shard holds THIS file, not the shard holding
    the role. Opening the role's shard, finding it green, and concluding the gate is
    intact is wrong by checking.
    """
    if _verdict_shortcircuits_to_usable(helper_tasks, present):
        assert verdict == "usable", (
            f"unreachable row: presence={present!r} short-circuits the verdict to "
            f"'usable', so {verdict!r} cannot occur with it. Fix the matrix rather than "
            f"the role -- a test that asserts over states the system cannot produce "
            f"passes without touching the behaviour it claims to cover"
        )
    got = eval_when(
        when_of(named(helper_tasks, task_name)),
        apt_repo_verify_package=PKG,
        _apt_repo_present={"stdout": present},
        _apt_repo_verdict=verdict,
        _apt_repo_probe_final={"stdout": "VERDICT=unusable\nUPDATE_RC=0"},
        _apt_repo_moved={"stdout": ""},
    )
    assert got is gates_fire, (
        f"{task_name!r} with presence={present!r} verdict={verdict!r} "
        f"{'did not fire when it must' if gates_fire else 'fired when it must not'}. "
        f"MISSING is the fresh-add path: nothing has been verified there, so it is the "
        f"one path that most needs the check it was skipping"
    )


def test_every_branch_of_the_failure_prose_is_reachable(
    helper_tasks: list[dict],
) -> None:
    """Prose that no input can produce is a symptom of a wrong gate, not a wrong message.

    The failure message says either "was moved to <backup>" or "No source for this
    repository was previously configured here". The second branch was unreachable: the
    task was gated on `_apt_repo_verdict != 'usable'`, which excluded MISSING -- the
    only state in which nothing had been moved aside. The dead prose was not a cosmetic
    leftover, it was a readable trace of the gate's hole, visible without running
    anything.

    The firing rows are computed by evaluating the task's REAL `when:`, not read from
    `_GATE_MATRIX`'s expected flags. A first version of this test did the latter and so
    could not see the gate at all: it rendered whatever the matrix said should fire and
    passed with the defect reinstated. Asserting over intended behaviour instead of
    actual behaviour is the same mistake as supplying a derived value as an input.

    Only native Jinja is involved here (`~`, `in`, `default`), so a plain environment is
    faithful -- unlike the verdict expression, which calls `regex_search`.
    """
    task = named(helper_tasks, "Fail with the real cause")
    template = " ".join(str(task["ansible.builtin.fail"]["msg"]).split())
    env = jinja2.Environment(autoescape=False)  # noqa: S701 - a log message, not markup

    # `_apt_repo_verdict` is the PRE-add verdict; `_apt_repo_probe_final` is the
    # post-add probe. They are different measurements, and this message is only ever
    # emitted when the post-add probe is still not usable -- so that one is fixed.
    def state(present: str, verdict: str) -> dict:
        return {
            "apt_repo_verify_package": PKG,
            "_apt_repo_present": {"stdout": present},
            "_apt_repo_verdict": verdict,
            "_apt_repo_probe_final": {"stdout": "VERDICT=unusable\nUPDATE_RC=0"},
            "_apt_repo_moved": {"stdout": "Moved aside" if present == "PRESENT" else ""},
        }

    firing = [
        (present, verdict)
        for present, verdict, _ in _GATE_MATRIX
        if eval_when(when_of(task), **state(present, verdict))
    ]
    assert firing, (
        "the failure task fires in no state of the matrix, so no prose is reachable and "
        "this test would pass by vacuity -- check the gate before the message"
    )
    rendered = "\n".join(
        env.from_string(template).render(
            apt_repo_label="PGDG",
            apt_repo_spec="deb [signed-by=...] <repo-url> noble-pgdg main",
            apt_repo_match="pgdg",
            apt_repo_backup_dir="/var/backups/autobot-apt-sources",
            ansible_facts={"distribution_release": "noble"},
            **state(present, verdict),
        )
        for present, verdict in firing
    )
    for branch in (
        "was moved to",
        "No source for this repository was previously configured here",
    ):
        assert branch in rendered, (
            f"no state in which this task fires produces {branch!r}. Either the gate "
            f"excludes the state the branch describes -- the #17897 defect, with the "
            f"branch as its visible symptom -- or the branch is genuinely dead. Check "
            f"which before deleting the prose: deleting it hides the gate's hole. "
            f"Firing states: {firing}"
        )


# The regex group spec's escaping is NOT asserted here. `ansible_regex_backslash_scalar_17897_test.py`
# already enforces it repo-wide -- every `regex_search` backreference in every parsed YAML must carry
# exactly one backslash post-parse -- with its own reach check and a detector-fires case. A second
# assertion of the same property would be a second patch for one defect: more witnesses, not more
# repair. The measured asymmetry that makes a TEXT assertion the only safe form (Ansible delivers
# `'\1'` as backslash-one; plain Jinja applies unicode_escape and delivers \x01, so a render-based
# harness argues for exactly the form Ansible rejects) is recorded in `_ansible_tasks.py`'s module
# docstring, where the next person reaching for Jinja will meet it.
