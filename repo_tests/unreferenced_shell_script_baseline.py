# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Shell scripts under the infrastructure tree that nothing yet references (#15079).

A **down-only ratchet.** Entries come off this list; they never go on. A script
that gains a reference -- a caller, or a documented operator procedure -- must be
removed from here in the same change, and ``unreferenced_shell_script_test.py``
fails while a stale entry remains.

Being listed here is not approval. Each of these is either unfinished wiring or a
manual tool whose documentation was never written, and #15127 tracks working
through them. #15127's first batch took ten off this list: five retired, two
wired in, three recorded as operator tools. Eleven remain, each still undecided
-- see that issue for what is known about them. The list exists so that the *next* script to arrive unreferenced
fails immediately instead of joining a pile nobody is counting.
"""

from __future__ import annotations

KNOWN_UNREFERENCED: frozenset[str] = frozenset(
    {
        "autobot-infrastructure/shared/scripts/backup_ollama_models.sh",
        "autobot-infrastructure/shared/scripts/build_secure_sandbox.sh",
        "autobot-infrastructure/shared/scripts/cleanup-legacy-python.sh",
        "autobot-infrastructure/shared/scripts/debug_chat_system.sh",
        "autobot-infrastructure/shared/scripts/fix-frontend-dependencies.sh",
        "autobot-infrastructure/shared/scripts/start_containers.sh",
        "autobot-infrastructure/shared/scripts/start_seq.sh",
        "autobot-infrastructure/shared/scripts/utilities/batch-configure-vms.sh",
        "autobot-infrastructure/shared/scripts/utilities/enable-phase4-enterprise.sh",
        "autobot-infrastructure/shared/scripts/utilities/ollama_thread_utility.sh",
        "autobot-infrastructure/shared/scripts/utilities/security-audit.sh",
    }
)
