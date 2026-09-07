#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# Pre-flight for a PR: run every gate that CI runs, locally, BEFORE pushing.
#
# Each check here exists because it has actually cost a round-trip:
#   - a PR body missing "## What Changed"      -> PR Template Check red, twice
#   - a body with no Closes/Refs keyword       -> PR issue-link gate red, twice
#   - backticks in a commit message            -> the shell EXECUTED them and
#                                                 blanked a line of the message
#   - a fleet address in source                -> repo secret-scanning hook
#   - lint run with different flags than CI    -> green locally, red in CI
#
# Usage:
#   scripts/pr-preflight.sh --issue 13162 [--body pr.md] [--message msg.txt]
#
#   --issue N     the issue this PR links to (required)
#   --body FILE   the PR body you are about to post
#   --message F   the commit message file you are about to pass to git commit -F
#   --full        also run the required checks that import the backend or run a
#                 suite. Minutes rather than seconds; skipped by default so the
#                 fast path stays worth running before every push (#15933).
#
# Exit 0 = every gate that can be checked locally would pass.

set -uo pipefail

ISSUE="" BODY_FILE="" MSG_FILE="" FULL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --issue)   ISSUE="$2";     shift 2 ;;
    --body)    BODY_FILE="$2"; shift 2 ;;
    --message) MSG_FILE="$2";  shift 2 ;;
    --full)    FULL=1;         shift ;;
    -h|--help) sed -n '3,25p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# shellcheck source=scripts/lib/git-root.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/git-root.sh" || exit 2
REPO_ROOT=$(git_repo_root) || exit 2
cd "$REPO_ROOT" || exit 2

BASE="${PREFLIGHT_BASE:-origin/Dev_new_gui}"

# Which interpreter runs the lint gates. CI runs 3.14; this box's default python3
# is often older, and running the gates on it makes this script's whole premise
# ("run every gate that CI runs") false in a way nothing surfaces (#13573).
#
# It matters most for black, which SKIPS its AST safety check when the running
# interpreter is older than the target version -- it warns, and passes anyway. So
# the weaker check is the silent one.
#
# Prefer the CI-parity venv built by scripts/setup-ci-parity-env.sh, at the same
# path CI uses. Fall back to python3 so this script keeps working on a box that
# has not built it, but say so, because a fallback nobody notices is how the
# divergence got here.
PARITY_VENV="${CI_PARITY_VENV:-$HOME/.venv-python-suite}"
PY="python3"
PY_SOURCE="system python3"
if [ -x "$PARITY_VENV/bin/python" ]; then
  PY="$PARITY_VENV/bin/python"
  PY_SOURCE="CI-parity venv"
fi
PY_VERSION=$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || echo unknown)
FAILED=0

# The fleet range is deliberately NOT written here -- putting it in a script is
# the very thing being checked for. It is read from the existing lint rule,
# which is the single source of truth for what "fleet IP" means.
FLEET_RULE="tools/lint/check_no_hardcoded_ip_fallbacks.py"
FLEET_IP_RE=$(grep -oE '\^[0-9]{1,3}\\\.[0-9]{1,3}\\\.[0-9]{1,3}\\\.' "$FLEET_RULE" 2>/dev/null \
              | head -1 | sed 's/^\^//' | sed 's/\\\././g')
if [ -n "$FLEET_IP_RE" ]; then
  FLEET_IP_RE="$(printf '%s' "$FLEET_IP_RE" | sed 's/\./\\./g')[0-9]{1,3}"
else
  FLEET_IP_RE='(?!)'  # rule file unreadable -- match nothing rather than guess
fi
pass() { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILED=$((FAILED + 1)); }
note() { printf '  --    %s\n' "$1"; }
section() { printf '\n%s\n' "$1"; }

# ---------------------------------------------------------------- interpreter
section "interpreter"

