# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The RECORD of guard inputs the python-suite filter does not reach (#15713).

`python_filter_covers_its_guards_test.py` asks a fixed question: does
`.github/filters/python-paths.yml` run the Python suite for every non-Python
file a `repo_tests` guard reads? Where it does not, a change confined to that
file computes ``python != 'true'``, the required-context shim reports
``python-suite`` green, and the guard written to catch that change never runs.

The entries below are the measured status quo, not an approval of it. Each one
is a guard that can be bypassed by editing only its subject.

Draining an entry means widening the filter to cover it -- and that has a real
cost, which is why this is a record rather than a fix: covering the remaining
trees wholesale would run twelve shards on almost every pull request. The
trade is worth making per tree, deliberately, not in one sweep.

Editing rules:

* ``MAX_UNCOVERED_READS`` must EQUAL the measured count, and only ever goes
  DOWN. Equality rather than a bound: spare capacity under a ceiling is room
  for a new bypass to appear without anything failing
* an entry is removed when the filter covers it, never to silence a failure
"""

#: Measured on the sweep that added this guard: 179 guards parsed, 24 of their
#: inputs uncovered. The ansible tree is NOT here -- #15713 covered it in the
#: same change, because it had already broken `Dev_new_gui` once (#15704) and
#: eighteen guards read it, which is the largest concentration in the repo.
UNCOVERED_READS: frozenset[str] = frozenset(
    {
        # CI definitions read by guards that assert on workflow structure. The
        # sharpest case in the set: editing a workflow is exactly when you want
        # the guard that checks workflows to run.
        ".github/actions/setup-python-ci/action.yml",
        ".github/dependabot.yml",
        ".github/filters/code-quality-paths.yml",
        ".github/workflows/auto-merge-base-into-parked-branches.yml",
        ".github/workflows/code-quality-required-context.yml",
        ".github/workflows/code-quality.yml",
        ".github/workflows/frontend-test.yml",
        ".github/workflows/ssot-coverage.yml",
        # Generated frontend types and the API surface guards compare against.
        "autobot-frontend/src/types/generated/api.ts",
        "autobot-slm-frontend/openapi.json",
        "autobot-slm-frontend/src/composables/useAutobotApi.ts",
        "autobot-slm-frontend/src/types/generated/api.ts",
        "autobot-slm-frontend/src/views/tools/admin/TerminalTool.vue",
        # Shell entry points asserted on by shape rather than by extension.
        ".claude/hooks/block-dangerous-commands_test.sh",
        ".mcp/autobot-mcp-server.js",
        "autobot-frontend/scripts/check-ts-delta.sh",
        "docker/generate-secrets.sh",
        "docker/secrets-init.sh",
        "docker/with-secrets.sh",
        # The constraints SSOT, and docs a guard reads for cross-link integrity.
        "constraints/shared.txt",
        "docs/audit/python_314_consistency.md",
        "docs/developer/WSL2_NETWORKING.md",
        "docs/development/MCP_DEBUG_SCENARIOS.md",
        "docs/runbooks/ROTATE_SSH_KEYS.md",
    }
)

#: DOWN-ONLY ceiling. NEVER raise this to let a new uncovered read through:
#: either widen the filter, or the guard has become the thing it replaced.
MAX_UNCOVERED_READS = 24
