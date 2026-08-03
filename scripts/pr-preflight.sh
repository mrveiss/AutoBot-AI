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
#
# Exit 0 = every gate that can be checked locally would pass.

set -uo pipefail

ISSUE="" BODY_FILE="" MSG_FILE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --issue)   ISSUE="$2";     shift 2 ;;
    --body)    BODY_FILE="$2"; shift 2 ;;
    --message) MSG_FILE="$2";  shift 2 ;;
    -h|--help) sed -n '3,22p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

REPO_ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$REPO_ROOT" || exit 2

BASE="${PREFLIGHT_BASE:-origin/Dev_new_gui}"
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

# ---------------------------------------------------------------- branch
section "branch"

BRANCH=$(git rev-parse --abbrev-ref HEAD)
case "$BRANCH" in
  main|master|Dev_new_gui)
    fail "on protected branch '$BRANCH' -- the pre-commit hook will refuse this" ;;
  *) pass "branch '$BRANCH' is not protected" ;;
esac

if [ "$(git rev-parse --show-toplevel)" = "$(git rev-parse --git-common-dir | xargs dirname 2>/dev/null)" ]; then
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

    # Mirrors .github/workflows/pr-issue-validation.yml.
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
    if python3 -m black --check --line-length=120 "${PY[@]}" >/dev/null 2>&1; then
      pass "black --line-length=120"
    else
      fail "black -- run: python3 -m black --line-length=120 ${PY[*]}"
    fi

    if python3 -m isort --check-only --settings-path=. --line-length=120 "${PY[@]}" >/dev/null 2>&1; then
      pass "isort --settings-path=. --line-length=120"
    else
      fail "isort -- run: python3 -m isort --settings-path=. --line-length=120 ${PY[*]}"
    fi

    if python3 -m flake8 --config=.flake8 "${PY[@]}" >/dev/null 2>&1; then
      pass "flake8 --config=.flake8"
    else
      fail "flake8 --config=.flake8"
      python3 -m flake8 --config=.flake8 "${PY[@]}" 2>&1 | head -15 | sed 's/^/        /'
    fi

    # code-quality.yml runs bandit with NO severity floor -- stricter than the
    # medium-and-up filter used elsewhere. A B105 on a constant named *_PREFIX
    # is the classic false positive; annotate it with "# nosec B105".
    BANDIT_OUT=$(python3 -m bandit -c .bandit -q "${PY[@]}" 2>&1)
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

# ---------------------------------------------------------------- result
printf '\n'
if [ "$FAILED" -eq 0 ]; then
  printf 'pre-flight clean -- safe to commit and push\n'
  exit 0
fi
printf '%d pre-flight failure(s) -- fix before pushing\n' "$FAILED"
exit 1
