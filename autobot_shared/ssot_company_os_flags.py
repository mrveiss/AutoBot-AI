# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company OS feature flags, split out of ``ssot_config.FeatureConfig`` (#19934).

``ssot_config.py`` is over the file-size ceiling and may not grow, so the Company OS
switches live here and ``FeatureConfig`` inherits them: ``config.feature.<name>`` and
``is_feature_enabled`` are unchanged. ``RedactedSettings`` is defined in ``ssot_config``,
so this base uses ``BaseSettings`` directly; ``FeatureConfig`` supplies the redacted repr.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from autobot_shared.paths import project_root


class CompanyOsFeatureFlags(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(project_root() / ".env"), env_file_encoding="utf-8", extra="ignore")

    # Issue #16950/#16974: enforce each Company OS agent's org-role tool bound at
    # dispatch. Off by default -- copilot_local/copilot_subscription take no
    # tool-permission flags today, so turning this on refuses every dispatch to
    # those two adapters (codex_subscription is already a non-functional stub).
    # Flips on once those adapters can actually enforce a bound, or the owner
    # accepts the refusal; whether the underlying CLI even exposes such a flag
    # is unknown and external to this repo.
    org_role_bound_enabled: bool = Field(default=False, alias="AUTOBOT_FEATURE_ORG_ROLE_BOUND")

    # Issue #19934: the Workflow Planner (plan a process before it becomes a workflow).
    # Master switch, off by default: with it off every /llc/company-os/workflow-plans
    # route is a 404. Its tunables are AUTOBOT_COMPANY_OS_WORKFLOW_PLANNER_* settings.
    company_os_workflow_planner_enabled: bool = Field(
        default=False, alias="AUTOBOT_FEATURE_COMPANY_OS_WORKFLOW_PLANNER"
    )
