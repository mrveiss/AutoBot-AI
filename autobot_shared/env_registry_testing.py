# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Testing-only AUTOBOT_* environment variable registrations.

Split out of ``env_registry.py`` to keep that file under its grandfathered
file-size ceiling (#14236) while making room to register a new "terminal"
component variable there (#14961) — ``env_registry.py`` was already at its
ceiling with no slack for either addition. This is the one "testing"-component
entry that lived at the tail of that file; relocated verbatim rather than
merged into ``env_registry_terminal.py`` so neither sibling file mixes
unrelated components (see ``env_registry_ai.py``'s docstring for the same
reasoning).

Importing this module registers the variable below into
``autobot_shared.env_registry.REGISTRY`` as a side effect, exactly like the
``register_env_var(...)`` calls in ``env_registry.py`` itself. It is imported
from there, after ``EnvVarSpec``/``register_env_var``/``REGISTRY`` are
defined, so nothing ever observes a partially-populated registry.

Closes GH#7081.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_LIVE_PROBE_TIMEOUT_SECONDS",
        type=float,
        default=1.0,
        description=(
            "Seconds a test's live-service precondition probe waits for a TCP connect "
            "before reporting the service as absent and skipping "
            "(autobot_shared/live_service_probe.py, #14930). Short by default: a "
            "refused loopback connect returns immediately, and this runs once per "
            "endpoint per process. Raise it when probing a fleet host across a link "
            "slow enough that a live service could be mistaken for a missing one."
        ),
        component="testing",
        range=(0.1, 60.0),
    )
)