if [ "$PY_SOURCE" = "CI-parity venv" ]; then
  # "from the CI-parity venv" is a claim about the PACKAGES, not the path. The
  # venv reconciles on every setup run now, but it can still go stale between
  # those runs, and an unqualified ok next to a floor report listing
  # 21 shortfalls said two contradictory things at once (#15130). Ask that
  # script -- in --check mode, so preflight never installs anything -- and let
  # the answer decide which of the two lines this is.
  #
  # Reported, not gated -- the same call #15091 made. A stale venv is still a
  # far better interpreter than the system one, and failing preflight for a
  # condition unrelated to the diff teaches people to ignore preflight. The
  # detail is left to the floor report immediately below; this line only has
  # to stop claiming parity it does not have.
  if scripts/setup-ci-parity-env.sh --check >/dev/null 2>&1; then
    pass "python $PY_VERSION from the CI-parity venv"
  else
    note "python $PY_VERSION from the CI-parity venv -- but the venv is STALE (#15130)"
    note "it no longer matches requirements-ci.txt / requirements-ci-test.txt"
    note "reconcile it: scripts/setup-ci-parity-env.sh"
  fi
else
  note "python $PY_VERSION from the system python3 -- CI runs 3.14 (#13573)"
  note "black skips its AST safety check on an older interpreter; build parity with:"
  note "    scripts/setup-ci-parity-env.sh"
fi

# The interpreter is only half of it. An environment whose PACKAGES are older
# than the repo declares passes every gate below and still disagrees with CI,
# because CI installs the declared set. #14998 spent a diagnosis cycle on a
# guard that read 26 routes here and 3 there, purely from a fastapi delta.
# Reported, never fatal (#15091) -- exit 2 means the check itself broke.
if ! FLOOR_REPORT=$("$PY" pipeline-scripts/check_dependency_floors.py 2>&1); then
  fail "dependency floor check did not run: $FLOOR_REPORT"
elif printf '%s' "$FLOOR_REPORT" | grep -q 'all satisfied'; then
  pass "$(printf '%s' "$FLOOR_REPORT" | head -1)"
else
  while IFS= read -r line; do note "$line"; done <<EOF_FLOORS
$FLOOR_REPORT
EOF_FLOORS
fi

# ---------------------------------------------------------------- branch
section "branch"

BRANCH=$(git rev-parse --abbrev-ref HEAD)
case "$BRANCH" in
  main|master|Dev_new_gui)
    fail "on protected branch '$BRANCH' -- the pre-commit hook will refuse this" ;;
  *) pass "branch '$BRANCH' is not protected" ;;
esac

if [ "$(git_repo_root)" = "$(git rev-parse --git-common-dir | xargs dirname 2>/dev/null)" ]; then
  note "this looks like the main checkout, not a worktree"
fi

# ---------------------------------------------------------------- commit message
if [ -n "$MSG_FILE" ]; then
  section "commit message ($MSG_FILE)"

  if [ ! -f "$MSG_FILE" ]; then
    fail "no such file"
  else
    # Backticks are the expensive one: `git commit -m "...\`x\`..."` runs x.
    if grep -q '`' "$MSG_FILE"; then
      fail "contains a backtick -- the shell will EXECUTE it if this is ever passed via -m"
      grep -n '`' "$MSG_FILE" | sed 's/^/        /'
    else
      pass "no backticks"
    fi

    SUBJECT=$(head -1 "$MSG_FILE")
    if printf '%s' "$SUBJECT" | grep -qE '^[a-z]+(\([a-z0-9._-]+\))?: .+ \(#[0-9]+\)$'; then
      pass "subject matches <type>(scope): <description> (#issue)"
    else
      fail "subject does not match <type>(scope): <description> (#issue)"
      printf '        %s\n' "$SUBJECT"
    fi

    if [ "${#SUBJECT}" -gt 100 ]; then
      fail "subject is ${#SUBJECT} chars (keep it under 100)"
    else
      pass "subject length ${#SUBJECT}"
    fi

    # mrveiss is sole author; a "No commit trailers" job enforces this.
    if grep -qiE '^(co-authored-by|signed-off-by|generated with|assisted-by):' "$MSG_FILE"; then
      fail "contains an authorship trailer -- the 'No commit trailers' check will fail"
    else
      pass "no authorship trailers"
    fi
  fi
fi

