# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The three infrastructure validators run against today's backend APIs (#18289).

``validate_configuration.py``, ``utilities/validate-security-config.py`` and
``utilities/validate_chat_knowledge.py`` imported names the backend no longer has (the Redis and
WebSocket values of ``config``, the ``auth_middleware`` instance, ``ChatKnowledgeManager`` and
``KnowledgeDecision`` from the router module), and the class guard (#18288) cannot see that: the
module exists, the name does not. Each is loaded by path here and its checks are RUN against the real
backend; the names-resolve test (``infra_analysis_backend_names_resolve_18289_test``) covers the
imports. Not run here: ``validate-security-config``'s user and role checks and the chat-knowledge
manager round trip, which need a configured deployment (users, Redis, a knowledge base).
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from repo_tests._paths import repo_root

SCRIPTS = "autobot-infrastructure/shared/scripts"
#: In a child interpreter: the validators reload and edit the backend's ``config``, so they never run in
#: the test session. argv: script path, then ``name`` or ``name:path_attr=dir`` steps; prints each result.
_DRIVER = textwrap.dedent("""
    import importlib.util, json, pathlib, sys
    spec = importlib.util.spec_from_file_location("validator_under_test", sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = {}
    for step in sys.argv[2:]:
        name, _, override = step.partition(":")
        if override:
            attr, _, value = override.partition("=")
            setattr(module, attr, pathlib.Path(value))
        results[name] = getattr(module, name)()
    print(json.dumps(results))
    """)


def _run(rel: str, *steps: str, tmp_path: Path) -> dict[str, bool]:
    done = subprocess.run(  # noqa: S603 - fixed argv, our own interpreter
        [sys.executable, "-I", "-c", _DRIVER, str(repo_root() / SCRIPTS / rel), *steps],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        timeout=240,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-800:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_configuration_validator_passes_against_the_real_config(tmp_path: Path) -> None:
    steps = ("test_default_configuration", "test_custom_configuration", "test_backend_configuration")
    assert _run("validate_configuration.py", *steps, tmp_path=tmp_path) == dict.fromkeys(steps, True)


def test_the_security_validator_builds_the_middleware_through_the_lazy_getter(tmp_path: Path) -> None:
    assert _run("utilities/validate-security-config.py", "test_auth_middleware", tmp_path=tmp_path) == {
        "test_auth_middleware": True
    }


def test_the_chat_knowledge_validator_finds_the_frontend_files_and_the_router_endpoints(tmp_path: Path) -> None:
    steps = ("test_frontend_components", "test_api_endpoints")
    assert _run("utilities/validate_chat_knowledge.py", *steps, tmp_path=tmp_path) == dict.fromkeys(steps, True)


def test_contrast_a_missing_frontend_file_fails_the_check(tmp_path: Path) -> None:
    """The pre-#18289 shape: paths that do not exist (``autobot-vue/``) fail rather than pass."""
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    result = _run(
        "utilities/validate_chat_knowledge.py", f"test_frontend_components:_REPO_ROOT={empty_root}", tmp_path=tmp_path
    )
    assert result == {"test_frontend_components": False}
