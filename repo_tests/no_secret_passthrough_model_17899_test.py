# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A field-less, extras-allowed response model is UNVERIFIABLE, not clean (#17899).

``no_secret_in_response_model_17865_test.py`` matches secret-shaped names among
a model's **declared** fields. A model that declares nothing and sets
``extra: "allow"`` offers nothing to match, so the route passed — while the
serialised response may carry any field, including a provider key. Ask what
that pass licenses and the answer is nothing: it means "this model declares no
fields", which is true of every pass-through.

This file adds the third verdict and the controls that make it mean something:

* a CONTRAST PAIR per shape, so the detector is shown rejecting as well as
  accepting;
* a SUBJECT control — a model that has the property the verdict names
  (undeclared output) without the spelling the code looks for — pinned as a
  documented limit rather than left for a reader to discover;
* a REACH FLOOR, so an empty unverifiable set cannot read as "every route is
  auditable";
* a shrink-only record, so a NEW pass-through route fails.

Detection lives in ``no_secret_passthrough_detect_17899.py`` and the record in
``no_secret_passthrough_routes_17899.py``: the guard file is at its 600-line
ceiling and the ceiling is split, not raised.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests.no_secret_in_response_model_17865_test import _build_index, _index
from repo_tests.no_secret_passthrough_detect_17899 import (
    declares_extra_allow,
    is_passthrough,
    record_keys,
    unverifiable_routes,
)
from repo_tests.no_secret_passthrough_routes_17899 import (
    MIN_ROUTES_INDEXED,
    PASSTHROUGH_FROZEN_AT,
    PASSTHROUGH_ROUTES,
)

_ROOT = repo_root()

#: The motivating route, named rather than described. `LLMConfigResponse` in
#: `autobot-backend/api/schemas_agent.py` declares nothing and allows extras;
#: `autobot-backend/api/llm.py` returns it from `GET /config`.
_MOTIVATING = ("autobot-backend/api/llm.py", "GET /config", "LLMConfigResponse")


# --------------------------------------------------------------------------
# the guard
# --------------------------------------------------------------------------


def test_no_new_passthrough_response_model_has_landed():
    """The ratchet. A route the record does not name must declare its fields."""
    found = record_keys(_index())
    new = sorted(found - PASSTHROUGH_ROUTES)
    assert not new, (
        "response model(s) declare no fields and allow extras, so this guard cannot say "
        "whether the route returns a credential — which is NOT the same as saying it does "
        "not. Declare the fields, or (only for a genuinely provider-shaped payload) add the "
        "route to no_secret_passthrough_routes_17899.py with the reason in the commit:\n"
        + "\n".join(f"  {rel} [{route}] response_model={model}" for rel, route, model in new)
    )


def test_every_recorded_passthrough_still_describes_a_real_route():
    """Shrink-only. An entry that stopped firing was fixed or moved — delete it.

    Without this the record becomes a permanent exemption: the next route to
    land on the same (file, path, model) triple inherits a pass granted for a
    model that has since declared its fields.
    """
    stale = sorted(PASSTHROUGH_ROUTES - record_keys(_index()))
    assert (
        not stale
    ), "recorded pass-through route(s) no longer fire — remove them, the record only " "turns down:\n" + "\n".join(
        f"  {entry}" for entry in stale
    )


def test_the_record_is_not_silently_growing():
    """Pins the size, so admitting a route is a visible decision, not a diff line."""
    assert len(PASSTHROUGH_ROUTES) <= PASSTHROUGH_FROZEN_AT, (
        f"the pass-through record grew to {len(PASSTHROUGH_ROUTES)}, over the frozen "
        f"{PASSTHROUGH_FROZEN_AT}. It may only shrink — a new pass-through means the model "
        "should declare its fields, not that the guard should stop asking."
    )


