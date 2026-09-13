# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A factory reset must not drop the four logging settings-UI keys (#15587).

``config/defaults.py`` never declared ``logging.console``,
``logging.log_requests``, ``logging.log_sql``, or ``logging.max_file_size`` --
only the live ``config.yaml`` carried them. ``config/loader.py`` always starts
from ``get_default_config()`` and merges the YAML on top (its own docstring:
"Always starts with default config and merges the YAML on top"), so a factory
reset -- any rebuild of config where the YAML is absent, corrupt, or simply
doesn't mention a key -- silently dropped whatever the operator had set for
these four.
"""

from pathlib import Path

import yaml

from autobot_shared.paths import project_root
from config.defaults import get_default_config
from config.loader import deep_merge

_TOGGLE_KEYS = ("console", "log_requests", "log_sql", "max_file_size")


def _live_config_yaml_logging_section() -> dict:
    config_yaml: Path = project_root() / "autobot-infrastructure" / "shared" / "config" / "config.yaml"
    return yaml.safe_load(config_yaml.read_text(encoding="utf-8"))["logging"]


def test_defaults_declare_all_four_toggle_keys():
    """The concrete defect: these four were absent from the schema entirely."""
    logging_defaults = get_default_config()["logging"]
    for key in _TOGGLE_KEYS:
        assert key in logging_defaults, f"config/defaults.py's logging section is missing {key!r}"


def test_factory_reset_with_no_yaml_still_carries_the_four_toggle_values():
    """Simulates a factory reset: config.yaml is gone, defaults are all there is.

    ``config/loader.load_configuration`` always calls ``deep_merge(base_config,
    user_settings)`` starting from ``get_default_config()`` -- an empty override
    (no config.yaml, no settings.json) reproduces exactly what a reset leaves
    behind.
    """
    reset_config = deep_merge(get_default_config(), {})
    logging_cfg = reset_config["logging"]

    assert logging_cfg["console"] is True
    assert logging_cfg["log_requests"] is False
    assert logging_cfg["log_sql"] is False
    assert logging_cfg["max_file_size"] == 10


def test_declared_defaults_match_what_the_live_config_yaml_already_carries():
    """Reset must not silently *change* a currently-deployed operator value.

    Declaring a default that disagrees with the live config.yaml would still
    pass ``test_defaults_declare_all_four_toggle_keys`` while quietly flipping
    an operator's setting the moment config.yaml was regenerated from schema
    with that key omitted. Pin defaults.py to the values config.yaml actually
    carries today.
    """
    defaults_logging = get_default_config()["logging"]
    live_logging = _live_config_yaml_logging_section()

    for key in _TOGGLE_KEYS:
        assert defaults_logging[key] == live_logging[key], (
            f"config/defaults.py's logging.{key}={defaults_logging[key]!r} disagrees with "
            f"the live config.yaml's {live_logging[key]!r}"
        )
