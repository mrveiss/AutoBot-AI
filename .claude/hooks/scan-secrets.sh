#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Scans file content for accidental secrets before writing.
# PreToolUse hook for Edit|Write operations.
# Exit 2 = block (with "ask" decision so user can override). Exit 0 = allow.
#
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
# Issue: #3022

# Allow if jq is missing (don't block the user)
if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

# Extract the content being written
if [ "$TOOL_NAME" = "Write" ]; then
  CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty')
elif [ "$TOOL_NAME" = "Edit" ]; then
  CONTENT=$(echo "$INPUT" | jq -r '.tool_input.new_string // empty')
else
  exit 0
fi

if [ -z "$CONTENT" ]; then
  exit 0
fi

MATCHES=""

# ──────────────────────────────────────────────
# Cloud provider keys
# ──────────────────────────────────────────────

# AWS Access Key IDs
if echo "$CONTENT" | grep -qE 'AKIA[0-9A-Z]{16}'; then
  MATCHES="$MATCHES AWS access key (AKIA...);"
fi

# AWS Secret Access Keys
if echo "$CONTENT" | grep -qiE '(aws_secret_access_key|secret_key)[[:space:]]*[=:][[:space:]]*["\x27]?[A-Za-z0-9/+=]{40}'; then
  MATCHES="$MATCHES AWS secret key;"
fi

# ──────────────────────────────────────────────
# API tokens
# ──────────────────────────────────────────────

# GitHub tokens (PAT, OAuth, App)
if echo "$CONTENT" | grep -qE '(ghp_|gho_|ghs_|ghr_|github_pat_)[a-zA-Z0-9_]{20,}'; then
  MATCHES="$MATCHES GitHub token;"
fi

# OpenAI / Stripe / Anthropic style keys (sk-...)
if echo "$CONTENT" | grep -qE 'sk-[a-zA-Z0-9]{20,}'; then
  MATCHES="$MATCHES API key (sk-...);"
fi

# Slack tokens
if echo "$CONTENT" | grep -qE 'xox[bpras]-[0-9a-zA-Z-]{10,}'; then
  MATCHES="$MATCHES Slack token;"
fi

# ──────────────────────────────────────────────
# Cryptographic material
# ──────────────────────────────────────────────

# Private key blocks
if echo "$CONTENT" | grep -qE -- '-----BEGIN[[:space:]]+(RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'; then
  MATCHES="$MATCHES private key block;"
fi

# ──────────────────────────────────────────────
# Connection strings & credentials
# ──────────────────────────────────────────────

# Connection strings with embedded credentials
if echo "$CONTENT" | grep -qE '(mongodb|postgres|mysql|redis|amqp|smtp)(\+[a-z]+)?://[^:[:space:]]+:[^@[:space:]]+@'; then
  MATCHES="$MATCHES connection string with credentials;"
fi

# Generic password/secret/token assignments with literal values
# Excludes env var references (process.env, os.environ, getenv, ${...})
if echo "$CONTENT" | grep -qiE '(password|secret|token|api_key|apikey|api_secret)[[:space:]]*[=:][[:space:]]*["\x27][^"\x27]{8,}["\x27]' && \
   ! echo "$CONTENT" | grep -qiE '(password|secret|token|api_key|apikey|api_secret)[[:space:]]*[=:][[:space:]]*["\x27]?(process\.env|os\.environ|getenv|\$\{|ENV\[|env\(|config\.)'; then
  MATCHES="$MATCHES hardcoded credential;"
fi

# ──────────────────────────────────────────────
# AutoBot-specific: hardcoded fleet IPs
# ──────────────────────────────────────────────

# Detect hardcoded IPs in the AutoBot fleet range (except in comments, docs, or config references)
if echo "$CONTENT" | grep -qE '172\.16\.168\.[0-9]{1,3}' && \
   ! echo "$CONTENT" | grep -qE '^[[:space:]]*(#|//|/\*|\*|<!--|""").*172\.16\.168\.' && \
   ! echo "$CONTENT" | grep -qiE '(config\.|ssot_config|AUTOBOT_REFERENCE).*172\.16\.168\.'; then
  MATCHES="$MATCHES hardcoded AutoBot fleet IP (use SSOT config);"
fi

if [ -n "$MATCHES" ]; then
  REASON="Possible secret detected in content:$MATCHES Review carefully before allowing."
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"ask\",\"permissionDecisionReason\":\"$REASON\"}}"
  exit 2
fi

exit 0
