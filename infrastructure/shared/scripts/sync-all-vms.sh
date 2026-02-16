#!/bin/bash
# Sync code to all fleet VMs
# Fixed quote escaping and added missing components

set -e  # Exit on error

# Define components and their targets
declare -A SYNC_MAP
SYNC_MAP["/home/kali/Desktop/AutoBot/autobot-user-backend"]="172.16.168.20:/opt/autobot/autobot-user-backend"
SYNC_MAP["/home/kali/Desktop/AutoBot/autobot-user-frontend"]="172.16.168.21:/opt/autobot/autobot-user-frontend"
SYNC_MAP["/home/kali/Desktop/AutoBot/autobot-slm-backend"]="172.16.168.19:/opt/autobot/autobot-slm-backend"
SYNC_MAP["/home/kali/Desktop/AutoBot/autobot-slm-frontend"]="172.16.168.19:/opt/autobot/autobot-slm-frontend"
SYNC_MAP["/home/kali/Desktop/AutoBot/autobot-shared"]="172.16.168.19,172.16.168.20,172.16.168.21,172.16.168.22,172.16.168.23,172.16.168.24,172.16.168.25:/opt/autobot/autobot-shared"
SYNC_MAP["/home/kali/Desktop/AutoBot/autobot-npu-worker"]="172.16.168.22:/opt/autobot/autobot-npu-worker"
SYNC_MAP["/home/kali/Desktop/AutoBot/autobot-browser-worker"]="172.16.168.25:/opt/autobot/autobot-browser-worker"

# Use array for rsync options to avoid quote escaping issues
RSYNC_OPTS=(
  -av
  --rsync-path="sudo rsync"
  --exclude="venv"
  --exclude="__pycache__"
  --exclude="*.pyc"
  --exclude=".git"
  --exclude="node_modules"
  --exclude="*.log"
)

echo "=== Syncing Code to All Fleet VMs ==="
echo ""

for src in "${!SYNC_MAP[@]}"; do
  targets="${SYNC_MAP[$src]}"
  IFS=',' read -ra DEST_ARRAY <<< "$targets"

  for dest in "${DEST_ARRAY[@]}"; do
    echo ">>> Syncing: $src -> autobot@$dest"
    if rsync "${RSYNC_OPTS[@]}" "$src/" "autobot@$dest/" 2>&1 | tail -10; then
      echo "✓ Done"
    else
      echo "✗ Failed"
    fi
    echo ""
  done
done

echo "=== Sync Complete ==="
