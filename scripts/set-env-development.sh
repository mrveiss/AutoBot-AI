#!/bin/bash

# AutoBot Environment Configuration - Development Setup
# This script configures AutoBot for development with debugging enabled

echo "🔧 Configuring AutoBot for development..."

# Source the DeepSeek configuration first
source "$(dirname "$0")/set-env-deepseek.sh"

# Developer Configuration
export AUTOBOT_DEVELOPER_MODE="true"
export AUTOBOT_DEBUG_LOGGING="true"
export AUTOBOT_LOG_LEVEL="debug"
export AUTOBOT_LOG_TO_FILE="true"
export AUTOBOT_LOG_FILE_PATH="data/autobot-debug.log"
export AUTOBOT_ENHANCED_ERRORS="true"

# Message Display - Show all debugging info
export AUTOBOT_SHOW_THOUGHTS="true"
export AUTOBOT_SHOW_PLANNING="true"
export AUTOBOT_SHOW_JSON="true"
export AUTOBOT_SHOW_DEBUG="true"
export AUTOBOT_SHOW_UTILITY="true"

# Enable Redis for advanced debugging
export AUTOBOT_REDIS_ENABLED="true"
export AUTOBOT_REDIS_HOST="localhost"
export AUTOBOT_REDIS_PORT="6379"

echo "✅ Development environment configured!"
echo ""
echo "Development settings:"
echo "  Debug Logging: $AUTOBOT_DEBUG_LOGGING"
echo "  Log Level: $AUTOBOT_LOG_LEVEL"
echo "  Log File: $AUTOBOT_LOG_FILE_PATH"
echo "  Show All Messages: JSON, Debug, Utility enabled"
echo "  Redis: $AUTOBOT_REDIS_ENABLED"
