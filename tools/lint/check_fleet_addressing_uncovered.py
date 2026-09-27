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
The ratchet makes the COUNT monotone, and the contract is exactly that -- no
more, because review (#17447) was right that the docstring claimed more.

WHEN THIS GUARD DOES NOT RUN AT ALL (#17542). The sweep below reads EVERY
tracked file, but the `code-quality` job that runs `--audit` only starts when
`.github/filters/code-quality-paths.yml` matches a changed path -- a specific
list, not the whole tree. A pull request touching only a file kind outside that
list (frontend TypeScript, `.txt`, `.csv`) skips the job, and a skipped required
check reads as a pass (#14550/#14551). This checker is also absent from
`_GUARDED_CHECKERS` in `check_code_quality_guard_reach.py`, the meta-guard that
exists to catch exactly that, so nothing currently reports the gap. It is
bounded rather than open: the ratchet is whole-tree, so the next PR that does
trigger the job still sees the count -- it fails the wrong author's PR instead
of the right one. #17542 carries the fix and the decision it needs.

WHAT THE RATCHET DOES AND DOES NOT CATCH. `audit()` compares per-path counts
against `BASELINE`. So it catches a new file, a grown count, and an improvement
left unrecorded. It does **not** catch a baselined file swapping one fleet-range
address for a different one at the same count: the replacement still matches the
pattern, the count is unchanged, and nothing here can see the difference.

That gap is accepted rather than overlooked. Closing it needs a base-revision
comparison, and the alternative -- storing which address is at which path -- is
the one thing this file must never do, since it is as public as the files it
guards. The narrower point stands: the replacement must itself be a fleet-range
address in a file that already had one, so the ratchet still bounds the blast
radius to paths already on the list.

It is not a licence for the existing occurrences either -- the shortlist and its
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
#: Measured against THIS guard's own population, twice now, because both earlier
#: values were taken from a different number:
#:   6000 -- from the 10,815 tracked files in the tree      (population was 1085)
#:    700 -- correct for 1085, stale the moment review widened the population
#: Review (#17447) corrected `is_covered` to mirror the shared detector's real
#: scope, so test files and anything outside HV_SCAN_DIRS are no longer treated
#: as covered, and the population is now **4715**. 3200 leaves churn alone and
#: still fires on a collapse.
DISCOVERY_FLOOR = 3200

_HV_EXTENSIONS = re.compile(r"^HV_SCAN_EXTENSIONS='(?P<exts>[^']+)'", re.MULTILINE)
_HV_DIRS = re.compile(r"^HV_SCAN_DIRS=\((?P<dirs>.*?)\)", re.MULTILINE | re.DOTALL)
_HV_EXCLUDE = re.compile(r"^_HV_EXCLUDE_RE\+?='([^']+)'", re.MULTILINE)


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


def scanned_dirs(base: pathlib.Path | None = None) -> tuple[str, ...]:
    """`HV_SCAN_DIRS`, parsed from the one source. Raises rather than defaulting."""
    root = base or repo_root()
    try:
        text = (root / RULES_REL).read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - environment failure
        raise RuleSourceError(f"cannot read {RULES_REL}: {exc}") from exc
    match = _HV_DIRS.search(text)
    if not match:
        raise RuleSourceError(f"{RULES_REL} no longer assigns HV_SCAN_DIRS")
    dirs = tuple(d.strip().strip('"') for d in match.group("dirs").split() if d.strip().strip('"'))
    if not dirs:
        raise RuleSourceError(f"{RULES_REL} assigns an empty HV_SCAN_DIRS")
    return dirs


def exclude_pattern(base: pathlib.Path | None = None) -> re.Pattern[str]:
    """`_HV_EXCLUDE_RE`, rebuilt from its `=` and `+=` assignments in order.

    Parsed rather than restated for the same reason as everything else here: a
    second copy of "which files the shared detector skips" would drift, and the
    drift would be invisible -- it only shows up as a file neither audit reads.
    """
    root = base or repo_root()
    text = (root / RULES_REL).read_text(encoding="utf-8")
    parts = _HV_EXCLUDE.findall(text)
    if not parts:
        raise RuleSourceError(f"{RULES_REL} no longer assigns _HV_EXCLUDE_RE")
    # Concatenated, NOT joined with "|": every `+=` fragment after the first
    # already carries its own leading `|`. Joining added a second pipe, and
    # `(a)||(b)` has an EMPTY alternative that matches at any position -- so the
    # pattern matched every path, every file looked excluded, and the population
    # inflated from 1085 to 9933. The number was the only thing that showed it.
    joined = "".join(parts)
    if "||" in joined:
        raise RuleSourceError(f"{RULES_REL} produced an empty alternative in _HV_EXCLUDE_RE")
    return re.compile(joined)


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


def is_covered(rel: str, exts: frozenset[str], dirs: tuple[str, ...], exclude: re.Pattern[str]) -> bool:
    """True when some OTHER guard already scans this file.

    Mirrors the shared detector's real scope rather than its extension list
    alone. `hv_file_in_scope()` requires the extension AND a path the
    `_HV_EXCLUDE_RE` does not match, and the tree scan additionally restricts to
    `HV_SCAN_DIRS` -- so a `.py` under `pipeline-scripts/`, or any `*_test.py`,
    has a scanned extension and is **not** scanned. Treating those as covered
    left a gap where neither audit looked; review found it and it was real:
    4 files, 20 occurrences, two of them genuine (#17447 review).

    The asymmetry is deliberate. Getting this wrong in the "covered" direction
    creates a hole; getting it wrong the other way merely guards a file twice.
    So every clause here narrows what counts as covered.
    """
    if rel.startswith("docs/") and rel.endswith(".md"):
        return True  # #15208
    name = rel.rsplit("/", 1)[-1]
    if "." not in name or name.rsplit(".", 1)[-1] not in exts:
        return False
    if not rel.startswith(tuple(d + "/" for d in dirs)):
        return False
    return not exclude.search(rel)


def scannable_text(path: pathlib.Path) -> str | None:
    """The file's text for scanning, or ``None`` when it is binary.

    #17447 review: this used ``read_text(encoding="utf-8")`` inside a bare
    ``except (OSError, UnicodeDecodeError): continue``, so a file that could not
    be decoded was dropped from the sweep without a word. A single invalid byte
    anywhere in a file hid every ASCII fleet address in it -- *did not look*
    reported as *nothing found*, which is the one thing a guard may not do.

    So a decode failure no longer skips: invalid bytes are replaced and the
    surrounding ASCII is still matched. Binary files are the genuine exception
    and are identified the way git identifies them -- a NUL byte -- rather than
    by having failed to decode, because "not UTF-8" and "not text" are
    different questions and only the second one justifies not scanning.
    """
    raw = path.read_bytes()
    if b"\x00" in raw:
        return None
    return raw.decode("utf-8", errors="replace")


def uncovered_counts(base: pathlib.Path | None = None) -> tuple[dict[str, int], int, list[str]]:
    """(path -> fleet-range occurrences, files reached, unreadable paths)."""
    root = base or repo_root()
    exts = scanned_extensions(root)
    dirs = scanned_dirs(root)
    exclude = exclude_pattern(root)
    pattern = fleet_address_pattern(root)
    counts: dict[str, int] = {}
    unreadable: list[str] = []
    reached = 0
    for rel in tracked_files(root):
        if is_covered(rel, exts, dirs, exclude) or rel == SELF_REL:
            continue
        try:
            text = scannable_text(root / rel)
        except OSError as exc:
            unreadable.append(f"{rel}: {type(exc).__name__}")
            continue
        if text is None:
            continue
        reached += 1
        found = len(pattern.findall(text))
        if found:
            counts[rel] = found
    return counts, reached, unreadable


#: Files that MUST contain the fleet range, with the reason each one does.
#:
#: Distinct from BASELINE on purpose. A baseline entry is a debt that should
#: reach zero; these never can, and recording them as debt would make the
#: shrink-only number permanently unreachable and therefore meaningless. Every
#: entry here is either the pattern's own definition or a fixture belonging to
#: a guard that exists to match it -- the same rationale
#: `check_no_hardcoded_ip_fallbacks.py` states in its own ALLOWLIST.
EXEMPT: dict[str, str] = {
    "scripts/lib/hardcoded-value-rules.sh": "defines HV_VM_IP -- this is the pattern every guard parses",
    "tools/lint/check_no_hardcoded_ip_fallbacks.py": (
        "#6783's detector holds the regex as a string; on its own ALLOWLIST"
    ),
    "tools/lint/check_no_hardcoded_ip_fallbacks_test.py": (
        "#6783's fixtures use the pattern by design; on its own ALLOWLIST"
    ),
    "autobot-frontend/eslint-tests/no-hardcoded-vm-ip-allow.test.ts": (
        "fixture for the eslint rule that matches this pattern"
    ),
    "autobot-frontend/eslint-tests/no-hardcoded-vm-ip-deny.test.ts": (
        "fixture for the eslint rule that matches this pattern"
    ),
    "autobot-infrastructure/shared/scripts/hooks/pre-commit-hardcoded-values_test.py": (
        "fixture for the hook that matches this pattern"
    ),
    "pipeline-scripts/check_baseline_no_growth_test.py": (
        "fixture asserting the hardcoded-values baseline does not grow"
    ),
}


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
    "autobot-backend/tests/test_prompt_manager.py": 1,
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
    "autobot-slm-backend/services/inventory_placeholder_test.py": 1,
    "autobot-slm-frontend/README.md": 4,
    "autobot-tts-worker/README.md": 2,
    "changelog/v0.4.0.md": 9,
    "check-grafana-health.sh": 2,
    "context7.json": 2,
    "pipeline-scripts/hardcoded_values_baseline.txt": 5,
    "scripts/autobot-ctl": 1,
}


def audit(base: pathlib.Path | None = None) -> tuple[list[str], int]:
    """(problems, files reached)."""
    counts, reached, unreadable = uncovered_counts(base)
    problems: list[str] = []

    for entry in unreadable:
        problems.append(
            f"{entry}: tracked but could not be read, so it was not scanned. An unscanned "
            "file is not a clean file -- fix the permission or remove the path from the tree."
        )

    if reached < DISCOVERY_FLOOR:
        problems.append(
            f"reached only {reached} uncovered files, below the floor of {DISCOVERY_FLOOR} -- "
            "the sweep has stopped seeing the tree, so a clean result asserts nothing"
        )

    for rel in sorted(set(EXEMPT) - set(counts)):
        problems.append(
            f"{rel}: EXEMPT but no longer carries the fleet range -- delete the entry, "
            "a stranded exemption is a stale claim (the doctrine #15208 states)."
        )

    for rel in sorted(set(counts) - set(BASELINE) - set(EXEMPT)):
        problems.append(
            f"{rel}: carries the fleet range and is not in BASELINE "
            f"({counts[rel]} occurrence(s)). No guard scanned this file kind before #17440; "
            "use a role placeholder or an RFC5737 documentation address instead."
        )

    # Count-only by contract: a same-count swap of one fleet address for another
    # inside an already-baselined file is invisible here. See the module
    # docstring -- closing it needs a base-revision diff, and the cheap
    # alternative (recording WHICH address sits at which path) is the one thing
    # this file must never do.
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
