#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# Write apt's network and lock bounds for a CI runner (#21325).
#
# Usage: sudo apt_network_config.sh [CONF_FILE]    (default: /etc/apt/apt.conf.d/80-ci-provisioning)
# The one definition of these settings for CI: the setup-python-suite action's provisioning step and the
# Clean install workflow both run this script before their first apt call, so every `apt-get update` on
# the runner -- including the ones the installer and Ansible's apt_repository make -- drops a stalled
# connection and a stuck dpkg lock wait instead of waiting out apt's defaults. There is no Error-Mode
# here: the runner image's own third-party sources are outside this repo, and one of them failing must
# not fail a job whose packages come from the Ubuntu archive (docker/apt/80-autobot-resilience, for image
# builds, makes that fatal instead).
#
# CI-environment mitigation only: it does not reach an installer run on a real host (#21358).

set -euo pipefail

readonly APT_FETCH_RETRIES=3      # apt's own retries of one failed download
readonly APT_HTTP_IDLE_S=30       # drop a connection that sends nothing this long
readonly APT_LOCK_WAIT_S=120      # wait this long for the dpkg lock

conf="${1:-/etc/apt/apt.conf.d/80-ci-provisioning}"
printf '%s\n' \
    "Acquire::Retries \"${APT_FETCH_RETRIES}\";" \
    "Acquire::http::Timeout \"${APT_HTTP_IDLE_S}\";" \
    "Acquire::https::Timeout \"${APT_HTTP_IDLE_S}\";" \
    "DPkg::Lock::Timeout \"${APT_LOCK_WAIT_S}\";" \
    | tee "${conf}" >/dev/null
