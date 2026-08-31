#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# provision-runner-host.sh — install what a self-hosted CI runner needs (#15310).
#
# Run ON a runner host. Idempotent: every step checks before acting, so a second
# run reports and changes nothing.
#
#   --check    report what is missing and exit non-zero if anything is; changes nothing
#   --apply    install what is missing
#
# WHY THIS EXISTS
#
# CI jobs moved onto the self-hosted runners failed at `Set up Python 3.14`.
# actions/setup-python resolves a version by downloading from
# actions/python-versions, which publishes builds for LTS Ubuntu only
# (22.04/24.04/26.04). The runners are on 25.10, so there is nothing to fetch
# (#15313). #15314 made the shared setup action fall back to the interpreter
# already on PATH — which only helps once that interpreter exists.
#
# A venv cannot supply it: `python3.14 -m venv` needs python3.14 to already be
# installed. The interpreter comes first, the venv second — the same order
# install.sh:396-406 and the backend ansible role already use on every other
# AutoBot host. This script applies that established step to runner hosts, which
# had no provisioning path of their own.
#
# The deadsnakes PPA is deliberate and matches the rest of the platform: it
# publishes for non-LTS releases, so the runner OS does not have to change.

set -euo pipefail

PYTHON_VERSION="${RUNNER_PYTHON_VERSION:-3.14}"
PY_BIN="python${PYTHON_VERSION}"
MODE=""

case "${1:-}" in
  --check) MODE=check ;;
  --apply) MODE=apply ;;
  -h|--help) sed -n '8,14p' "$0"; exit 0 ;;
  *) echo "usage: $(basename "$0") {--check|--apply}" >&2; exit 2 ;;
esac

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; NC=$'\033[0m'
ok()   { echo "${GREEN}[OK]${NC} $*"; }
warn() { echo "${YELLOW}[--]${NC} $*"; }
bad()  { echo "${RED}[!!]${NC} $*"; }

missing=0

# --- the interpreter -------------------------------------------------------
# Checked by name, not by `python3 --version`: the shared setup action resolves
# the versioned binary specifically, and a host whose default python3 happens to
# be 3.14 still fails if `python3.14` is absent from PATH.
if command -v "$PY_BIN" >/dev/null 2>&1; then
  ok "$PY_BIN present ($("$PY_BIN" --version 2>&1))"
else
  bad "$PY_BIN NOT on PATH — this is what fails CI jobs on this host"
  missing=1
fi

# `python3.14 -m venv` is a separate package on Debian/Ubuntu and fails at USE
# time, not install time, so check it by actually creating one.
#
# NOT `-m venv --help`: that exits through argparse before `create()` runs, so
# it proves only that the venv module imports. Debian keeps `venv` in the stdlib
# while shipping `ensurepip` in python3.x-venv, so a host missing that package
# answers --help happily and then fails the first real creation with
# "ensurepip is not available" — a false pass in the one check meant to prevent it.
if command -v "$PY_BIN" >/dev/null 2>&1; then
  _probe="$(mktemp -d)"
  if "$PY_BIN" -m venv "$_probe/v" >/dev/null 2>&1; then
    ok "$PY_BIN -m venv works (created and removed a throwaway venv)"
  else
    bad "$PY_BIN present but creating a venv fails — install python${PYTHON_VERSION}-venv"
    missing=1
  fi
  rm -rf "$_probe"
fi

# NOTE: pip on the host is deliberately NOT checked. setup-python-ci builds a
# venv from this interpreter and installs into that, so the venv supplies its
# own pip (via ensurepip) and its own script directory. A host pip would be
# unused, and installing into it would hit PEP 668's externally-managed guard
# anyway (#15310).

if [ "$MODE" = check ]; then
  if [ "$missing" -eq 0 ]; then
    ok "runner host is provisioned for CI"
    exit 0
  fi
  warn "re-run with --apply to install the missing pieces"
  exit 1
fi

# --- apply -----------------------------------------------------------------
if [ "$missing" -eq 0 ]; then
  ok "nothing to do"
  exit 0
fi

if [ "$(id -u)" -ne 0 ] && ! command -v sudo >/dev/null 2>&1; then
  bad "need root or sudo to install packages"
  exit 1
fi
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

# Same PPA the rest of the platform uses (install.sh:398). Added only when no
# deadsnakes source is already configured, so a device-shipped repo is preserved.
if grep -rqsE "deadsnakes" /etc/apt/sources.list.d/ 2>/dev/null; then
  ok "deadsnakes PPA already configured"
else
  warn "adding deadsnakes PPA"
  $SUDO add-apt-repository -y ppa:deadsnakes/ppa
fi

$SUDO apt-get update -qq
DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq \
  "$PY_BIN" "${PY_BIN}-venv" "${PY_BIN}-dev"

# Bootstrap pip into the interpreter. apt does not provide a python3.14-pip
# package; ensurepip (from python3.14-venv) is the supported route.
if ! "$PY_BIN" -m pip --version >/dev/null 2>&1; then
  warn "bootstrapping pip via ensurepip"
  "$PY_BIN" -m ensurepip --upgrade || $SUDO "$PY_BIN" -m ensurepip --upgrade
fi

# Verify by the same tests the check mode uses, rather than trusting apt's exit.
if command -v "$PY_BIN" >/dev/null 2>&1 \
   && "$PY_BIN" -m venv --help >/dev/null 2>&1 \
   && "$PY_BIN" -m pip --version >/dev/null 2>&1; then
  ok "$PY_BIN installed ($("$PY_BIN" --version 2>&1)), venv and pip work"
else
  bad "install completed but $PY_BIN is still not usable — check apt output above"
  exit 1
fi
