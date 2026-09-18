# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16299: backend_secret_key and grafana_admin_password generate on first run.

Both shipped with a guessable role default (`change-me-in-production`,
`admin`). Generation follows the same shape `slm_secret_key` and friends
already use: `slm_manager`'s "Generate security secrets" block produces the
value once (gated on the secrets file not existing yet), persists it to
`slm-secrets.env`, and the consuming role (`backend`, `monitoring`) reads it
back the same way `backend_jwt_secret` already reads `SLM_SECRET_KEY` back
(#10400) — because the consuming role commonly runs on a different host, or
in a different play, than `slm_manager`.

These assert the provisioning wiring, not a live deployment (no ansible
target host is available in this environment) -- see
`repo_tests/secrets_root_key_provisioned_test.py` for the same "assert the
surfaces, not just the consumers" reasoning applied to
`AUTOBOT_SECRETS_ROOT_KEY`.
"""

from __future__ import annotations

import pytest
from repo_tests._paths import repo_root

REPO_ROOT = repo_root()

_SLM_MANAGER_TASKS = REPO_ROOT / "autobot-slm-backend/ansible/roles/slm_manager/tasks/main.yml"
_SLM_SECRETS_TEMPLATE = REPO_ROOT / "autobot-slm-backend/ansible/roles/slm_manager/templates/slm-secrets.env.j2"
_BACKEND_TASKS = REPO_ROOT / "autobot-slm-backend/ansible/roles/backend/tasks/main.yml"
_BACKEND_DEFAULTS = REPO_ROOT / "autobot-slm-backend/ansible/roles/backend/defaults/main.yml"
_MONITORING_GRAFANA_TASKS = REPO_ROOT / "autobot-slm-backend/ansible/roles/monitoring/tasks/grafana.yml"
_MONITORING_DEFAULTS = REPO_ROOT / "autobot-slm-backend/ansible/roles/monitoring/defaults/main.yml"


def _text(path) -> str:
    assert path.is_file(), f"{path} is missing — this guard would otherwise pass vacuously"
    return path.read_text(encoding="utf-8")


def _generate_secrets_block(text: str) -> str:
    """The "SLM | Generate security secrets" task body, up to the next task."""
    start = text.index('name: "SLM | Generate security secrets"')
    end = text.index('name: "SLM | Deploy secrets file"')
    assert start < end, "task order changed -- this guard's slice no longer isolates the generate block"
    return text[start:end]


@pytest.mark.parametrize("var_name", ["backend_secret_key", "grafana_admin_password"])
def test_generated_once_in_slm_manager(var_name: str) -> None:
    text = _text(_SLM_MANAGER_TASKS)
    assert f"{var_name}: >-" in text, f"slm_manager's generate block no longer sets {var_name} (#16299)"


@pytest.mark.parametrize("env_key", ["AUTOBOT_BACKEND_SECRET_KEY", "GRAFANA_ADMIN_PASSWORD"])
def test_no_backfill_for_an_existing_install(env_key: str) -> None:
    """Regression test for a real bug caught before it shipped: unlike the three
    existing backfills in this file (root key, chromadb token, Redis password --
    each enabling a previously-OFF security feature), a backend or Grafana on an
    existing install is already running on ITS CURRENT secret. Backfilling a fresh
    value into an existing install's secrets file would flow through the read-back
    tasks below and silently replace that secret -- signed sessions stop
    validating, an operator logged into Grafana with the old password gets locked
    out. That is exactly the "regenerated credential breaks a running service"
    case the owner's 2026-09-17 ruling excludes. There must be no
    `ansible.builtin.lineinfile` task adding this key to an existing file."""
    text = _text(_SLM_MANAGER_TASKS)
    assert f'"^{env_key}="' not in text, (
        f"a lineinfile backfill for {env_key} exists in slm_manager's tasks -- this would silently "
        "rotate a credential a running service already depends on for every install provisioned "
        "before this change, which the owner's ruling explicitly excludes (see this test's docstring)"
    )


def test_generated_once_gated_on_secrets_file_not_existing() -> None:
    """generate on first run only -- never regenerated on an existing install (owner
    ruling 2026-09-17): the whole set_fact block this test's vars live in must stay
    gated on `not slm_secrets_stat.stat.exists`."""
    generate_block = _generate_secrets_block(_text(_SLM_MANAGER_TASKS))
    assert "backend_secret_key" in generate_block
    assert "grafana_admin_password" in generate_block
    assert "when: not slm_secrets_stat.stat.exists" in generate_block


def test_grafana_password_guard_compares_the_literal_default_not_mere_emptiness() -> None:
    """Regression test for a real bug found while writing this fix: `monitoring` is
    listed in the SAME play as `slm_manager` (playbooks/deploy-slm-manager.yml), and
    Ansible's static `roles:` list loads every listed role's defaults/main.yml up
    front for the whole play -- verified empirically with a throwaway two-role
    playbook, not assumed. So `grafana_admin_password | default('') | length > 0`
    would already see monitoring's own "admin" role default as "the operator set
    this" and never generate -- a silent no-op. The guard must compare against the
    known literal specifically."""
    generate_block = _generate_secrets_block(_text(_SLM_MANAGER_TASKS))
    assert "grafana_admin_password != 'admin'" in generate_block, (
        "the grafana_admin_password generate-or-reuse guard must explicitly exclude "
        "the literal 'admin' default, not just check non-emptiness -- see this "
        "test's docstring for why a naive length-check silently regenerates nothing"
    )


def test_persisted_to_the_secrets_template() -> None:
    text = _text(_SLM_SECRETS_TEMPLATE)
    assert "AUTOBOT_BACKEND_SECRET_KEY={{ backend_secret_key }}" in text
    assert "GRAFANA_ADMIN_PASSWORD={{ grafana_admin_password }}" in text


def test_backend_reads_its_secret_key_back() -> None:
    text = _text(_BACKEND_TASKS)
    assert "AUTOBOT_BACKEND_SECRET_KEY" in text, "backend role no longer reads AUTOBOT_BACKEND_SECRET_KEY back (#16299)"
    assert 'backend_secret_key: "{{ _backend_secret_key_read.stdout | trim }}"' in text


def test_monitoring_reads_the_grafana_password_back() -> None:
    text = _text(_MONITORING_GRAFANA_TASKS)
    assert "GRAFANA_ADMIN_PASSWORD" in text, "monitoring role no longer reads GRAFANA_ADMIN_PASSWORD back (#16299)"
    assert 'grafana_admin_password: "{{ _grafana_admin_password_read.stdout | trim }}"' in text


def test_standalone_fallback_defaults_still_documented() -> None:
    """A backend deployed standalone (no SLM ever reaching it) and monitoring
    deployed standalone (deploy-monitoring.yml) still need SOME default -- these
    are deliberately kept, not dead code, per the owner's 2026-09-17 ruling that
    generation applies at install time and existing/standalone paths are not
    broken by this change."""
    assert 'backend_secret_key: "change-me-in-production"' in _text(_BACKEND_DEFAULTS)
    assert 'grafana_admin_password: "admin"' in _text(_MONITORING_DEFAULTS)
