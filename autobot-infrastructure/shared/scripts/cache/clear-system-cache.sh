#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot System-Level Cache Clearing Script
# Comprehensive system cache clearing to prevent configuration issues

set -e

echo "🧹 AutoBot System Cache Clearing Started..."
echo "==========================================="

# Check if running with sudo for system-level operations
if [ "$EUID" -ne 0 ] && [ "$1" = "--system" ]; then
    echo "🔒 System-level cache clearing requires sudo privileges"
    echo "💡 Run: sudo ./clear-system-cache.sh --system"
    echo "📋 Running user-level cache clearing instead..."
    echo ""
fi

# Function to run command with error handling
run_command() {
    local cmd="$1"
    local description="$2"
    local require_sudo="$3"

    if [ "$require_sudo" = "true" ] && [ "$EUID" -ne 0 ]; then
        echo "⚠️  $description - SKIPPED (requires sudo)"
        return
    fi

    echo "📋 $description"
    if eval "$cmd"; then
        echo "✅ $description - SUCCESS"
    else
        echo "⚠️  $description - FAILED (continuing...)"
    fi
    echo ""
}

# DNS Cache Clearing
echo "🌐 Clearing DNS caches..."

# Clear systemd-resolved cache
run_command "systemctl is-active systemd-resolved >/dev/null && systemctl flush-dns || true" "Flushing systemd-resolved DNS cache" "true"

# Clear nscd cache if running
run_command "systemctl is-active nscd >/dev/null && systemctl restart nscd || true" "Restarting nscd DNS cache" "true"

# WSL2 specific DNS cache clearing
if grep -qi microsoft /proc/version 2>/dev/null; then
    echo "🪟 Detected WSL2 environment..."
    run_command "echo 'WSL2 detected - Windows host DNS cache may need clearing'" "WSL2 DNS notice"

    # Clear WSL2 resolv.conf cache
    run_command "sudo rm -f /etc/resolv.conf.bak && sudo cp /etc/resolv.conf /etc/resolv.conf.bak || true" "Backing up WSL2 DNS config" "true"
fi

# Browser cache clearing (user-level)
echo "🌍 Clearing user browser caches..."

# Clear Chrome cache
CHROME_CACHE_DIRS=(
    "$HOME/.cache/google-chrome"
    "$HOME/.config/google-chrome/Default/Cache"
    "$HOME/.config/google-chrome/Default/Code Cache"
    "$HOME/.config/chromium/Default/Cache"
    "$HOME/.config/chromium/Default/Code Cache"
)

for dir in "${CHROME_CACHE_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        run_command "rm -rf '$dir'" "Clearing Chrome cache: $(basename "$dir")"
    fi
done

# Clear Firefox cache
FIREFOX_CACHE_DIRS=(
    "$HOME/.cache/mozilla/firefox"
    "$HOME/.mozilla/firefox/*/cache2"
)

for pattern in "${FIREFOX_CACHE_DIRS[@]}"; do
    for dir in $pattern; do
        if [ -d "$dir" ]; then
            run_command "rm -rf '$dir'" "Clearing Firefox cache: $(basename "$dir")"
        fi
    done
done

# System-level cache clearing
if [ "$1" = "--system" ] && [ "$EUID" -eq 0 ]; then
    echo "🖥️  Clearing system-level caches..."

    # Clear package manager caches
    run_command "apt-get clean" "Clearing apt package cache" "true"
    run_command "rm -rf /var/cache/apt/archives/*.deb" "Removing cached deb packages" "true"

    # Clear font cache
    run_command "fc-cache -fv" "Refreshing font cache" "true"

    # Clear thumbnail cache
    run_command "rm -rf /home/*/.cache/thumbnails" "Clearing thumbnail caches" "true"
    run_command "rm -rf /root/.cache/thumbnails" "Clearing root thumbnail cache" "true"
fi

# Container runtime cache clearing
echo "📦 Clearing container runtime caches..."

# Docker cache clearing
if command -v docker >/dev/null 2>&1; then
    run_command "docker system prune -f" "Clearing Docker system cache"
    run_command "docker builder prune -f" "Clearing Docker build cache"
    run_command "docker volume prune -f" "Clearing unused Docker volumes"
fi

# Clear container-specific caches
if [ -d "/var/lib/docker" ] && [ "$EUID" -eq 0 ]; then
    run_command "docker system df" "Showing Docker disk usage"
fi

# Memory and buffer cache clearing (system-level)
if [ "$1" = "--memory" ] || [ "$1" = "--system" ]; then
    echo "💾 Clearing memory caches..."

    if [ "$EUID" -eq 0 ]; then
        run_command "sync" "Syncing filesystems" "true"
        run_command "echo 1 > /proc/sys/vm/drop_caches" "Clearing page cache" "true"
        run_command "echo 2 > /proc/sys/vm/drop_caches" "Clearing dentries and inodes" "true"
        run_command "echo 3 > /proc/sys/vm/drop_caches" "Clearing all caches" "true"
    else
        echo "⚠️  Memory cache clearing requires sudo privileges"
    fi
fi

# Network cache clearing
echo "🔗 Clearing network caches..."

# Clear ARP cache
run_command "ip neigh flush all" "Clearing ARP cache" "true"

# Clear routing cache
run_command "ip route flush cache" "Clearing routing cache" "true"

# Application-specific cache clearing
echo "📱 Clearing application caches..."

# Clear Python pip cache
run_command "python3 -m pip cache purge" "Clearing pip cache"

# Clear npm cache
if command -v npm >/dev/null 2>&1; then
    run_command "npm cache clean --force" "Clearing npm cache"
fi

# Clear yarn cache
if command -v yarn >/dev/null 2>&1; then
    run_command "yarn cache clean" "Clearing yarn cache"
fi

# Clear various application caches
USER_CACHE_DIRS=(
    "$HOME/.cache/pip"
    "$HOME/.cache/npm"
    "$HOME/.cache/yarn"
    "$HOME/.cache/electron"
    "$HOME/.cache/node"
    "$HOME/.cache/vscode-*"
)

for pattern in "${USER_CACHE_DIRS[@]}"; do
    for dir in $pattern; do
        if [ -d "$dir" ]; then
            run_command "rm -rf '$dir'" "Clearing cache: $(basename "$dir")"
        fi
    done
done

echo ""
echo "==========================================="
echo "✅ AutoBot System Cache Clearing COMPLETED!"
echo ""
echo "📋 What was cleared:"
echo "   • DNS resolution caches"
echo "   • Browser caches (Chrome, Firefox)"
echo "   • Container runtime caches (Docker)"
echo "   • Application caches (pip, npm, yarn)"
echo "   • User-level cache directories"

if [ "$1" = "--system" ] && [ "$EUID" -eq 0 ]; then
    echo "   • System package caches"
    echo "   • Font and thumbnail caches"
    echo "   • Network routing and ARP caches"
fi

if [ "$1" = "--memory" ] || [ "$1" = "--system" ]; then
    echo "   • Memory page and inode caches"
fi

echo ""
echo "🚀 Next steps:"
echo "   • Restart browser for full effect"
echo "   • Test API connectivity"
echo "   • Monitor system performance"
echo ""
echo "💡 Usage:"
echo "   ./clear-system-cache.sh              # User-level cache clear"
echo "   sudo ./clear-system-cache.sh --system # System-level cache clear"
echo "   sudo ./clear-system-cache.sh --memory # Include memory caches"
echo ""
echo "⚠️  Note: Some network settings may require reconnection"
echo "🔄 Consider restarting services if issues persist"
echo ""
