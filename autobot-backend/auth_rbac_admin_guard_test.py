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

Adding ``superadmin``/``platform_admin`` to the shared ``Role`` enum is the
deeper fix and is still open on #12786 — that enum drives ``ROLE_PERMISSIONS``
for both backends, so it needs a cross-backend review rather than a drive-by.
"""

import ast
import functools
import pathlib

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


def _python_files():
    for path in BACKEND_ROOT.rglob("*.py"):
        if SKIP_DIR_PARTS & set(path.parts):
            continue
        if path.name.endswith("_test.py") or path.name.startswith("test_"):
            continue
        if path.name in EXEMPT_FILES:
            continue
        yield path


def _may_contain_offender(source: str) -> bool:
    """Cheap text prefilter: can *source* possibly hold an offending compare?

    ``_offenders_in`` only ever flags a comparison that pairs a ``role``-ish
    operand (name/attribute/subscript/kwarg all matched on the text ``role``)
    with one of :data:`ADMIN_ROLE_LITERALS` (all three contain ``admin``). A
    file whose source contains neither substring cannot produce a hit, so it
    never needs parsing.

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
        except (OSError, UnicodeDecodeError):
            continue
        if not _may_contain_offender(source):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for line in _offenders_in(tree):
            offenders.append(f"{path.relative_to(BACKEND_ROOT)}:{line}")
    return tuple(sorted(offenders))


def test_no_hand_rolled_admin_role_comparisons():
    """Use ``is_admin_role()`` instead — it admits superadmin, as guards do."""
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
