# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A variable declared in both the env registry and the SSOT models has one default (#17419).

Also: one ``alias="AUTOBOT_*"`` binds one field. A name bound by two fields is set by one
environment variable yet read through two differently-typed or differently-defaulted attributes.

Compares the planes as loaded, so a value spelled through a constant is compared by what it is.
``None`` and ``""`` both mean unset, and ``"8001"`` and ``8001`` differ only in the declared type.
"""

from __future__ import annotations

import inspect
from typing import Any, Iterator

from pydantic import Field
from pydantic.fields import PydanticUndefined
from pydantic_settings import BaseSettings

from autobot_shared import ssot_config
from autobot_shared.env_registry import REGISTRY

#: Names in both planes on main when this guard landed, less a margin for removals.
MIN_NAMES_COMPARED = 20


#: Aliases still bound by two fields (the SSH identity in PathConfig and TLSConfig), shrink-only.
KNOWN_DOUBLE_BINDINGS = frozenset({"AUTOBOT_SSH_KEY", "AUTOBOT_SSH_USER"})


def _normalized(value: Any) -> str:
    return "" if value is None else str(value)


def _settings_classes() -> Iterator[type[BaseSettings]]:
    for value in vars(ssot_config).values():
        if isinstance(value, type) and issubclass(value, BaseSettings) and value is not BaseSettings:
            yield value


def _ssot_defaults() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for cls in _settings_classes():
        for field in cls.model_fields.values():
            if not (field.alias or "").startswith("AUTOBOT_"):
                continue
            default = field.default_factory() if field.default_factory else field.default
            if default is not PydanticUndefined:
                found.setdefault(field.alias, set()).add(_normalized(default))
    return found


def disagreements(registry: dict[str, Any], ssot: dict[str, set[str]]) -> dict[str, tuple[str, set[str]]]:
    return {
        name: (_normalized(registry[name]), values)
        for name, values in ssot.items()
        if name in registry and _normalized(registry[name]) not in values
    }


def test_every_name_in_both_planes_has_one_default() -> None:
    ssot = _ssot_defaults()
    registry = {name: spec.default for name, spec in REGISTRY.items()}
    compared = set(registry) & set(ssot)
    assert len(compared) >= MIN_NAMES_COMPARED, f"compared only {len(compared)} names"
    assert disagreements(registry, ssot) == {}


def test_a_different_value_is_caught_and_a_different_spelling_is_not() -> None:
    ssot = {"AUTOBOT_A": {"127.0.0.1"}, "AUTOBOT_B": {""}, "AUTOBOT_C": {"8001"}, "AUTOBOT_D": {"x"}}
    registry = {"AUTOBOT_A": "localhost", "AUTOBOT_B": None, "AUTOBOT_C": 8001}
    assert disagreements(registry, ssot) == {"AUTOBOT_A": ("localhost", {"127.0.0.1"})}


def _own_aliases(cls: type[BaseSettings]) -> Iterator[str]:
    """Aliases of the fields *cls* itself declares, so an inherited field is not counted per subclass."""
    for name in inspect.get_annotations(cls):
        field = cls.model_fields.get(name)
        if field is not None and (field.alias or "").startswith("AUTOBOT_"):
            yield field.alias


def double_bindings(classes: Iterator[type[BaseSettings]]) -> set[str]:
    seen: set[str] = set()
    twice: set[str] = set()
    for cls in classes:
        for alias in _own_aliases(cls):
            (twice if alias in seen else seen).add(alias)
    return twice


def test_every_alias_binds_one_field() -> None:
    assert double_bindings(_settings_classes()) - KNOWN_DOUBLE_BINDINGS == set()


def test_the_double_binding_exemptions_are_not_stale() -> None:
    assert KNOWN_DOUBLE_BINDINGS <= double_bindings(_settings_classes())


def test_a_second_binding_is_caught_and_an_inherited_field_is_not() -> None:
    class Base(BaseSettings):
        shared: int = Field(default=1, alias="AUTOBOT_X_SHARED")

    class Left(Base):
        own: int = Field(default=1, alias="AUTOBOT_X_OWN")

    class Right(Base):
        again: float = Field(default=1.0, alias="AUTOBOT_X_OWN")

    assert double_bindings(iter([Base, Left, Right])) == {"AUTOBOT_X_OWN"}
