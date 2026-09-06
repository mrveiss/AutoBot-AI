# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Wrong-node cleanup: the gate, and the token it reads (#14856, #15822).

Split from ``test_cleanup_never_destroys_data_14856.py``, which is grandfathered
at 1006 lines and may not grow — an exemption freezes the size it was granted
for, it does not license more (#14236). The #15822 scenarios pushed it to 1193.

The cut is a concern, not an arithmetic trim: everything here is about the
*wrong-node* branch — whether the role-active fact survives ``set_fact``
coercion, and whether the gate takes the right branch for each spelling of it.
The parent file keeps the removal primitive, the delegation checks and the
legacy-retirement migration.

Helpers are imported rather than copied. Two copies of a simulation harness
drift, and the copy that drifts still passes — the failure this whole suite
exists to prevent, one level up.
"""

from __future__ import annotations

import json
from typing import Any

import jinja2
import pytest
from test_cleanup_never_destroys_data_14856 import (
    _WRONG_NODE,
    _and,
    _ansible_bool,
    _apply_set_fact,
    _FactUndefined,
    _load,
    _module,
    _primitive_when,
    _stat,
    _wrong_node_normalise,
    _wrong_node_when,
)

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
# #15822: the token the gate reads must survive set_fact, whatever its spelling
# --------------------------------------------------------------------------
def _leaves(node: Any, path: tuple = ()):
    """Every scalar in a set_fact argument tree, with the path that reaches it."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _leaves(value, path + (index,))
    else:
        yield path, node


def _token_path() -> tuple:
    """Where the normalise step puts the role fact — found by content, not by name.

    The gate could spell its token `_wrong_node_fact`, `_wrong_node.token` or
    anything else; what identifies it is that it is the leaf built from
    `lookup('vars', role_check_fact, ...)`. Locating it this way means these
    tests keep testing the real thing after a rename, instead of silently
    asserting about a variable that no longer exists.
    """
    spec = _module(_wrong_node_normalise(), "ansible.builtin.set_fact", "set_fact")
    assert spec, "the normalise step is not a set_fact task"
    found = [
        path
        for path, value in _leaves(spec)
        if isinstance(value, str) and "lookup(" in value and "role_check_fact" in value
    ]
    assert len(found) == 1, f"expected exactly one leaf reading the role fact, found {found}"
    return found[0]


def _at(container: Any, path: tuple) -> Any:
    for step in path:
        container = container[step]
    return container


def _set_at(container: Any, path: tuple, value: Any) -> None:
    for step in path[:-1]:
        container = container[step]
    container[path[-1]] = value


# Every spelling set_fact converts, in the case shapes group_vars actually uses.
_COERCED_FACTS = [
    pytest.param(False, id="yaml_bool_false"),
    pytest.param(True, id="yaml_bool_true"),
    pytest.param("false", id="string_false"),
    pytest.param("true", id="string_true"),
    pytest.param("no", id="string_no"),
    pytest.param("yes", id="string_yes"),
    pytest.param("FALSE", id="string_uppercase_false"),
    pytest.param("false\n", id="folded_scalar_false"),
]


@pytest.mark.parametrize("fact", _COERCED_FACTS)
def test_wrong_node_token_is_not_flattened_into_a_bool_by_set_fact(fact: Any) -> None:
    """#15822: the token the allowlists are compared against must stay a string.

    `set_fact` converts a TOP-LEVEL string argument rendering to
    'true'/'false'/'yes'/'no' straight back into a Python bool. A bool equals
    none of the false-token spellings, so the wrong-node gate stops matching and
    the cleanup goes silently dead — measured on the fleet as "not fired on any
    host since 2026-08-24" — while `| length` on the same value raises
    "object of type 'bool' has no len()" and aborts the run outright.

    Asserted on the type of the stored value rather than on the shape of the
    YAML, so any future arrangement that survives the coercion passes and any
    that does not fails.
    """
    scope: dict[str, Any] = {"role_check_fact": "role_backend_active", "role_backend_active": fact}
    _apply_set_fact(_wrong_node_normalise(), scope)
    stored = _at(scope, _token_path())
    assert isinstance(stored, str), (
        f"role_backend_active={fact!r} reached the gate as {stored!r} "
        f"({type(stored).__name__}). set_fact flattened the normalised token, so "
        f"every allowlist comparison below it is a bool-against-string mismatch."
    )


def _wrong_node_message() -> str:
    """The 'not decidable' message, which is the expression that actually raised."""
    tasks = [t for t in _load(_WRONG_NODE) if isinstance(t, dict)]
    debugs = [t for t in tasks if _module(t, "ansible.builtin.debug", "debug")]
    assert debugs, "clean_wrong_node_dir.yml no longer reports an undecidable fact"
    msg = _module(debugs[0], "ansible.builtin.debug", "debug").get("msg")
    assert isinstance(msg, str) and msg, "the undecidable branch has no message to render"
    return msg


def _render_message(text: str, scope: dict[str, Any]) -> str:
    env = jinja2.Environment(undefined=jinja2.ChainableUndefined, autoescape=False)
    env.filters["bool"] = _ansible_bool
    env.filters["to_json"] = json.dumps
    return env.from_string(text).render(**scope)


# (token the gate ends up holding, what the message must call it)
_MESSAGE_TOKENS = [
    pytest.param("", "undefined", id="empty_token_reads_as_undefined"),
    pytest.param("off", '"off"', id="unlisted_token_is_quoted_verbatim"),
    pytest.param("none", '"none"', id="rendered_none_is_quoted_verbatim"),
    pytest.param(False, "false", id="bool_token_still_renders"),
    pytest.param(True, "true", id="bool_true_token_still_renders"),
    pytest.param(None, "null", id="null_token_still_renders"),
]


@pytest.mark.parametrize("token, expected", _MESSAGE_TOKENS)
def test_wrong_node_undecidable_message_survives_a_non_string_token(token: Any, expected: str) -> None:
    """#15822: the emptiness test in front of the message must answer for any type.

    `| length == 0` reads as a definedness check and is not one — it raises on
    everything without a `__len__`, which is how a message whose entire job is
    to say "I could not decide, so I am leaving the directory alone" became the
    thing that aborted the wizard at step 7 and `install.sh` at phase 4.

    The bool rows are the regression: they are the exact values set_fact was
    handing this expression on the fleet. They must render, and they must not be
    mislabelled 'undefined' — an inactive role and an absent fact are different
    diagnoses and the operator acts differently on each.
    """
    scope: dict[str, Any] = {"role_check_fact": "role_backend_active", "dir_name": "autobot-backend"}
    _apply_set_fact(_wrong_node_normalise(), scope)
    _set_at(scope, _token_path(), token)

    try:
        rendered = _render_message(_wrong_node_message(), scope)
    except TypeError as exc:  # pragma: no cover - the failure this test exists for
        raise AssertionError(
            f"the undecidable message raised on a {type(token).__name__} token: {exc}. "
            f"This is #15822 — the branch that reports 'leaving it in place' cannot "
            f"itself be the branch that kills the run."
        ) from exc

    assert f"role_backend_active is {expected}" in rendered, (
        f"token {token!r} was reported as {rendered.split(' on this host')[0]!r}, "
        f"expected 'role_backend_active is {expected}'"
    )
