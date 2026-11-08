# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The setup wizard does not hand stored secrets to ``execute_playbook`` as caller vars (#19005).

Caller-supplied extra vars are written ``!unsafe``; the executor merges the stored secrets itself and
writes them plain. A wizard that passed ``fetch_deploy_secrets()`` as ``extra_vars`` would have tagged
the secrets unsafe (a behaviour change for any secret containing ``{{``) and fetched them twice. The
wizard's source is read, not imported: importing ``api.setup_wizard`` needs the full stub harness.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SOURCE = (Path(__file__).resolve().parents[2] / "api" / "setup_wizard.py").read_text(encoding="utf-8")
_TREE = ast.parse(_SOURCE)


def _execute_playbook_calls() -> list[ast.Call]:
    return [
        n
        for n in ast.walk(_TREE)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "execute_playbook"
    ]


def test_the_wizard_still_calls_the_provisioning_playbook():
    names = [kw.value.value for c in _execute_playbook_calls() for kw in c.keywords if kw.arg == "playbook_name"]
    assert "playbooks/provision-fleet-roles.yml" in names


def test_no_wizard_execute_playbook_call_passes_extra_vars():
    for call in _execute_playbook_calls():
        assert "extra_vars" not in {kw.arg for kw in call.keywords}, ast.unparse(call)[:120]


def test_the_wizard_does_not_fetch_or_import_the_secrets_itself():
    names = {n.id for n in ast.walk(_TREE) if isinstance(n, ast.Name)} | {
        a.name for n in ast.walk(_TREE) if isinstance(n, ast.ImportFrom) for a in n.names
    }
    assert "fetch_deploy_secrets" not in names
