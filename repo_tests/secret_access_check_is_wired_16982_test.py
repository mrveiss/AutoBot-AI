# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A secret-access rule may not exist only in code no production path calls (#16982).

`Secret.is_accessible_by` models secret access over owner, org, team and scope plus
a session/`shared_with` grant lookup, and its only callers are its own tests. So a
reader concludes the secrets rules live there; they do not, and a change to it
changes nothing that ships. #16927's owner ruling first drafted it as "the real
access check" for secrets, which is the misreading this guard exists to prevent.

## Why the assertion is a disjunction

#16982 offers two dispositions — wire it into the read path, or retire it in favour
of the vault grant — and this test deliberately does not prefer one. The invariant
that matters under either is:

    the symbol is referenced from at least one non-test production module,
    OR it does not exist

Written as a disjunction so the guard survives the decision instead of having to be
rewritten by it. It fails in exactly one state: **defined and unwired**, which is
today's. A guard that encoded the fix would have to be edited to permit the fix,
and a guard edited to permit what it forbids is the shape
`MEASUREMENT_DISCIPLINE.md` warns about — #17650 is an open instance.

## Why it searches for the symbol rather than counting call sites

A control reached through a shared helper looks uncalled to a grep of its own name,
which is how "no production caller" claims go wrong. The check here is deliberately
weak in the permissive direction: **any** production reference satisfies it,
including one inside a helper that forwards. It answers "is this reachable from
shipped code at all", not "is it correctly enforced" — the second needs a test of
the read path, not a reachability sweep.

The complement of that weakness is what makes a failure meaningful: if not even a
mention exists outside the tests, the rule cannot be running.

## Why it is an AST walk and not a text search (#17822)

Through #17772 the finder was ``if _SYMBOL not in source`` -- raw text over the
whole file, docstrings and comments included. The owner stated the mutation on
#16982 on 2026-09-29: **put ``return True`` above the real call site and leave the
sentence that describes it, and this guard stays green while the access check is
gone.** That is the exact state #16982 exists to end, inside the guard asserting
#16982 was delivered.

A docstring is an ``ast.Constant`` in statement position and a comment is not in
the tree at all, so neither can ever be an ``ast.Name``, ``ast.Attribute`` or
``ast.alias``. Walking the tree separates prose from code by construction rather
than by a heuristic that has to be kept ahead of how people write comments.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

_SYMBOL = "is_accessible_by"

#: Where the definition lives today. If it moves, the finder below still locates it
#: — this is the hint for the failure message, not the search.
_DEFINING_MODULE = "autobot-backend/models/secret.py"

#: Production trees. `repo_tests/` is absent on purpose: a reference from a guard is
#: not a production caller, and counting one would let this test satisfy itself.
_ROOTS = ("autobot-backend", "autobot_shared", "autobot-slm-backend")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_test_path(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name.endswith("_test.py") or name.startswith("test_") or "/tests/" in f"/{rel}"


def _production_modules() -> list[Path]:
    root = _repo_root()
    out: list[Path] = []
    for tree in _ROOTS:
        for path in sorted((root / tree).rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            if any(skip in rel for skip in ("__pycache__", "/.venv/", "/node_modules/")):
                continue
            if _is_test_path(rel):
                continue
            out.append(path)
    return out


#: Builtins that reach an attribute by name at runtime. A string argument to one
#: of these is a real reference; a string anywhere else may be a docstring, which
#: is the whole defect #17822 is about, so no other `ast.Constant` counts.
_FORWARDING_BUILTINS = frozenset({"getattr", "setattr", "hasattr", "delattr"})


def _parsed(path: Path) -> ast.AST | None:
    """The module tree, or None when it cannot be read or parsed."""
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _defines_symbol(path: Path, symbol: str = _SYMBOL) -> bool:
    """True if *path* defines *symbol* (as opposed to referencing it)."""
    tree = _parsed(path)
    if tree is None:
        return False
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == symbol for n in ast.walk(tree))


def _forwards_by_name(node: ast.Call, symbol: str) -> bool:
    """True for `getattr(obj, "symbol")` and its siblings.

    Only the **attribute-name position** counts. All four builtins take the name
    second, so `getattr("is_accessible_by", "other")` looks up `other` on a string
    that merely spells the symbol -- the constant is in the *object* position and
    is not a reference to anything. Scanning every argument made that a match.
    """
    func = node.func
    called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if called not in _FORWARDING_BUILTINS:
        return False
    if len(node.args) < 2:
        return False
    name_arg = node.args[1]
    return isinstance(name_arg, ast.Constant) and name_arg.value == symbol


#: Statements after which the rest of their own block cannot execute. A call
#: placed below one of these is dead code, so it is not evidence that anything
#: is wired -- and "return early, leave the call behind" is precisely the owner's
#: mutation this guard exists to catch.
_TERMINATORS = (ast.Return, ast.Raise, ast.Continue, ast.Break)


def _reachable_nodes(node: ast.AST) -> Iterator[ast.AST]:
    """Every node execution can reach, pruning each block after its terminator.

    This is deliberately *syntactic* reachability, not control-flow analysis:
    within one statement list nothing after a `return`/`raise`/`continue`/`break`
    can run, and that is the whole claim. It does not try to prove a branch is
    never taken -- an `if False:` body is still yielded -- because guessing in
    that direction drops real references, and a guard blind in the permissive
    direction is vacuous (`MEASUREMENT_DISCIPLINE.md`). Pruning applies per
    statement list, so code after `if cond: return` stays reachable, as it is.
    """
    yield node
    for _field, value in ast.iter_fields(node):
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, ast.AST):
                    continue
                yield from _reachable_nodes(item)
                if isinstance(item, _TERMINATORS):
                    break  # the rest of this block is unreachable
        elif isinstance(value, ast.AST):
            yield from _reachable_nodes(value)


