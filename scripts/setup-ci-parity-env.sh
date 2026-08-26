#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# Build the same Python environment CI builds, locally (#13573).
#
# CI runs Python 3.14. A developer box's default `python3` is usually older, and
# every local gate silently uses it. That is not cosmetic:
#
#   - `black` SKIPS its AST safety check when the running interpreter is older
#     than the target version, so the local format gate is structurally weaker
#     than the CI one and says so only in a warning
#   - version-dependent tests cannot be reproduced at all. `\z` in a regex is a
#     re.error on 3.10 and valid from 3.12, so a red CI test is green locally and
#     can only be diagnosed by reading shard logs
#   - it has already changed an implementation decision: #13547 chose
#     `(str, Enum)` over `StrEnum` because the dev box could not run 3.11+
#
# This mirrors .github/actions/setup-python-suite/action.yml step for step: same
# interpreter, same two requirement files, same --prefer-binary, same PyTorch CPU
# index, same venv path. Keeping the path identical to CI's means a developer and
# a runner describe the same location when something goes wrong.
#
# Reconciles on every run. No sudo. Installs nothing outside the venv.
#
# It used to be idempotent by EXISTENCE: a second run checked the directory was
# there and the interpreter was 3.14, then stopped. So the venv drifted as the
# requirement files moved, while pr-preflight.sh kept calling it parity (#15130).
# Measured before the fix, against these two files alone: 21 of 86 declared
# versions unsatisfied, and 9 declared packages not installed at all. The
# second number is the dangerous one -- a test module that importorskip()s a
# missing package is never collected, so the run passes by doing less.
#
# Every run now compares what is installed against what those two files declare,
# using pipeline-scripts/check_dependency_floors.py (#15091) scoped with --roots
# to the files this script installs -- judging it against the backend
# requirements it deliberately never installs would report drift that isn't.
#
# Usage:
#   scripts/setup-ci-parity-env.sh            # build if missing, reconcile if stale
#   scripts/setup-ci-parity-env.sh --check    # report only; never installs. exit 1 if stale
#   scripts/setup-ci-parity-env.sh --recreate # rebuild from scratch
#   scripts/setup-ci-parity-env.sh --print    # print the interpreter path, nothing else
#
# Then either activate it, or let scripts/pr-preflight.sh find it automatically:
#   source "$HOME/.venv-python-suite/bin/activate"

set -euo pipefail

VENV="${CI_PARITY_VENV:-$HOME/.venv-python-suite}"
PY_BIN="$VENV/bin/python"

# Kept in one place so a CI bump is a one-line change here too. Sourced from
# .github/actions/setup-python-suite/action.yml and code-quality.yml.
REQUIRED_MAJOR_MINOR="3.14"
TORCH_CPU_INDEX="https://download.pytorch.org/whl/cpu"

# The requirement files this script installs -- and, necessarily, the exact set
# it is judged against. One array feeds both the pip install and the floor
# check, so the two can never describe different environments.
REQUIREMENT_FILES=(requirements-ci.txt requirements-ci-test.txt)
FLOOR_CHECK="pipeline-scripts/check_dependency_floors.py"

RECREATE=0 PRINT_ONLY=0 CHECK_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --recreate) RECREATE=1; shift ;;
    --print)    PRINT_ONLY=1; shift ;;
    --check)    CHECK_ONLY=1; shift ;;
    -h|--help)  sed -n '5,44p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ "$PRINT_ONLY" = 1 ]; then
  [ -x "$PY_BIN" ] && echo "$PY_BIN" || exit 1
  exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$REPO_ROOT" || exit 2

# ---------------------------------------------------------------- interpreter

find_interpreter() {
  # An explicit override wins, so a box that keeps 3.14 somewhere unusual is not
  # stuck. Otherwise prefer the exact version CI pins over whatever `python3` is.
  if [ -n "${CI_PARITY_PYTHON:-}" ]; then
    command -v "$CI_PARITY_PYTHON" && return 0
  fi
  command -v "python$REQUIRED_MAJOR_MINOR" 2>/dev/null && return 0
  # Last resort: the default, but only if it already IS the right version.
  local default_mm
  default_mm=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)
  if [ "$default_mm" = "$REQUIRED_MAJOR_MINOR" ]; then
    command -v python3 && return 0
  fi
  return 1
}

if ! BASE_PYTHON=$(find_interpreter); then
  cat >&2 <<EOF
error: no Python $REQUIRED_MAJOR_MINOR interpreter found.

CI runs $REQUIRED_MAJOR_MINOR (.github/actions/setup-python-suite/action.yml). This box's
default python3 is $(python3 -V 2>&1 | awk '{print $2}').

Install $REQUIRED_MAJOR_MINOR through your OS package manager, or point this script at an
existing one:

    CI_PARITY_PYTHON=/path/to/python$REQUIRED_MAJOR_MINOR scripts/setup-ci-parity-env.sh

This script deliberately does not install an interpreter for you -- that is a
system-level change, and it belongs to whoever owns the box.
EOF
  exit 1
fi

echo "base interpreter: $BASE_PYTHON ($("$BASE_PYTHON" -V 2>&1))"

# --------------------------------------------------------------------- build

