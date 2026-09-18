# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Guard against hand-rolled admin-role string comparisons (#12786).

``require_role(*roles: Role | str)`` accepts raw strings, so 17 call sites pass
``require_role("admin", "superadmin")`` even though ``superadmin`` is not a
member of the shared ``Role`` enum. That splits authorization into two
populations that silently disagree: every ``require_role`` guard admits a
superadmin, while every hand-rolled ``role == "admin"`` check rejects one.

Where a router has both, a superadmin can perform the write but not the read.
That has already produced #12704 (six forked ``_require_admin`` dependencies)
and #12717 (a superadmin silently *downgraded* rather than denied).

``is_admin_role()`` is the single answer for imperative checks. This test stops
the class from returning: a new ``role == "admin"`` comparison fails here rather
than becoming the next incident.

#13854/#12786 did the deeper fix for ``superadmin``: it is a first-class
``Role`` member with an explicit (empty) ``ROLE_PERMISSIONS`` entry, and
``ADMIN_ROLES`` is now derived from the enum, so it can no longer name a role
the enum does not have.

``platform_admin`` is deliberately NOT in that enum. Nothing anywhere mints it
as a role string — the platform-level signal the codebase actually uses is the
boolean ``users.is_platform_admin`` — so adding it would invent a role rather
than canonicalise one. It stays in ``ADMIN_ROLE_LITERALS`` below because this
guard's job is to catch hand-rolled comparisons against ANY administrative
literal, and a comparison against a role nothing mints is still a bug worth
failing on.
"""

import ast
import functools
import os
import pathlib
import sys

import pytest

BACKEND_ROOT = pathlib.Path(__file__).parent

#: Comparing a role against any of these by hand is the bug this guards.
ADMIN_ROLE_LITERALS = {"admin", "superadmin", "platform_admin"}

#: ``auth_rbac`` is where the canonical set is *defined*, so it is exempt.
EXEMPT_FILES = {"auth_rbac.py"}

SKIP_DIR_PARTS = {
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "archive",
    "migrations",
}


def _is_role_operand(node: ast.expr) -> bool:
    """Whether *node* reads something called ``role``.

    Covers ``role``/``user_role`` locals, ``obj.role`` attributes, and
    ``user_data["role"]`` subscripts — the shapes these checks actually take.
    """
    if isinstance(node, ast.Name):
        return "role" in node.id.lower()
    if isinstance(node, ast.Attribute):
        return "role" in node.attr.lower()
    if isinstance(node, ast.Subscript):
        key = node.slice
        return isinstance(key, ast.Constant) and str(key.value).lower() == "role"
    if isinstance(node, ast.Call):  # e.g. user_data.get("role")
        return any(isinstance(a, ast.Constant) and str(a.value).lower() == "role" for a in node.args)
    return False


def _is_admin_literal(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and str(node.value).lower() in ADMIN_ROLE_LITERALS


def _offenders_in(tree: ast.AST) -> list[int]:
    """Line numbers of ``<role> == "admin"``-shaped comparisons."""
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
            continue
        operands = [node.left, *node.comparators]
        has_role = any(_is_role_operand(o) for o in operands)
        has_admin = any(_is_admin_literal(o) for o in operands)
        if has_role and has_admin:
            lines.append(node.lineno)
    return lines


#: Floor on the swept population. The backend tree carries ~2.3k non-test
#: modules; this is set far below that so ordinary churn never trips it, while
#: a collapsed sweep still fails by name. Before #14484 this guard had no floor
#: at all, so a sweep reaching zero files reported a clean tree.
MIN_SWEPT_FILES = 500


def _python_files():
    # #16601: walked with os.walk, pruning SKIP_DIR_PARTS from dirnames in
    # place, rather than BACKEND_ROOT.rglob("*.py") filtered afterward.
    # rglob has no pruning hook -- it descends into every directory
    # unconditionally and only skips the FILES it finds there, so it still
    # pays the full traversal cost of whatever sits under a denylisted
    # directory. A shard-10 hang was measured frozen inside rglob's own
    # scandir call for 40+ minutes with zero progress (in a sibling sweep,
    # repo_tests/collected_test_model.py, same anti-pattern); this sweep
    # walks the same backend tree with the same shape and was flagged
    # alongside it (#16915) for the same reason.
    for dirpath, dirnames, filenames in os.walk(BACKEND_ROOT):
        # #14484: relative to the scan root, never the absolute path. Testing
        # ``set(path.parts)`` asks whether the *checkout* sits under a directory
        # named `archive`/`migrations`/`venv` as well as whether the file does,
        # so the guard's reach depended on where the tree was cloned.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_PARTS]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            if filename.endswith("_test.py") or filename.startswith("test_"):
                continue
            if filename in EXEMPT_FILES:
                continue
            yield pathlib.Path(dirpath, filename)


def _may_contain_offender(source: str) -> bool:
    """Cheap text prefilter: can *source* possibly hold an offending compare?

    ``_offenders_in`` only ever flags a comparison that pairs a ``role``-ish
    operand (name/attribute/subscript/kwarg all matched on the text ``role``)
    with one of :data:`ADMIN_ROLE_LITERALS` (all three contain ``admin``). A
    file whose source contains neither substring cannot produce a hit, so it
    never needs parsing.

    Known limit: any *obfuscated* spelling of the literal defeats the prefilter —
    implicit concatenation (``"ad" "min"``), escape sequences (``"\x61dmin"``,
    ``"\u0061dmin"``), an escaped subscript key (``d["\x72ole"]``), or an
    NFKC-normalised identifier (``ｒｏｌｅ``). Each is a hit for the matcher whose
    source text lacks the substring. Verified zero such constructs exist across
    all 2,171 backend files; someone writing one is defeating a lint guard
    deliberately, not tripping one accidentally.

    This is what makes the guard affordable (#13284): ``ast.walk`` plus the
    per-node loop in ``_offenders_in`` is pure Python, so under ``--cov`` every
    one of ~2.7M AST nodes is traced. The prefilter is a C-level ``str.lower``
    and ``in``, and drops ~2,170 backend files to ~90 — a ~96% cut in nodes
    walked.

    Known limit: a literal spelled indirectly (``"ad" "min"``, ``"\\x61dmin"``)
    would be skipped. Every call site in this repo spells it plainly, and
    ``TestGuardDetection`` still pins the AST shapes the matcher must catch.
    """
    lowered = source.lower()
    return "admin" in lowered and "role" in lowered


@functools.lru_cache(maxsize=1)
def _hand_rolled_admin_comparisons() -> tuple[str, ...]:
    """``path:line`` for every hand-rolled admin-role comparison in the backend.

    Cached so repeat callers (and reruns within a session) pay the sweep once.
    """
    offenders: list[str] = []
    for path in _python_files():
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # A non-UTF-8 source cannot hold the ASCII literals this guard matches on.
            continue
        except OSError as exc:
            # #13284: do NOT skip silently. Before the prefilter this read was not
            # wrapped, so an unreadable file failed the run. An unreadable file inside
            # a security guard is exactly where an offender could hide, so keep it loud.
            raise AssertionError(f"admin-role guard could not read {path}: {exc}") from exc
        if not _may_contain_offender(source):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for line in _offenders_in(tree):
            offenders.append(f"{path.relative_to(BACKEND_ROOT)}:{line}")
    return tuple(sorted(offenders))


def _assert_population() -> None:
    """Raise unless the sweep reached the backend tree it claims to scan.

    Called from the floor test *and* from the offender assertion, so the floor
    is evaluated before the substantive check whatever order the tests run in.
    """
    swept = sum(1 for _ in _python_files())
    assert swept >= MIN_SWEPT_FILES, (
        f"the admin-role sweep reached only {swept} files under {BACKEND_ROOT} "
        f"(floor {MIN_SWEPT_FILES}). FIX THE SWEEP -- an empty sweep reports no "
        "offenders, which reads exactly like a clean tree. Do not lower this bound."
    )


def test_the_sweep_reached_the_backend_tree():
    """Population floor, evaluated before the offender assertion below."""
    _assert_population()


def test_no_hand_rolled_admin_role_comparisons():
    """Use ``is_admin_role()`` instead — it admits superadmin, as guards do."""
    _assert_population()
    offenders = _hand_rolled_admin_comparisons()

    assert not offenders, (
        "Hand-rolled admin-role comparison(s) found — a superadmin is admitted by "
        "require_role() but would be rejected here (#12704, #12717, #12786).\n"
        "Use `from autobot_shared.auth.permissions import is_admin_role` and `is_admin_role(role)`:\n  "
        + "\n  ".join(sorted(offenders))
    )


class TestGuardDetection:
    """The guard must actually catch the shapes it claims to."""

    @pytest.mark.parametrize(
        "source",
        [
            'if role == "admin": pass',
            'if user_role == "superadmin": pass',
            'if user.role != "admin": pass',
            'if user_data["role"] == "admin": pass',
            'if user_data.get("role") == "platform_admin": pass',
            'if "admin" == role: pass',
        ],
    )
    def test_detects_offending_shapes(self, source):
        assert _offenders_in(ast.parse(source)) == [1]

    @pytest.mark.parametrize(
        "source",
        [
            "if is_admin_role(role): pass",
            "if role in ADMIN_ROLES: pass",
            'if name == "admin": pass',  # not a role
            'if role == "operator": pass',  # not an admin literal
            '"""A docstring mentioning role == \'admin\' must not match."""',
        ],
    )
    def test_ignores_acceptable_shapes(self, source):
        assert _offenders_in(ast.parse(source)) == []


