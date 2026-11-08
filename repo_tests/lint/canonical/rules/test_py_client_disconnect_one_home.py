# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for py-client-disconnect-one-home (#20939), with a planted control and a tree census."""

from pathlib import Path

from repo_tests._paths import repo_root

from tools.lint import _parse_cache as parse_cache
from tools.lint.canonical.context import Context
from tools.lint.canonical.rules import py_client_disconnect_one_home as rule

REPO = repo_root()


def _handler(clause: str, body: str) -> str:
    """A function whose ``send`` is guarded by one ``except`` clause."""
    return f"def f(ws, logger):\n    try:\n        ws.send()\n    except {clause}:\n        {body}\n"


_CANON = "from autobot_shared.client_disconnect import PEER_CLOSED_ERRORS, log_client_disconnect\n"


def _check(tmp_path: Path, body: str, rel: str = "autobot-backend/api/m.py") -> list:
    f = tmp_path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body, encoding="utf-8")
    tree = parse_cache.parse(body, filename=str(f))
    return rule.check(f, tree, Context(repo_root=tmp_path))


def test_planted_handlers_that_decide_for_themselves_are_flagged(tmp_path):
    for exc in ("WebSocketDisconnect", "ClientDisconnect", "ConnectionResetError", "(OSError, BrokenPipeError)"):
        body = f"def f(ws, logger):\n    try:\n        ws.send()\n    except {exc}:\n        logger.error('x')\n"
        assert len(_check(tmp_path, body)) == 1, exc


def test_attribute_spelling_is_flagged(tmp_path):
    body = _handler("starlette.websockets.WebSocketDisconnect", "pass")
    assert len(_check(tmp_path, body)) == 1


def test_canonical_logger_and_classifier_pass(tmp_path):
    ok = _CANON + _handler("PEER_CLOSED_ERRORS as e", "log_client_disconnect(logger, e, 'f')")
    assert _check(tmp_path, ok) == []
    classified = (
        "def f(ws, logger):\n    try:\n        ws.send()\n    except WebSocketDisconnect as e:\n"
        "        if is_client_disconnect(e):\n            log_client_disconnect(logger, e, 'f')\n"
    )
    assert _check(tmp_path, classified) == []


def test_a_handler_that_reraises_is_a_translation_and_passes(tmp_path):
    body = _handler("WebSocketDisconnect as e", "raise RuntimeError('x') from e")
    assert _check(tmp_path, body) == []


def test_unrelated_handlers_tests_and_the_home_are_ignored(tmp_path):
    other = "def f():\n    try:\n        g()\n    except ValueError:\n        pass\n"
    assert _check(tmp_path, other) == []
    bad = "def f(ws):\n    try:\n        ws.send()\n    except WebSocketDisconnect:\n        pass\n"
    assert _check(tmp_path, bad, "autobot-backend/api/m_test.py") == []
    assert _check(tmp_path, bad, "autobot_shared/client_disconnect.py") == []


def test_the_tree_has_no_violation_and_the_census_is_not_empty():
    handlers = flagged = 0
    for base in rule.TARGETS:
        for p in (REPO / base).rglob("*.py"):
            rel = p.relative_to(REPO).as_posix()
            if not rule._in_scope(rel) or "/.worktrees/" in rel:
                continue
            text = p.read_text(encoding="utf-8")
            if "client_disconnect import" in text and "PEER_CLOSED_ERRORS" in text:
                handlers += 1
            flagged += len(rule.violations(parse_cache.parse(text, filename=str(p))))
    assert handlers >= 15, "census found no migrated handlers: the scan is blind"
    assert flagged == 0