# A venv records an absolute path to the interpreter that created it, so one
# built against 3.14.6 is a dangling symlink after an upgrade to 3.14.7. CI keys
# its cache on the full version for the same reason; here we just rebuild.
venv_is_healthy() {
  [ -x "$PY_BIN" ] || return 1
  "$PY_BIN" -c 'import sys' 2>/dev/null || return 1
  local mm
  mm=$("$PY_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  [ "$mm" = "$REQUIRED_MAJOR_MINOR" ]
}

# requirements-ci.txt never names torch -- it arrives transitively via
# sentence-transformers, and resolved against PyPI that pulls the CUDA build
# (~1.6GB of nvidia-* wheels). The CPU index yields torch==X.Y.Z+cpu, whose
# PEP 440 local version segment sorts above the plain release, so the CPU
# build wins without torch being pinned anywhere.
install_requirements() {
  local file
  for file in "${REQUIREMENT_FILES[@]}"; do
    echo "installing $file..."
    "$PY_BIN" -m pip install -r "$file" --prefer-binary \
      --extra-index-url "$TORCH_CPU_INDEX"
  done
}

# What the venv is measured against. Scoped with --roots to the files this
# script installs: the backend requirement files describe components CI's
# python suite never installs either, so counting them would report a
# shortfall no rebuild could ever clear. --strict turns the report into an
# exit code; --all lists every offender, because "and 11 more" is exactly the
# information a developer deciding whether to rebuild needs.
#
# --require-present because for THIS venv a declared package with nothing
# installed against it is the worst kind of drift, not a neutral fact: a test
# module that importorskip()s it is never collected, so the shard passes by
# running less. Nine of the 86 were missing here when this was written.
FLOOR_REPORT=""
floor_check_passes() {
  FLOOR_REPORT=$("$PY_BIN" "$FLOOR_CHECK" --root "$REPO_ROOT" \
    --roots "${REQUIREMENT_FILES[@]}" --require-present --all --strict 2>&1) && return 0
  # Exit 2 is the reporter saying it could not do its job -- an unreadable or
  # empty requirement sweep. Treating that as "stale" would send a developer
  # into a reinstall to fix a broken checker, so it stops here instead.
  if [ "$?" -gt 1 ]; then
    echo "error: the dependency floor check did not run:" >&2
    printf '%s\n' "$FLOOR_REPORT" | sed 's/^/  /' >&2
    exit 2
  fi
  return 1
}

report_floors() {
  printf '%s\n' "$FLOOR_REPORT" | sed 's/^/  /'
}

if [ "$RECREATE" = 1 ] || ! venv_is_healthy; then
  if [ "$CHECK_ONLY" = 1 ]; then
    echo "error: no usable $REQUIRED_MAJOR_MINOR venv at $VENV" >&2
    echo "       build it with: scripts/setup-ci-parity-env.sh" >&2
    exit 1
  fi
  if [ "$RECREATE" = 1 ]; then
    echo "recreating $VENV"
  elif [ -e "$VENV" ]; then
    echo "existing venv is unusable or the wrong version -- rebuilding $VENV"
  else
    echo "creating $VENV"
  fi
  # Rebuild from scratch so a partially-populated directory left by a failed
  # earlier attempt can never masquerade as a complete environment. Same
  # reasoning as the CI action.
  rm -rf "$VENV"
  "$BASE_PYTHON" -m venv "$VENV"
  "$PY_BIN" -m pip install --quiet --upgrade pip setuptools wheel
  install_requirements

  # Say what a fresh build actually achieves rather than implying zero. A
  # residual shortfall here is a resolver outcome -- two declarations pip
  # cannot satisfy at once -- not drift, and it is the developer's to judge.
  if floor_check_passes; then
    echo "$FLOOR_REPORT"
  else
    echo "note: freshly built, and still below the declared set:"
    report_floors
    echo "      This is what pip could resolve for the two files above, not drift."
  fi
else
  # The reason this script exists is that "the directory is there" was being
  # read as "the environment matches CI". Reconcile instead of assuming.
  echo "checking $VENV against ${REQUIREMENT_FILES[*]}"
  if floor_check_passes; then
    echo "$FLOOR_REPORT"
  elif [ "$CHECK_ONLY" = 1 ]; then
    echo "STALE -- the venv no longer matches what these files declare:"
    report_floors
    exit 1
  else
    echo "stale -- reconciling in place:"
    report_floors
    # Repair, do not rebuild. Every shortfall observed has been an installed
    # version OLDER than a satisfiable declaration, which re-running the same
    # two installs fixes; a rm -rf would re-download the whole torch stack to
    # reach the same place. --recreate stays for the case this cannot fix.
    install_requirements
    if ! floor_check_passes; then
      echo "error: still below the declared set after reinstalling:" >&2
      report_floors >&2
      echo "       re-run with --recreate to rebuild from scratch" >&2
      exit 1
    fi
    echo "$FLOOR_REPORT"
  fi
fi

# -------------------------------------------------------------------- verify

# Fail loudly rather than leaving a half-built environment that silently falls
# back to the system interpreter -- which is the exact failure this script exists
# to remove.
missing=()
for module in pytest black flake8 bandit; do
  "$PY_BIN" -c "import $module" 2>/dev/null || missing+=("$module")
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "error: environment is incomplete, missing: ${missing[*]}" >&2
  echo "       re-run with --recreate" >&2
  exit 1
fi

cat <<EOF

ready: $("$PY_BIN" -V 2>&1) at $PY_BIN
       $("$PY_BIN" -m pip list 2>/dev/null | wc -l) packages

scripts/pr-preflight.sh picks this up automatically. To use it directly:

    export SLM_SECRET_KEY=throwaway SLM_ENCRYPTION_KEY=x
    "$PY_BIN" -m pytest <target> -q

or activate it for the shell:

    source "$VENV/bin/activate"
EOF
