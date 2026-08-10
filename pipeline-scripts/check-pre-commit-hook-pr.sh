#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Generic CI wrapper for pre-commit hooks and Python validators.
# Issue #6785 (follow-up to #6725 / #6783): closes the bypass gap for
# pre-commit hooks across the board, not just hardcoded-values.
# Issue #6991: extended to also support Python validators (tools/lint/*.py)
# so the two per-hook wrappers (check-hardcoded-values-pr.sh,
# check-hardcoded-ip-fallbacks-pr.sh) can be retired in favour of this one.
#
# Each hook gets an argv mode (positional args = files to scan, no args =
# fall back to git diff --cached). This wrapper computes the changed-file
# set for the PR/push context and invokes the hook in argv mode.
#
# Usage:
#   bash pipeline-scripts/check-pre-commit-hook-pr.sh [--changed-lines-only] <hook-name>
#   bash pipeline-scripts/check-pre-commit-hook-pr.sh --python <validator-path> [--ext py,ts,...]
#
# --changed-lines-only (#13950)
#   Report only violations on lines this PR actually added. Without it the hook
#   reads each changed file whole, so editing one line of a legacy module makes
#   the PR answerable for that file's entire backlog: four PRs in one session
#   failed on violations blame attributes to other commits, and in two of them
#   the constant the message suggested was the wrong concept (an RBAC role and a
#   ceiling), so the mechanical fix would have gone green while encoding a
#   different meaning. Opt-in per invocation rather than default, so hooks whose
#   output this wrapper cannot parse keep their existing behaviour exactly.
#   Suppressed violations are still printed, and the whole-file backlog stays
#   visible by running the hook directly.
#
# Examples (in GitHub Actions steps):
#   - run: bash pipeline-scripts/check-pre-commit-hook-pr.sh pre-commit-no-print-console
#   - run: bash pipeline-scripts/check-pre-commit-hook-pr.sh --python tools/lint/check_no_hardcoded_ip_fallbacks.py
#   - run: bash pipeline-scripts/check-pre-commit-hook-pr.sh --python tools/lint/check_no_hardcoded_ip_fallbacks.py --ext py
#
# Inputs (env, all optional — defaults derived from git/GH Actions):
#   BASE_SHA          explicit PR base SHA
#   HEAD_SHA          explicit head SHA (default: HEAD or GITHUB_SHA)
#   GITHUB_BASE_REF   PR target branch (set by GH Actions)
#   GITHUB_SHA        commit SHA (set by GH Actions)
#
# Bash hook requirements:
#   1. Live at autobot-infrastructure/shared/scripts/hooks/<hook-name>
#   2. Accept positional args as a file list (override git diff --cached)
#   3. Exit 1 on violations, 0 on clean
#
# Python validator requirements:
#   1. Accept positional file paths as arguments
#   2. Exit 1 on violations, 0 on clean

set -euo pipefail

# ── Argument parsing ─────────────────────────────────────────────────────────

USE_PYTHON=false
VALIDATOR_PATH=""
HOOK_NAME=""
CHANGED_LINES_ONLY=false
# An ARRAY, not a string (#13880). As a string it was passed unquoted to
# `git diff -- $EXT_GLOB`, so the SHELL expanded the globs against the cwd
# before git saw them. In CI the cwd is the repo root, where `*.py` matches
# only the handful of root-level Python files — so the pathspec silently
# collapsed to those, and changed files under autobot-backend/ etc. were never
# scanned. `*.ts`/`*.vue`/`*.js` had no root matches, stayed literal, and were
# handled correctly by git, which is why the gap only affected Python.
EXT_PATHSPEC=('*.py' '*.ts' '*.tsx' '*.vue' '*.js' '*.mjs')

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <hook-name>" >&2
    echo "       $0 --python <validator-path> [--ext py,ts,...]" >&2
    exit 2
fi

if [ "$1" = "--changed-lines-only" ]; then
    CHANGED_LINES_ONLY=true
    shift
    if [ "$#" -lt 1 ]; then
        echo "Usage: $0 --changed-lines-only <hook-name>" >&2
        exit 2
    fi
fi

