# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Transitive skill resolution with sources (#18390). No database."""

from llc.services.company_os.skill_resolution import MetaSkillDef, resolve_held_skills

METAS = {
    "outer": MetaSkillDef("outer", "Outer", skills=("a",), calls=("inner",)),
    "inner": MetaSkillDef("inner", "Inner", skills=("b",), calls=()),
    "loop1": MetaSkillDef("loop1", "Loop1", skills=("c",), calls=("loop2",)),
    "loop2": MetaSkillDef("loop2", "Loop2", skills=("d",), calls=("loop1",)),
}


def _by_skill(held):
    return {h.skill: h for h in held}


def test_direct_skill_is_reported_as_direct():
    held = _by_skill(resolve_held_skills(["x"], [], METAS))
    assert [s.kind for s in held["x"].sources] == ["direct"]


def test_meta_skill_delivers_its_skills_and_names_itself():
    held = _by_skill(resolve_held_skills([], ["outer"], METAS))
    src = held["a"].sources[0]
    assert (src.kind, src.meta_skill_id, src.meta_skill_name, src.via) == ("meta_skill", "outer", "Outer", ("Outer",))


def test_nested_meta_skill_is_transitive_and_shows_the_path():
    held = _by_skill(resolve_held_skills([], ["outer"], METAS))
    assert held["b"].sources[0].meta_skill_id == "outer"
    assert held["b"].sources[0].via == ("Outer", "Inner")


def test_every_source_is_kept_when_a_skill_is_held_several_ways():
    held = _by_skill(resolve_held_skills(["b"], ["outer", "inner"], METAS))
    kinds = sorted((s.kind, s.meta_skill_id or "") for s in held["b"].sources)
    assert kinds == [("direct", ""), ("meta_skill", "inner"), ("meta_skill", "outer")]


def test_a_cycle_terminates():
    held = _by_skill(resolve_held_skills([], ["loop1"], METAS))
    assert set(held) == {"c", "d"}


def test_unknown_meta_skill_delivers_nothing():
    assert resolve_held_skills([], ["ghost"], METAS) == []
