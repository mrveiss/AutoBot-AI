# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A request model must not declare a field its handler never reads (#15966).

``POST /heartbeat/report`` took a ``HeartbeatReport`` declaring
``duration_seconds``, ``tokens_in``, ``tokens_out`` and ``model``. Its handler
read none of them. The route accepted them, returned ``200``, and discarded all
four on every call.

**Why that is worse than an unused field.** The schema is the promise. An agent
reporting its cost got a success response and had no way to learn that four of
its seven fields were dropped — a ``200`` that stored something is
indistinguishable from a ``200`` that stored four fields fewer. There was no
threshold and no ordering: it failed on every single call.

**The route had already been hardened against exactly this.** Its docstring
records that the stub *"echoed the caller's own run_id back, so a client reading
the response saw its input and concluded the write had happened"*, and that
``recorded`` is now an UPDATE's rowcount rather than a constant (#15859). The
author identified a success response the client could not distinguish from a
real write, fixed it for ``run_id``, and left four sibling fields on the same
model silently dropped. The fix and the bug were in the same function, which is
why a guard belongs here rather than a second reading of that file.

**Why this checks reads rather than storage.** Asserting "the field reaches the
database" would pass for a field written to a column nothing queries. Asserting
the handler *reads* it is the weaker claim that is actually checkable from
source, and it is the one that fails for the defect above. A field the handler
reads and then discards is still possible and is not caught here; that is a
narrower hole than the one being closed.

The parse is deliberately shallow — it looks for ``body.<field>`` in the
function that takes the model. A handler that unpacks the model differently
(``**body.model_dump()``, a helper taking the whole object) would read as
unused, so such a model is skipped explicitly rather than reported: see
``_HANDLER_READS_WHOLE_MODEL``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ._paths import repo_root

MODULE = repo_root() / "autobot-backend" / "llc" / "api" / "agent_api.py"

# Models whose handler consumes the object as a whole, so per-field reads are not
# visible to this check. Each entry needs a reason, so the list cannot quietly
# become the place a defect is hidden.
_HANDLER_READS_WHOLE_MODEL: dict[str, str] = {}

# Known-unread fields, each tracked by an issue. This is a RATCHET, not an
# exemption list: `test_known_unread_entries_are_still_unread` fails when one is
# fixed, forcing its removal here in the same PR. An exemption list that only
# ever grows is where this defect would hide, which is the thing being guarded.
_KNOWN_UNREAD: dict[str, tuple[str, str]] = {
    # #16017 removed: StatusUpdate.comment now reaches `add_comment` in the same
    # commit as the transition. The ratchet worked as designed -- wiring the field
    # failed this test, which is what forced the entry out in the same PR.
    "CostEvent": ("work_item_id", "#16016"),
}


def _module() -> ast.Module:
    if not MODULE.exists():
        pytest.skip(f"{MODULE} not present in this checkout")
    return ast.parse(MODULE.read_text(encoding="utf-8"))


def _model_fields(tree: ast.Module) -> dict[str, list[str]]:
    """Field names per BaseModel subclass defined in the module."""
    models: dict[str, list[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(isinstance(b, ast.Name) and b.id == "BaseModel" for b in node.bases):
            continue
        models[node.name] = [
            stmt.target.id
            for stmt in node.body
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
        ]
    return models


def _handlers_by_model(tree: ast.Module) -> dict[str, ast.AST]:
    """The function taking each model, keyed by model name.

    Matches the parameter *annotation*, so it finds the handler regardless of
    what the parameter is called.
    """
    handlers: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for arg in node.args.args:
            if isinstance(arg.annotation, ast.Name):
                handlers.setdefault(arg.annotation.id, node)
    return handlers


def _read_attributes(func: ast.AST) -> set[str]:
    return {
        node.attr
        for node in ast.walk(func)
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
    }


def _cases() -> list[tuple[str, list[str], ast.AST]]:
    tree = _module()
    handlers = _handlers_by_model(tree)
    return [
        (name, fields, handlers[name])
        for name, fields in _model_fields(tree).items()
        if name in handlers and name not in _HANDLER_READS_WHOLE_MODEL
    ]


@pytest.mark.parametrize("model,fields,handler", _cases(), ids=lambda v: v if isinstance(v, str) else "")
def test_every_declared_field_is_read_by_its_handler(
    model: str, fields: list[str], handler: ast.AST
) -> None:
    """A declared field the handler never reads is a promise the API does not keep."""
    read = _read_attributes(handler)
    known = _KNOWN_UNREAD.get(model)
    unread = [f for f in fields if f not in read and not (known and f == known[0])]
    assert not unread, (
        f"{model} declares {unread} which {getattr(handler, 'name', '?')}() never reads. "
        "The route will accept them and answer 200 while discarding them, and the caller "
        "cannot tell that from a 200 that stored them. Either read the field, or remove it "
        "from the model and point callers at the route that does own it. If the handler "
        "consumes the model as a whole, add it to _HANDLER_READS_WHOLE_MODEL with a reason."
    )


def test_the_sweep_actually_found_models_to_check() -> None:
    """Guard the guard: a parse that silently matches nothing passes vacuously.

    #15966 was a field nobody read. A test that checks no fields at all is the
    same failure one layer up — green, and covering nothing.
    """
    cases = _cases()
    assert cases, (
        f"no BaseModel/handler pairs found in {MODULE.name}; the AST match has probably "
        "gone stale and this suite is passing without checking anything"
    )
    assert any(fields for _, fields, _ in cases), "models found, but none declares a field"


@pytest.mark.parametrize("model,fields,handler", _cases(), ids=lambda v: v if isinstance(v, str) else "")
def test_known_unread_entries_are_still_unread(
    model: str, fields: list[str], handler: ast.AST
) -> None:
    """A tracked field that starts being read must leave `_KNOWN_UNREAD`.

    Without this, the dict above is an exemption list — it would silently keep
    covering a field long after the defect was fixed, and the next real
    occurrence on that model would be invisible. Failing here is the whole point:
    it costs one line in the PR that fixes the issue, and it means the list can
    only shrink.
    """
    known = _KNOWN_UNREAD.get(model)
    if known is None:
        pytest.skip(f"{model} has no tracked unread field")
    field, issue = known
    if field not in fields:
        pytest.fail(
            f"{model}.{field} no longer exists; remove its _KNOWN_UNREAD entry ({issue})"
        )
    assert field not in _read_attributes(handler), (
        f"{model}.{field} is now read by {getattr(handler, 'name', '?')}() — {issue} appears "
        f"to be fixed. Remove the _KNOWN_UNREAD entry so the model is fully guarded again."
    )
