#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Takes a fresh install of the remote test node to ready (#20935). Idempotent: every step checks before it
# acts and the last step VERIFIES the result, so a second run changes nothing and a broken node fails loudly.
# Runs ON the node; `run.py --provision` sends it. Nothing done to the node by hand is assumed.
#   provision.sh <base> <origin-url> <python-floor, e.g. 3.14> < requirements
#
# Base systems: Debian family (apt: Debian, Ubuntu, elementary OS ...) and Fedora family (dnf). The distro is
# read from /etc/os-release (ID, ID_LIKE), never assumed. Python: the base's own interpreter when it meets the
# repo's floor (run.py reads the floor from .python-version). Below the floor, the base's package is tried
# (python<floor> from the base's repositories), and if the base does not have it, the canonical route is
# `uv python install <floor>`, with uv itself installed from PyPI at AUTOBOT_TEST_NODE_UV_VERSION into a venv
# under <base> (no remote install script is run).
set -euo pipefail

die() { echo "[provision] ERROR: $*" >&2; exit 1; }
info() { echo "[provision] $*" >&2; }

detect_pkg_manager() {
  local file="${OS_RELEASE_FILE:-/etc/os-release}" id="" like=""
  [ -r "$file" ] || die "cannot read $file: the node's distribution is unknown"
  id=$(. "$file" && echo "${ID:-}")
  like=$(. "$file" && echo "${ID_LIKE:-}")
  case " $id $like " in
    *" debian "*|*" ubuntu "*) echo apt ;;
    *" fedora "*|*" rhel "*) echo dnf ;;
    *) die "unsupported distribution '$id' (ID_LIKE='$like'): add its package manager to detect_pkg_manager" ;;
  esac
}

# 0 when `$1` (an interpreter) is at least major.minor `$2`.
python_meets_floor() {
  command -v "$1" >/dev/null 2>&1 || return 1
  "$1" -c 'import sys; f = tuple(map(int, sys.argv[1].split(".")[:2])); sys.exit(0 if sys.version_info[:2] >= f else 1)' "$2" 2>/dev/null
}

check_floor_or_die() {
  python_meets_floor "$1" "$2" && return 0
  local have
  have=$("$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "none")
  die "Python $have ($1) is below the repository floor $2 (.python-version)"
}

pkg_install() {
  case "$(detect_pkg_manager)" in
    apt) sudo -n apt-get install -y --no-install-recommends "$@" ;;
    dnf) sudo -n dnf install -y "$@" ;;
  esac
}

pkg_available() {
  case "$(detect_pkg_manager)" in
    apt) apt-cache show "$1" >/dev/null 2>&1 ;;
    dnf) dnf list --available "$1" >/dev/null 2>&1 ;;
  esac
}

install_base_tools() {
  local need=() tool
  for tool in flock setsid git; do command -v "$tool" >/dev/null 2>&1 || need+=("$tool"); done
  [ "${#need[@]}" -eq 0 ] && return 0
  info "installing base tools for: ${need[*]}"
  case "$(detect_pkg_manager)" in
    apt) sudo -n apt-get update -qq; pkg_install util-linux git ;;
    dnf) pkg_install util-linux git ;;
  esac
}

# Prints the path of an interpreter that meets the floor, installing one if the base has none.
ensure_python() {
  local floor="$1" cand
  for cand in "python$floor" python3; do
    python_meets_floor "$cand" "$floor" && { command -v "$cand"; return 0; }
  done
  if pkg_available "python$floor"; then
    info "installing python$floor from the base's repositories"
    pkg_install "python$floor" "python$floor-venv" >&2 || true
    python_meets_floor "python$floor" "$floor" && { command -v "python$floor"; return 0; }
  fi
  install_python_with_uv "$floor"
}

install_python_with_uv() {
  local floor="$1" tools="$base/uv-tools" ver="${AUTOBOT_TEST_NODE_UV_VERSION:-0.9.0}"
  info "the base has no Python $floor: installing it with uv $ver"
  python3 -c 'import ensurepip' 2>/dev/null || pkg_install python3-venv >&2
  [ -x "$tools/bin/uv" ] || { python3 -m venv "$tools" && "$tools/bin/python" -m pip install --quiet "uv==$ver"; } >&2
  UV_PYTHON_INSTALL_DIR="$base/python" "$tools/bin/uv" python install "$floor" >&2
  UV_PYTHON_INSTALL_DIR="$base/python" "$tools/bin/uv" python find "$floor"
}

make_venv() {
  local py="$1" floor="$2"
  if [ -x "$base/venv/bin/python" ] && ! python_meets_floor "$base/venv/bin/python" "$floor"; then
    info "the venv's Python is below $floor: rebuilding it"
    rm -rf -- "$base/venv"
  fi
  [ -x "$base/venv/bin/python" ] && return 0
  "$py" -m venv "$base/venv" 2>/dev/null && return 0
  pkg_install "python$floor-venv" >&2 || pkg_install python3-venv >&2
  "$py" -m venv "$base/venv"
}

sync_mirror() {
  # The mirror the pushed commits land in. It follows the public base branch, so a run ships only what the
  # branch adds; the node holds no repository credential.
  if [ ! -d "$base/mirror.git" ]; then
    git init --quiet --bare "$base/mirror.git"
    git --git-dir="$base/mirror.git" remote add origin "$origin"
  fi
  git --git-dir="$base/mirror.git" fetch --quiet --no-tags origin '+refs/heads/main:refs/heads/main'
}

install_requirements() {
  local want have
  want=$(sha256sum "$reqs" | cut -c1-64)
  have=$(cat "$base/venv/.requirements.sha256" 2>/dev/null || true)
  [ "$want" = "$have" ] && return 0
  "$base/venv/bin/python" -m pip install --quiet --upgrade pip
  "$base/venv/bin/python" -m pip install --quiet -r "$reqs"
  printf '%s\n' "$want" > "$base/venv/.requirements.sha256"
}

# The last word: everything a run needs, checked, so "provisioned" is a claim with evidence.
verify_node() {
  local tool floor="$1"
  for tool in flock setsid git timeout; do command -v "$tool" >/dev/null 2>&1 || die "verify: $tool is missing"; done
  check_floor_or_die "$base/venv/bin/python" "$floor"
  "$base/venv/bin/python" -c 'import pytest, xdist' || die "verify: pytest / xdist are not importable in the venv"
  git --git-dir="$base/mirror.git" rev-parse --verify -q refs/heads/main >/dev/null || die "verify: the mirror has no main"
  info "verified: $("$base/venv/bin/python" --version), $(git --version), pytest, xdist, mirror at $(git --git-dir="$base/mirror.git" rev-parse --short refs/heads/main)"
}

main() {
  base="$1"; origin="$2"; local floor="$3" py
  reqs=$(mktemp)
  trap 'rm -f -- "$reqs"' EXIT
  cat > "$reqs"
  mkdir -p "$base"; base=$(cd "$base" && pwd)
  info "distribution package manager: $(detect_pkg_manager)"
  install_base_tools
  mkdir -p "$base/runs" "$base/slots"
  py=$(ensure_python "$floor")
  check_floor_or_die "$py" "$floor"
  make_venv "$py" "$floor"
  sync_mirror
  install_requirements
  verify_node "$floor"
  echo "provisioned"
}

[ -n "${PROVISION_SOURCE_ONLY:-}" ] || main "$@"
