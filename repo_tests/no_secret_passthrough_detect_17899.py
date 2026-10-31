# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The third verdict for the response-model secret guard: UNVERIFIABLE (#17899).

The guard in ``no_secret_in_response_model_17865_test.py`` matches secret-shaped
names among a model's **declared** fields. A model that declares nothing and
allows extras has no field names to match, so the route passes — while the
serialised response may carry any field at all, including a provider key:

```python
class LLMConfigResponse(BaseModel):
    \"\"\"Response for GET /llm/config — provider-specific shape, extra fields allowed.\"\"\"

    model_config = {"extra": "allow"}
```

**Ask what a PASS licenses there and the answer is nothing.** For a
declared-field model a pass means "no field is secret-shaped". For a
pass-through it means "this model declares no fields", which is true of every
pass-through and says nothing about what the endpoint returns. That is a
different claim wearing the same green, which is the exact shape
MEASUREMENT_DISCIPLINE.md calls family F.

So this is a THIRD verdict, not a violation. The guard cannot say whether such
a route carries a secret, and "cannot say" must not read as "does not".

WHICH DEFINITION SITE COUNTS, and why the rule is what it is.
The index in the guard is keyed by bare class name across all three trees, so
two classes that share a name are merged. ``LLMConfigResponse`` exists twice —
``autobot-backend/api/schemas_agent.py`` (a pass-through) and
``autobot-slm-backend/api/llm_config.py`` (which declares ``config:
LLMConfig``) — and the merge is why the *existing* baseline carries four
entries against ``autobot-backend/api/llm.py`` naming fields that model does
not declare. That conflation is a real defect in the index and is tracked
separately (#17935); it is NOT fixed here, because fixing it means resolving
imports and that changes the violation path too.

What this module does instead is resolve per route, with a rule that degrades
honestly:

* the route's OWN file defines a class of that name -> judge that one;
* otherwise -> every definition site, and if ANY is a pass-through the route
  is unverifiable.

The fallback over-reports when a name is reused, and that is correct for a
verdict that means "cannot say": if two classes share a name and one is a
pass-through, the guard genuinely cannot tell which one the route returns.
Over-reporting a *violation* would be wrong; over-reporting *uncertainty* is
what uncertainty is.
"""

from __future__ import annotations

import ast

#: Field-less + extras-allowed is the shape. Both spellings Pydantic v2 accepts
#: are matched -- a dict literal and ``ConfigDict(...)`` -- plus the v1
#: ``class Config:`` form, because a model written in the old style is no less
#: a pass-through for it.
_ALLOW = "allow"


def _config_value_allows_extra(value: ast.expr) -> bool:
    """True when a ``model_config`` value sets ``extra`` to ``"allow"``.

    Walks the value rather than matching a shape: ``{"extra": "allow"}``,
    ``ConfigDict(extra="allow")`` and ``{**BASE, "extra": "allow"}`` are three
    spellings of one decision, and enumerating spellings is how the #13841
    guards came to match one of six (#17891).

    The looseness is bounded by what it is used for. A false positive here
    costs one extra "cannot say" entry in a record; a false negative costs a
    route that reads as audited and was not.
    """
    for node in ast.walk(value):
        if isinstance(node, ast.Constant) and node.value == _ALLOW:
            return True
    return False


def declares_extra_allow(node: ast.ClassDef) -> bool:
    """True when *node* permits undeclared fields in its serialised output."""
    for stmt in node.body:
        target = value = None
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            target, value = stmt.targets[0].id, stmt.value
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            target, value = stmt.target.id, stmt.value
        if target == "model_config" and value is not None and _config_value_allows_extra(value):
            return True
        if isinstance(stmt, ast.ClassDef) and stmt.name == "Config" and _config_value_allows_extra(stmt):
            return True
    return False


def declared_field_names(node: ast.ClassDef) -> list[str]:
    """The annotated attribute names *node* declares, in source order."""
    return [s.target.id for s in node.body if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)]


def is_passthrough(node: ast.ClassDef) -> bool:
    """A model that declares NO fields and permits any — nothing to match on."""
    return declares_extra_allow(node) and not declared_field_names(node)


def _sites_for(model: str, route_file: str, defined_in: dict[str, list[str]]) -> list[str]:
    """Definition sites to judge *model* by, from the route in *route_file*.

    Same file first. The fallback is deliberately every site; see the module
    docstring for why over-reporting uncertainty is the correct direction.
    """
    sites = defined_in.get(model, [])
    own = [rel for rel in sites if rel == route_file]
    return own or sites


def unverifiable_routes(idx) -> list[tuple[str, int, str, str]]:
    """``(file, line, "METHOD /path", model)`` for every pass-through route.

    Sorted and de-duplicated so the list is a comparable record rather than an
    index-order accident.
    """
    out = set()
    for route in idx.routes:
        sites = _sites_for(route.model, route.file, idx.defined_in)
        if any((rel, route.model) in idx.passthrough for rel in sites):
            out.add((route.file, route.line, f"{route.method} {route.path}".strip(), route.model))
    return sorted(out)


def record_keys(idx) -> set[tuple[str, str, str]]:
    """The route-keyed form stored in the frozen record — no line numbers.

    A line number moves whenever anything above the decorator is edited, so
    keying the record by it would turn every unrelated edit into a record
    churn and train the reader to re-freeze without looking.
    """
    return {(rel, route, model) for rel, _line, route, model in unverifiable_routes(idx)}
