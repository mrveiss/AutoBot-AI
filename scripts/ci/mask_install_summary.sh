#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# Filter installer output for a public CI log (#19403): the value after "Password:" on the
# summary line is replaced, colour codes included, and every other line passes unchanged.
#   <installer> 2>&1 | mask_install_summary.sh
exec sed -u -E 's/(Password:(\x1b\[[0-9;]*m)?[[:space:]]+).*/\1<masked>/'
