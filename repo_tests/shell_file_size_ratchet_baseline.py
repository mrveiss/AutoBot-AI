# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Second copy of the shell size ceilings (#17353).

This mirrors ``KNOWN_LARGE`` in ``scripts/check_shell_file_size.py``. Two
copies is the point, not an accident: the ratchet test asserts they agree, so
lowering a ceiling means editing BOTH in the same commit.

With one copy, a ceiling lowered in the hook is just a smaller number in the
file the same PR is already editing — nothing outside that edit records what
the size used to be. The mirror is what makes a shrink irreversible: the gap
between a lowered hook and an unlowered mirror is exactly the lines just cut,
and the test refuses to let that gap exist. Same mechanism as the Python gate's
(#14498), for the same reason.

NEVER raise a number here. Never add an entry to admit a new oversized file —
entries are grandfathered history, not a way in.
"""

from __future__ import annotations

RATCHET_BASELINE: dict[str, int] = {
    "autobot-infrastructure/autobot-slm-backend/scripts/bootstrap-slm.sh": 652,
    "autobot-infrastructure/shared/scripts/bulletproof-frontend/zero-downtime-update.sh": 614,
    "autobot-infrastructure/shared/scripts/cleanup-disk-space.sh": 838,
    "autobot-infrastructure/shared/scripts/deployment/validate_access_control.sh": 659,
    "autobot-infrastructure/shared/scripts/install-bare-metal.sh": 882,
    "autobot-infrastructure/shared/scripts/install-slm.sh": 822,
    "autobot-slm-backend/ansible/deploy.sh": 718,
    "install.sh": 1265,
    "scripts/lib/hardcoded-value-rules.sh": 842,
    "scripts/pr-preflight.sh": 818,
}
