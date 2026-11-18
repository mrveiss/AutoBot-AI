#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Write the ACL file the compose Redis reads, from the password in $AUTOBOT_REDIS_PASSWORD (#17500).
# Only the password's hash goes in it, so the file can be readable by the container's user and no
# password appears on Redis's command line.
#
# Usage: AUTOBOT_REDIS_PASSWORD=... bash docker/write-redis-acl.sh
set -euo pipefail

: "${AUTOBOT_REDIS_PASSWORD:?AUTOBOT_REDIS_PASSWORD is required}"
acl_file="$(cd "$(dirname "$0")" && pwd)/.redis-users.acl"
hash="$(printf '%s' "$AUTOBOT_REDIS_PASSWORD" | openssl dgst -sha256 -r | cut -d' ' -f1)"
printf 'user default on #%s ~* &* +@all\n' "$hash" >"$acl_file"
chmod 644 "$acl_file"
