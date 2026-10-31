# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every repo file Alertmanager installs from is looked up before anything installs (#18556 review).

The monitoring role copies Alertmanager's config and its Prometheus rules with ``remote_src``
from the host's repo clone. A host without that checkout used to fail mid-install, and in check
mode too. ``tasks/main.yml`` now stats each source and asserts before the first include; this
guard fails when an ``alertmanager_*_src`` copy is added that the preflight does not look up.
"""

from __future__ import annotations

import re

import yaml
from repo_tests._paths import repo_root

_TASKS = repo_root() / "autobot-slm-backend" / "ansible" / "roles" / "monitoring" / "tasks"
_SRC_VAR = re.compile(r"\{\{\s*(alertmanager_\w+_src)\s*\}\}")


def _load(name: str) -> list[dict]:
    return yaml.safe_load((_TASKS / name).read_text(encoding="utf-8"))


def _copied_sources(tasks: list[dict]) -> set[str]:
    out = set()
    for task in tasks:
        copy = task.get("ansible.builtin.copy") or {}
        if copy.get("remote_src"):
            out |= set(_SRC_VAR.findall(str(copy.get("src", ""))))
    return out


def _preflight(main: list[dict]) -> tuple[set[str], int, int]:
    """(variables the stat loop looks up, index of the assert, index of the first include)."""
    stat = next(t for t in main if "ansible.builtin.stat" in t and t.get("register") == "_alertmanager_sources")
    looked_up = {m for item in stat["loop"] for m in _SRC_VAR.findall(item)}
    asserted = next(i for i, t in enumerate(main) if "_alertmanager_sources" in str(t.get("ansible.builtin.assert")))
    first_include = next(i for i, t in enumerate(main) if "ansible.builtin.include_tasks" in t)
    return looked_up, asserted, first_include


def _unchecked(main: list[dict], copied: set[str]) -> set[str]:
    return copied - _preflight(main)[0]


def test_every_alertmanager_source_is_looked_up_before_any_install() -> None:
    copied = _copied_sources(_load("alertmanager.yml")) | _copied_sources(_load("prometheus.yml"))
    assert copied == {"alertmanager_config_src", "alertmanager_rules_src"}, f"read {copied} -- the scan is broken"
    main = _load("main.yml")
    assert _unchecked(main, copied) == set()
    _, asserted, first_include = _preflight(main)
    assert asserted < first_include, "the preflight must fail before the first install include runs"


def test_contrast_a_source_the_preflight_does_not_look_up_is_reported() -> None:
    main = _load("main.yml")
    assert _unchecked(main, {"alertmanager_config_src", "alertmanager_templates_src"}) == {"alertmanager_templates_src"}
