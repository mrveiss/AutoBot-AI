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
# (#14875) All five named a `src.` package that has never existed in this tree,
# so all five failed on every run and the 3/4 pass threshold below absorbed
# them. The real modules, reachable from the PYTHONPATH exported above:
#   src.config                              -> config
#   src.agents.chat_agent                   -> agents.chat_agent
#   src.agents.enhanced_system_commands_agent -> agents.system_command_agent
#   src.agents.rag_agent                    -> agents.rag_agent
#   src.agents.agent_orchestrator           -> agents.agent_orchestration
#                                              (folded into the package by #3393)
check_python_module "config" "Configuration manager"
check_python_module "agents.chat_agent" "Chat Agent"
check_python_module "agents.system_command_agent" "System Commands Agent"
check_python_module "agents.rag_agent" "RAG Agent"
check_python_module "agents.agent_orchestration" "Agent Orchestration"

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
# (#14875) This block named three things that do not exist:
#   src.agents                        - no `src` package in this tree
#   get_agent_orchestrator            - zero hits repo-wide
#   get_task_specific_model           - removed; agents/agent_models_e2e_test.py
#                                       documents config.llm.get_model_for_agent
#                                       as its replacement
# The first ImportError fired before the other two were ever reached, so fixing
# only the import would have swapped one loud failure for the next. All three
# are repointed at the current API here.
# NOTE: no backticks inside this double-quoted block - bash would run them.
if python3 -c "
try:
    from agents.agent_orchestration import AgentType, get_distributed_agent_coordinator
    from autobot_shared.ssot_config import config

    for agent_id in ('chat', 'orchestrator', 'rag'):
        print(f'{agent_id} model: {config.llm.get_model_for_agent(agent_id)}')

    coordinator = get_distributed_agent_coordinator()
    print(f'Agent coordinator instantiated: {type(coordinator).__name__}')
    print(f'Agent types available: {len(list(AgentType))}')

    print('Agent configuration test passed')
except Exception as e:
    import sys, traceback
    print(f'Agent configuration test failed: {e}', file=sys.stderr)
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
    # (#14867) This exited 0. A verification that reports "most checks passed"
    # and then tells its caller everything is fine is not distinguishable from
    # a clean run by anything a script can read - which is how the five broken
    # `src.*` module checks above stayed broken. A failed check now reaches the
    # exit status.
    echo -e "${YELLOW}⚠️  Most checks passed, but $((total_checks - success_count)) FAILED.${NC}" >&2
    echo -e "${YELLOW}This is NOT a clean installation - review the failures above.${NC}" >&2
    exit 1
else
    echo -e "${RED}❌ Multiple checks failed. Please review the installation.${NC}"
    echo -e "${RED}Run ./setup_agent.sh to fix missing components.${NC}"
    exit 1
fi