def test_the_motivating_route_is_actually_caught():
    """#17899's own example, asserted by name rather than trusted to the count.

    A record of 174 entries passes its ratchet whether or not it contains the
    one route the issue was filed about, and that route is the reason the
    verdict exists. Pinned so a resolution change that silently drops it fails
    here instead of reading as a shrink.
    """
    assert _MOTIVATING in record_keys(_index()), (
        "GET /api/llm/config returns LLMConfigResponse, which declares no fields and "
        "allows extras — the shape #17899 was filed about. If this stopped firing, check "
        "whether the model now declares its fields (good) or whether resolution changed "
        "and the route is simply unseen again (not good)."
    )


def test_the_sweep_reaches_enough_files_to_mean_something():
    """A floor: an empty unverifiable set must mean 'looked', not 'did not look'.

    MEASURED ON REACH, NOT ON FINDINGS (CodeRabbit, #17899). This counted the
    files that produced a finding, so the number it guarded went DOWN as the
    routes got fixed -- draining them would have tripped the floor and reported
    "a broken detector" about a sweep that worked and a tree that improved. It
    also could not see the failure it exists for: a detector that stopped
    parsing most of the tree still clears a findings floor on a few hits.

    `idx.routes` is what the sweep actually examined, and it does not move when
    a route is repaired.
    """
    idx = _index()
    assert len(idx.routes) >= MIN_ROUTES_INDEXED, (
        f"the pass-through sweep indexed only {len(idx.routes)} route(s) across "
        f"{len(idx.files)} file(s), under the {MIN_ROUTES_INDEXED}-route floor. An "
        "unverifiable set computed from a sweep this small is a broken detector "
        "reported as a clean tree."
    )


# --------------------------------------------------------------------------
# contrast pairs — each runs the WHOLE detector over a fixture tree
# --------------------------------------------------------------------------

_ROUTE = "@router.get('/x', response_model=Shape)\ndef h(): ...\n"

#: `(name, files, expect_unverifiable)`. Every positive is paired with a twin
#: differing by ONE token, so a fixture cannot pass by being structurally
#: unlike the thing it contrasts with.
_FIXTURES = [
    (
        # THE #17899 SHAPE, spelled as a dict literal.
        "passthrough-dict-literal",
        'class Shape(BaseModel):\n    model_config = {"extra": "allow"}\n',
        True,
    ),
    (
        # The SAME model with one declared field is auditable again.
        "declared-field-with-extra-allow",
        'class Shape(BaseModel):\n    model_config = {"extra": "allow"}\n    name: str\n',
        False,
    ),
    (
        # ConfigDict() rather than a dict literal — one decision, two spellings.
        "passthrough-configdict",
        'class Shape(BaseModel):\n    model_config = ConfigDict(extra="allow")\n',
        True,
    ),
    (
        # The TWIN for the spelling above: one token, "allow" -> "forbid".
        # Without it the ConfigDict positive was witnessed only against the
        # dict-literal twin, so the detector could have been keyed on the
        # SPELLING rather than on the decision (CodeRabbit, #17899).
        "configdict-extras-forbidden",
        'class Shape(BaseModel):\n    model_config = ConfigDict(extra="forbid")\n',
        False,
    ),
    (
        # The pydantic v1 inner class. A model written in the old style is no
        # less a pass-through for it.
        "passthrough-inner-config-class",
        'class Shape(BaseModel):\n    class Config:\n        extra = "allow"\n',
        True,
    ),
    (
        # The TWIN for the v1 spelling, same one-token difference.
        "inner-config-class-extras-forbidden",
        'class Shape(BaseModel):\n    class Config:\n        extra = "forbid"\n',
        False,
    ),
    (
        # extra FORBIDDEN and no fields: nothing can travel, so nothing to say.
        "fieldless-but-extras-forbidden",
        'class Shape(BaseModel):\n    model_config = {"extra": "forbid"}\n',
        False,
    ),
    (
        # No model_config at all. Pydantic's default IGNORES extras.
        "fieldless-with-no-config",
        "class Shape(BaseModel):\n    pass\n",
        False,
    ),
]


