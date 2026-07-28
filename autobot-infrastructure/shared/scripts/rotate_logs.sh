#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot Log Rotation Script

LOGS_DIR="${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/logs"
ARCHIVE_DIR="${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/logs/archive"
MAX_AGE_DAYS=30

# Create archive directory
mkdir -p "$ARCHIVE_DIR"

# Rotate logs
find "$LOGS_DIR" -name "*.log" -size +10M -exec gzip {} \; -exec mv {}.gz "$ARCHIVE_DIR/" \;

# Clean old archives
find "$ARCHIVE_DIR" -name "*.gz" -mtime +$MAX_AGE_DAYS -delete

echo "Log rotation completed at $(date)"
