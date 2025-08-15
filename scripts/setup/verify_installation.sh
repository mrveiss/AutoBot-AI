#!/bin/bash

# AutoBot Multi-Agent Architecture Installation Verification Script
echo "🔍 AutoBot Multi-Agent Architecture Installation Verification"
echo "============================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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
check_item "Python 3.10+" "python3 --version | grep -E '3\.(10|11|12)'"
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
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
    export PYTHONPATH=$(pwd)

    python3 -c "
try:
    from src.config import global_config_manager
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
    print(f'❌ Agent configuration test failed: {e}')
    exit(1)
" && echo -e "${GREEN}✅ Agent configuration test passed${NC}" || echo -e "${RED}❌ Agent configuration test failed${NC}"
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