@pytest.mark.parametrize("name,model_src,expect", _FIXTURES, ids=[f[0] for f in _FIXTURES])
def test_the_detector_end_to_end(tmp_path, name, model_src, expect):
    """Drives `_build_index` + `unverifiable_routes`, not just the shape matcher.

    The repository only ever supplies the detector with trees it already
    agrees with, so without these a refactor that broke route discovery or the
    site resolution would leave every assertion above passing on an empty set.
    """
    tree = _fixture_tree(tmp_path, {"autobot-slm-backend/api/r.py": model_src + _ROUTE})
    hits = unverifiable_routes(_build_index(tree))
    assert bool(hits) is expect, f"{name}: expected unverifiable={expect}, got {hits}"


def _fixture_tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, src in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(src, encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------
# site resolution — the half that decides WHICH class a route returns
# --------------------------------------------------------------------------


def test_a_same_named_declared_model_in_the_routes_own_file_wins(tmp_path):
    """Same file beats a same-named pass-through in another module.

    This is what keeps `autobot-slm-backend/api/llm_config.py` out of the
    record: it defines its OWN `LLMConfigResponse` with a declared `config`
    field, and the guard can rule on that one.
    """
    tree = _fixture_tree(
        tmp_path,
        {
            "autobot-backend/api/schemas.py": 'class Shape(BaseModel):\n    model_config = {"extra": "allow"}\n',
            "autobot-slm-backend/api/r.py": "class Shape(BaseModel):\n    name: str\n" + _ROUTE,
        },
    )
    assert unverifiable_routes(_build_index(tree)) == []


def test_an_imported_ambiguous_name_is_reported_rather_than_guessed(tmp_path):
    """The fallback direction, pinned: ambiguity resolves to 'cannot say'.

    The route's file defines nothing, two other modules each define the name,
    and one of them is a pass-through. Guessing the safe one would be a verdict
    the guard has not earned.
    """
    tree = _fixture_tree(
        tmp_path,
        {
            "autobot-backend/api/schemas.py": 'class Shape(BaseModel):\n    model_config = {"extra": "allow"}\n',
            "autobot-slm-backend/models/s.py": "class Shape(BaseModel):\n    name: str\n",
            "autobot-slm-backend/api/r.py": _ROUTE,
        },
    )
    assert len(unverifiable_routes(_build_index(tree))) == 1


# --------------------------------------------------------------------------
# the SUBJECT control — the limit, stated rather than discovered later
# --------------------------------------------------------------------------


def test_an_untyped_dict_field_is_not_caught_by_this_verdict(tmp_path):
    """THE SUBJECT CONTROL. It returns no hit, and that is the finding.

    `secret: Dict[str, Any]` has the property this verdict names — the guard
    cannot say what travels in it — while lacking the spelling the code checks
    (``extra: "allow"`` with no declared fields). So this verdict covers
    *pass-through models*, not *unauditable responses*, and the two are not the
    same set.

    Those routes are not unobserved: five of them are already in
    ``no_secret_in_response_model_baseline_17865.py`` as untyped-dict entries,
    which is a different record reached by a different mechanism. Pinned here
    so nobody reads this verdict as covering them.
    """
    tree = _fixture_tree(
        tmp_path,
        {
            "autobot-slm-backend/api/r.py": "class Shape(BaseModel):\n    secret: Dict[str, Any]\n" + _ROUTE,
        },
    )
    assert unverifiable_routes(_build_index(tree)) == []


def test_extra_allow_is_detected_independently_of_field_count():
    """The two halves of `is_passthrough` are separable, and must be.

    A model can allow extras AND declare fields; it is then auditable, and the
    existing matcher rules on it. Asserting only the conjunction would let a
    detector that ignored ``extra`` entirely pass every fixture above, because
    "declares no fields" alone already separates most of them.
    """
    with_fields = ast.parse('class S(BaseModel):\n    model_config = {"extra": "allow"}\n    a: str\n').body[0]
    assert declares_extra_allow(with_fields) is True
    assert is_passthrough(with_fields) is False
    bare = ast.parse("class S(BaseModel):\n    pass\n").body[0]
    assert declares_extra_allow(bare) is False
    assert is_passthrough(bare) is False