# Trailers already committed on this branch would fail the same gate.
if git rev-parse --verify --quiet "$BASE" >/dev/null; then
  section "commits on this branch"
  if git log --format='%B' "$BASE..HEAD" | grep -qiE '^(co-authored-by|signed-off-by|assisted-by):'; then
    fail "a commit already on this branch carries an authorship trailer"
  else
    pass "no authorship trailers in $(git rev-list --count "$BASE..HEAD") commit(s)"
  fi
else
  note "$BASE not found -- skipping branch-commit checks (run git fetch)"
fi

# ---------------------------------------------------------------- PR body
if [ -n "$BODY_FILE" ]; then
  section "PR body ($BODY_FILE)"

  if [ ! -f "$BODY_FILE" ]; then
    fail "no such file"
  else
    BODY=$(cat "$BODY_FILE")

    # Mirrors .github/workflows/pr-template-check.yml exactly: content between
    # this ## header and the next ## header, comments stripped, must be
    # non-empty. A heading present but empty fails there and must fail here.
    for heading in "Thinking Path" "What Changed" "Verification" "Model Used"; do
      content=$(printf '%s' "$BODY" \
        | awk "/^## ${heading}/{found=1; next} found && /^## /{exit} found{print}" \
        | sed 's/<!--[^>]*-->//g' \
        | sed '/^[[:space:]]*$/d')
      if [ -z "$content" ]; then
        fail "section '## ${heading}' is missing or empty"
      else
        pass "section '## ${heading}'"
      fi
    done

    # Mirrors .github/workflows/pr-issue-validation.yml, with one deliberate
    # difference: #14241 lets a FORK PR override the branch-derived issue with an
    # explicit `Closes #N` in the body. This script takes --issue explicitly, so
    # it has no branch to derive from and no fork/same-repo distinction to make.
    # A fork contributor relying on that relaxation therefore sees a FAIL here for
    # a check CI will pass -- a false negative, not a false accept.
    if printf '%s' "$BODY" \
      | grep -iqE "(resolves|closes|fixes|refs|references|part of)[[:space:]]+(#?[0-9]+|MVA-[0-9]+)"; then
      pass "carries a close/refs keyword"
    else
      fail "no Closes/Fixes/Refs keyword -- the issue-link gate requires one even for partial work"
    fi

    if [ -n "$ISSUE" ]; then
      if printf '%s' "$BODY" | grep -qE "#${ISSUE}([^0-9]|$)"; then
        pass "names issue #${ISSUE}"
      else
        fail "does not name issue #${ISSUE}"
      fi
      # Partial delivery must not silently close the issue.
      if printf '%s' "$BODY" | grep -iqE "(closes|fixes|resolves)[[:space:]]+#${ISSUE}([^0-9]|$)" \
         && printf '%s' "$BODY" | grep -iq "partial"; then
        note "closes #${ISSUE} AND says 'partial' -- confirm the body states the issue stays open"
      fi
    fi

    # Only the fleet deployment range. tools/lint/check_no_hardcoded_ip_fallbacks.py
    # is explicit that loopback and RFC-1918 example space are legitimate by
    # project convention -- flagging those would make this script cry wolf.
    if printf '%s' "$BODY" | grep -qE "$FLEET_IP_RE"; then
      fail "contains a fleet IP -- outward artifacts must not carry one"
    else
      pass "no fleet IP literals"
    fi

    if printf '%s' "$BODY" | grep -qE '(/home/|/opt/autobot|/var/log/autobot)'; then
      fail "contains an internal filesystem path"
    else
      pass "no internal filesystem paths"
    fi
  fi
fi

# ---------------------------------------------------------------- changed files
section "changed files"

if ! git rev-parse --verify --quiet "$BASE" >/dev/null; then
  note "$BASE not found -- skipping lint (run git fetch)"
