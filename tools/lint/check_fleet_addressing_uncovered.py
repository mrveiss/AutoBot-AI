#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#17440 — the fleet range in the file kinds no other guard scans.

#15208 closed `docs/**.md`. This closes what that left, and the gap was most of
it: of every fleet-range literal in tracked files, **54 sit in an extension the
hardcoded-value hook scans, 6 in the Markdown #15208 guards, and 549 in neither.**
Roughly nine in ten were unguarded, in a PUBLIC repository.

WHERE THE GAP CAME FROM. Each existing mechanism is correct and narrow, and
nothing owned the complement:

    scripts/lib/hardcoded-value-rules.sh   HV_SCAN_EXTENSIONS (a short source-extension list)
    check_docs_no_fleet_addressing.py      Markdown under docs/ only (#15208)
    check_no_hardcoded_ip_fallbacks.py     Python os.getenv fallbacks only (#6783)
    eslint no-hardcoded-vm-ip              TypeScript literals only

`.md` outside `docs/` alone held 311 occurrences across 65 files, because two
thirds of this repository's Markdown is READMEs sitting next to the code they
describe rather than under `docs/`. `.json` held 148 more — committed Grafana
dashboards and captured connectivity-test results, which are reachability maps
rather than prose: which address answered, on which port, at a timestamp.

THE PATTERN IS NOT COPIED, AND NEITHER IS THE EXTENSION LIST. Both are parsed
from `scripts/lib/hardcoded-value-rules.sh` at runtime -- the pattern through
`check_docs_no_fleet_addressing.fleet_address_pattern()`, which already does it
and already aborts loudly on an unreadable source. A renumbered fleet or a
widened extension list updates every guard at once, and this module's population
is *defined* as the complement of the others: extend `HV_SCAN_EXTENSIONS` and
these files leave this baseline automatically rather than being guarded twice.

NO ADDRESS IS STORED HERE. The baseline is `path -> count`. This file is as
public as the ones it guards, so a baseline keyed by the literal would republish
every address it exists to contain -- the same mistake one directory across.

WHY A BASELINE RATHER THAN A CLEAN SWEEP. 549 occurrences across 107 files is
not one commit's work, and four of those files are captured runtime output whose
removal is a data decision an agent does not get to make on its own (#17038).
The ratchet makes the number monotone: nothing new lands, and every removal is
locked in. It is not a licence for the existing 549 -- the shortlist and its
tiers are on #17440 for the owner to rule on.

Mutation check, all four verified before this landed: a fleet-range literal in
a file not in `BASELINE`, a baselined count that grows, an improvement left
unrecorded, and an unparseable rule source each make `audit()` report -- and
`test_the_tree_is_clean_against_its_baseline` is what surfaces the first three
in CI. `test_the_baseline_stores_no_address` is the load-bearing one: it fails
if any line of this module matches the pattern it guards.

Exit code:
  0 -- clean
  1 -- a new file, a grown count, or a stale baseline entry
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from check_docs_no_fleet_addressing import fleet_address_pattern, repo_root  # noqa: E402

RULES_REL = "scripts/lib/hardcoded-value-rules.sh"
SELF_REL = "tools/lint/check_fleet_addressing_uncovered.py"

#: Below this, the sweep has stopped reaching the tree and a clean result means
#: nothing.
#:
#: Measured against the UNCOVERED population, which is the only one this guard
#: sees: **1085** files. The first value here was 6000, taken from the 10,815
#: tracked files in the whole tree -- a number measuring a different question,
#: and the floor refused it on the first run. 700 leaves ordinary churn alone
#: and still fires on a collapse.
DISCOVERY_FLOOR = 700

_HV_EXTENSIONS = re.compile(r"^HV_SCAN_EXTENSIONS='(?P<exts>[^']+)'", re.MULTILINE)


class RuleSourceError(RuntimeError):
    """The shared rule set could not be read or parsed."""


def scanned_extensions(base: pathlib.Path | None = None) -> frozenset[str]:
    """`HV_SCAN_EXTENSIONS`, parsed from the one source (never restated).

    Raises rather than defaulting: an unread list and an empty one are
    indistinguishable to every caller, and an empty one would silently widen
    this guard's population to the whole tree.
    """
    root = base or repo_root()
    try:
        text = (root / RULES_REL).read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - environment failure
        raise RuleSourceError(f"cannot read {RULES_REL}: {exc}") from exc
    match = _HV_EXTENSIONS.search(text)
    if not match:
        raise RuleSourceError(f"{RULES_REL} no longer assigns HV_SCAN_EXTENSIONS")
    exts = frozenset(e for e in match.group("exts").split("|") if e)
    if not exts:
        raise RuleSourceError(f"{RULES_REL} assigns an empty HV_SCAN_EXTENSIONS")
    return exts


def tracked_files(base: pathlib.Path | None = None) -> list[str]:
    """Every tracked path, through the ONE canonical enumeration.

    Not a direct ``git ls-files``: that shells out without scrubbing ``GIT_DIR``
    (#15176/#15245 -- a hook exports it and the query then answers for a
    different repository), and ``one_git_enumeration_15926_test`` counts direct
    calls with a floor that only shrinks, so a new guard rolling its own is a
    regression even while it works. Both were caught here by the pre-commit
    hooks rather than by review.
    """
    from _scan_helpers import EmptyEnumeration, tracked_paths  # noqa: PLC0415

    try:
        return tracked_paths(base or repo_root())
    except EmptyEnumeration:
        return []


def is_covered(rel: str, exts: frozenset[str]) -> bool:
    """True when some OTHER guard already scans this file.

    The complement is this module's whole population, so widening
    `HV_SCAN_EXTENSIONS` or #15208's reach shrinks this one rather than
    double-guarding a file.
    """
    name = rel.rsplit("/", 1)[-1]
    if "." in name and name.rsplit(".", 1)[-1] in exts:
        return True
    return rel.startswith("docs/") and rel.endswith(".md")


def uncovered_counts(base: pathlib.Path | None = None) -> tuple[dict[str, int], int]:
    """(path -> fleet-range occurrences, files reached)."""
    root = base or repo_root()
    exts = scanned_extensions(root)
    pattern = fleet_address_pattern(root)
    counts: dict[str, int] = {}
    reached = 0
    for rel in tracked_files(root):
        if is_covered(rel, exts) or rel == SELF_REL:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        reached += 1
        found = len(pattern.findall(text))
        if found:
            counts[rel] = found
    return counts, reached


#: path -> occurrences permitted today. **This may only SHRINK.**
#: No address appears here by design -- see the module docstring.
BASELINE: dict[str, int] = {
    ".claude/agents/frontend-engineer-agent.md": 4,
    ".claude/skills/bugfix/SKILL.md": 3,
    ".claude/skills/deploy/SKILL.md": 6,
    "CHANGELOG.md": 11,
    "autobot-backend/README.md": 1,
    "autobot-backend/resources/prompts/chat/installation_help.md": 1,
    "autobot-backend/resources/prompts/chat/troubleshooting.md": 3,
    "autobot-backend/skills/builtin/bugfix/SKILL.md": 3,
    "autobot-browser-worker/README.md": 1,
    "autobot-frontend/README.md": 1,
    "autobot-frontend/src/components/examples/AsyncOperationExample.delivery.md": 1,
    "autobot-frontend/src/components/examples/AsyncOperationExample.integration.md": 4,
    "autobot-frontend/src/components/examples/BEFORE_AFTER_COMPARISON.md": 12,
    "autobot-frontend/src/components/examples/README.md": 3,
    "autobot-frontend/src/composables/useConnectionTester.examples.md": 12,
    "autobot-infrastructure/README.md": 7,
    "autobot-infrastructure/autobot-ai-stack/README.md": 2,
    "autobot-infrastructure/autobot-ai-stack/templates/autobot-ai-stack.service": 1,
    "autobot-infrastructure/autobot-backend/README.md": 8,
    "autobot-infrastructure/autobot-browser-worker/README.md": 2,
    "autobot-infrastructure/autobot-browser-worker/templates/autobot-browser-worker.service": 1,
    "autobot-infrastructure/autobot-database/README.md": 4,
    "autobot-infrastructure/autobot-database/templates/autobot-chromadb.service": 1,
    "autobot-infrastructure/autobot-database/templates/autobot-postgres.service": 1,
    "autobot-infrastructure/autobot-database/templates/autobot-redis.service": 1,
    "autobot-infrastructure/autobot-frontend/README.md": 5,
    "autobot-infrastructure/autobot-monitoring/README.md": 6,
    "autobot-infrastructure/autobot-npu-worker/README.md": 3,
    "autobot-infrastructure/autobot-npu-worker/templates/autobot-npu-worker.service": 1,
    "autobot-infrastructure/autobot-ollama/README.md": 6,
    "autobot-infrastructure/autobot-ollama/templates/autobot-ollama.service": 1,
    "autobot-infrastructure/autobot-shared/README.md": 4,
    "autobot-infrastructure/autobot-slm-agent/README.md": 2,
    "autobot-infrastructure/autobot-slm-backend/README.md": 4,
    "autobot-infrastructure/autobot-slm-database/README.md": 3,
    "autobot-infrastructure/autobot-slm-frontend/README.md": 4,
    "autobot-infrastructure/shared/config/environment-files.md": 3,
    "autobot-infrastructure/shared/config/grafana/dashboards/autobot-multi-machine.json": 44,
    "autobot-infrastructure/shared/config/grafana/grafana.ini": 1,
    "autobot-infrastructure/shared/mcp/tools/knowledge-base-mcp/README.md": 3,
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/README.md": 5,
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/correlate-unfinished-tasks.cjs": 1,
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/generate-insights.cjs": 2,
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/ingest-conversation.cjs": 1,
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/test_conversation.json": 1,
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/validate-fixes.cjs": 7,
    "autobot-infrastructure/shared/scripts/bulletproof-frontend/README.md": 2,
    "autobot-infrastructure/shared/scripts/hooks/slm-post-commit": 1,
    "autobot-infrastructure/shared/scripts/systemd/autobot-frontend.service": 2,
    "autobot-infrastructure/shared/scripts/systemd/slm-admin-ui.service": 1,
    "autobot-infrastructure/shared/scripts/utilities/README-SECURITY.md": 4,
    "autobot-infrastructure/shared/tests/KNOWLEDGE_MANAGER_TESTS_README.md": 1,
    "autobot-infrastructure/shared/tests/README_AGENT_OPTIMIZATION_TESTS.md": 1,
    "autobot-infrastructure/shared/tests/integration/README_KB_INTEGRATION_TESTS.md": 4,
    "autobot-infrastructure/shared/tests/performance/results/async_baseline_20251009_214400.json": 1,
    "autobot-infrastructure/shared/tests/performance/results/async_baseline_20251010_075214.json": 1,
    "autobot-infrastructure/shared/tests/results/COMPREHENSIVE_AUTOBOT_VALIDATION_REPORT_20250910.md": 5,
    "autobot-infrastructure/shared/tests/results/COMPREHENSIVE_FRONTEND_TEST_REPORT.md": 4,
    "autobot-infrastructure/shared/tests/results/FRONTEND_FINAL_TEST_REPORT.md": 9,
    "autobot-infrastructure/shared/tests/results/KB_ASYNC_009_INTEGRATION_TESTS_COMPLETION_REPORT.md": 7,
    "autobot-infrastructure/shared/tests/results/MEMORY_GRAPH_TEST_METRICS.json": 1,
    "autobot-infrastructure/shared/tests/results/api_backend_test_results_20250927_203400.json": 1,
    "autobot-infrastructure/shared/tests/results/api_backend_test_summary_20250927_203400.txt": 1,
    "autobot-infrastructure/shared/tests/results/chunk-loading-test-results.json": 1,
    "autobot-infrastructure/shared/tests/results/codebase_indexing_test_results.json": 1,
    "autobot-infrastructure/shared/tests/results/comprehensive_frontend_analysis_report.md": 8,
    "autobot-infrastructure/shared/tests/results/comprehensive_test_report_20250910_232041.json": 6,
    "autobot-infrastructure/shared/tests/results/frontend_connectivity_summary_2025-09-28T16-35-57-946Z.txt": 24,
    "autobot-infrastructure/shared/tests/results/frontend_connectivity_test_2025-09-28T16-35-57-946Z.json": 29,
    "autobot-infrastructure/shared/tests/results/frontend_test_progress.md": 2,
    "autobot-infrastructure/shared/tests/results/frontend_test_report.md": 6,
    "autobot-infrastructure/shared/tests/results/frontend_test_todo.md": 3,
    "autobot-infrastructure/shared/tests/results/integration_test_summary.json": 8,
    "autobot-infrastructure/shared/tests/results/phase9_comprehensive_test_report_20250910_232041.json": 6,
    "autobot-infrastructure/shared/tests/results/quick_infrastructure_assessment_20250927_212903.json": 2,
    "autobot-infrastructure/shared/tests/results/system_validation_20250910_215508.json": 19,
    "autobot-infrastructure/shared/tests/results/system_validation_20250910_215839.json": 25,
    "autobot-npu-worker/README.md": 1,
    "autobot-npu-worker/resources/windows-npu-worker/DEPLOYMENT_SUMMARY.md": 12,
    "autobot-npu-worker/resources/windows-npu-worker/INSTALLATION.md": 9,
    "autobot-npu-worker/resources/windows-npu-worker/NETWORK_INFO_FEATURE.md": 5,
    "autobot-npu-worker/resources/windows-npu-worker/PACKAGE_INFO.txt": 7,
    "autobot-npu-worker/resources/windows-npu-worker/QUICK_START.md": 6,
    "autobot-npu-worker/resources/windows-npu-worker/README.md": 7,
    "autobot-npu-worker/resources/windows-npu-worker/scripts/check-health.ps1": 2,
    "autobot-slm-backend/QUICK_REFERENCE.md": 2,
    "autobot-slm-backend/README.md": 4,
    "autobot-slm-backend/README_NEW_ENDPOINTS.md": 3,
    "autobot-slm-backend/ansible/FIREWALL_SAFETY.md": 1,
    "autobot-slm-backend/ansible/QUICK_START.md": 6,
    "autobot-slm-backend/ansible/README-BACKEND-DEADLOCK-FIX.md": 1,
    "autobot-slm-backend/ansible/README-PLAYBOOKS.md": 32,
    "autobot-slm-backend/ansible/ROLE_STRUCTURE_README.md": 12,
    "autobot-slm-backend/ansible/inventory-grafana-migration.ini": 6,
    "autobot-slm-backend/ansible/inventory/dynamic/README.md": 3,
    "autobot-slm-backend/ansible/playbooks/README-backend-fixes.md": 1,
    "autobot-slm-backend/ansible/roles/distributed_setup/README.md": 1,
    "autobot-slm-backend/ansible/roles/dns/README.md": 3,
    "autobot-slm-backend/database/schemas/infrastructure_management_schema.sql": 1,
    "autobot-slm-backend/docs/API_ENDPOINTS.md": 3,
    "autobot-slm-backend/scripts/README-remove-orphaned-node.md": 11,
    "autobot-slm-frontend/README.md": 4,
    "autobot-tts-worker/README.md": 2,
    "changelog/v0.4.0.md": 9,
    "context7.json": 2,
    "pipeline-scripts/hardcoded_values_baseline.txt": 5,
    "scripts/autobot-ctl": 1,
}


def audit(base: pathlib.Path | None = None) -> tuple[list[str], int]:
    """(problems, files reached)."""
    counts, reached = uncovered_counts(base)
    problems: list[str] = []

    if reached < DISCOVERY_FLOOR:
        problems.append(
            f"reached only {reached} uncovered files, below the floor of {DISCOVERY_FLOOR} -- "
            "the sweep has stopped seeing the tree, so a clean result asserts nothing"
        )

    for rel in sorted(set(counts) - set(BASELINE)):
        problems.append(
            f"{rel}: carries the fleet range and is not in BASELINE "
            f"({counts[rel]} occurrence(s)). No guard scanned this file kind before #17440; "
            "use a role placeholder or an RFC5737 documentation address instead."
        )

    for rel in sorted(set(counts) & set(BASELINE)):
        if counts[rel] > BASELINE[rel]:
            problems.append(
                f"{rel}: {counts[rel]} occurrence(s), baseline allows {BASELINE[rel]}. " "This number may only go down."
            )
        elif counts[rel] < BASELINE[rel]:
            problems.append(
                f"{rel}: down to {counts[rel]} from {BASELINE[rel]} -- lower the baseline "
                "so the improvement is locked in and cannot drift back."
            )

    for rel in sorted(set(BASELINE) - set(counts)):
        problems.append(
            f"{rel}: baseline entry no longer carries the fleet range " "(or the file is gone) -- delete the entry."
        )

    return problems, reached


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", action="store_true", help="report and exit non-zero on findings")
    parser.parse_args(argv)

    try:
        problems, reached = audit()
    except RuleSourceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if problems:
        print(f"FAIL (#17440): {len(problems)} problem(s) across {reached} uncovered files:")
        for line in problems:
            print(f"  {line}")
        return 1
    total = sum(BASELINE.values())
    print(
        f"OK (#17440): {reached} uncovered files reached; {total} baselined occurrence(s) in {len(BASELINE)} file(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
