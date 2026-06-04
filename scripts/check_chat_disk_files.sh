#!/usr/bin/env bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
#
# Phase 4 (#7590): Nightly disk file count monitor for chat SSOT observability.
#
# Samples data/chats/ file count, writes a baseline on first run, logs a
# structured JSON line, and optionally pushes Prometheus gauges to a
# Prometheus Pushgateway.
#
# Usage:
#   check_chat_disk_files.sh [--data-dir PATH] [--pushgateway URL] [--dry-run]
#
# Environment:
#   AUTOBOT_DATA_DIR            Root of the data directory (default: /app/data)
#   AUTOBOT_CHAT_DISK_BASELINE  Override baseline count (skip first-run bootstrap)
#
# Cron example (nightly at 02:00):
#   0 2 * * * /app/scripts/check_chat_disk_files.sh \
#       --data-dir /app/data/chats \
#       --pushgateway http://pushgateway:9091 \
#       >> /var/log/autobot/chat_disk_monitor.log 2>&1

set -euo pipefail

DATA_DIR="${AUTOBOT_DATA_DIR:-/app/data}/chats"
BASELINE_FILE="${AUTOBOT_DATA_DIR:-/app/data}/.chat_disk_baseline"
PUSHGATEWAY=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --data-dir)    DATA_DIR="$2";      shift 2 ;;
        --pushgateway) PUSHGATEWAY="$2";   shift 2 ;;
        --dry-run)     DRY_RUN=true;       shift   ;;
        *) printf 'Unknown argument: %s\n' "$1" >&2; exit 1 ;;
    esac
done

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Use find -maxdepth 1 so we don't recurse into subdirectories and avoid
# issues with directories containing spaces in names.
if [[ -d "$DATA_DIR" ]]; then
    FILE_COUNT=$(find "$DATA_DIR" -maxdepth 1 -type f | wc -l | tr -d ' ')
else
    FILE_COUNT=0
    printf '%s  WARN data_dir=%s does not exist, reporting 0\n' "$TIMESTAMP" "$DATA_DIR" >&2
fi

# Establish baseline on first run, or read from env override
if [[ -n "${AUTOBOT_CHAT_DISK_BASELINE:-}" ]]; then
    BASELINE="${AUTOBOT_CHAT_DISK_BASELINE}"
elif [[ ! -f "$BASELINE_FILE" ]]; then
    BASELINE="$FILE_COUNT"
    if [[ "$DRY_RUN" == "false" ]]; then
        printf '%s\n' "$BASELINE" > "$BASELINE_FILE"
    fi
    printf '%s  BASELINE_SET value=%s data_dir=%s\n' "$TIMESTAMP" "$BASELINE" "$DATA_DIR"
else
    BASELINE=$(cat "$BASELINE_FILE")
fi

THRESHOLD=$(( BASELINE * 2 ))

# Structured JSON log line — Loki-parseable
LOG_PAYLOAD=$(printf '{"event":"chat_disk_file_count","timestamp":"%s","value":%s,"baseline":%s,"threshold":%s,"data_dir":"%s"}' \
    "$TIMESTAMP" "$FILE_COUNT" "$BASELINE" "$THRESHOLD" "$DATA_DIR")
printf '%s\n' "$LOG_PAYLOAD"

if [[ "$FILE_COUNT" -gt "$THRESHOLD" ]]; then
    printf '{"event":"chat_disk_file_count_alert","timestamp":"%s","value":%s,"baseline":%s,"message":"file count exceeds 2x baseline — investigate data/chats/ for leaks"}\n' \
        "$TIMESTAMP" "$FILE_COUNT" "$BASELINE" >&2
fi

# Push Prometheus metrics to Pushgateway when configured
if [[ -n "$PUSHGATEWAY" && "$DRY_RUN" == "false" ]]; then
    METRICS_BODY=$(cat <<METRICS
# TYPE autobot_chat_disk_file_count gauge
# HELP autobot_chat_disk_file_count Number of files in data/chats/ (sampled nightly)
autobot_chat_disk_file_count ${FILE_COUNT}
# TYPE autobot_chat_disk_file_count_baseline gauge
# HELP autobot_chat_disk_file_count_baseline Baseline file count established on first run
autobot_chat_disk_file_count_baseline ${BASELINE}
METRICS
)
    if printf '%s\n' "$METRICS_BODY" | curl --silent --fail \
        --data-binary @- \
        "${PUSHGATEWAY}/metrics/job/autobot_chat_disk_monitor/instance/$(hostname)"; then
        printf '{"event":"chat_disk_pushgateway_ok","timestamp":"%s","url":"%s"}\n' \
            "$TIMESTAMP" "$PUSHGATEWAY"
    else
        printf '{"event":"chat_disk_pushgateway_error","timestamp":"%s","url":"%s"}\n' \
            "$TIMESTAMP" "$PUSHGATEWAY" >&2
        exit 1
    fi
fi
