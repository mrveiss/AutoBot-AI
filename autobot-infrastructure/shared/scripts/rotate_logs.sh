#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot Log Rotation Script

# #13149: both paths defaulted to the deployed install, so running this from a
# checkout gzipped and `-delete`d the LIVE install's logs — the #13092 failure
# class. The shared helper resolves the root from this file's own location and
# still lets AUTOBOT_PROJECT_ROOT override it.
# shellcheck source=scripts/lib/project_root.sh
source "$(dirname "${BASH_SOURCE[0]}")/../../../scripts/lib/project_root.sh"

LOGS_DIR="${PROJECT_ROOT}/logs"
ARCHIVE_DIR="${PROJECT_ROOT}/logs/archive"
MAX_AGE_DAYS=30

# Create archive directory
mkdir -p "$ARCHIVE_DIR"

# Rotate logs
find "$LOGS_DIR" -name "*.log" -size +10M -exec gzip {} \; -exec mv {}.gz "$ARCHIVE_DIR/" \;

# Clean old archives
find "$ARCHIVE_DIR" -name "*.gz" -mtime +$MAX_AGE_DAYS -delete

echo "Log rotation completed at $(date)"
