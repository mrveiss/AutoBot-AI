#!/bin/bash

# AutoBot Environment Configuration - DeepSeek Setup
# This script configures AutoBot to use DeepSeek-R1 model

echo "🔧 Configuring AutoBot for DeepSeek-R1 model..."

# LLM Configuration
export AUTOBOT_OLLAMA_MODEL="deepseek-r1:14b"
export AUTOBOT_ORCHESTRATOR_LLM="deepseek-r1:14b"
export AUTOBOT_DEFAULT_LLM="ollama_deepseek-r1:14b"
export AUTOBOT_TASK_LLM="ollama_deepseek-r1:14b"
export AUTOBOT_OLLAMA_SELECTED_MODEL="deepseek-r1:14b"

# Backend Configuration (defaults)
export AUTOBOT_BACKEND_HOST="0.0.0.0"
export AUTOBOT_BACKEND_PORT="8001"
export AUTOBOT_BACKEND_API_ENDPOINT="http://localhost:8001"
export AUTOBOT_OLLAMA_HOST="http://localhost:11434"
export AUTOBOT_OLLAMA_ENDPOINT="http://localhost:11434/api/generate"

# Frontend Configuration
export VITE_API_BASE_URL="http://localhost:8001"

# Message Display - Show relevant debugging info 
export AUTOBOT_SHOW_THOUGHTS="true"
export AUTOBOT_SHOW_PLANNING="true"
export AUTOBOT_SHOW_JSON="false"
export AUTOBOT_SHOW_DEBUG="false"
export AUTOBOT_SHOW_UTILITY="false"

# Chat Configuration
export AUTOBOT_CHAT_AUTO_SCROLL="true"
export AUTOBOT_CHAT_MAX_MESSAGES="100"

echo "✅ Environment configured for DeepSeek-R1!"
echo ""
echo "Current LLM settings:"
echo "  Model: $AUTOBOT_OLLAMA_MODEL"
echo "  Orchestrator: $AUTOBOT_ORCHESTRATOR_LLM"
echo "  Backend: $AUTOBOT_BACKEND_API_ENDPOINT"
echo "  Ollama: $AUTOBOT_OLLAMA_HOST"
echo ""
echo "To apply these settings, run:"
echo "  source scripts/set-env-deepseek.sh"
echo "  ./run_agent.sh"