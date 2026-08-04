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
# Idempotent. No sudo. Installs nothing outside the venv.
#
# Usage:
#   scripts/setup-ci-parity-env.sh            # build if missing, else verify
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

RECREATE=0 PRINT_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --recreate) RECREATE=1; shift ;;
    --print)    PRINT_ONLY=1; shift ;;
    -h|--help)  sed -n '5,31p' "$0"; exit 0 ;;
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

if [ "$RECREATE" = 1 ] || ! venv_is_healthy; then
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

  # requirements-ci.txt never names torch -- it arrives transitively via
  # sentence-transformers, and resolved against PyPI that pulls the CUDA build
  # (~1.6GB of nvidia-* wheels). The CPU index yields torch==X.Y.Z+cpu, whose
  # PEP 440 local version segment sorts above the plain release, so the CPU
  # build wins without torch being pinned anywhere.
  echo "installing requirements-ci.txt (this is the slow one)..."
  "$PY_BIN" -m pip install -r requirements-ci.txt --prefer-binary \
    --extra-index-url "$TORCH_CPU_INDEX"

  echo "installing requirements-ci-test.txt..."
  "$PY_BIN" -m pip install -r requirements-ci-test.txt --prefer-binary \
    --extra-index-url "$TORCH_CPU_INDEX"
else
  echo "reusing healthy venv at $VENV"
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
