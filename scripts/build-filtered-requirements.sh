#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
#
# Canonical filtered-requirements + constraint/requirements rewrite (#11134).
#
# Both the backend ansible role (ansible/roles/backend/tasks/main.yml) and
# services/role_registry.py's backend post_sync_cmd previously duplicated this
# grep|sed pipeline independently — a drift hazard (#11134). This script is
# the single source of truth both now invoke.
#
# What it does, and why:
#  - Strips the editable `-e ../autobot_shared` include: autobot_shared is
#    installed separately as its own editable package on deploy, so this
#    self-reference would otherwise fail (../autobot_shared does not exist
#    relative to the synced autobot-backend/ directory).
#  - Rewrites the sibling-relative `-c ../constraints/...` include (#10524
#    shared-version constraints) to the canonical code_source path, which
#    always exists as the git checkout on deploy targets (#11117). Without
#    this, pip errors on the missing constraint file.
#  - Rewrites the sibling-relative `-r ../requirements.txt` include (~23 root
#    runtime deps: paramiko, asyncssh, pypdf, python-docx/pptx, openpyxl, ...)
#    to the same code_source path (#11135). An earlier version of this
#    pipeline stripped `-r` lines entirely instead of rewriting them, which
#    silently dropped those root deps on deploy.
#
# Usage:
#   build-filtered-requirements.sh <requirements_file> <code_source_dir>
#
# Output: filtered requirements written to stdout.
set -euo pipefail

requirements_file="${1:?usage: build-filtered-requirements.sh <requirements_file> <code_source_dir>}"
code_source_dir="${2:?usage: build-filtered-requirements.sh <requirements_file> <code_source_dir>}"

# #14272: the `\.\./` prefix is matched at ANY depth, not just one level.
# The pattern used to be a literal `\.\./`, which fitted the backend's
# requirements.txt (one level up from autobot-backend/) and silently did not
# match autobot-infrastructure/shared/docker/ai-stack/requirements-ai.txt, which
# needs four. A rewrite that only handles the depth it was written against does
# not transfer to the next caller, and the failure is a provisioning abort:
#   ERROR: Could not open constraint file: '/constraints/shared.txt'
grep -Ev '^-e.*autobot[-_]shared' "${requirements_file}" \
  | sed -E "s|^-c (\\.\\./)+constraints/|-c ${code_source_dir}/constraints/|; s|^-r (\\.\\./)+requirements\\.txt|-r ${code_source_dir}/requirements.txt|"
