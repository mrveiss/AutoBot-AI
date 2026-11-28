# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#14678: the role_*_active facts have ONE definition, and the guard can tell.

The guard (``tools/lint/check_role_facts_single_source.py``) replaced a diff
guard that kept two copies equal. Contrast pairs below prove it fails on a
re-created duplicate (a passing copy-equality check would not), and the live
tree is checked against it.
"""

import importlib.util
from pathlib import Path

_ANSIBLE = Path(__file__).resolve().parents[2] / "autobot-slm-backend" / "ansible"
_spec = importlib.util.spec_from_file_location(
    "check_role_facts_single_source", Path(__file__).with_name("check_role_facts_single_source.py")
)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

_FACTS = "role_a_active: >-\n  {{ true }}\n\nchromadb_service_owner: x\n"
_GOOD = {guard.CANONICAL: _FACTS, "deploy.yml": "vars_files:\n  - inventory/group_vars/all.yml\n"}


def test_the_live_tree_has_exactly_one_definition():
    files = guard.tracked_yaml()
    assert len(files) > 100, "the guard read almost nothing -- it did not look"
    assert guard.violations(files) == []


def test_contrast_single_definition_passes():
    assert guard.violations(_GOOD) == []


def test_contrast_an_identical_copy_is_a_violation():
    """The old diff guard PASSED this (two equal copies); this one must not."""
    files = {**_GOOD, "playbooks/vars/role_active_facts.yml": _FACTS}
    problems = guard.violations(files)
    assert any("exactly" in p for p in problems), problems
    assert any("second role_active_facts.yml" in p for p in problems), problems


def test_contrast_a_fact_defined_in_another_file_is_a_violation():
    files = {**_GOOD, "inventory/group_vars/all.yml": "role_b_active: true\n"}
    assert guard.violations(files)


def test_contrast_an_indented_key_is_not_a_definition():
    files = {**_GOOD, "tests/inventory/x.yml": "all:\n  hosts:\n    h:\n      role_a_active: true\n"}
    assert guard.violations(files) == []


def test_contrast_role_defaults_floor_is_out_of_scope():
    files = {**_GOOD, "roles/redis/defaults/main.yml": 'chromadb_service_owner: "redis"\n'}
    assert guard.violations(files) == []


def test_contrast_vars_files_pointing_elsewhere_is_a_violation():
    files = {**_GOOD, "deploy.yml": "vars_files:\n  - vars/role_active_facts.yml\n"}
    assert any("vars_files" in p for p in guard.violations(files))


def test_contrast_relative_vars_files_to_the_canonical_file_passes():
    files = {
        **_GOOD,
        "tests/playbooks/t.yml": "vars_files:\n  - ../../inventory/group_vars/all.yml\n",
    }
    assert guard.violations(files) == []


def test_an_empty_tree_is_a_violation_not_a_pass():
    assert guard.violations({})


def test_group_vars_all_yml_is_the_single_definition():
    """#18514: the facts live IN all.yml; a sibling all/ directory would shadow it."""
    text = (_ANSIBLE / "inventory" / "group_vars" / "all.yml").read_text(encoding="utf-8")
    assert len(guard.defined_facts(text)) >= 2
    assert not (_ANSIBLE / "inventory" / "group_vars" / "all").exists()
