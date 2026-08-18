# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Shared service-discovery cache TTL (#14465).

Single source of truth for `slm/agent/health_collector.py`'s discovery-sweep
cache TTL and `services/reconciler.py`'s restart-churn window, which must
stay comfortably larger than this TTL -- see `RESTART_CHURN_WINDOW_S`'s own
docstring for why a window too close to the TTL restores pulse-shaped
flapping in the churn signal it replaced.

Previously two independent hardcoded literals (`_SERVICE_DISCOVERY_TTL` in
the agent, `RESTART_CHURN_WINDOW_S`'s `min_v` in the backend) in two
different processes with no guard against drift -- raising one without the
other silently reintroduced the exact bug both were fixed to close. Both
processes already depend on `autobot_shared` (the agent imports
`autobot_shared.redis_client`/`time_utils`), so this adds no new dependency
either side did not already have.

Deliberately NOT env-var-backed, unlike this repo's usual TTL convention: the
agent reads its environment on each fleet node, the backend reads its own on
the manager host -- two different machines, each with its own env. An env
var would need to be set to the SAME value on every node AND the manager for
this to actually stay a single source of truth; a plain shared constant,
shipped in the one codebase both processes deploy from, cannot drift that
way. See `docs/developer/ARCHITECTURE_EXCEPTIONS.md`.
"""

SERVICE_DISCOVERY_TTL_S = 300