def _references_symbol(path: Path, symbol: str = _SYMBOL) -> bool:
    """True if *path* uses *symbol* **as code** -- never because prose names it.

    The mechanisms a production reference can take are enumerated rather than
    guessed, because a control only ever witnesses the form it is written in
    (`MEASUREMENT_DISCIPLINE.md`: a control per mechanism, not per direction):

    * ``secret.is_accessible_by(...)``        -> `ast.Attribute.attr`
    * ``is_accessible_by(...)`` once imported -> `ast.Name.id`
    * ``from models.secret import is_accessible_by`` (or ``as``) -> `ast.alias`
    * ``getattr(secret, "is_accessible_by")`` -> a string argument to a
      forwarding builtin, which a docstring can never be

    A ``def``/``async def`` of the name is **not** a reference -- `_defines_symbol`
    answers that question, and a `FunctionDef` is neither a `Name` nor an
    `Attribute`, so the old "defines it and mentions it exactly once" arithmetic
    is no longer needed to subtract the definition out.
    """
    tree = _parsed(path)
    if tree is None:
        return False
    for node in _reachable_nodes(tree):
        if isinstance(node, ast.Name) and node.id == symbol:
            return True
        if isinstance(node, ast.Attribute) and node.attr == symbol:
            return True
        if isinstance(node, ast.alias) and symbol in (node.asname, node.name.rsplit(".", 1)[-1]):
            return True
        if isinstance(node, ast.Call) and _forwards_by_name(node, symbol):
            return True
    return False


@pytest.fixture(scope="module")
def modules() -> list[Path]:
    found = _production_modules()
    # Non-vacuity: an empty or tiny sweep would satisfy every assertion below by
    # finding nothing. `MEASUREMENT_DISCIPLINE.md` -- nothing found and did not look
    # must not read alike.
    assert len(found) > 500, f"only {len(found)} production modules swept -- the roots or filters are wrong"
    return found


def test_the_access_check_is_wired_into_production_or_absent(modules: list[Path]) -> None:
    """#16982: defined-and-unwired is the one state that fails."""
    root = _repo_root()
    definers = [p for p in modules if _defines_symbol(p)]
    referencers = [p for p in modules if _references_symbol(p)]

    if not definers:
        return  # disposition (b): retired. The rule no longer claims to exist.

    assert referencers, (
        f"`{_SYMBOL}` is defined in "
        f"{', '.join(p.relative_to(root).as_posix() for p in definers)} "
        "and referenced by no production module -- only by its own tests.\n"
        "A secret-access rule that no shipped path calls decides nothing, while reading "
        "as the place the rules live (#16982, and #16927's ruling first drafted it as "
        '"the real access check").\n'
        "Resolve by either wiring it into the secret read path beside the vault-grant "
        "check, or retiring it in favour of that check and moving its tests to the "
        "semantics they were really about. This guard accepts either."
    )


