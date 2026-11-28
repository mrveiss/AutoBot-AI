# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The grace every SLM ansible/git runner passes to ``kill_and_reap`` (#14524, #19475, #20924).

A timed-out run is stopped with ``kill_and_reap(proc, process_group=True, terminate_first=True,
bounded=True, grace=KILL_GRACE_S)`` from ``autobot_shared.subprocess_reap``; the spawning call uses
``start_new_session=True`` so the child's pid is its process-group id.
"""

from autobot_shared.env_utils import env_float_clamped

# Grace between SIGTERM and SIGKILL, and the bound on each wait after it. Long enough for
# ansible-playbook's signal handling / a forked ssh child to unwind; short enough that a wedged run
# does not become a second unbounded wait on top of the timeout that triggered it. Clamped, not
# bare: 0 collapses the grace (SIGKILL with no chance to exit on SIGTERM) and inf makes the wait
# unbounded; 60s is generous, a process alive that long after SIGKILL is in D-state.
KILL_GRACE_S = env_float_clamped("AUTOBOT_PLAYBOOK_KILL_GRACE_S", 5.0, min_v=0.1, max_v=60.0)