else
  mapfile -t CHANGED < <(git diff --name-only --diff-filter=ACMR "$BASE...HEAD"; git diff --name-only --diff-filter=ACMR HEAD)
  mapfile -t PY < <(printf '%s\n' "${CHANGED[@]}" | sort -u | grep -E '\.py$' | while read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done)

  if [ "${#PY[@]}" -eq 0 ]; then
    note "no changed Python files"
  else
    printf '  %d changed Python file(s)\n' "${#PY[@]}"

    # Same flags as .github/workflows/code-quality.yml. Different flags is how
    # a local green becomes a CI red.
    if "$PY" -m black --check --line-length=120 "${PY[@]}" >/dev/null 2>&1; then
      pass "black --line-length=120"
    else
      fail "black -- run: python3 -m black --line-length=120 ${PY[*]}"
    fi

    if "$PY" -m isort --check-only --settings-path=. --line-length=120 "${PY[@]}" >/dev/null 2>&1; then
      pass "isort --settings-path=. --line-length=120"
    else
      fail "isort -- run: python3 -m isort --settings-path=. --line-length=120 ${PY[*]}"
    fi

    # #13521: flake8 checks a file named explicitly on the command line even when
    # .flake8 excludes it, so passing changed files by path made this stricter
    # than CI -- which lints whole directories and therefore honours `exclude`.
    # That produced failures on pre-existing findings in excluded trees
    # (code_analysis, tools, scripts, tests...) that CI never sees. Drop the same
    # directories here so the gate matches the gate it is meant to predict.
    # #14419: the list now carries two shapes and they are dropped differently.
    # A bare name (build/runtime artifact directories only) is matched by flake8
    # against a path's basename, so it prunes at any depth. An anchored entry
    # ends in `/` and prunes only that path. Treating an anchored entry as a
    # bare component would drop nothing and make this gate stricter than CI
    # again -- the exact #13521 regression the block exists to prevent.
    FLAKE_ENTRIES=$(awk '/^exclude *=/{f=1;next} /^[a-z_-]+ *=/{f=0} f' .flake8 \
                    | sed 's/#.*//' | tr ',' '\n' | tr -d ' ' | grep -vE '^\*|^$')
    FLAKE_BARE=$(printf '%s\n' "$FLAKE_ENTRIES" | grep -v '/' | tr '\n' '|' | sed 's/|$//')
    FLAKE_ANCHORED=$(printf '%s\n' "$FLAKE_ENTRIES" | grep '/' | tr '\n' '|' | sed 's/|$//')
    mapfile -t PY_LINT < <(printf '%s\n' "${PY[@]}")
    if [ -n "$FLAKE_BARE" ]; then
      mapfile -t PY_LINT < <(printf '%s\n' "${PY_LINT[@]}" | grep -vE "(^|/)(${FLAKE_BARE})(/|$)" || true)
    fi
    if [ -n "$FLAKE_ANCHORED" ]; then
      mapfile -t PY_LINT < <(printf '%s\n' "${PY_LINT[@]}" | grep -vE "^(${FLAKE_ANCHORED})" || true)
    fi
    # An empty array round-trips through printf as one empty line; drop it so
    # the count below means "nothing to lint" rather than "one blank path".
    if [ "${#PY_LINT[@]}" -eq 1 ] && [ -z "${PY_LINT[0]}" ]; then
      PY_LINT=()
    fi

    if [ "${#PY_LINT[@]}" -eq 0 ]; then
      note "flake8 -- every changed Python file is in .flake8's exclude list"
    elif "$PY" -m flake8 --config=.flake8 "${PY_LINT[@]}" >/dev/null 2>&1; then
      pass "flake8 --config=.flake8"
    else
      fail "flake8 --config=.flake8"
      "$PY" -m flake8 --config=.flake8 "${PY_LINT[@]}" 2>&1 | head -15 | sed 's/^/        /'
    fi

    # code-quality.yml runs bandit with NO severity floor -- stricter than the
    # medium-and-up filter used elsewhere. A B105 on a constant named *_PREFIX
    # is the classic false positive; annotate it with "# nosec B105".
    # #13521: "nosec encountered (Bxxx), but no failed test" is bandit telling
    # you a suppression is unnecessary, not that this change is unsafe. It is a
    # property of the file you happened to touch, and blocking on it would stop
    # anyone editing a file that carries a stale suppression. Reported by the
    # dedicated sweep instead; a real finding still says "Issue:".
    BANDIT_OUT=$("$PY" -m bandit -c .bandit -q "${PY[@]}" 2>&1 | grep -v "nosec encountered")
    if [ -z "$BANDIT_OUT" ]; then
      pass "bandit -c .bandit (no severity floor, as CI runs it)"
    else
      fail "bandit"
      printf '%s\n' "$BANDIT_OUT" | head -15 | sed 's/^/        /'
    fi
  fi

  section "content of changed files"

  mapfile -t EXISTING < <(printf '%s\n' "${CHANGED[@]}" | sort -u | while read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done)

  if [ "${#EXISTING[@]}" -eq 0 ]; then
    note "nothing to scan"
  else
    if grep -nE '^(<<<<<<< |=======$|>>>>>>> )' "${EXISTING[@]}" >/dev/null 2>&1; then
      fail "conflict markers present"
      grep -nE '^(<<<<<<< |>>>>>>> )' "${EXISTING[@]}" 2>/dev/null | head -10 | sed 's/^/        /'
    else
      pass "no conflict markers"
    fi

    # The next two look at ADDED lines only. A pre-existing marker elsewhere in
    # a file this PR happens to touch is not this PR's to answer for, and
    # flagging it would train the reader to ignore the script.
    #
    # This script and its test are excluded: they necessarily contain the
    # patterns they search for (the message strings below say "TODO/FIXME"),
    # so scanning them reports the checker as a violation of itself.
    # tools/lint/check_no_hardcoded_ip_fallbacks.py carries an ALLOWLIST for
    # exactly this reason.
    SELF_EXCLUDE=(':(exclude)scripts/pr-preflight.sh' ':(exclude)scripts/pr-preflight_test.sh')
    ADDED=$( { git diff "$BASE...HEAD" -- . "${SELF_EXCLUDE[@]}"
               git diff HEAD -- . "${SELF_EXCLUDE[@]}"; } 2>/dev/null \
             | grep '^+' | grep -v '^+++' | sed 's/^+//')

    # Mirrors .claude/hooks/scan-secrets.sh: the fleet range only, and not when
    # the line is a comment or an SSOT lookup -- the same exemptions the hook
    # grants. Loopback and RFC-1918 example space stay allowed by convention.
    FLEET_HITS=$(printf '%s\n' "$ADDED" | grep -E "$FLEET_IP_RE" \
                 | grep -vE '^[[:space:]]*(#|//|/\*|\*|<!--|""")' \
                 | grep -viE '(config\.|ssot_config|AUTOBOT_REFERENCE|NetworkConstants)')
    if [ -n "$FLEET_HITS" ]; then
      fail "an added line carries a fleet IP -- source it from SSOT NetworkConstants instead"
      printf '%s\n' "$FLEET_HITS" | head -10 | sed 's/^/        /'
    else
      pass "no fleet IP literals in added lines"
    fi

    MARKERS=$(printf '%s\n' "$ADDED" | grep -nE '\bTODO\b|\bFIXME\b')
    if [ -n "$MARKERS" ]; then
      fail "an added line carries a TODO/FIXME -- this repo does not accept deferred-work markers"
      printf '%s\n' "$MARKERS" | head -10 | sed 's/^/        /'
    else
      pass "no TODO/FIXME in added lines"
    fi
  fi
