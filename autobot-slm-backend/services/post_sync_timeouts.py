# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Env-backed ceilings for post-sync work (#14275, #17455).

Its own module so ``services/sync_orchestrator.py`` can read the post-sync ceiling without
importing the recorder (and with it the ORM model), and so there is one definition of each.
"""

from autobot_shared.env_utils import env_int

# Seconds a post-sync command may run before it is abandoned (#14275). A `pip install` on a
# slow link takes far longer than a service restart, so an operator can raise it.
POST_SYNC_TIMEOUT_S = env_int("AUTOBOT_SYNC_POST_CMD_TIMEOUT_S", 300)

# Seconds one `sudo -n systemctl restart` may take before it is recorded as failed (#17455).
# Env-backed because a heavy unit on a slow node legitimately takes longer.
RESTART_TIMEOUT_S = env_int("AUTOBOT_SYNC_RESTART_TIMEOUT_S", 60)
