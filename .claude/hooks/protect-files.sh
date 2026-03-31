#!/bin/bash
# PreToolUse hook: protect sensitive files from edits (#3026)
# Exit 0 = allow, Exit 2 = block (reason on stdout)

input=$(cat)

file_path=$(echo "$input" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')

[ -z "$file_path" ] && exit 0

basename=$(basename "$file_path")

# Block: secrets and credentials
case "$basename" in
    .env|.env.*|credentials.json)
        echo "BLOCKED: $basename is a secrets file — do not edit via Claude" >&2
        exit 2 ;;
esac

case "$file_path" in
    */secrets/*|*/secret/*)
        echo "BLOCKED: files under secrets/ are protected" >&2
        exit 2 ;;
esac

# Block: crypto keys and certificates
case "$basename" in
    *.pem|*.key|*.crt|*.p12|*.pfx|id_rsa|id_ed25519)
        echo "BLOCKED: $basename is a cryptographic key/cert — do not edit via Claude" >&2
        exit 2 ;;
esac

# Block: git internals
case "$file_path" in
    */.git/*|*.git/*)
        echo "BLOCKED: .git/ internals are protected" >&2
        exit 2 ;;
esac

# Block: self-protection — hook scripts
case "$file_path" in
    */.claude/hooks/*)
        echo "BLOCKED: .claude/hooks/ scripts are self-protected — edit manually" >&2
        exit 2 ;;
esac

# Block: lock files
case "$basename" in
    package-lock.json|yarn.lock|pnpm-lock.yaml)
        echo "BLOCKED: $basename is a lock file — do not edit manually" >&2
        exit 2 ;;
esac

# Block: generated/minified files
case "$basename" in
    *.gen.ts|*.generated.*|*.min.js|*.min.css)
        echo "BLOCKED: $basename is a generated file — do not edit manually" >&2
        exit 2 ;;
esac

# Warn: settings files (allow but notify)
case "$file_path" in
    */.claude/settings.json|*/.claude/settings.local.json)
        echo "WARNING: editing Claude settings file $basename — proceed with caution" >&2
        exit 0 ;;
esac

exit 0
