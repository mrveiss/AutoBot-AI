# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SSOT defaults that an Ansible role mirrors (#19319).

Ansible cannot import Python, so a role default that must equal an SSOT default is a pinned
mirror: the value is defined here once, the role carries a copy, and a test fails when the two
diverge. ``ssot_config`` imports these for its field defaults; split out of it (#19319) because it
is at its size ceiling.
"""

# Service-auth failure rate limiting (#13326).
# These mirror the values the service_auth Ansible role has always written to
# .env; the Pydantic fields previously defaulted to 0, which made
# ``len(failures) >= max_failures`` true on the very first request and rejected
# every SERVICE_ONLY_PATHS call on a default install.
SERVICE_AUTH_RATE_LIMIT_MAX_FAILURES_DEFAULT = 10
SERVICE_AUTH_RATE_LIMIT_WINDOW_DEFAULT = 300

# Service-auth enforcement gate (#13335) - the third drift in this same block.
# The Ansible role has always written ``true``/``100``; the Pydantic fields
# defaulted to ``""``/``0.0``, so every install that did not go through Ansible
# ran the service-auth middleware in LOGGING MODE with the circuit breaker
# sampling 0% of requests. Unlike #13326 (which failed closed and was loud),
# this pair failed OPEN and was silent. ``tests/test_service_auth_default_parity``
# now pins each of these to the Ansible role default.
SERVICE_AUTH_ENFORCEMENT_MODE_DEFAULT = "true"
SERVICE_AUTH_CIRCUIT_BREAKER_PERCENTAGE_DEFAULT = 100.0

# Replay window for HMAC-signed service requests (#13335). The Ansible role and
# ``export_service_keys.py`` have always written ``AUTH_TIMESTAMP_WINDOW``, but
# no Pydantic field claimed the alias, so ``ServiceAuthManager`` hard-coded 300
# and the operator-facing knob did nothing. The default matches the role so
# wiring it in cannot change behaviour on an existing install.
SERVICE_AUTH_TIMESTAMP_WINDOW_DEFAULT = 300

# Feature-router boot mode (#6690, #19319): whether one failed feature-router import aborts
# startup. #6690 ruled strict wherever a broken import should surface before deploy, and a
# degraded start in production, which prefers a backend missing one router (logged at ERROR,
# published to the router health endpoint) over an outage. Both profiles live here:
#   * DEFAULT -- every process that does not set AUTOBOT_FEATURE_ROUTERS_STRICT: dev checkouts
#     and CI. ``MiscConfig.feature_routers_strict`` defaults to it; the dev compose override
#     example carries it explicitly so it is not inherited from the production base file.
#   * PRODUCTION -- the two production deployments: Ansible-managed backends (the backend role's
#     ``backend_feature_routers_strict``, rendered by ``backend.env.j2``; an inventory may override
#     it) and the ``autobot-backend`` service in ``docker-compose.yml`` (owner ruling on #19319).
# Every carrier is pinned by ``repo_tests/feature_routers_strict_one_home_19319_test.py``.
FEATURE_ROUTERS_STRICT_DEFAULT = "1"
FEATURE_ROUTERS_STRICT_PRODUCTION = "0"
