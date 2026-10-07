#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# pr-merge-gate.sh — the merge-time half of the pre-merge gates (#15995).
#
#   --pr N        judge this pull request (default: the open PR for HEAD's branch)
#   --branch B    resolve the open PR for B instead of the current branch
#   --repo R      owner/name (default: the gate's own default)
#   --base B      the protected branch whose required-context list is read
#
# Exit 0 = every required context on the PR's CURRENT head is green.
#
# WHY THIS EXISTS AS A CALLER, AND NOT ONLY AS PROSE.
# `scripts/pr_required_gate.py` has been correct since #16001 and was reached by
# nothing: `git grep -l pr_required_gate` returned its own test, one research
# document and a pytest timing file. An uncalled gate is the same artefact as
# the rule in CLAUDE_REVIEW.md it was written to enforce — a sentence — and that
# rule already existed. The gate's first acceptance criterion is that whatever
# decides a merge CALLS it, so this is the command that does.
#
# WHY IT IS SEPARATE FROM pr-preflight.sh, which is the other half of
# "Pre-Merge Validation" in docs/developer/CLAUDE_WORKFLOW.md:
#
#   * the two answer different questions about different commits. The preflight
#     asks "would CI pass on what I am about to push"; this asks "is the head
#     already on the PR clear to merge". Run before a push, this gate's verdict
#     would be correct, complete, and about the commit the push is replacing —
#     and `never-reported`, which it BLOCKS on deliberately, is the normal state
#     seconds after a push. A gate that fails for a reason its reader cannot act
#     on is one people stop running.
#   * scripts/pr-preflight.sh is at its recorded size ceiling (818 lines,
#     repo_tests/shell_file_size_ratchet_baseline.py). A grandfathered file may
#     not grow, and raising a ratchet to fit new code is the one repair
#     RATCHET_BASELINES.md forbids by name.
#
# WHAT THIS ADDS over calling the Python gate directly: it resolves a BRANCH to
# its open PR, and it keeps "gh could not be asked" apart from "there is nothing
# to ask about". Those are opposite answers, and reporting the first as the
# second is the exact defect the gate downstream exists to catch.

set -uo pipefail

PR_NUMBER="" BRANCH="" REPO="" BASE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --pr)      PR_NUMBER="${2:-}"; shift 2 ;;
    --branch)  BRANCH="${2:-}";    shift 2 ;;
    --repo)    REPO="${2:-}";      shift 2 ;;
    --base)    BASE="${2:-}";      shift 2 ;;
    -h|--help) sed -n '5,13p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# shellcheck source=scripts/lib/git-root.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/git-root.sh" || {
  echo "FATAL: cannot load scripts/lib/git-root.sh — refusing to report a verdict" >&2
  exit 2
}
REPO_ROOT=$(git_repo_root) || { echo "not a git repo" >&2; exit 2; }
cd "$REPO_ROOT" || { echo "not a git repo" >&2; exit 2; }

# Same interpreter choice as pr-preflight.sh, for the same reason: the box's
# default python3 is often older than the one the tooling is written against.
PARITY_VENV="${CI_PARITY_VENV:-$HOME/.venv-python-suite}"
PY="python3"
[ -x "$PARITY_VENV/bin/python" ] && PY="$PARITY_VENV/bin/python"

# Overridable so the WIRING has a test. Without it the only way to exercise this
# script is a live PR and three network calls, and "the caller has no test" is
# how #15995 shipped a correct gate that nothing ran. The default is the real
# gate; nothing in CI sets this.
GATE_SCRIPT="${PR_MERGE_GATE_SCRIPT:-$REPO_ROOT/scripts/pr_required_gate.py}"

[ -f "$GATE_SCRIPT" ] || {
  echo "FATAL: required-contexts gate not found at $GATE_SCRIPT" >&2
  exit 2
}

if [ -z "$PR_NUMBER" ]; then
  command -v gh >/dev/null 2>&1 || {
    echo "gh is not installed — the PR's required contexts cannot be read, so the verdict is UNKNOWN, not green" >&2
    exit 2
  }
  [ -n "$BRANCH" ] || BRANCH=$(git branch --show-current 2>/dev/null)
  [ -n "$BRANCH" ] || { echo "detached HEAD and no --branch/--pr — nothing to resolve" >&2; exit 2; }
  # A `gh` that FAILED and a branch with no PR are different answers and get
  # different exits. Collapsing them is the defect the gate downstream exists
  # for: "could not ask" must never render as "nothing to report".
  # SCOPED THE SAME WAY THE VERDICT IS. The lookup used to take neither
  # --repo nor --base while the gate took both, so the two could answer about
  # different things:
  #   --repo R   the lookup searched the CHECKOUT, then handed that number to
  #              a gate pointed at R -- an unrelated PR judged against R's
  #              protection, or no PR found in R at all.
  #   --base B   with two open PRs sharing a head branch, the lookup could
  #              return the one targeting a DIFFERENT base, and the gate reads
  #              protection for B. `gh pr view` fetches headRefOid/state/
  #              isDraft and never the target branch, so nothing downstream
  #              catches it: a green clearance for the wrong PR.
  # Both filters are forwarded, so a mismatch becomes "no OPEN pull request"
  # (exit 2, unknown) instead of a confident answer about something else.
  LOOKUP_ARGS=(--head "$BRANCH" --state open --limit 1 --json number --jq '.[0].number')
  [ -n "$REPO" ] && LOOKUP_ARGS+=(--repo "$REPO")
  [ -n "$BASE" ] && LOOKUP_ARGS+=(--base "$BASE")
  if ! PR_NUMBER=$(gh pr list "${LOOKUP_ARGS[@]}" 2>/dev/null); then
    echo "gh could not be queried for '$BRANCH' — the verdict is UNKNOWN, which is not green" >&2
    exit 2
  fi
  [ -n "$PR_NUMBER" ] || { echo "no OPEN pull request for '$BRANCH' — there is no head to judge" >&2; exit 2; }
fi

GATE_ARGS=("$PR_NUMBER")
[ -n "$REPO" ] && GATE_ARGS+=(--repo "$REPO")
[ -n "$BASE" ] && GATE_ARGS+=(--base "$BASE")

# Printed in full, including the gate's own "NOT EXAMINED" block: it names the
# merge preconditions it does not check, and a caller that swallowed that would
# re-create the silence it was written to break.
"$PY" "$GATE_SCRIPT" "${GATE_ARGS[@]}"
GATE_RC=$?

if [ "$GATE_RC" -eq 0 ]; then
  echo "pr-merge-gate: PR #$PR_NUMBER — every required context on the current head is green"
  exit 0
fi
# THREE outcomes, not two. The gate exits 0 for green, 1 for a verdict that is
# not clearing, and EXIT_GATE_ERROR (2) when it could not reach a verdict at
# all -- a `gh` call that raised, a malformed response. This branch used to be
# the `else` of a two-way test, so an operational failure printed "is NOT clear
# to merge on its required contexts ... verdict above" with no verdict above
# it. "Could not ask" rendering as "asked and the answer is no" is the exact
# collapse the lookup guard above refuses, and it was happening here.
if [ "$GATE_RC" -ne 1 ]; then
  echo "pr-merge-gate: PR #$PR_NUMBER — the gate could not reach a verdict (gate exit $GATE_RC)." >&2
  echo "pr-merge-gate: this is UNKNOWN, not a refusal. Nothing above is a verdict." >&2
  exit 2
fi
echo "pr-merge-gate: PR #$PR_NUMBER is NOT clear to merge on its required contexts (gate exit $GATE_RC, verdict above)"
exit 1