fi

# ------------------------------------------------- required status checks
#
# Everything above predicts a gate that is cheap to run. This block covers the
# TEN contexts the `Main` ruleset actually requires on Dev_new_gui, because
# those are the ones whose failure costs a push -- and a push costs an 8.9-minute
# suite (#15932: ~6 commits per PR, 49 failed check-runs across 9 merged PRs,
# so every PR goes red at least once on the way).
#
# Each entry names the SAME script its workflow invokes. The rule is that a
# check here must not re-implement its gate: a local re-implementation drifts
# from CI silently, which is the failure mode #13573 and #13521 both were.
# Where a workflow's gate is inline YAML with no extractable script, the check
# is reported as unavailable with that as its reason rather than approximated.
#
# Cost tiers, because a preflight nobody runs saves nothing:
#   default   script-only gates -- no imports, no services, seconds
#   --full    gates that import the backend or run a suite -- minutes
#   never     gates needing infrastructure this box does not have
#
# `migration-matrix` sits in that last tier: it needs a live PostgreSQL and is
# reported unavailable unless AUTOBOT_MIGRATION_TEST_ADMIN_URL is set. #15933
# was filed claiming nine of the ten were locally reproducible; that was one
# too many, and the honest count is eight plus one conditional.

section "required status checks"

# Run one required context locally. Args: <context> <path-filter-regex> <cmd...>
# An empty path filter means the gate is unconditional.
require_check() {
  local ctx="$1" filter="$2"; shift 2

  if [ -n "$filter" ] && [ "${#CHANGED[@]}" -gt 0 ]; then
    if ! printf '%s\n' "${CHANGED[@]}" | grep -qE "$filter"; then
      note "$ctx -- no matching paths changed (CI path-filters it too)"
      return 0
    fi
  fi

  if "$@" >/tmp/preflight-$$.log 2>&1; then
    pass "$ctx"
  else
    fail "$ctx -- reproduce with: $*"
    head -12 /tmp/preflight-$$.log | sed 's/^/        /'
  fi
  rm -f /tmp/preflight-$$.log
}

