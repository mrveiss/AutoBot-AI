#!/usr/bin/env bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
#
# Phase 4 (#7590): Nightly disk file count monitor for chat SSOT observability.
#
# Usage:
#   check_chat_disk_files.sh [--data-dir PATH] [--pushgateway URL]
#
# Counts files in data/chats/, writes the baseline on first run, then
# alerts if the count exceeds 2× baseline.  Pushes gauges to a Prometheus
# Pushgateway when --pushgateway is set.
#
# Cron example (nightly at 02:00):
#   0 2 * * * /app/scripts/check_chat_disk_files.sh \
#     --data-dir /app/data/chats \
#     --pushgateway http://pushgateway:9091 \
#     >> /var/log/autobot/chat_disk_monitor.log 2>&1

set -euo pipefail

DATA_DIR="${AUTOBOT_DATA_DIR:-/app/data}/chats"
BASELINE_FILE="${AUTOBOT_DATA_DIR:-/app/data}/.chat_disk_baseline"
PUSHGATEWAY=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --data-dir)   DATA_DIR="$2";    shift 2 ;;
        --pushgateway) PUSHGATEWAY="$2"; shift 2 ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

FILE_COUNT=$(ls -1 "$DATA_DIR" 2>/dev/null | wc -l | tr -d ' ')
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "$TIMESTAMP  chat_disk_file_count=$FILE_COUNT  data_dir=$DATA_DIR"

# Establish baseline on first run
if [[ ! -f "$BASELINE_FILE" ]]; then
    echo "$FILE_COUNT" > "$BASELINE_FILE"
    echo "$TIMESTAMP  Baseline established: $FILE_COUNT"
fi

BASELINE=$(cat "$BASELINE_FILE")
THRESHOLD=$(( BASELINE * 2 ))

if [[ "$FILE_COUNT" -gt "$THRESHOLD" ]]; then
    echo "ALERT: chat disk file count ($FILE_COUNT) > 2× baseline ($BASELINE). Investigate data/chats/ for leaks." >&2
fi

# Push to Prometheus Pushgateway if configured
if [[ -n "$PUSHGATEWAY" ]]; then
    cat <<EOF | curl --silent --fail \
        --data-binary @- \
        "${PUSHGATEWAY}/metrics/job/autobot_chat_disk_monitor"
# TYPE autobot_chat_disk_file_count gauge
# HELP autobot_chat_disk_file_count Number of files in data/chats/
autobot_chat_disk_file_count $FILE_COUNT
# TYPE autobot_chat_disk_file_count_baseline gauge
# HELP autobot_chat_disk_file_count_baseline Baseline file count (first run)
autobot_chat_disk_file_count_baseline $BASELINE
EOF
    echo "$TIMESTAMP  Pushed to Pushgateway: $PUSHGATEWAY"
fi
