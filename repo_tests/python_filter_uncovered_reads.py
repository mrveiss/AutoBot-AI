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

#: Measured on the sweep that added this guard: 178 guards parsed, 27 of their
#: inputs uncovered. The ansible tree is NOT here -- #15713 covered it in the
#: same change, because it had already broken `main` once (#15704) and
#: eighteen guards read it, which is the largest concentration in the repo.
UNCOVERED_READS: frozenset[str] = frozenset(
    {
        ".bandit",
        ".claude/hooks/block-dangerous-commands_test.sh",
        ".dockerignore",
        ".flake8",
        ".github/actions/setup-python-ci/action.yml",
        ".github/actions/setup-python-suite/action.yml",
        ".github/dependabot.yml",
        ".github/filters/code-quality-paths.yml",
        ".github/workflows/auto-merge-base-into-parked-branches.yml",
        ".github/workflows/code-quality-required-context.yml",
        ".github/workflows/code-quality.yml",
        ".github/workflows/frontend-test.yml",
        ".github/workflows/hardened-smoke-test.yml",
        ".github/workflows/marker-tests.yml",
        ".github/workflows/ssot-coverage.yml",
        ".mcp/autobot-mcp-server.js",
        ".pre-commit-config.yaml",
        "autobot-frontend/scripts/check-ts-delta.sh",
        "autobot-frontend/src/types/generated/api.ts",
        "autobot-slm-frontend/openapi.json",
        "autobot-slm-frontend/src/composables/useAutobotApi.ts",
        "autobot-slm-frontend/src/types/generated/api.ts",
        "autobot-slm-frontend/src/views/tools/admin/TerminalTool.vue",
        # #17129: doc_index_worktree_contamination_16934_test.py's "CLAUDE.md" is a
        # literal it writes inside a synthetic tmp_path repo fixture, never a read of
        # the real root-level file -- covering the real path in the filter would run
        # twelve shards on every CLAUDE.md edit for a guard that does not depend on
        # its content. Recorded, not covered, per this file's own trade-off rule.
        "CLAUDE.md",
        "constraints/shared.txt",
        "docker/generate-secrets.sh",
        "docker/secrets-init.sh",
        "docker/with-secrets.sh",
        "docs/audit/python_314_consistency.md",
        "docs/developer/CLAUDE_GIT.md",
        "docs/developer/THREAT_MODEL.md",
        "docs/developer/WSL2_NETWORKING.md",
        "docs/development/MCP_DEBUG_SCENARIOS.md",
        "docs/runbooks/ROTATE_SSH_KEYS.md",
        "pytest.ini",
        "requirements-ci.txt",
        "requirements-gpu-torch.txt",
        "requirements-gpu.txt",
        "requirements.txt",
        # #17133: "README.md" is a literal pre_push_open_pr_cap_17006_test.py
        # writes inside its own synthetic tmp_path repo fixture (_seed_repo),
        # never a read of the real root-level file -- same shape as the
        # CLAUDE.md entry above (#17129).
        "README.md",
        # #17133: secrets_baseline_reasons.py's SPECIFIC_REASONS dict carries
        # this path as a (filename, type, hash) key, never opens the file --
        # the guard works off the baseline's stored hash, not this doc's
        # live content, so covering it would run twelve shards on every
        # unrelated edit to this doc for a guard that does not depend on it.
        "docs/developer/GITHUB_FILING_CREDENTIAL_ROTATION.md",
    }
)

#: RAISED 27 -> 39 by #15900, and that is a denominator correction, not a
#: licence. 27 was measured by a detector that could not see composed reads
#: unless the module named its root `_REPO_ROOT` -- 87 of 133 guards name it
#: something else. The bypasses below were always there; nothing about the tree
#: changed. Distinguish the two cases whenever this number moves up: correcting
#: an instrument that was under-counting is not the same act as accepting a new
#: bypass, and only the second is what "only ever goes DOWN" forbids.
#:
#: LOWERED 39 -> 38 by #16237: the filter now covers the ratchet base guard's
#: workflow, because `workflow_rc_capture_test.py` runs its audit step on a
#: planted failing path and has to run whenever that step changes.
#:
#: RAISED 38 -> 39 by #17129: `CLAUDE.md` above is a new bypass (a guard's
#: tmp_path fixture literal, not a real-file dependency), not a denominator
#: correction -- the same run's other new find,
#: `.github/workflows/auto-fix-generated-types.yml`, was covered in the filter
#: instead and so is not counted here.
#:
#: RAISED 39 -> 41 by #17133: `README.md` (a synthetic tmp_path fixture
#: literal, same shape as the CLAUDE.md entry) and
#: `docs/developer/GITHUB_FILING_CREDENTIAL_ROTATION.md` (a baseline-reasons
#: dict key, never opened) above are both new bypasses, not a denominator
#: correction.
MAX_UNCOVERED_READS = 41
