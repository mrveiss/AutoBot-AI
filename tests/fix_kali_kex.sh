#!/bin/bash
# Fix Kali KEX (Desktop Environment) Issues
# This script diagnoses and fixes common KEX problems in WSL2

echo "🔍 Kali KEX Diagnostic and Fix Script"
echo "======================================"

# Function to check if we're in WSL2
check_wsl2() {
    if grep -q Microsoft /proc/version; then
        echo "✅ Running in WSL2 environment"
        return 0
    else
        echo "❌ Not running in WSL2 - KEX may not work properly"
        return 1
    fi
}

# Function to check KEX installation
check_kex_installation() {
    echo "🔍 Checking KEX installation..."
    
    if command -v kex &> /dev/null; then
        echo "✅ KEX command found"
        KEX_PATH=$(which kex)
        echo "   Path: $KEX_PATH"
    else
        echo "❌ KEX not found - installing..."
        sudo apt update
        sudo apt install -y kali-win-kex
        return $?
    fi
}

# Function to check required services
check_services() {
    echo "🔍 Checking required services..."
    
    # Check if systemd is available
    if command -v systemctl &> /dev/null; then
        echo "✅ systemd available"
    else
        echo "⚠️  systemd not available - may need alternative approach"
    fi
    
    # Check X11 processes
    X_PROCESSES=$(ps aux | grep -E "(Xvnc|vncserver|tigervnc)" | grep -v grep)
    if [ -n "$X_PROCESSES" ]; then
        echo "⚠️  Existing X11/VNC processes found:"
        echo "$X_PROCESSES"
        echo "   These may interfere with KEX"
    else
        echo "✅ No conflicting X11/VNC processes"
    fi
}

# Function to fix common KEX issues
fix_kex_issues() {
    echo "🔧 Fixing common KEX issues..."
    
    # Kill any existing KEX processes
    echo "   Stopping existing KEX processes..."
    sudo pkill -f "kex"
    sudo pkill -f "Xvnc"
    sudo pkill -f "vncserver"
    sleep 2
    
    # Clean up lock files
    echo "   Cleaning up lock files..."
    sudo rm -f /tmp/.X*-lock 2>/dev/null
    sudo rm -f /tmp/.X11-unix/X* 2>/dev/null
    
    # Fix permissions on KEX directories
    echo "   Fixing permissions..."
    mkdir -p ~/.vnc 2>/dev/null
    chmod 755 ~/.vnc 2>/dev/null
    
    # Create or fix VNC password if needed
    if [ ! -f ~/.vnc/passwd ]; then
        echo "   Setting up VNC password..."
        echo "kali" | vncpasswd -f > ~/.vnc/passwd
        chmod 600 ~/.vnc/passwd
    fi
    
    # Fix firewall if needed
    echo "   Checking firewall settings..."
    if command -v ufw &> /dev/null; then
        sudo ufw allow 5900:5999/tcp 2>/dev/null
    fi
}

# Function to test KEX startup
test_kex_startup() {
    echo "🧪 Testing KEX startup..."
    
    # Try to start KEX
    echo "   Attempting to start KEX..."
    timeout 10s kex start 2>&1 | head -20
    
    sleep 3
    
    # Check if KEX is running
    KEX_PROCESSES=$(ps aux | grep -E "(kex|Xvnc)" | grep -v grep)
    if [ -n "$KEX_PROCESSES" ]; then
        echo "✅ KEX processes detected:"
        echo "$KEX_PROCESSES"
        
        # Check listening ports
        KEX_PORTS=$(netstat -tlnp 2>/dev/null | grep -E ":59[0-9][0-9].*LISTEN")
        if [ -n "$KEX_PORTS" ]; then
            echo "✅ KEX VNC ports listening:"
            echo "$KEX_PORTS"
        else
            echo "⚠️  KEX running but no VNC ports detected"
        fi
    else
        echo "❌ KEX failed to start"
        return 1
    fi
}

# Function to provide troubleshooting steps
provide_troubleshooting() {
    echo "🔧 TROUBLESHOOTING STEPS"
    echo "======================="
    
    echo "1. Manual KEX commands to try:"
    echo "   sudo kex kill          # Kill all KEX processes"
    echo "   kex --win -s           # Start KEX for Windows"
    echo "   kex --esm              # Start KEX seamless mode"
    echo "   kex --sl2700           # Start KEX SL2700 mode"
    echo ""
    
    echo "2. Alternative VNC approach:"
    echo "   vncserver :1           # Start VNC server manually"
    echo "   export DISPLAY=:1      # Set display"
    echo "   startxfce4 &           # Start desktop environment"
    echo ""
    
    echo "3. Check Windows side:"
    echo "   - Ensure Windows has VNC viewer installed"
    echo "   - Connect to localhost:5901"
    echo "   - Check Windows Defender firewall"
    echo ""
    
    echo "4. WSL2 network issues:"
    echo "   - Check WSL2 IP: ip addr show eth0"
    echo "   - Windows may need WSL2 IP instead of localhost"
    echo ""
    
    echo "5. If all else fails:"
    echo "   wsl --shutdown         # Restart WSL2 completely"
    echo "   # Then restart WSL2 and try again"
}

# Function to check AutoBot compatibility
check_autobot_compatibility() {
    echo "🤖 Checking AutoBot + KEX compatibility..."
    
    # Check if AutoBot is using ports that might conflict
    AUTOBOT_PORTS=$(netstat -tlnp 2>/dev/null | grep -E ":(5173|8001|6379)" | grep LISTEN)
    if [ -n "$AUTOBOT_PORTS" ]; then
        echo "✅ AutoBot services detected:"
        echo "$AUTOBOT_PORTS"
        echo "   AutoBot should work fine with KEX"
    else
        echo "ℹ️  No AutoBot services detected currently"
    fi
    
    # Check display environment
    if [ -n "$DISPLAY" ]; then
        echo "✅ DISPLAY variable set: $DISPLAY"
    else
        echo "⚠️  DISPLAY variable not set - may affect GUI applications"
        echo "   Try: export DISPLAY=:0"
    fi
}

# Main execution
main() {
    echo "Starting KEX diagnostic..."
    echo ""
    
    check_wsl2
    check_kex_installation
    check_services
    check_autobot_compatibility
    
    echo ""
    echo "🔧 ATTEMPTING FIXES..."
    fix_kex_issues
    
    echo ""
    echo "🧪 TESTING KEX..."
    if test_kex_startup; then
        echo ""
        echo "🟢 KEX APPEARS TO BE WORKING!"
        echo "   Try connecting with VNC viewer to localhost:5901"
        echo "   Or use: kex --win"
    else
        echo ""
        echo "🔴 KEX STARTUP FAILED"
        provide_troubleshooting
    fi
    
    echo ""
    echo "📋 KEX STATUS SUMMARY"
    echo "===================="
    ps aux | grep -E "(kex|Xvnc|vnc)" | grep -v grep || echo "No KEX/VNC processes running"
    netstat -tlnp 2>/dev/null | grep -E ":59[0-9][0-9].*LISTEN" || echo "No VNC ports listening"
}

# Run with sudo check
if [ "$EUID" -eq 0 ]; then
    echo "⚠️  Running as root - some features may not work correctly"
    echo "   Consider running as regular user with sudo when needed"
fi

main "$@"