if [ "$1" = "--python" ]; then
    USE_PYTHON=true
    if [ "$#" -lt 2 ]; then
        echo "Usage: $0 --python <validator-path> [--ext py,ts,...]" >&2
        exit 2
    fi
    VALIDATOR_PATH="$2"
    shift 2
    # Optional --ext override: comma-separated extensions without dots
    if [ "${1:-}" = "--ext" ]; then
        if [ "${2:-}" = "" ]; then
            echo "--ext requires a comma-separated list of extensions" >&2
            exit 2
        fi
        EXT_PATHSPEC=()
        # `|| [ -n "$_ext" ]` catches the final field: tr leaves no trailing
        # newline, so a plain `read` drops the last (or only) extension.
        while IFS= read -r _ext || [ -n "$_ext" ]; do
            [ -n "$_ext" ] || continue
            # Reject anything that is not a bare extension. `--ext .py` would
            # build the pathspec `*..py` and `--ext " py"` builds `*. py`;
            # both match nothing, so the run would report "no changed source
            # files" and exit 0 — the exact silent pass this script exists to
            # prevent, reached by a different route (#13880).
            case "$_ext" in
                *[!A-Za-z0-9]*|"")
                    echo "--ext: '$_ext' is not a bare extension (expected e.g. py,ts)" >&2
                    exit 2
                    ;;
            esac
            EXT_PATHSPEC+=("*.${_ext}")
        done < <(printf '%s' "$2" | tr ',' '\n')
        if [ "${#EXT_PATHSPEC[@]}" -eq 0 ]; then
            echo "--ext produced no usable extensions" >&2
            exit 2
        fi
        shift 2
    fi
    if [ ! -f "$VALIDATOR_PATH" ]; then
        echo "Python validator not found: $VALIDATOR_PATH" >&2
        exit 2
    fi
else
    HOOK_NAME="$1"
    HOOK_PATH="$(dirname "$0")/../autobot-infrastructure/shared/scripts/hooks/${HOOK_NAME}"
    if [ ! -f "$HOOK_PATH" ]; then
        echo "Hook script not found: $HOOK_PATH" >&2
        exit 2
    fi
fi

# ── Changed-file set ─────────────────────────────────────────────────────────

BASE_SHA="${BASE_SHA:-}"
HEAD_SHA="${HEAD_SHA:-${GITHUB_SHA:-HEAD}}"

if [ -z "$BASE_SHA" ]; then
    # On a pull_request event HEAD_SHA is the MERGE commit: ^1 is the base tip
    # as of the event and ^2 is the PR head, so ^1..HEAD is exactly this PR's
    # changes. Resolving origin/<base> instead uses the base's CURRENT tip, so
    # every PR merged in between shows up as a changed file here — worst on a
    # re-run, where HEAD_SHA is frozen but origin/<base> is fetched fresh
    # (#13880). This path was dead under fetch-depth: 1 and would have become
    # live the moment full history arrived.
    if git cat-file -e "${HEAD_SHA}^2^{commit}" 2>/dev/null; then
        BASE_SHA="${HEAD_SHA}^1"
    elif [ -n "${GITHUB_BASE_REF:-}" ]; then
        BASE_SHA=$(git rev-parse "origin/${GITHUB_BASE_REF}" 2>/dev/null || true)
    fi
fi

if [ -n "$BASE_SHA" ]; then
    base="$BASE_SHA"
else
    base="${HEAD_SHA}^"
fi

# A guard that cannot compute its scope must FAIL, never report "nothing
# changed" (#13880). actions/checkout defaults to fetch-depth: 1, so the PR
# base commit is absent, `git diff` fatals, the old `|| true` swallowed it, and
# an empty file list printed "No changed source files — skipping" and exited 0.
# Four CI steps were green no-ops for exactly this reason.
for _ref in "$base" "$HEAD_SHA"; do
    if ! git cat-file -e "${_ref}^{commit}" 2>/dev/null; then
        echo "FATAL: '${_ref}' does not resolve in this clone." >&2
        echo "  A shallow checkout cannot diff against the base — set 'fetch-depth: 0'" >&2
        echo "  on actions/checkout. Refusing to report 'no changed files' for a" >&2
        echo "  scope that could not be computed." >&2
        exit 1
    fi
done

# Cast a wide net (all relevant source extensions); the hook/validator itself
# applies its category-specific allowlist. Quoted array expansion — git must
# receive the globs verbatim and do its own pathspec matching.
if ! raw_files=$(git diff --name-only "$base" "$HEAD_SHA" -- "${EXT_PATHSPEC[@]}"); then
    echo "FATAL: git diff failed for ${base}..${HEAD_SHA} — refusing to report clean." >&2
    exit 1
fi

# Deleted paths still appear in the diff; keep only files that exist on disk.
# The trailing `|| true` normalises the while-loop's EOF exit status (1) under
# `set -e`. It is scoped to the FILTER only — git's exit status is checked
# above, so this no longer hides a failed diff the way the original did.
files=$(printf '%s\n' "$raw_files" \
    | while read -r f; do [ -n "$f" ] && [ -f "$f" ] && printf '%s\n' "$f"; done \
    || true)

if [ -z "$files" ]; then
    if $USE_PYTHON; then
        echo "No changed source files — skipping ${VALIDATOR_PATH}."
    else
        echo "No changed source files — skipping ${HOOK_NAME}."
    fi
    exit 0
fi

count=$(echo "$files" | wc -l)

# ── Invocation ────────────────────────────────────────────────────────────────

if $USE_PYTHON; then
    echo "Running ${VALIDATOR_PATH} against $count changed file(s)..."
    # shellcheck disable=SC2086
    echo "$files" | xargs python3 "$VALIDATOR_PATH"
elif ! $CHANGED_LINES_ONLY; then
    echo "Running ${HOOK_NAME} against $count changed file(s)..."
    # shellcheck disable=SC2086
    bash "$HOOK_PATH" $files
