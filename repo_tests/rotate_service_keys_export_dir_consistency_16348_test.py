# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``rotate-service-keys.yml``'s export directory and the ``service_auth``
role's ``service_auth_keys_source_dir`` must resolve to the same directory
(#16348).

Before this fix, Phase 1 derived its export path from a hard-coded
``autobot_root: /opt/autobot``, Phase 5 repeated the literal independently,
and the role read from ``{{ autobot.base_dir }}/config/service-keys`` -- three
expressions that happened to agree only because nobody had yet overridden
``autobot.base_dir``. This statically pins that all three now derive from the
one group_vars value.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

import yaml
from repo_tests._paths import repo_root

REPO_ROOT = repo_root()
PLAYBOOK = REPO_ROOT / "autobot-slm-backend" / "ansible" / "playbooks" / "rotate-service-keys.yml"
ROLE_DEFAULTS = REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles" / "service_auth" / "defaults" / "main.yml"
DEPLOY_KEYS = REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles" / "service_auth" / "tasks" / "deploy-keys.yml"

# The single expression every export/read path must agree on (#16348).
_EXPECTED_EXPORT_DIR_EXPR = "{{ autobot.base_dir }}/config/service-keys"


def _load_plays() -> List[Dict[str, Any]]:
    return yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))


def _find_play(plays: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    for play in plays:
        if play.get("name") == name:
            return play
    raise AssertionError(f"no play named {name!r}")


def test_phase1_autobot_root_derives_from_the_shared_group_var():
    play = _find_play(_load_plays(), "Phase 1 - Generate New Service Keys")
    assert play["vars"]["autobot_root"] == "{{ autobot.base_dir }}"
    assert play["vars"]["keys_backup_dir"] == "{{ autobot_root }}/config/service-keys"


def test_phase5_export_dir_matches_phase1_after_substitution():
    play = _find_play(_load_plays(), "Phase 5 - Rotation Summary")
    assert play["vars"]["keys_backup_dir"] == _EXPECTED_EXPORT_DIR_EXPR


def test_role_source_dir_matches_the_playbooks_export_dir():
    role_defaults = yaml.safe_load(ROLE_DEFAULTS.read_text(encoding="utf-8"))
    assert role_defaults["service_auth_keys_source_dir"] == _EXPECTED_EXPORT_DIR_EXPR

    phase1 = _find_play(_load_plays(), "Phase 1 - Generate New Service Keys")
    # Phase 1's keys_backup_dir is "{{ autobot_root }}/config/service-keys"
    # with autobot_root == "{{ autobot.base_dir }}" -- substitute one level
    # so both sides are compared as the same fully-expanded expression.
    substituted = phase1["vars"]["keys_backup_dir"].replace("{{ autobot_root }}", phase1["vars"]["autobot_root"])
    assert substituted == role_defaults["service_auth_keys_source_dir"]


def test_no_hardcoded_autobot_root_literal_remains():
    text = PLAYBOOK.read_text(encoding="utf-8")
    assert "/opt/autobot" not in text, (
        "rotate-service-keys.yml must derive its export dir from autobot.base_dir, "
        "never a hard-coded /opt/autobot literal (#16348)"
    )


def test_generator_is_invoked_with_an_explicit_output_dir():
    plays = _load_plays()
    phase1 = _find_play(plays, "Phase 1 - Generate New Service Keys")
    generate_task = next(t for t in phase1["tasks"] if t.get("name") == "Generate new service keys")
    cmd = generate_task["ansible.builtin.command"]["cmd"]
    assert "--output-dir {{ keys_backup_dir }}" in cmd


def test_newest_export_selectors_sort_by_path_not_mtime():
    """Every "pick the newest export" selector -- Phase 1, Phase 5 and the
    service_auth role's deploy task -- must sort by path (the filename's
    embedded timestamp), matching the generator's own prune
    (generate_service_keys.py::_prune_old_backups). mtime disagrees after a
    restored/copied export or a clock step, which could delete the
    just-rotated export while deploy picks a stale one (#16348)."""
    for path in (PLAYBOOK, DEPLOY_KEYS):
        text = path.read_text(encoding="utf-8")
        selectors = re.findall(r"sort\(attribute='(\w+)'\)\s*\|\s*last", text)
        assert selectors, f"no newest-export selector found in {path.name}"
        assert set(selectors) == {
            "path"
        }, f"{path.name} selects the newest export by {sorted(set(selectors))}, not 'path' (#16348)"