def test_the_sweep_would_notice_a_reference(modules: list[Path]) -> None:
    """The assertion above passes trivially if `_references_symbol` never matches.

    Proves the finder works by pointing it at a symbol that *is* production-wired:
    `is_visible`, the shared scoping primitive `is_accessible_by` delegates to, which
    `knowledge/ownership.py` calls. If this fails, the sweep is broken and the test
    above is not evidence of anything.
    """
    root = _repo_root()
    hits = [p for p in modules if _references_symbol(p, "is_visible")]
    assert len(hits) >= 2, (
        "the reference finder located fewer than 2 production modules mentioning "
        f"`is_visible`, which is wired -- the sweep is broken, not the codebase. Found: "
        f"{[p.relative_to(root).as_posix() for p in hits]}"
    )


# --- #17822: the contrast pair the raw-text finder could not state -------------
#
# Each fixture is a module the finder is pointed at directly, so the pair tests
# the INSTRUMENT rather than the tree. The two halves are written to differ in
# exactly one way -- whether the symbol appears in code or only in prose -- so a
# finder that cannot tell them apart fails one of them whichever way it is wrong.

#: The owner's mutation, verbatim in shape (#16982, 2026-09-29): the real call
#: replaced by `return True`, with the docstring and comment that describe it left
#: in place. Under the old `if _SYMBOL not in source` this module was a
#: "production caller" and the guard stayed green with the access check deleted.
_PROSE_ONLY = '''"""Scope pre-check.

Mirrors `Secret.is_accessible_by`: the model says whether this secret's scope
admits the principal, and this narrows it to the envelope rows.
"""


def scope_permits(secret, facts):
    # is_accessible_by used to be consulted here; see #16982.
    return True
'''

#: The same module with the call restored. Nothing else differs.
_REAL_CALL = '''"""Scope pre-check.

Mirrors `Secret.is_accessible_by`.
"""


def scope_permits(secret, facts):
    return secret.is_accessible_by(facts.user_id)
'''

#: Reference mechanisms that are not an attribute access. Enumerated because a
#: control witnesses only the shape it is written in.
_BARE_NAME = "from models.secret import is_accessible_by\n\n\ndef f(s, u):\n    return is_accessible_by(s, u)\n"
_IMPORT_ONLY = "from models.secret import is_accessible_by  # re-exported\n"
_RENAMED_IMPORT = "from models.secret import is_accessible_by as _check\n"
_GETATTR = 'def f(s, u):\n    return getattr(s, "is_accessible_by")(u)\n'

#: Dead-code shapes. The symbol is present *as code* and still proves nothing,
#: because execution cannot reach it. These are not prose, so comment-stripping
#: would not catch them -- only reachability does.
_UNREACHABLE_AFTER_RETURN = """def scope_permits(secret, facts):
    return True
    return secret.is_accessible_by(facts.user_id)
"""
_UNREACHABLE_AFTER_RAISE = """def scope_permits(secret, facts):
    raise NotImplementedError
    return secret.is_accessible_by(facts.user_id)
"""

#: The symbol in the *object* position of a forwarding builtin. `other` is the
#: attribute actually looked up; the constant only spells our symbol.
_GETATTR_OBJECT_POSITION = 'def f():\n    return getattr("is_accessible_by", "other")\n'

#: Reachable despite an early return above it -- the control for the pruning.
#: Without this, `_reachable_nodes` could prune whole functions and the
#: dead-code pair above would still pass.
_CALL_AFTER_CONDITIONAL_RETURN = """def scope_permits(secret, facts):
    if facts is None:
        return False
    return secret.is_accessible_by(facts.user_id)
"""
_CALL_AFTER_A_SIBLING_FUNCTION_RETURNS = """def unrelated():
    return True


def scope_permits(secret, facts):
    return secret.is_accessible_by(facts.user_id)
"""

#: Prose-only shapes other than a module docstring.
_COMMENT_ONLY = "# TODO(#16982): call is_accessible_by here.\ndef f(s, u):\n    return True\n"
_FUNCTION_DOCSTRING_ONLY = 'def f(s, u):\n    """Equivalent to is_accessible_by."""\n    return True\n'
_PLAIN_STRING_ONLY = 'MESSAGE = "is_accessible_by refused this secret"\n'


