# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The configured JSON formatter must name a class that exists (#14745).

`logging.config.dictConfig` resolves a formatter's `class` from a dotted string
at load time, so a wrong path is invisible to every static check and to every
importer — it surfaces only when some *other* service loads the config. The
aggregator dumps this config as YAML for others to read and never calls
`dictConfig` itself, so nothing in this repo ever exercised the string. That is
precisely why the stale path sat there.

These close that gap from both ends: the two places that declare the path must
agree, and where the package is installed the path must actually import.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONFIG = _REPO_ROOT / "autobot-infrastructure" / "shared" / "config" / "logging.yml"
_AGGREGATOR = _REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "log_aggregator.py"


def _configured_formatter_class() -> str:
    assert _CONFIG.is_file(), f"{_CONFIG.name} has moved — re-point this guard rather than deleting it"
    data = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))
    return data["formatters"]["json"]["class"]


def test_the_yaml_and_the_aggregator_name_the_same_class() -> None:
    """One of them drifting is how the stale path survived a version bump.

    Runs everywhere, with no dependency on the package being installed — the
    durable half of this guard.
    """
    configured = _configured_formatter_class()
    source = _AGGREGATOR.read_text(encoding="utf-8")

    declared = re.findall(r'"class":\s*"([\w.]*JsonFormatter)"', source)

    assert declared, "the aggregator no longer declares a JSON formatter class — re-point this guard"
    assert set(declared) == {configured}, (
        f"logging.yml says {configured!r} but log_aggregator.py says {sorted(set(declared))} — "
        "a service loading the dumped config would resolve a different class than the one "
        "this repo believes it configured"
    )


def test_the_configured_class_actually_imports() -> None:
    """Executed, not inspected — the check `dictConfig` would have made."""
    configured = _configured_formatter_class()
    module_path, _, class_name = configured.rpartition(".")

    pytest.importorskip(
        module_path,
        reason=f"{module_path} is not installed in this job; the agreement test above still runs",
    )
    module = importlib.import_module(module_path)

    assert hasattr(module, class_name), (
        f"{configured} does not exist — dictConfig would raise for any service "
        f"loading this config. {module_path} exports: {sorted(n for n in dir(module) if 'Format' in n)}"
    )
