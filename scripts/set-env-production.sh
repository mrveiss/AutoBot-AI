#!/bin/bash

# AutoBot Environment Configuration - Production Setup
# This script configures AutoBot for production deployment

echo "🔧 Configuring AutoBot for production..."

# Source the DeepSeek configuration first
source "$(dirname "$0")/set-env-deepseek.sh"

# Production Configuration
export AUTOBOT_DEVELOPER_MODE="false"
export AUTOBOT_DEBUG_LOGGING="false"
export AUTOBOT_LOG_LEVEL="info"
export AUTOBOT_LOG_TO_FILE="true"
export AUTOBOT_LOG_FILE_PATH="data/autobot.log"
export AUTOBOT_ENHANCED_ERRORS="false"

# Message Display - Hide debugging info
export AUTOBOT_SHOW_THOUGHTS="false"
export AUTOBOT_SHOW_PLANNING="false"
export AUTOBOT_SHOW_JSON="false"
export AUTOBOT_SHOW_DEBUG="false"
export AUTOBOT_SHOW_UTILITY="false"

# Security Configuration
export AUTOBOT_ENABLE_ENCRYPTION="true"
export AUTOBOT_SESSION_TIMEOUT="30"

# Performance Configuration
export AUTOBOT_CHAT_MAX_MESSAGES="50"
export AUTOBOT_CHAT_RETENTION_DAYS="7"
export AUTOBOT_KB_UPDATE_FREQUENCY="1"

# Redis for production caching
export AUTOBOT_REDIS_ENABLED="true"
export AUTOBOT_REDIS_HOST="localhost"
export AUTOBOT_REDIS_PORT="6379"

echo "✅ Production environment configured!"
echo ""
echo "Production settings:"
echo "  Debug Logging: $AUTOBOT_DEBUG_LOGGING"
echo "  Log Level: $AUTOBOT_LOG_LEVEL"
echo "  Encryption: $AUTOBOT_ENABLE_ENCRYPTION"
echo "  Session Timeout: $AUTOBOT_SESSION_TIMEOUT minutes"
echo "  Message Retention: $AUTOBOT_CHAT_RETENTION_DAYS days"