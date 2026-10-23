# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Extra vars for a role's registry-path ansible run, split out of ``api/roles.py`` (#19040).

``api/roles.py`` is a grandfathered large file and may not grow.
"""

from __future__ import annotations

SLM_AGENT_PLAYBOOK = "playbooks/deploy-slm-agent.yml"


def role_procedure_extra_vars(role) -> dict:
    """Extra vars for ``run_role_full_procedure`` (#19040).

    The slm-agent playbook also runs the ``common`` role (emergency admin user and sudo, SSH keys,
    UFW reset). The registry path (Migrate/Redeploy, co-located update) stays agent-only, so it
    switches that role off; the UI deploy button passes nothing and keeps the playbook default.
    """
    extra_vars: dict = {"role_name": role.name}
    if role.ansible_playbook == SLM_AGENT_PLAYBOOK:
        extra_vars["slm_agent_run_common"] = False
    return extra_vars