else
    echo "Running ${HOOK_NAME} against $count changed file(s), reporting only added lines..."

    # The set of lines this PR added, as "path:line" keys. -U0 so hunk headers
    # bound exactly the added lines and nothing either side of them.
    added_lines=$(
        for f in $files; do
            git diff -U0 "$base" "$HEAD_SHA" -- "$f" | awk -v path="$f" '
                /^@@/ {
                    # @@ -a,b +c,d @@   (d omitted means 1)
                    match($0, /\+[0-9]+(,[0-9]+)?/)
                    spec = substr($0, RSTART + 1, RLENGTH - 1)
                    n = split(spec, parts, ",")
                    start = parts[1] + 0
                    len = (n > 1) ? parts[2] + 0 : 1
                    for (i = 0; i < len; i++) print path ":" (start + i)
                }'
        done
    ) || {
        echo "FATAL: could not compute the added-line set — refusing to report clean." >&2
        exit 1
    }

    set +e
    hook_output=$(bash "$HOOK_PATH" $files 2>&1)
    hook_status=$?
    set -e

    if [ "$hook_status" -eq 0 ]; then
        printf '%s\n' "$hook_output"
        exit 0
    fi

    # Partition the hook's violation blocks. A block starts at a VIOLATION
    # header carrying "path:line" and runs to the next blank line.
    filtered=$(printf '%s\n' "$hook_output" | ADDED="$added_lines" awk '
        # is_violation distinguishes a real violation block from the hook'"'"'s
        # banner and trailer. Counting those as kept reported "6 violations on
        # lines this PR added" for a PR that added one clean line — the summary
        # would have contradicted the (correct) suppression right above it.
        function flush_block() {
            if (block == "") return
            if (!is_violation) { kept_text = kept_text block }
            else if (keep)     { kept_text = kept_text block; kept++ }
            else               { supp_text = supp_text block; suppressed++ }
            block = ""; keep = 1; is_violation = 0
        }
        BEGIN {
            split(ENVIRON["ADDED"], a, "\n")
            for (i in a) if (a[i] != "") added[a[i]] = 1
            keep = 1
        }
        {
            plain = $0
            gsub(/\033\[[0-9;]*m/, "", plain)
            # The hook'"'"'s trailer counts what the hook found across whole files.
            # In scoped mode this wrapper decides, so printing "COMMIT BLOCKED"
            # next to "not failing the build" would contradict the verdict.
            if (plain ~ /COMMIT BLOCKED/) next
            if (plain ~ /VIOLATION[[:space:]]+[^[:space:]]+:[0-9]+/) {
                flush_block()
                seen_header++
                is_violation = 1
                match(plain, /[^[:space:]]+:[0-9]+/)
                key = substr(plain, RSTART, RLENGTH)
                keep = (key in added) ? 1 : 0
            }
            block = block $0 "\n"
            if (plain ~ /^[[:space:]]*$/) flush_block()
        }
        END {
            flush_block()
            print "@@HEADERS@@" seen_header
            print "@@KEPT@@" kept
            print "@@SUPPRESSED@@" suppressed
            print "@@KEPTTEXT@@"
            printf "%s", kept_text
            print "@@SUPPTEXT@@"
            printf "%s", supp_text
        }
    ')

    seen_headers=$(printf '%s\n' "$filtered" | sed -n 's/^@@HEADERS@@//p')
    kept_count=$(printf '%s\n' "$filtered" | sed -n 's/^@@KEPT@@//p')
    supp_count=$(printf '%s\n' "$filtered" | sed -n 's/^@@SUPPRESSED@@//p')

    # Fail closed. The hook said "violations" and we parsed none, so the output
    # format is not one this filter understands. Suppressing an unparsed
    # failure would turn a real regression into a green build — the precise
    # failure mode #13880 was about, reached from the other direction.
    if [ "${seen_headers:-0}" -eq 0 ]; then
        printf '%s\n' "$hook_output"
        echo "FATAL: ${HOOK_NAME} failed but produced no parseable 'file:line' violations." >&2
        echo "  --changed-lines-only cannot scope this output, and refuses to drop it." >&2
        exit "$hook_status"
    fi

    printf '%s\n' "$filtered" | sed -n '/^@@KEPTTEXT@@$/,/^@@SUPPTEXT@@$/p' | sed '1d;$d'

    if [ "${supp_count:-0}" -gt 0 ]; then
        echo "----------------------------------------"
        echo "${supp_count} pre-existing violation(s) on lines this PR did not touch (#13950):"
        printf '%s\n' "$filtered" | sed -n '/^@@SUPPTEXT@@$/,$p' | sed '1d'
        echo "Not failing the build for these. Run the hook directly for the whole-file backlog."
    fi

    if [ "${kept_count:-0}" -gt 0 ]; then
        echo "${kept_count} violation(s) on lines this PR added."
        exit 1
    fi
    echo "No violations on lines this PR added."
    exit 0
fi
