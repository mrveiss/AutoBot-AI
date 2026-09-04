#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every ``logging.*`` config key has both a publisher and a reader (#15575).

``autobot_shared/logging_manager.py`` read ``logging.level`` while
``config/defaults.py`` publishes ``logging.log_level`` — a key nothing in the
config tree ever wrote. ``ConfigManager.get(key, default)`` doesn't raise or
warn on a miss, so the mismatch was invisible from either side alone: each
file looks correct in isolation, and only comparing the *resolved* key names
from both sides shows the divergence.

This is a structural guard, not a behavioural one (the behavioural regression
test lives in ``autobot_shared/logging_manager_log_level_test.py``). It
re-derives both sides at test time rather than hardcoding either list:

* "published" = the keys actually present under ``get_default_config()["logging"]``
  (config/defaults.py, called for real) unioned with the keys actually present
  under the live ``logging:`` section of ``config.yaml`` — the two layers
  ``config/loader.py`` merges to build the base config.
* "read" = every literal ``"logging.<dotted.path>"`` string passed to a
  ``.get(`` call anywhere under ``autobot-backend`` / ``autobot_shared``
  (excluding tests and the code-analysis/code-intelligence tools, whose
  ``logging.*`` strings are example *data*, not a real config read).

A few keys are read with a safe inline default and have never had a config
entry under any name — genuine optional overrides, not a renamed field. Those
are the only permitted exemption, and each entry says why.
"""

import os
import re
import sys
from typing import Any, Dict, Set

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autobot_shared.paths import project_root  # noqa: E402
from config.defaults import get_default_config  # noqa: E402

# Optional per-deployment overrides with a safe inline default at every call
# site. Verified (#15575 sweep) to have no entry in config/defaults.py,
# config.yaml, or any env-var mapping under ANY key name -- unlike
# "logging.level", these were never renamed from something that publishes
# them, so a missing publisher is the intended, documented behaviour.
_EXEMPT_OPTIONAL_READ_KEYS = {
    "logging.format",
    "logging.rotation.max_bytes",
    "logging.rotation.backup_count",
}

# Meta-tooling that stores "logging.*" strings as example/report *data*
# (before/after code snippets), never as a real ConfigManager.get() call.
_EXCLUDED_DIR_NAMES = {"code_analysis", "code_intelligence"}

_READ_KEY_PATTERN = re.compile(r"""get\(\s*(["'])logging((?:\.[A-Za-z_][A-Za-z0-9_]*)+)\1""")


def _flatten_keys(section: Dict[str, Any], prefix: str = "logging") -> Set[str]:
    """Flatten a nested dict into dotted key paths, e.g. {"a": {"b": 1}} -> {"a.b"}."""
    keys: Set[str] = set()
    for key, value in section.items():
        path = f"{prefix}.{key}"
        if isinstance(value, dict):
            keys |= _flatten_keys(value, path)
        else:
            keys.add(path)
    return keys


def _published_logging_keys() -> Set[str]:
    """Keys under "logging" in config/defaults.py's schema and config.yaml's live base."""
    defaults_logging = get_default_config().get("logging", {})
    config_yaml = project_root() / "autobot-infrastructure" / "shared" / "config" / "config.yaml"
    yaml_logging = yaml.safe_load(config_yaml.read_text(encoding="utf-8")).get("logging", {})
    return _flatten_keys(defaults_logging) | _flatten_keys(yaml_logging)


def _read_logging_keys() -> Set[str]:
    """Every literal "logging.<path>" string passed to a .get( call in backend source."""
    keys: Set[str] = set()
    for scan_root in ("autobot-backend", "autobot_shared"):
        for path in (project_root() / scan_root).rglob("*.py"):
            if path.name.endswith("_test.py") or _EXCLUDED_DIR_NAMES & set(path.parts):
                continue
            text = path.read_text(encoding="utf-8")
            keys.update("logging" + m.group(2) for m in _READ_KEY_PATTERN.finditer(text))
    return keys


def test_every_read_logging_key_has_a_publisher_or_a_documented_exemption():
    """Catches #15575's shape: a read key nothing publishes under that name."""
    read_keys = _read_logging_keys()
    published_keys = _published_logging_keys()

    unpublished = read_keys - published_keys - _EXEMPT_OPTIONAL_READ_KEYS
    assert not unpublished, (
        f"logging.* keys read but never published under that name: {sorted(unpublished)}. "
        "Either config/defaults.py (or config.yaml) needs to publish them, the reader has "
        "the wrong key name, or they belong in _EXEMPT_OPTIONAL_READ_KEYS with a reason."
    )


def test_every_published_logging_key_has_a_reader():
    """Catches the mirror shape: a config value nothing ever consumes."""
    published_keys = _published_logging_keys()
    read_keys = _read_logging_keys()

    unread = published_keys - read_keys
    assert not unread, f"logging.* keys published but never read by anything: {sorted(unread)}"


def test_exempt_optional_read_keys_still_have_no_publisher():
    """Keeps the exemption list honest: it may only hold keys nothing publishes.

    If a later change adds e.g. "logging.format" to config/defaults.py, this
    fails so the now-stale exemption gets removed rather than silently
    surviving as dead documentation.
    """
    published_keys = _published_logging_keys()

    still_unpublished = _EXEMPT_OPTIONAL_READ_KEYS & published_keys
    assert not still_unpublished, (
        f"Exempt keys now have a real publisher, remove from _EXEMPT_OPTIONAL_READ_KEYS: "
        f"{sorted(still_unpublished)}"
    )
