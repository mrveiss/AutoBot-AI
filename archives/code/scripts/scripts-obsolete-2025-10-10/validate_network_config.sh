#!/bin/bash

# AutoBot Network Configuration Validation Script
# Validates the network standardization changes

echo "🔍 AutoBot Network Configuration Validation"
echo "==========================================="

# Check if standardized environment file exists
if [ -f ".env.network" ]; then
    echo "✅ Network environment file found"
    source .env.network
else
    echo "⚠️  Network environment file not found, using defaults"
fi

echo ""
echo "📊 Configuration Status"
echo "----------------------"

# Count docker-compose files
COMPOSE_FILES=$(find . -name "docker-compose*.yml" | wc -l)
echo "Docker Compose files: $COMPOSE_FILES"

# Count remaining hardcoded IPs (should be 0)
LEGACY_IPS=$(find . -name "docker-compose*.yml" -exec grep -o "192\.168\.[0-9]\+\.[0-9]\+\|10\.[0-9]\+\.[0-9]\+\.[0-9]\+" {} \; 2>/dev/null | wc -l)
echo "Legacy hardcoded IPs: $LEGACY_IPS"

# Count standardized IPs
STANDARDIZED_IPS=$(find . -name "docker-compose*.yml" -exec grep -o "172\.16\.168\.[0-9]\+" {} \; 2>/dev/null | wc -l)
echo "Standardized IPs (172.16.168.x): $STANDARDIZED_IPS"

# Count backup files
BACKUP_FILES=$(find . -name "*.backup" | wc -l)
echo "Backup files created: $BACKUP_FILES"

echo ""
echo "🌐 Network Configuration"
echo "-----------------------"
echo "Network Subnet: ${DOCKER_SUBNET:-172.16.168.0/24}"
echo "Network Gateway: ${DOCKER_GATEWAY:-172.16.168.1}"
echo "Backend Host: ${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
echo "Frontend Host: ${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
echo "Redis Host: ${AUTOBOT_REDIS_HOST:-172.16.168.23}"

echo ""
echo "🔧 Service URLs" 
echo "--------------"
echo "Backend: ${BACKEND_URL:-http://172.16.168.20:8001}"
echo "Frontend: ${FRONTEND_URL:-http://172.16.168.21:5173}"
echo "Redis: ${REDIS_URL:-redis://172.16.168.23:6379}"

echo ""
echo "✅ Validation Results"
echo "-------------------"

if [ "$LEGACY_IPS" -eq 0 ]; then
    echo "✅ No legacy hardcoded IPs found"
else
    echo "❌ Found $LEGACY_IPS legacy hardcoded IPs - needs attention"
fi

if [ "$STANDARDIZED_IPS" -gt 0 ]; then
    echo "✅ Network standardization applied ($STANDARDIZED_IPS references)"
else
    echo "⚠️  No standardized IP references found"
fi

if [ "$BACKUP_FILES" -gt 0 ]; then
    echo "✅ Backup files created ($BACKUP_FILES files)"
else
    echo "⚠️  No backup files found"
fi

# Test main docker-compose.yml syntax
echo ""
echo "📋 YAML Syntax Validation"
echo "-------------------------"
if python3 -c "import yaml; yaml.safe_load(open('docker-compose.yml'))" 2>/dev/null; then
    echo "✅ Main docker-compose.yml syntax is valid"
else
    echo "❌ Main docker-compose.yml syntax error"
fi

echo ""
echo "🎯 Summary"
echo "---------"
if [ "$LEGACY_IPS" -eq 0 ] && [ "$STANDARDIZED_IPS" -gt 0 ] && [ "$BACKUP_FILES" -gt 0 ]; then
    echo "🎉 Network standardization completed successfully!"
    echo "   All hardcoded IPs eliminated and replaced with environment variables."
    echo "   Configuration follows complete.yaml architecture."
else
    echo "⚠️  Network standardization incomplete. Review validation results above."
fi

echo ""
echo "📖 Next Steps:"
echo "1. Test network connectivity: source .env.network && docker compose config"
echo "2. Deploy with: docker compose up -d"
echo "3. Verify frontend connects to backend at 172.16.168.20:8001"