# ---------------------------------------------------------------------------
# Does the walk actually PRUNE a SKIP_DIR_PARTS directory, or merely filter it
# out of the result afterward? (#16601)
#
# ``BACKEND_ROOT.rglob("*.py")`` filtered post-hoc and ``os.walk()`` with
# ``dirnames[:] = [...]`` pruning produce the identical final file list --
# that identity is exactly why no assertion on ``_python_files()``'s RETURN
# VALUE can tell them apart, and why the shard-10 hang (rglob descending into
# a huge excluded directory regardless) shipped without any test noticing.
# This test instead watches which directories ``os.walk`` is fed to next: a
# SKIP_DIR_PARTS directory holding a sentinel file must never be YIELDED by
# the walk at all, which is true only when ``dirnames`` is mutated in place
# before the walk continues past it.
# ---------------------------------------------------------------------------


def test_python_files_prunes_skip_dirs_during_the_walk_not_after(tmp_path, monkeypatch) -> None:
    skip_name = next(iter(SKIP_DIR_PARTS))
    skip_dir = tmp_path / skip_name
    skip_dir.mkdir()
    # A file that would be collected if this directory were ever descended
    # into -- its mere presence in the returned files, or its directory being
    # visited at all, is the tell.
    (skip_dir / "sentinel.py").write_text("role = 'admin'\n", encoding="utf-8")
    kept_dir = tmp_path / "kept"
    kept_dir.mkdir()
    (kept_dir / "kept.py").write_text("role = 'admin'\n", encoding="utf-8")

    visited_dirpaths: list[str] = []
    real_walk = os.walk

    def spying_walk(root, *args, **kwargs):
        for dirpath, dirnames, filenames in real_walk(root, *args, **kwargs):
            visited_dirpaths.append(dirpath)
            yield dirpath, dirnames, filenames

    monkeypatch.setattr(sys.modules[__name__], "BACKEND_ROOT", tmp_path)
    monkeypatch.setattr(os, "walk", spying_walk)

    files = list(_python_files())

    assert str(skip_dir) not in visited_dirpaths, (
        f"os.walk descended into {skip_dir}, a directory in SKIP_DIR_PARTS -- "
        "pruning must mutate `dirnames` in place BEFORE the walk continues past "
        "it, not filter the results afterward (#16601). A post-hoc filter would "
        "leave this directory out of the returned files just the same, which is "
        "exactly the negative-control gap this test closes."
    )
    assert files == [kept_dir / "kept.py"], (
        "the sentinel file under the SKIP_DIR_PARTS directory must never reach " "the returned generator either"
    )
