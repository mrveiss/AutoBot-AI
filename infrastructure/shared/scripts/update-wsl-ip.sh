#!/bin/bash
# Update WSL IP in frontend configuration
# This script detects the current WSL IP and updates the frontend .env file

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get current WSL IP
WSL_IP=$(hostname -I | awk '{print $1}')

if [ -z "$WSL_IP" ]; then
    echo -e "${RED}❌ Could not detect WSL IP address${NC}"
    exit 1
fi

echo -e "${GREEN}🔍 Detected WSL IP: $WSL_IP${NC}"

# Path to frontend .env file
ENV_FILE="/home/kali/Desktop/AutoBot/autobot-vue/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}❌ Frontend .env file not found: $ENV_FILE${NC}"
    exit 1
fi

# Create backup
cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
echo -e "${YELLOW}📋 Created backup of .env file${NC}"

# Update IP addresses in .env file
sed -i "s/VITE_BACKEND_HOST=.*/VITE_BACKEND_HOST=$WSL_IP/" "$ENV_FILE"
sed -i "s|VITE_PLAYWRIGHT_VNC_URL=http://[^:]*:|VITE_PLAYWRIGHT_VNC_URL=http://$WSL_IP:|" "$ENV_FILE"
sed -i "s|VITE_PLAYWRIGHT_API_URL=http://[^:]*:|VITE_PLAYWRIGHT_API_URL=http://$WSL_IP:|" "$ENV_FILE"
sed -i "s|VITE_OLLAMA_URL=http://[^:]*:|VITE_OLLAMA_URL=http://$WSL_IP:|" "$ENV_FILE"
sed -i "s|VITE_CHROME_DEBUG_URL=http://[^:]*:|VITE_CHROME_DEBUG_URL=http://$WSL_IP:|" "$ENV_FILE"
sed -i "s|VITE_LMSTUDIO_URL=http://[^:]*:|VITE_LMSTUDIO_URL=http://$WSL_IP:|" "$ENV_FILE"

echo -e "${GREEN}✅ Updated .env file with WSL IP: $WSL_IP${NC}"

# Update vite.config.ts defaults
VITE_CONFIG="/home/kali/Desktop/AutoBot/autobot-vue/vite.config.ts"

if [ -f "$VITE_CONFIG" ]; then
    # Create backup
    cp "$VITE_CONFIG" "$VITE_CONFIG.backup.$(date +%Y%m%d_%H%M%S)"

    # Update default IPs in vite.config.ts
    sed -i "s/192\\.168\\.168\\.[0-9]\\+/$WSL_IP/g" "$VITE_CONFIG"
    sed -i "s/host\\.docker\\.internal/$WSL_IP/g" "$VITE_CONFIG"
    sed -i "s/localhost/$WSL_IP/g" "$VITE_CONFIG"

    echo -e "${GREEN}✅ Updated vite.config.ts with WSL IP: $WSL_IP${NC}"
else
    echo -e "${YELLOW}⚠️  vite.config.ts not found, skipping${NC}"
fi

echo -e "${GREEN}🎉 WSL IP configuration updated successfully!${NC}"
echo -e "${YELLOW}💡 Remember to restart the Vite dev server to apply proxy changes${NC}"
echo -e "${YELLOW}   cd autobot-vue && npm run dev${NC}"
