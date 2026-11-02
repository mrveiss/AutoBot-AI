# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Frozen runtime `<client>.keys(<pattern>)` sites (#18999; guard: `redis_keys_runtime_18999_test`).

A shrink-only RATCHET: a count is exact. A new site, or another site in a listed file, fails the
guard; a site that leaves the tree makes its entry stale and fails until lowered or removed.
Replace a site with `autobot_shared.redis_scan.scan_keys` / `count_keys` or an index and drop
its entry in the same change -- never raise a count.

Frozen on origin/main 7420f3bd54 (after the two skill_metrics sites moved to SCAN).
Entry: ``repo-relative path -> site count``.
"""

from __future__ import annotations

BASELINE: dict[str, int] = {
    "autobot-backend/a2a/trust_score.py": 2,
    "autobot-backend/agents/classification_agent.py": 1,
    "autobot-backend/agents/npu_code_search_agent.py": 4,
    "autobot-backend/api/analytics_evolution.py": 3,
    "autobot-backend/api/codebase_analytics/progress_tracker.py": 1,
    "autobot-backend/api/error_monitoring.py": 2,
    "autobot-backend/api/knowledge.py": 2,
    "autobot-backend/api/knowledge_grounding.py": 1,
    "autobot-backend/api/system.py": 1,
    "autobot-backend/initialization/router_registry/feature_routers.py": 1,
    "autobot-backend/llc/services/portability.py": 1,
    "autobot-backend/security/enterprise/threat_detection/learner.py": 1,
    "autobot-backend/services/agent_analytics.py": 1,
    "autobot-backend/services/npu_pipeline/invalidation.py": 1,
    "autobot-backend/services/npu_pipeline/plan_cache.py": 1,
    "autobot-backend/services/npu_worker_manager.py": 1,
    "autobot-backend/utils/advanced_cache_manager.py": 3,
    "autobot-backend/utils/long_running_operations/checkpoint_manager.py": 3,
    "autobot_shared/coordination/shared_runtime_bag.py": 1,
    "autobot_shared/error_boundaries/boundary_manager.py": 1,
}
