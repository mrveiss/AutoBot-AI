# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""PostgreSQL identity table -- the one home for every database, role and host default (#19320).

AutoBot talks to THREE distinct databases. Each value below is what provisioning
actually creates today, so a reader that falls back to it connects where the host
already is; it is not a preference.

=================  ======================  ===========================  =====================
Concept            Env var (canonical)     Fleet (installer + Ansible)  Docker compose
=================  ======================  ===========================  =====================
User-mgmt DB       AUTOBOT_POSTGRES_DB     ``autobot_users``            ``autobot_users``
Backend role       AUTOBOT_POSTGRES_USER   ``autobot_app``              ``autobot`` (owner)
User-mgmt DB host  AUTOBOT_POSTGRES_HOST   ``127.0.0.1``                ``autobot-postgres``
SLM role           SLM_POSTGRES_USER       ``slm_app``                  ``autobot`` (owner)
SLM control DB     SLM_DATABASE_URL        ``slm``                      ``autobot_slm``
SLM users DB       SLM_POSTGRES_DB         ``slm_users``                ``slm_users``
=================  ======================  ===========================  =====================

The SLM reaches the user-management DB with ITS OWN role (``slm_app``), never the
backend's: that is why the SLM's role is ``SLM_POSTGRES_USER`` and not
``AUTOBOT_POSTGRES_USER`` (which the SLM still honours as a deprecated alias).

Compose sets every value explicitly; its cluster owner role is the image's
``POSTGRES_USER`` and is reused as the app role, so the compose column is a
deployment value, not a code default. Python readers import these names; the
Ansible, compose, SQL and shell copies are pinned to them by
``repo_tests/postgres_identity_one_source_19320_test.py``.
"""

from __future__ import annotations

#: AutoBot application user-management database (backend + SLM ``autobot_users`` engine).
USERS_DB_NAME = "autobot_users"
#: Login role the AutoBot backend uses on ``USERS_DB_NAME`` (fleet provisioning).
USERS_DB_ROLE = "autobot_app"
#: Host of ``USERS_DB_NAME`` as the fleet's backend.env renders it.
USERS_DB_HOST = "127.0.0.1"
#: Port every provisioning path uses.
DB_PORT = 5432

#: Host of the SLM's own databases (``SLM_POSTGRES_HOST``): always local to the SLM.
SLM_DB_HOST = "127.0.0.1"
#: SLM control-plane database (``SLM_DATABASE_URL``) on the fleet.
SLM_DB_NAME = "slm"
#: SLM admin-users database (``SLM_POSTGRES_DB``).
SLM_USERS_DB_NAME = "slm_users"
#: Login role the SLM uses on ``SLM_DB_NAME``, ``SLM_USERS_DB_NAME`` and ``USERS_DB_NAME``.
SLM_DB_ROLE = "slm_app"

#: Docker compose: the postgres image's owner role (``AUTOBOT_POSTGRES_USER``), reused as the app role.
COMPOSE_OWNER_ROLE = "autobot"
#: Docker compose: the SLM control-plane database (``SLM_DB_NAME``).
COMPOSE_SLM_DB_NAME = "autobot_slm"
#: Docker compose: the postgres service name.
COMPOSE_DB_HOST = "autobot-postgres"