def _module(tmp_path: Path, name: str, source: str) -> Path:
    path = tmp_path / f"{name}.py"
    path.write_text(source, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "label,source",
    [
        ("the owner's return-True mutation with the docstring left behind", _PROSE_ONLY),
        ("a comment only", _COMMENT_ONLY),
        ("a function docstring only", _FUNCTION_DOCSTRING_ONLY),
        ("a plain string literal only", _PLAIN_STRING_ONLY),
    ],
)
def test_prose_alone_is_not_a_reference(tmp_path: Path, label: str, source: str) -> None:
    """#17822 half one: a module whose only mention is prose must NOT match."""
    assert not _references_symbol(_module(tmp_path, "prose", source)), (
        f"`{_SYMBOL}` appearing as {label} was counted as a production reference. "
        "That is the #17822 defect: the guard then passes with the access check deleted."
    )


@pytest.mark.parametrize(
    "label,source",
    [
        ("an attribute call", _REAL_CALL),
        ("a bare name after `from ... import`", _BARE_NAME),
        ("an import with no call in this module", _IMPORT_ONLY),
        ("an aliased import", _RENAMED_IMPORT),
        ("a getattr forward", _GETATTR),
        ("a call below an early return in a branch", _CALL_AFTER_CONDITIONAL_RETURN),
        ("a call in a function after a sibling function returns", _CALL_AFTER_A_SIBLING_FUNCTION_RETURNS),
    ],
)
def test_real_code_is_a_reference(tmp_path: Path, label: str, source: str) -> None:
    """#17822 half two: the finder must still see every way code reaches it.

    Without this half the fix could be `return False` and the pair above would
    pass -- the cheapest way to satisfy a check is to delete what it measured.
    """
    assert _references_symbol(_module(tmp_path, "code", source)), (
        f"`{_SYMBOL}` reached by {label} was not counted. The finder is now blind in "
        "the permissive direction, which makes the wiring assertion vacuous."
    )


@pytest.mark.parametrize(
    "label,source",
    [
        ("a call below a bare `return`", _UNREACHABLE_AFTER_RETURN),
        ("a call below a `raise`", _UNREACHABLE_AFTER_RAISE),
        ("the symbol in a forwarding builtin's object position", _GETATTR_OBJECT_POSITION),
    ],
)
def test_code_that_cannot_run_is_not_a_reference(tmp_path: Path, label: str, source: str) -> None:
    """A third way to be present without being wired, after prose and definition.

    Stripping comments does not catch these: the symbol really is in the AST as
    code. Only reachability (and, for the last one, argument position) separates
    "the call is there" from "the call happens". The first two are the owner's
    #17822 mutation in its most faithful form -- return early, leave the call
    sitting underneath -- which the comment-stripping fix would have passed.
    """
    assert not _references_symbol(_module(tmp_path, "dead", source)), (
        f"`{_SYMBOL}` reached only as {label} was counted as a production reference. "
        "Execution never gets there, so the wiring assertion it satisfies is vacuous."
    )


def test_the_pair_differs_only_in_prose_versus_code(tmp_path: Path) -> None:
    """Pins the discrimination itself, not the two halves separately.

    Both fixtures contain the literal text `is_accessible_by`; a raw-text finder
    returns True for both and this assertion is the one it cannot satisfy.
    """
    prose = _module(tmp_path, "prose_half", _PROSE_ONLY)
    code = _module(tmp_path, "code_half", _REAL_CALL)
    assert _SYMBOL in prose.read_text(encoding="utf-8"), "fixture is not a contrast pair"
    assert _SYMBOL in code.read_text(encoding="utf-8"), "fixture is not a contrast pair"
    assert [_references_symbol(prose), _references_symbol(code)] == [False, True]


def test_a_definition_alone_is_not_a_reference(tmp_path: Path) -> None:
    """`models/secret.py` defines it and calls nothing -- it must not satisfy the sweep."""
    definition = _module(
        tmp_path,
        "definition",
        f"class Secret:\n    def {_SYMBOL}(self, user_id):\n        return False\n",
    )
    assert _defines_symbol(definition)
    assert not _references_symbol(definition)
