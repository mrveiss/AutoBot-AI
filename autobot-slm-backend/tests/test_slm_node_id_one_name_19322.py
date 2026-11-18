# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM backend resolves the manager's node id from AUTOBOT_SLM_NODE_ID (#19322).

``SLM_NODE_ID`` is honoured only as a deprecated alias, so a manager that registered under it
keeps its id; when both are set and disagree, the canonical name wins. The resolver is lifted out
of ``config.py`` by AST and run alone: importing the module builds ``Settings`` (data dirs, secrets,
database configs), which is not what this test is about.
"""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path

import pytest

from autobot_shared import ssot_config

_CONFIG = Path(__file__).resolve().parents[1] / "config.py"
_DEFAULT = ssot_config.MiscConfig.model_fields["slm_node_id"].default


def _resolve(monkeypatch, canonical: str | None, legacy: str | None) -> str:
    for name, value in (("AUTOBOT_SLM_NODE_ID", canonical), ("SLM_NODE_ID", legacy)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    misc = ssot_config.MiscConfig(_env_file=None)
    monkeypatch.setattr(ssot_config, "get_config", lambda: type("C", (), {"misc": misc})())
    tree = ast.parse(_CONFIG.read_text(encoding="utf-8"))
    wanted = {"_LEGACY_SLM_NODE_ID_VAR", "_resolve_slm_node_id"}
    nodes = [n for n in tree.body if getattr(n, "name", None) in wanted or _assigns(n, wanted)]
    assert len(nodes) == 2, "config.py no longer defines the resolver and its legacy-name constant"
    namespace = {"os": os, "logger": logging.getLogger("slm-config-19322")}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(_CONFIG), "exec"), namespace)  # noqa: S102  # nosec B102
    return namespace["_resolve_slm_node_id"]()


def _assigns(node: ast.stmt, names: set[str]) -> bool:
    return isinstance(node, ast.Assign) and any(getattr(t, "id", None) in names for t in node.targets)


@pytest.mark.parametrize(
    ("canonical", "legacy", "expected"),
    [
        (None, None, _DEFAULT),  # nothing set: the SSOT default
        ("99-Renamed", None, "99-Renamed"),  # the canonical name is read
        (None, "77-Legacy", "77-Legacy"),  # a legacy-only deployment keeps its id
        ("99-Renamed", "77-Legacy", "99-Renamed"),  # both set: the canonical name wins
        (_DEFAULT, "77-Legacy", _DEFAULT),  # canonical set to the default value still wins
        # Blank counts as unset, as ssot-config.sh treats it: never an empty manager id.
        ("", "77-Legacy", "77-Legacy"),  # blank canonical: the legacy name is honoured
        ("   ", "77-Legacy", "77-Legacy"),  # whitespace is blank too
        ("", None, _DEFAULT),  # blank canonical, no legacy: the SSOT default
        ("", "  ", _DEFAULT),  # both blank: the SSOT default
        (" 99-Renamed ", None, "99-Renamed"),  # a padded canonical value is stripped
    ],
)
def test_the_manager_node_id_resolves_canonical_first(monkeypatch, canonical, legacy, expected) -> None:
    assert _resolve(monkeypatch, canonical, legacy) == expected
