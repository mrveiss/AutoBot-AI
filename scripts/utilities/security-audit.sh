#!/bin/bash

# Security audit script for AutoBot project
# Checks for sensitive data that shouldn't be committed to git

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
}

log_header() {
    echo -e "${BLUE}[AUDIT]${NC} $1"
}

ISSUES_FOUND=0

log_header "AutoBot Security Audit"
echo "=================================================="

# Check for sensitive files in git
log_header "Checking for sensitive files in git repository..."

SENSITIVE_PATTERNS=(
    "\.key$"
    "\.pem$"
    "\.ppk$"
    "id_rsa"
    "id_dsa"
    "authorized_keys$"
    "\.password$"
    "\.passwd$"
    "\.token$"
    "\.auth$"
)

for pattern in "${SENSITIVE_PATTERNS[@]}"; do
    results=$(git ls-files | grep -E "$pattern" 2>/dev/null || true)
    if [ -n "$results" ]; then
        log_error "Found sensitive files matching pattern '$pattern':"
        echo "$results" | sed 's/^/  /'
        ((ISSUES_FOUND++))
    fi
done

if [ $ISSUES_FOUND -eq 0 ]; then
    log_info "No sensitive files found in git repository"
fi

# Check for hardcoded passwords in code
log_header "Checking for hardcoded passwords in code..."

PASSWORD_PATTERNS=(
    "password\s*=\s*[\"'][^\"']+[\"']"
    "passwd\s*=\s*[\"'][^\"']+[\"']"
    "pwd\s*=\s*[\"'][^\"']+[\"']"
    "token\s*=\s*[\"'][^\"']+[\"']"
    "api_key\s*=\s*[\"'][^\"']+[\"']"
    "secret\s*=\s*[\"'][^\"']+[\"']"
    "sshpass\s+-p\s+[\"'][^\"']+[\"']"
)

EXCLUDE_DIRS=(
    ".git"
    "node_modules"
    "venv"
    "dist"
    "build"
    "logs"
    "data"
)

EXCLUDE_ARGS=""
for dir in "${EXCLUDE_DIRS[@]}"; do
    EXCLUDE_ARGS="$EXCLUDE_ARGS --exclude-dir=$dir"
done

PASSWORD_ISSUES=0
for pattern in "${PASSWORD_PATTERNS[@]}"; do
    results=$(grep -r -i -E "$pattern" . $EXCLUDE_ARGS 2>/dev/null | grep -v ".gitignore" | grep -v "security-audit.sh" | head -5 || true)
    if [ -n "$results" ]; then
        if [ $PASSWORD_ISSUES -eq 0 ]; then
            log_warn "Found potential hardcoded passwords (showing first 5):"
        fi
        echo "$results" | sed 's/^/  /'
        ((PASSWORD_ISSUES++))
    fi
done

if [ $PASSWORD_ISSUES -gt 0 ]; then
    log_warn "Review the above for actual hardcoded passwords"
    ((ISSUES_FOUND+=$PASSWORD_ISSUES))
else
    log_info "No obvious hardcoded passwords found"
fi

# Check .gitignore effectiveness
log_header "Checking .gitignore configuration..."

REQUIRED_PATTERNS=(
    "*.key"
    "*.pem"
    "*.pub"
    "authorized_keys"
    "known_hosts"
    "*.password"
    "*.token"
    ".env"
)

MISSING_PATTERNS=0
for pattern in "${REQUIRED_PATTERNS[@]}"; do
    if ! grep -q "$pattern" .gitignore 2>/dev/null; then
        log_warn ".gitignore missing pattern: $pattern"
        ((MISSING_PATTERNS++))
    fi
done

if [ $MISSING_PATTERNS -eq 0 ]; then
    log_info ".gitignore properly configured for sensitive files"
else
    ((ISSUES_FOUND+=$MISSING_PATTERNS))
fi

# Check SSH key permissions
log_header "Checking SSH key permissions..."

if [ -d ~/.ssh ]; then
    for keyfile in ~/.ssh/autobot_key ~/.ssh/id_rsa ~/.ssh/id_dsa ~/.ssh/id_ecdsa ~/.ssh/id_ed25519; do
        if [ -f "$keyfile" ]; then
            perms=$(stat -c %a "$keyfile")
            if [ "$perms" != "600" ]; then
                log_error "$keyfile has insecure permissions: $perms (should be 600)"
                ((ISSUES_FOUND++))
            else
                log_info "$keyfile has correct permissions: $perms"
            fi
        fi
    done
fi

# Check for sensitive environment variables
log_header "Checking environment configuration..."

if [ -f .env ]; then
    if git ls-files .env 2>/dev/null | grep -q ".env"; then
        log_error ".env file is tracked in git!"
        ((ISSUES_FOUND++))
    else
        log_info ".env file is not tracked in git"
    fi
fi

# Summary
echo
echo "=================================================="
log_header "Security Audit Summary"

if [ $ISSUES_FOUND -eq 0 ]; then
    log_info "✅ No security issues found!"
    echo -e "${GREEN}Your repository appears to be properly secured.${NC}"
else
    log_error "⚠️  Found $ISSUES_FOUND potential security issues"
    echo -e "${YELLOW}Please review and address the issues above.${NC}"
fi

echo
log_info "Security Tips:"
echo "  • Always use SSH keys instead of passwords"
echo "  • Never commit .env files or secrets to git"
echo "  • Use environment variables for sensitive data"
echo "  • Regularly audit your repository for security issues"
echo "  • Keep .gitignore updated with security patterns"

exit $ISSUES_FOUND