# Report a gate this box cannot run, naming the reason. Never approximated:
# a check that silently does something weaker than CI is worse than no check,
# because it is read as coverage.
skip_check() { note "$1 -- $2"; }

if ! git rev-parse --verify --quiet "$BASE" >/dev/null; then
  note "$BASE not found -- skipping required checks (run git fetch)"
else
  # verify-precommit-config: enforce-precommit.yml runs exactly these two, and
  # runs them UNCONDITIONALLY. It carries no `paths:` key (see its own comment at
  # :22-27: "a required check that is path-filtered out never reports, wedging
  # any PR that touches only non-matching files"). So these two take an EMPTY
  # filter. A filter here would skip, for a .py-only PR, the one gate CI can
  # never skip -- and would print "no matching paths changed (CI path-filters it
  # too)", which is false of this workflow. Silent and passing is the worst
  # direction for a preflight to be wrong in.
  require_check "verify-precommit-config (gating hooks)" \
    '' \
    "$PY" pipeline-scripts/check_gating_precommit_hooks.py

  require_check "verify-precommit-config (hooks executed)" \
    '' \
    "$PY" pipeline-scripts/check_precommit_hooks_executed.py

  # code-quality runs these repo-wide script gates alongside the lint above.
  #
  # All three share ONE filter, because CI gates the whole `code-quality` job on
  # a single set: `.github/filters/code-quality-paths.yml`'s `backend`. Three
  # hand-written per-check regexes were a second copy of that set, which the
  # filter file itself forbids -- "SINGLE SOURCE OF TRUTH ... A second copy would
  # drift, and the drift direction is silent". It had already drifted: none of
  # the three matched `.flake8`, `.bandit`, `pyproject.toml`, `requirements*.txt`
  # or `repo_tests/**`, so editing any of them ran code-quality in CI while the
  # preflight reported "no matching paths changed" three times.
  #
  # Derived from the filter file AT RUNTIME -- there is no second copy to drift.
  # The translation is explicit because dorny/paths-filter globs are anchored at
  # the repo root:  `a/**` -> `^a/` (prefix),  a bare `a/b.c` -> `^a/b\.c$`
  # (exact),  a leading `**/` -> unanchored suffix,  and `*` inside a segment
  # -> `[^/]*` (never crossing `/`). Hand-inlining these 25 arms was tried first
  # and was wrong on the first attempt -- the list was read truncated.
  CQ_PATHS="$(_CQ_FILTER_FILE="${REPO_ROOT}/.github/filters/code-quality-paths.yml" "$PY" - <<'CQEOF'
import os, re, yaml
globs = yaml.safe_load(open(os.environ["_CQ_FILTER_FILE"]))["backend"]
arms = []
for g in globs:
    if g.startswith("**/"):
        arms.append(re.escape(g[3:]).replace(r"\*", "[^/]*") + "$")
    elif g.endswith("/**"):
        arms.append("^" + re.escape(g[:-3]) + "/")
    else:
        arms.append("^" + re.escape(g).replace(r"\*", "[^/]*") + "$")
