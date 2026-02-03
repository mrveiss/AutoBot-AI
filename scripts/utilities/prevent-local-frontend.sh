#!/bin/bash

# prevent-local-frontend.sh
# Prevents accidental local frontend server startup
# Part of AutoBot Single Frontend Server Architecture enforcement

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOBOT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${RED}⚠️  SINGLE FRONTEND SERVER ARCHITECTURE VIOLATION DETECTED${NC}"
echo ""
echo -e "${YELLOW}CRITICAL ERROR: Attempt to start local frontend server blocked${NC}"
echo ""
echo "AutoBot uses a SINGLE FRONTEND SERVER architecture:"
echo -e "  ✅ ${GREEN}ONLY 172.16.168.21:5173 runs the frontend (Frontend VM)${NC}"
echo -e "  ❌ ${RED}NO frontend servers on main machine (172.16.168.20)${NC}"
echo -e "  ❌ ${RED}NO local development servers (localhost:5173)${NC}"
echo ""
echo "FORBIDDEN COMMANDS on main machine:"
echo "  • npm run dev"
echo "  • yarn dev"
echo "  • vite dev"
echo "  • Any command that starts a server on port 5173"
echo ""
echo "CORRECT DEVELOPMENT WORKFLOW:"
echo "1. Edit code locally in: /home/kali/Desktop/AutoBot/autobot-vue/"
echo "2. Sync to Frontend VM: ./sync-frontend.sh"
echo "3. Frontend VM managed by: bash run_autobot.sh"
echo ""
echo -e "${RED}Running local frontend servers breaks the distributed architecture!${NC}"
echo ""
echo "Consequences of violation:"
echo "  • Port conflicts between local and VM servers"
echo "  • Configuration confusion (local vs VM environment variables)"
echo "  • API proxy routing failures"
echo "  • WebSocket connection issues"
echo "  • Lost development work due to sync conflicts"
echo ""
exit 1