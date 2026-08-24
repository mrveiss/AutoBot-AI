# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Ansible/Pydantic default parity for the service_auth field block (#13335).

Three separate defaults in this one block have now drifted from the values the
``service_auth`` Ansible role writes, and every one of them shipped silently:

* #13326 -- ``max_failures``/``window`` both defaulted to ``0``, so
  ``len(failures) >= max_failures`` was true for the first request and every
  service-only route rejected its first caller.  Failed **closed**, and loudly.
* #13335 -- ``service_auth_enforcement_mode`` defaulted to ``""`` while the
  middleware tests ``mode.lower() == "true"``, and
  ``service_auth_circuit_breaker_percentage`` defaulted to ``0.0`` while the
  breaker treats ``<= 0`` as "sample nothing".  Failed **open**, and silently:
  any install that did not run the Ansible role had the security gate off.

The durable fix is not the two corrected values -- it is this test.  It reads
every ``NAME={{ var }}`` assignment the role and the backend env template
actually emit, resolves ``NAME`` to the Pydantic field that claims it as an
alias, and asserts the rendered Ansible value validates to that field's
declared default.  A fourth drift becomes a red test instead of a silent
misconfiguration, and a new key added to the role with no Pydantic field is
caught the same way.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator, NamedTuple

import pytest
import yaml
from pydantic import TypeAdapter
from pydantic.fields import FieldInfo

from autobot_shared.ssot_config import MiscConfig

# Resolved from this file, NOT from ``ssot_config.PROJECT_ROOT``: that helper
# walks up looking for a ``.env``, which does not exist inside a git worktree,
# so it silently returns the main checkout and this test would assert against
# somebody else's tree (see #13149).
REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE_DEFAULTS = REPO_ROOT / "autobot-slm-backend/ansible/roles/service_auth/defaults/main.yml"
ROLE_TASKS = REPO_ROOT / "autobot-slm-backend/ansible/roles/service_auth/tasks"
BACKEND_ENV_TEMPLATE = REPO_ROOT / "autobot-slm-backend/ansible/roles/backend/templates/backend.env.j2"

# ``NAME={{ expr }}`` -- both as a bare template line and inside a lineinfile
# ``line:`` value.  Anchored on the env-var name so prose never matches, and on
# end-of-value so a composite line (``{{ dir }}/{{ id }}.env``) is skipped
# rather than silently compared against only its first expression.
_ASSIGNMENT = re.compile(r'(?m)^\s*(?:line:\s*")?(?P<env>[A-Z][A-Z0-9_]*)=\{\{\s*(?P<expr>[^{}]+?)\s*\}\}"?\s*$')
_DEFAULT_FILTER = re.compile(r"^default\((?P<literal>.*)\)$")


class Assignment(NamedTuple):
    """One ``ENV_NAME={{ ansible_var | filters }}`` pair found in the role."""

    source: str
    env: str
    var: str
    filters: tuple[str, ...]


def _role_defaults() -> dict[str, Any]:
    return yaml.safe_load(ROLE_DEFAULTS.read_text(encoding="utf-8"))


def _parse_assignments(path: Path, declared: frozenset[str]) -> Iterator[Assignment]:
    """Yield every env assignment in ``path`` fed by a role-declared variable.

    Scoped to ``declared`` on purpose: a template may also reference per-host
    identity vars (``service_auth_service_id``) that no role default can supply,
    and those are not a defaults-parity question.
    """
    for match in _ASSIGNMENT.finditer(path.read_text(encoding="utf-8")):
        parts = [p.strip() for p in match.group("expr").split("|")]
        if parts[0] not in declared:
            continue
        yield Assignment(path.name, match.group("env"), parts[0], tuple(parts[1:]))


def _all_assignments() -> list[Assignment]:
    declared = frozenset(_role_defaults())
    paths = sorted(ROLE_TASKS.glob("*.yml")) + [BACKEND_ENV_TEMPLATE]
    return [a for path in paths for a in _parse_assignments(path, declared)]


def _render(value: Any, filters: tuple[str, ...]) -> str:
    """Reproduce what Ansible writes into the .env file for ``value``."""
    rendered = str(value)
    if "lower" in filters:
        rendered = rendered.lower()
    return rendered


def _field_for_alias(alias: str) -> tuple[str, FieldInfo] | None:
    for name, field in MiscConfig.model_fields.items():
        if field.alias == alias:
            return name, field
    return None


ASSIGNMENTS = _all_assignments()
DEFAULTS = _role_defaults()


