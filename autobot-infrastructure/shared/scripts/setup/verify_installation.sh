#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0

# AutoBot Multi-Agent Architecture Installation Verification Script
echo "🔍 AutoBot Multi-Agent Architecture Installation Verification"
echo "============================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Import roots for the inline Python below, derived from this script's own
# location: the repo root is four levels up (setup/ -> scripts/ -> shared/ ->
# autobot-infrastructure/ -> repo root). `config.*` and `agents.*` live under
# autobot-backend, `autobot_shared.*` at the repo root. This replaces the old
# `export PYTHONPATH=$(pwd)`, which resolved to wherever the operator happened
# to be standing (#14867).
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
export PYTHONPATH="${REPO_ROOT}/autobot-backend:${REPO_ROOT}:${PYTHONPATH:-}"

success_count=0
total_checks=0

check_item() {
    local description=$1
    local command=$2
    total_checks=$((total_checks + 1))

    echo -n "Checking $description... "

    if eval "$command" &>/dev/null; then
        echo -e "${GREEN}✅ OK${NC}"
        success_count=$((success_count + 1))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC}"
        return 1
    fi
}

check_python_module() {
    local module_name=$1
    local description=${2:-$module_name}
    check_item "$description" "python3 -c 'import $module_name'"
}

# Basic system requirements
echo -e "${BLUE}📋 System Requirements${NC}"
check_item "Python 3.12+" "python3 --version | grep -E '3\.1[2-9]'"
check_item "Docker" "docker --version"
check_item "Ollama" "ollama --version"
check_item "Node.js" "node --version"
check_item "npm" "npm --version"

# Docker containers
echo -e "\n${BLUE}🐳 Docker Containers${NC}"
check_item "Redis Stack container" "docker ps | grep redis-stack"
check_item "Playwright container" "docker ps | grep autobot-playwright"

# Python environment
echo -e "\n${BLUE}🐍 Python Environment${NC}"
check_item "Virtual environment active" "[ -n \"\$VIRTUAL_ENV\" ]"
check_python_module "fastapi" "FastAPI"
check_python_module "uvicorn" "Uvicorn"
check_python_module "redis" "Redis client"
check_python_module "langchain" "LangChain"
check_python_module "llama_index" "LlamaIndex"

# Multi-Agent Architecture modules
echo -e "\n${BLUE}🤖 Multi-Agent Architecture Modules${NC}"
check_python_module "src.config" "Configuration manager"
check_python_module "src.agents.chat_agent" "Chat Agent"
check_python_module "src.agents.enhanced_system_commands_agent" "System Commands Agent"
check_python_module "src.agents.rag_agent" "RAG Agent"
check_python_module "src.agents.agent_orchestrator" "Agent Orchestrator"

# Ollama models
echo -e "\n${BLUE}🦙 Ollama Models${NC}"
if command -v ollama &>/dev/null; then
    check_item "Uncensored 1B model" "ollama list | grep 'artifish/llama3.2-uncensored:1b'"
    check_item "Uncensored 3B model" "ollama list | grep 'artifish/llama3.2-uncensored:3b'"
    check_item "General uncensored model" "ollama list | grep 'artifish/llama3.2-uncensored'"
    check_item "Nomic embeddings model" "ollama list | grep 'nomic-embed-text'"
    check_item "Fallback 1B model" "ollama list | grep -E 'llama3.2.*1b'"
    check_item "Fallback 3B model" "ollama list | grep -E 'llama3.2.*3b'"
else
    echo "⚠️  Ollama not available - skipping model checks"
fi

# Configuration files
echo -e "\n${BLUE}📄 Configuration Files${NC}"
check_item "Main config file" "[ -f config/config.yaml ]"
check_item "Settings override file" "[ -f config/settings.json ]"
check_item "Requirements file" "[ -f requirements.txt ]"
check_item "Multi-agent documentation" "[ -f docs/agents/multi-agent-architecture.md ]"

# Network connectivity
echo -e "\n${BLUE}🌐 Network Connectivity${NC}"
check_item "Redis connectivity" "redis-cli -h localhost ping | grep PONG"
check_item "Playwright service" "curl -sf http://localhost:3000/health"

# Agent configuration test
echo -e "\n${BLUE}⚙️  Agent Configuration Test${NC}"
# (#14867) This check used to be skipped silently whenever ./venv/bin/activate
# was missing, and its outcome was neither counted in total_checks nor able to
# affect the exit status - so a failing agent configuration still ended in
# "All checks passed". It now always runs and always counts.
if [ -f venv/bin/activate ]; then
    # shellcheck source=/dev/null
    source venv/bin/activate
fi

total_checks=$((total_checks + 1))
# (#14867) There is no src package. config_manager is the canonical config
# singleton (see autobot-backend/worker_node.py).
# (#14867) UNRESOLVED: get_agent_orchestrator names nothing in this tree.
# AgentType lives in agents.agent_orchestration (types.py); the nearest accessor
# after the #3393 move of agents/agent_orchestrator.py is
# get_distributed_agent_coordinator, but that is a rename guess rather than a
# match, so the import below is left naming what it was written against and its
# failure is now loud instead of discarded.
# NOTE: no backticks inside this double-quoted block - bash would run them.
if python3 -c "
try:
    from config import config_manager as global_config_manager
    from src.agents import AgentType, get_agent_orchestrator

    # Test model assignments
    chat_model = global_config_manager.get_task_specific_model('chat')
    orchestrator_model = global_config_manager.get_task_specific_model('orchestrator')
    rag_model = global_config_manager.get_task_specific_model('rag')

    print(f'Chat Agent Model: {chat_model}')
    print(f'Orchestrator Model: {orchestrator_model}')
    print(f'RAG Agent Model: {rag_model}')

    # Test agent instantiation
    orchestrator = get_agent_orchestrator()
    print('✅ Agent orchestrator instantiated successfully')

    print('✅ Agent configuration test passed')
except Exception as e:
    import sys, traceback
    print(f'❌ Agent configuration test failed: {e}', file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)
"; then
    echo -e "${GREEN}✅ Agent configuration test passed${NC}"
    success_count=$((success_count + 1))
else
    echo -e "${RED}❌ Agent configuration test failed - see the traceback above${NC}" >&2
fi

# Summary
echo -e "\n${BLUE}📊 Installation Summary${NC}"
echo "=============================="
echo -e "Checks passed: ${GREEN}$success_count${NC}/$total_checks"

if [ $success_count -eq $total_checks ]; then
    echo -e "${GREEN}🎉 All checks passed! Your AutoBot multi-agent installation is ready.${NC}"
    echo -e "${GREEN}You can now start the system with: ./run_agent.sh${NC}"
    exit 0
elif [ $success_count -gt $((total_checks * 3 / 4)) ]; then
    echo -e "${YELLOW}⚠️  Most checks passed. You may proceed with caution.${NC}"
    echo -e "${YELLOW}Some optional features may not be available.${NC}"
    exit 0
else
    echo -e "${RED}❌ Multiple checks failed. Please review the installation.${NC}"
    echo -e "${RED}Run ./setup_agent.sh to fix missing components.${NC}"
    exit 1
fi
