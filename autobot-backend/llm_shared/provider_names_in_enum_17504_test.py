# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every provider the bootstrap registers is a member of ``LLMProvider`` (#17504).

``LLMProvider`` is the only enumerable list of provider names, so it can validate
a configured name only while it is complete.  ``custom_openai`` and ``nous`` were
registered under bare strings outside it, and nothing failed until a caller
spell-checked a name against the enum.

The classes come from the bootstrap's own imports of ``llm_shared.providers.*``,
so a provider added there is examined with no name list to maintain here.  The
check reads the CLASS attribute ``provider_name``; the one runtime override --
``CustomOpenAIProvider(instance_name=...)``, which registers extra instances
under user-chosen names -- sets an INSTANCE attribute and is exempt by that
mechanism alone.  The converse (every enum member has a provider) is not
asserted: ``AZURE``, ``LOCAL``, ``MOCK``, ``GOOGLE`` and others are deliberate
members with no registered class, so it would be a name list in disguise.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

from autobot_shared.status_enums import LLMProvider
from llm_shared.base_provider import BaseProvider
from llm_shared.providers.custom_openai import CustomOpenAIProvider

#: Read from disk: the backend conftest may stub the ``bootstrap`` module object.
_BOOTSTRAP = Path(__file__).parent / "providers" / "bootstrap.py"
_ENUM_VALUES = {member.value for member in LLMProvider}
_PROVIDERS_PREFIX = "llm_shared.providers."
_MIN_REGISTERED = 10  # bootstrap registers 12 today; far fewer means discovery broke


def _registered_classes(source: str) -> list[type]:
    """Provider classes the bootstrap source imports from ``llm_shared.providers.*``."""
    classes: list[type] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(_PROVIDERS_PREFIX):
            module = importlib.import_module(node.module)
            classes += [getattr(module, alias.name) for alias in node.names]
    return classes


def _names_outside_enum(classes: list[type]) -> list[str]:
    return sorted(c.__name__ for c in classes if c.provider_name not in _ENUM_VALUES)


def _bootstrap_classes() -> list[type]:
    return _registered_classes(_BOOTSTRAP.read_text(encoding="utf-8"))


def test_every_bootstrap_registered_provider_name_is_an_llm_provider() -> None:
    classes = _bootstrap_classes()
    assert len(classes) >= _MIN_REGISTERED, f"discovery found only {len(classes)} provider classes"
    assert all(issubclass(c, BaseProvider) for c in classes)
    assert _names_outside_enum(classes) == []


def test_the_two_formerly_bare_names_are_members() -> None:
    assert {"custom_openai", "nous"} <= _ENUM_VALUES


def test_a_registration_under_an_unknown_name_fails_the_guard() -> None:
    """Contrast: the shape of the original defect is caught, by the same predicate."""
    source = "from llm_shared.providers.custom_openai import CustomOpenAIProvider\n"
    unknown = type("UnknownProvider", (BaseProvider,), {"provider_name": "not_a_member"})
    assert _names_outside_enum([*_registered_classes(source), unknown]) == ["UnknownProvider"]


def test_the_instance_name_override_is_the_only_exempt_mechanism() -> None:
    """A custom instance's name is an instance attribute; the class attribute stays in the enum."""
    instance = CustomOpenAIProvider(settings={"base_url": "http://x"}, instance_name="user_chosen")
    assert instance.provider_name == "user_chosen" and "user_chosen" not in _ENUM_VALUES
    assert CustomOpenAIProvider.provider_name in _ENUM_VALUES