def test_the_parser_actually_found_the_role_assignments() -> None:
    """Guard the guard: a regex that matches nothing would pass every test."""
    envs = {a.env for a in ASSIGNMENTS}
    assert "SERVICE_AUTH_ENFORCEMENT_MODE" in envs
    assert "SERVICE_AUTH_CIRCUIT_BREAKER_PERCENTAGE" in envs
    assert len(envs) >= 5, f"only found {sorted(envs)} -- the role writes more than that"


def test_every_enforcement_knob_the_role_declares_reaches_the_backend() -> None:
    """A declared toggle that no task writes is a knob wired to nothing.

    This is how ``service_auth_rate_limit_window`` came to be declared by the
    role while only the backend env template ever emitted it (#13335).
    """
    emitted = {a.var for a in ASSIGNMENTS if a.source != BACKEND_ENV_TEMPLATE.name}
    expected = {
        "service_auth_enforcement_mode",
        "service_auth_circuit_breaker_percentage",
        "service_auth_rate_limit_window",
        "service_auth_rate_limit_max_failures",
        "service_auth_timestamp_window",
    }
    assert expected <= emitted, f"role tasks never write: {sorted(expected - emitted)}"


@pytest.mark.parametrize("assignment", ASSIGNMENTS, ids=lambda a: f"{a.source}:{a.env}")
def test_env_key_is_claimed_by_a_pydantic_field(assignment: Assignment) -> None:
    """Ansible writing a key nobody reads is a knob that silently does nothing."""
    assert _field_for_alias(assignment.env) is not None, (
        f"{assignment.source} writes {assignment.env}, but no MiscConfig field "
        f"claims that alias -- the value is parsed by nobody (this is how "
        f"AUTH_TIMESTAMP_WINDOW went unread while ServiceAuthManager hard-coded 300)"
    )


@pytest.mark.parametrize("assignment", ASSIGNMENTS, ids=lambda a: f"{a.source}:{a.env}")
def test_pydantic_default_matches_the_ansible_default(assignment: Assignment) -> None:
    """The #13326/#13335 drift, as an assertion.

    An install that never ran Ansible must behave exactly like one that did.
    """
    resolved = _field_for_alias(assignment.env)
    if resolved is None:
        pytest.skip("covered by test_env_key_is_claimed_by_a_pydantic_field")
    name, field = resolved

    rendered = _render(DEFAULTS[assignment.var], assignment.filters)
    from_ansible = TypeAdapter(field.annotation).validate_python(rendered)

    assert from_ansible == field.default, (
        f"MiscConfig.{name} defaults to {field.default!r}, but the service_auth "
        f"role writes {assignment.env}={rendered!r} (-> {from_ansible!r}). "
        f"An unmanaged install therefore behaves differently from a managed one."
    )


@pytest.mark.parametrize(
    "assignment",
    [a for a in ASSIGNMENTS if any(_DEFAULT_FILTER.match(f) for f in a.filters)],
    ids=lambda a: f"{a.source}:{a.env}",
)
def test_jinja_default_filter_matches_the_role_default(assignment: Assignment) -> None:
    """``| default(100)`` in the template is a fourth copy of the same number."""
    literal = next(m.group("literal") for f in assignment.filters if (m := _DEFAULT_FILTER.match(f)))
    role_value = _render(DEFAULTS[assignment.var], assignment.filters)
    inline_value = _render(yaml.safe_load(literal), assignment.filters)

    assert inline_value == role_value, (
        f"{assignment.source} falls back to `default({literal})` for "
        f"{assignment.env}, but the role default renders as {role_value!r}"
    )


class TestTheCorrectedValuesThemselves:
    """Pin the two #13335 values directly, so the intent survives a refactor."""

    def test_enforcement_is_on_by_default(self) -> None:
        """The exact comparison the middleware performs, on the bare default."""
        assert MiscConfig.model_fields["service_auth_enforcement_mode"].default.lower() == "true"

    def test_circuit_breaker_samples_every_request_by_default(self) -> None:
        """The breaker treats ``<= 0`` as 'sample nothing' -- i.e. enforce nothing."""
        assert MiscConfig.model_fields["service_auth_circuit_breaker_percentage"].default >= 100

    @pytest.mark.parametrize(
        "field_name",
        [
            "service_auth_enforcement_mode",
            "service_auth_circuit_breaker_percentage",
            "service_auth_rate_limit_max_failures",
            "service_auth_rate_limit_window",
            "service_auth_timestamp_window",
        ],
    )
    def test_falsy_meaning_is_documented(self, field_name: str) -> None:
        """``""``/``0`` meant 'disabled' only by accident of a comparison."""
        description = MiscConfig.model_fields[field_name].description or ""
        assert "DISABLES" in description or "does not disable" in description, (
            f"{field_name} does not state what its falsy value means; that "
            f"ambiguity is what let three of these defaults drift unnoticed"
        )
