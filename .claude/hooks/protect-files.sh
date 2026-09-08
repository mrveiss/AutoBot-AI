#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Blocks edits to sensitive or generated files.
# PreToolUse hook for Edit|Write operations.
# Exit 2 = block the action. Exit 0 = allow.
#
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
# Issue: #3026

if ! command -v jq >/dev/null 2>&1; then
  # Before `deny()` is defined, so this repeats its stderr write rather than
  # calling it. Worst of the deny sites to leave silent: with no jq, EVERY edit
  # is blocked, and the one sentence explaining why went to the discarded stream.
  printf '%s\n' "jq is required for file protection hooks but is not installed." >&2
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"jq is required for file protection hooks but is not installed."}}'
  exit 2
fi

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

deny() {
  # The reason goes to STDERR because this exits 2 (#15956).
  #
  # The comment below this function states the rule, and the first version of
  # that fix applied it to `ask` only -- so every one of the five deny sites
  # still discarded its reason and the operator got a bare block. `ask` and
  # `deny` differ in EXIT CODE; they do not differ in which stream carries the
  # explanation. On exit 2 that stream is stderr, and it is stderr for both.
  printf '%s\n' "$1" >&2
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$1\"}}"
  exit 2
}

# `ask` and `deny` end in DIFFERENT exit codes, and that difference is the whole
# mechanism (#15956).
#
# PreToolUse reads exit 2 as a blocking error and takes its reason from STDERR.
# The JSON below goes to STDOUT, which is parsed only on exit 0. So `ask` with
# `exit 2` discarded its own payload: every prompt this function exists to raise
# became a hard denial, and -- nothing having been written to stderr -- the
# operator saw "No stderr output" with no reason at all.
#
# It survived because a denial and a discarded ask produce an identical
# observable. Nothing in the output distinguishes "refused on purpose" from
# "meant to ask you and could not", so the hook looked like it was working.
#
# Both `ask` sites in this file guard the settings files, and they are its only
# two against five `deny` sites -- so for the whole life of that bug, the only
# path here capable of reaching a human never did.
#
# `deny` keeps `exit 2`: for a denial that is correct, and its reason is the one
# the operator should see.
ask() {
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"ask\",\"permissionDecisionReason\":\"$1\"}}"
  exit 0
}

BASENAME=$(basename "$FILE_PATH")

# ──────────────────────────────────────────────
# Protected file patterns
# ──────────────────────────────────────────────

PROTECTED_PATTERNS=(
  "*.pem"
  "*.key"
  "*.crt"
  "*.p12"
  "*.pfx"
  "id_rsa"
  "id_ed25519"
  "credentials.json"
  "*.gen.ts"
  "*.generated.*"
  "*.min.js"
  "*.min.css"
)

for pattern in "${PROTECTED_PATTERNS[@]}"; do
  case "$BASENAME" in
    $pattern)
      deny "Protected file: $BASENAME matches pattern '$pattern'. Cannot edit cryptographic keys, credentials, or generated files."
      ;;
  esac
done

# ──────────────────────────────────────────────
# Protected directories and paths
# ──────────────────────────────────────────────

case "$FILE_PATH" in
  # Git internals
  .git/*|*/.git/*)
    deny "Cannot edit files inside .git/"
    ;;
  # Secrets directories
  secrets/*|*/secrets/*)
    deny "Cannot edit files inside secrets/"
    ;;
  # Environment files
  .env|.env.*|*/.env|*/.env.*)
    deny "Cannot edit .env files — use SSOT config or Ansible variables instead."
    ;;
  # Self-protection: hook scripts
  .claude/hooks/*|*/.claude/hooks/*)
    deny "Cannot edit hook scripts — these enforce security boundaries. Edit manually if needed."
    ;;
  # Settings files require confirmation
  .claude/settings.json|*/.claude/settings.json)
    ask "Editing settings.json — this controls permissions and hooks. Confirm this change."
    ;;
  .claude/settings.local.json|*/.claude/settings.local.json)
    ask "Editing settings.local.json — this controls local permissions. Confirm this change."
    ;;
esac

exit 0
