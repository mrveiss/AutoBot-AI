# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""No SLM API logger call passes a request body's ``.value`` (#20485).

Settings and config values can hold credentials, so a handler logs the key and
never the value the caller sent. This walks every ``logger.<level>(...)`` call
under ``autobot-slm-backend/api/`` and fails on an argument that reads
``.value`` off a request-body name (``request``, ``body``, ``payload``,
``data`` or ``*_data``). Enum ``.value`` reads (``service_type.value``) are not
request bodies and are not flagged.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

_API = repo_root() / "autobot-slm-backend" / "api"
_LEVELS = {"debug", "info", "warning", "error", "critical", "exception", "log"}
_BODY_NAMES = {"request", "body", "payload", "data"}


def _is_body_name(name: str) -> bool:
    return name in _BODY_NAMES or name.endswith("_data")


def offending_lines(source: str) -> list[int]:
    """Line numbers of logger calls that pass ``<request-body>.value``."""
    hits: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in _LEVELS:
            continue
        for arg in [*node.args, *(kw.value for kw in node.keywords)]:
            for sub in ast.walk(arg):
                if (
                    isinstance(sub, ast.Attribute)
                    and sub.attr == "value"
                    and isinstance(sub.value, ast.Name)
                    and _is_body_name(sub.value.id)
                ):
                    hits.append(node.lineno)
    return hits


def test_detector_flags_a_request_value_and_spares_an_enum():
    """Control: the detector fires on the bad shape, and not on the benign ones."""
    assert offending_lines("logger.info('set %s', request.value)") == [1]
    assert offending_lines("logger.info('set %s', setting_data.value)") == [1]
    assert offending_lines("logger.info('svc %s', service_type.value)") == []
    assert offending_lines("logger.info('set %s', key)") == []


def test_api_dir_is_scanned():
    assert len(list(_API.glob("*.py"))) > 10


def test_no_slm_api_logger_passes_a_request_value():
    found = {}
    for path in sorted(_API.glob("*.py")):
        lines = offending_lines(path.read_text(encoding="utf-8"))
        if lines:
            found[path.name] = lines
    assert not found, f"logger call passes a request body .value (may be a credential): {found}"
