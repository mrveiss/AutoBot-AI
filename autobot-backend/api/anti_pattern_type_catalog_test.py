# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard for the /anti-pattern/types catalog (Issue #18099)."""

from enum import Enum

import pytest

from api import anti_pattern_type_catalog as catalog
from code_analysis.src.anti_pattern_detector import AntiPatternType

_SHAPE = ["type", "name", "description", "thresholds", "severity_range", "principle_violated"]
_ORIGINAL_EIGHT = [
    "god_class",
    "feature_envy",
    "circular_dependency",
    "long_method",
    "long_parameter_list",
    "lazy_class",
    "dead_code",
    "data_clump",
]


def _unadvertised(definitions, enum_cls, aliases):
    advertised = {d["type"] for d in definitions}
    return {m.value for m in enum_cls if m.value not in advertised and m not in aliases}


def _not_in_enum(definitions, enum_cls):
    return {d["type"] for d in definitions} - {m.value for m in enum_cls}


def test_every_member_is_advertised_or_an_alias():
    defs = catalog.build_anti_pattern_type_definitions()
    assert _unadvertised(defs, AntiPatternType, catalog.ALIAS_TYPES) == set()


def test_no_advertised_type_is_absent_from_the_enum():
    defs = catalog.build_anti_pattern_type_definitions()
    assert _not_in_enum(defs, AntiPatternType) == set()


def test_aliases_are_excluded_and_nothing_else():
    values = [d["type"] for d in catalog.build_anti_pattern_type_definitions()]
    assert "data_clumps" not in values and "duplicate_abstraction" not in values
    assert len(values) == len(set(values)) == len(AntiPatternType) - len(catalog.ALIAS_TYPES)


def test_original_eight_keep_their_order_first_and_every_entry_has_the_same_shape():
    defs = catalog.build_anti_pattern_type_definitions()
    assert [d["type"] for d in defs[:8]] == _ORIGINAL_EIGHT
    assert all(list(d) == _SHAPE for d in defs)


def test_new_members_follow_in_enum_order():
    tail = [d["type"] for d in catalog.build_anti_pattern_type_definitions()[8:]]
    expected = [m.value for m in AntiPatternType if m.value not in _ORIGINAL_EIGHT and m not in catalog.ALIAS_TYPES]
    assert tail == expected


def test_contrast_member_without_entry_fails(monkeypatch):
    fake = Enum("Fake", {**{m.name: m.value for m in AntiPatternType}, "EXTRA": "extra_type"})
    details = {fake[m.name]: v for m, v in catalog._TYPE_DETAILS.items()}
    aliases = frozenset(fake[m.name] for m in catalog.ALIAS_TYPES)
    monkeypatch.setattr(catalog, "AntiPatternType", fake)
    monkeypatch.setattr(catalog, "_TYPE_DETAILS", details)
    monkeypatch.setattr(catalog, "ALIAS_TYPES", aliases)
    with pytest.raises(RuntimeError, match="EXTRA"):
        catalog.build_anti_pattern_type_definitions()
    details[fake["EXTRA"]] = {**details[fake["GOD_CLASS"]]}
    assert "extra_type" in [d["type"] for d in catalog.build_anti_pattern_type_definitions()]


def test_contrast_advertised_type_absent_from_enum_is_detected():
    defs = catalog.build_anti_pattern_type_definitions() + ({"type": "not_a_real_type"},)
    assert _not_in_enum(defs, AntiPatternType) == {"not_a_real_type"}
    fake = Enum("Fake", {"ONLY": "only"})
    assert _unadvertised(catalog.build_anti_pattern_type_definitions(), fake, frozenset()) == {"only"}
