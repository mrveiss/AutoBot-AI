# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cross-source skill name-conflict detection + deterministic resolution (#11141).

A sandboxed external/hub import must never silently mask a trusted builtin (nor
vice-versa); the winner is decided by source trust, not discovery order, and
every genuine collision is recorded (visible via ``get_conflicts``).
"""

from skills.base_skill import SkillManifest
from skills.registry import SkillRegistry


def _m(name: str, version: str = "1.0.0") -> SkillManifest:
    return SkillManifest(name=name, version=version, description="d")


def test_no_conflict_when_names_differ():
    reg = SkillRegistry()
    reg.register_declarative(_m("a"), source="builtin")
    reg.register_declarative(_m("b"), source="hub")
    assert reg.get_conflicts() == []


def test_builtin_incumbent_kept_over_hub_incoming():
    reg = SkillRegistry()
    assert reg.register_declarative(_m("dup", "1.0.0"), source="builtin") is True
    # Hub tries to register the same name later — must NOT win.
    assert reg.register_declarative(_m("dup", "2.0.0"), source="hub") is False
    conflicts = reg.get_conflicts()
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["name"] == "dup"
    assert c["incumbent_source"] == "builtin" and c["incoming_source"] == "hub"
    assert c["resolution"] == "kept_incumbent"
    # incumbent unchanged
    assert reg.get_skill_detail("dup")["version"] == "1.0.0"


def test_builtin_incoming_overrides_lower_trust_incumbent_regardless_of_order():
    reg = SkillRegistry()
    # Hub registers FIRST (discovery-order would keep it) ...
    assert reg.register_declarative(_m("dup", "9.9.9"), source="hub") is True
    # ... but a trusted builtin arriving later must deterministically win.
    assert reg.register_declarative(_m("dup", "1.0.0"), source="builtin") is True
    conflicts = reg.get_conflicts()
    assert len(conflicts) == 1
    assert conflicts[0]["resolution"] == "replaced_with_incoming"
    assert conflicts[0]["incoming_source"] == "builtin"
    assert reg.get_skill_detail("dup")["version"] == "1.0.0"  # builtin now wins


def test_same_trust_tie_keeps_incumbent_and_records_conflict_when_version_differs():
    reg = SkillRegistry()
    reg.register_declarative(_m("dup", "1.0.0"), source="hub")
    assert reg.register_declarative(_m("dup", "2.0.0"), source="hub") is False
    conflicts = reg.get_conflicts()
    assert len(conflicts) == 1
    assert conflicts[0]["resolution"] == "kept_incumbent"
    assert reg.get_skill_detail("dup")["version"] == "1.0.0"


def test_idempotent_same_source_same_version_is_not_a_conflict():
    reg = SkillRegistry()
    reg.register_declarative(_m("dup", "1.0.0"), source="builtin")
    assert reg.register_declarative(_m("dup", "1.0.0"), source="builtin") is False
    assert reg.get_conflicts() == []  # pure reload, not a conflict


def test_get_conflicts_returns_structured_dicts():
    reg = SkillRegistry()
    reg.register_declarative(_m("dup"), source="builtin")
    reg.register_declarative(_m("dup", "2.0.0"), source="external")
    (c,) = reg.get_conflicts()
    assert set(c.keys()) == {
        "name",
        "incumbent_source",
        "incumbent_version",
        "incoming_source",
        "incoming_version",
        "resolution",
    }
