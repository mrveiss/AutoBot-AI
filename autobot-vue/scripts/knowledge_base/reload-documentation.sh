#!/bin/bash
#
# AutoBot Knowledge Base Documentation Reload Script
# Purpose: Reload all AutoBot documentation into knowledge base after Redis restart
# Usage: bash scripts/knowledge_base/reload-documentation.sh
#

set -e

BASE_DIR="/home/kali/Desktop/AutoBot"
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
BACKEND_PORT="${AUTOBOT_BACKEND_PORT:-8001}"
KB_API="http://${BACKEND_HOST}:${BACKEND_PORT}/api/knowledge_base/add_text"

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}📚 AutoBot Knowledge Base Documentation Reload${NC}"
echo "=============================================="
echo ""

# Function to upload a document
upload_doc() {
    local file="$1"
    local title="$2"
    
    if [ ! -f "$file" ]; then
        echo -e "${RED}⏭️  Skipping: $file (not found)${NC}"
        return 1
    fi
    
    echo -e "${BLUE}📤 Uploading: $title${NC}"
    
    cat "$file" | python3 -c "
import sys
import json

content = sys.stdin.read()
payload = {
    'text': content,
    'title': '$title',
    'source': 'autobot_docs',
    'category': 'autobot_documentation'
}
print(json.dumps(payload))
" | curl -s -X POST "$KB_API" \
    -H "Content-Type: application/json" -d @- | python3 -c "
import sys, json
try:
    result = json.load(sys.stdin)
    if result.get('status') == 'success':
        print(f\"   ${GREEN}✅ {result.get('fact_id', 'unknown')} ({result.get('text_length', 0):,} chars)${NC}\")
    else:
        print(f\"   ${RED}❌ Error: {result.get('detail', result.get('message', 'unknown'))}${NC}\")
except Exception as e:
    print(f\"   ${RED}❌ Error: {str(e)}${NC}\")
" 2>&1
}

cd "$BASE_DIR"

# Core documentation
echo -e "${GREEN}📚 Loading Core Documentation...${NC}"
upload_doc "docs/api/COMPREHENSIVE_API_DOCUMENTATION.md" "AutoBot Phase 5 API Documentation"
upload_doc "CLAUDE.md" "AutoBot Development Instructions & Project Reference"
upload_doc "docs/system-state.md" "AutoBot System Status and Updates"
upload_doc "docs/architecture/MULTI_NPU_QUICK_REFERENCE.md" "Multi-NPU Worker Architecture Quick Reference"
upload_doc "docs/troubleshooting/COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md" "Comprehensive Troubleshooting Guide"

# Architecture documentation
echo ""
echo -e "${GREEN}🏗️  Loading Architecture Documentation...${NC}"
upload_doc "docs/architecture/PHASE_5_DISTRIBUTED_ARCHITECTURE.md" "Phase 5 Distributed Architecture"
upload_doc "docs/architecture/AUTOBOT_MEMORY_GRAPH_ARCHITECTURE.md" "AutoBot Memory Graph Architecture"
upload_doc "docs/architecture/AGENT_SYSTEM_ARCHITECTURE.md" "Agent System Architecture"
upload_doc "docs/architecture/TERMINAL_ARCHITECTURE_DISTRIBUTED.md" "Terminal Architecture - Distributed"
upload_doc "docs/developer/PHASE_5_DEVELOPER_SETUP.md" "Phase 5 Developer Setup Guide"

# Feature documentation
echo ""
echo -e "${GREEN}🚀 Loading Feature Documentation...${NC}"
upload_doc "docs/features/AGENT_TERMINAL_IMPLEMENTATION_SUMMARY.md" "Agent Terminal Implementation Guide"
upload_doc "docs/features/AUTONOMOUS_TERMINAL_EXECUTION.md" "Autonomous Terminal Execution"
upload_doc "docs/features/NPU_LOAD_BALANCER_IMPLEMENTATION.md" "NPU Load Balancer Implementation"
upload_doc "docs/features/NPU_WORKER_REGISTRY_API.md" "NPU Worker Registry API"

# API documentation
echo ""
echo -e "${GREEN}🔌 Loading API Documentation...${NC}"
upload_doc "docs/api/WEBSOCKET_INTEGRATION_GUIDE.md" "WebSocket Integration Guide"
upload_doc "docs/api/AGENT_TERMINAL_API.md" "Agent Terminal API Documentation"

echo ""
echo -e "${GREEN}✅ Knowledge base documentation reload complete!${NC}"
echo ""
echo "Run: curl -s http://${BACKEND_HOST}:${BACKEND_PORT}/api/knowledge_base/stats | python3 -m json.tool"
echo "To verify the knowledge base stats"
