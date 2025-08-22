#!/bin/bash
# Setup to use Windows Ollama models exclusively
# This ensures all services use models from Windows directory only

set -e

echo "🪟 Setting up Windows-only Ollama models"
echo "========================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Get Windows username
WINDOWS_USER=$(powershell.exe -Command "echo \$env:USERNAME" 2>/dev/null | tr -d '\r' || echo "marti")
echo -e "${BLUE}Windows user detected: $WINDOWS_USER${NC}"

# Stop WSL Ollama if running
echo -e "${YELLOW}Stopping WSL Ollama service...${NC}"
systemctl stop ollama 2>/dev/null || true
pkill ollama 2>/dev/null || true

# Create environment file for Windows-only setup
cat > .env.windows-models << EOF
# Windows-only Ollama Model Configuration
# All services use Windows Ollama at 127.0.0.2:11434

# Windows Configuration
WINDOWS_USERNAME=$WINDOWS_USER
AUTOBOT_OLLAMA_HOST=127.0.0.2
AUTOBOT_OLLAMA_PORT=11434

# Disable WSL Ollama
DISABLE_WSL_OLLAMA=true

# Model directory (Windows)
WINDOWS_OLLAMA_PATH=/mnt/c/Users/$WINDOWS_USER/.ollama
EOF

# Create alias to manage Windows Ollama from WSL
cat > $HOME/.ollama_windows_alias << 'EOF'
# Ollama Windows aliases
alias ollama-win='function _ollama_win() {
    curl -X POST "http://127.0.0.2:11434/api/${1}" \
         -H "Content-Type: application/json" \
         -d "${2:-{}}"
}; _ollama_win'

# Common operations
alias ollama-list='curl -s http://127.0.0.2:11434/api/tags | jq -r ".models[].name"'
alias ollama-pull='function _pull() {
    curl -X POST http://127.0.0.2:11434/api/pull \
         -H "Content-Type: application/json" \
         -d "{\"name\": \"$1\"}" \
         -N
}; _pull'
EOF

# Symlink Windows models to WSL (optional - for easy browsing)
if [[ -d "/mnt/c/Users/$WINDOWS_USER/.ollama" ]]; then
    echo -e "${BLUE}Creating symbolic link to Windows models...${NC}"
    rm -f $HOME/.ollama-windows
    ln -s "/mnt/c/Users/$WINDOWS_USER/.ollama" "$HOME/.ollama-windows"
fi

# Update AutoBot configuration
echo -e "${BLUE}Updating AutoBot configuration...${NC}"
cat > autobot-windows-config.yml << EOF
# AutoBot configuration for Windows Ollama
services:
  ollama:
    host: 127.0.0.2
    port: 11434
    type: windows

  # Disable any local Ollama
  local_ollama:
    enabled: false
EOF

echo -e "${GREEN}✅ Windows-only setup complete!${NC}"
echo ""
echo "📋 Next steps:"
echo "1. Source the configuration: source .env.windows-models"
echo "2. Start Windows Ollama if not running"
echo "3. Run AutoBot: ./run_agent.sh"
echo ""
echo "🔧 Model management:"
echo "- List models: curl http://127.0.0.2:11434/api/tags"
echo "- Pull models: Use Windows Ollama UI or PowerShell"
echo "- Models location: C:\\Users\\$WINDOWS_USER\\.ollama"
echo ""
echo "🐳 Docker usage:"
echo "docker-compose -f docker/compose/docker-compose.windows-models.yml up"