print("|".join(arms))
CQEOF
)"
  # Fail THIS check, never the script. PyYAML is not declared in requirements
  # and the script deliberately supports a box that has not built the venv, so a
  # missing import must not take the changed-file scan, the content checks and
  # the summary down with it -- that would trade a narrow gap for a total one.
  if [ -z "${CQ_PATHS}" ]; then
    skip_check "code-quality (all three script gates)" \
      "cannot derive the path set from .github/filters/code-quality-paths.yml (PyYAML missing?) -- these three were NOT checked"
  else

  require_check "code-quality (env var registry)" \
    "$CQ_PATHS" \
    "$PY" pipeline-scripts/check_env_var_registry.py

  require_check "code-quality (nosec format)" \
    "$CQ_PATHS" \
    "$PY" scripts/check_nosec_format.py

  require_check "code-quality (doc references)" \
    "$CQ_PATHS" \
    "$PY" pipeline-scripts/check-doc-references.py
  fi

  # Several workflows gate themselves on .github/filters/*.yml; this verifies
  # the filters still name paths that exist, which is how a required context
  # silently stops covering a tree.
  require_check "workflow path filters" \
    '\.github/' \
    "$PY" pipeline-scripts/check_workflow_path_filters.py

  # ---- gates that import the backend or run a suite: --full only ----------
  if [ "$FULL" = "1" ]; then
    require_check "api-wiring" \
      'autobot-backend/|autobot-frontend/src/' \
      env PYTHONPATH="$REPO_ROOT:$REPO_ROOT/autobot-backend" AUTOBOT_SINGLE_USER=true \
      "$PY" scripts/audit_api_wiring.py --dump-openapi /tmp/preflight-openapi-$$.json

    require_check "startup-import-smoke" \
      'autobot-backend/' \
      env PYTHONPATH="$REPO_ROOT:$REPO_ROOT/autobot-backend" \
      "$PY" -c 'import initialization.lifespan'
  else
    skip_check "api-wiring"           "imports the backend -- re-run with --full"
    skip_check "startup-import-smoke" "imports the backend -- re-run with --full"
  fi

  # These two are reproducible but multi-step: each needs an `npm ci` in a
  # frontend workspace before its gate means anything, and a preflight that
  # installs packages is a preflight that gets run once and then avoided.
  # Named with their exact remediation rather than wired half-way -- a check
  # that runs a weaker version of its gate reads as coverage and is not.
  # Wiring these properly is the remaining half of #15933.
  skip_check "verify-generated-types" \
    "needs npm ci + a schema dump: see .github/workflows/verify-generated-types.yml, then npm run gen:types"
  skip_check "Unit & Integration Tests" \
    "needs npm ci in autobot-frontend: npm --prefix autobot-frontend ci && npm --prefix autobot-frontend run test:unit"

  # ---- gates this box cannot reproduce -----------------------------------
  if [ -n "${AUTOBOT_MIGRATION_TEST_ADMIN_URL:-}" ]; then
    # A bare `note` does not touch FAILED, so the preflight could exit 0 with
    # this gate unchecked -- "configured" read as "verified". Run it under
    # --full (it is a suite, minutes not seconds); otherwise say plainly that
    # it was not run, rather than that it was available.
    if [ "$FULL" = "1" ]; then
      require_check "migration-matrix" \
        'autobot-backend/(models|migrations)/|alembic' \
        "$PY" -m pytest autobot-backend/tests/migrations/ -q
    else
      skip_check "migration-matrix" \
        "configured but NOT run -- it is a suite; re-run with --full, or: pytest autobot-backend/tests/migrations/"
    fi
  else
    skip_check "migration-matrix" "needs a live PostgreSQL (set AUTOBOT_MIGRATION_TEST_ADMIN_URL)"
  fi
  skip_check "smoke-test" "builds images and starts the compose stack -- CI only"
  skip_check "No open blocks-merge issues reference this PR" "reads GitHub issue state, not the working tree"

  # `No commit trailers` is already predicted by the commit-message section
  # above; naming it here keeps the required-context list complete rather than
  # leaving the reader to notice the ninth entry is missing.
  note "No commit trailers -- covered by the commit message section above"
fi

# ---------------------------------------------------------------- result
printf '\n'
if [ "$FAILED" -eq 0 ]; then
  printf 'pre-flight clean -- safe to commit and push\n'
  exit 0
fi
printf '%d pre-flight failure(s) -- fix before pushing\n' "$FAILED"
exit 1
