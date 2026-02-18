#!/bin/bash
# AutoBot Frontend Cache Clearing Script
# Comprehensive cache clearing to prevent API configuration issues

set -e

echo "🧹 AutoBot Frontend Cache Clearing Started..."
echo "=========================================="

# Function to run command with error handling
run_command() {
    local cmd="$1"
    local description="$2"
    echo "📋 $description"
    if eval "$cmd"; then
        echo "✅ $description - SUCCESS"
    else
        echo "⚠️  $description - FAILED (continuing...)"
    fi
    echo ""
}

# Clear npm cache
run_command "npm cache clean --force" "Clearing npm global cache"

# Clear Vite development cache
run_command "rm -rf node_modules/.vite" "Removing Vite dev cache"

# Clear general node cache directories
run_command "rm -rf node_modules/.cache" "Removing Node.js cache directory"

# Clear build outputs
run_command "rm -rf dist" "Removing build output directory"

# Clear Vite cache in project root
run_command "rm -rf .vite" "Removing Vite project cache"

# Clear Playwright cache
run_command "rm -rf playwright-report" "Removing Playwright reports"
run_command "rm -rf test-results" "Removing test results"

# Clear coverage reports
run_command "rm -rf coverage" "Removing coverage reports"

# Clear TypeScript build cache
run_command "rm -rf node_modules/.cache/typescript" "Removing TypeScript cache"

# Clear ESLint cache
run_command "rm -rf node_modules/.eslintcache" "Removing ESLint cache"
run_command "rm -f .eslintcache" "Removing local ESLint cache"

# Clear Prettier cache
run_command "rm -rf node_modules/.cache/prettier" "Removing Prettier cache"

# Clear PostCSS cache
run_command "rm -rf node_modules/.cache/postcss" "Removing PostCSS cache"

# Clear Vitest cache
run_command "rm -rf node_modules/.vitest" "Removing Vitest cache"

# Clear Vue DevTools cache
run_command "rm -rf node_modules/.cache/vue-devtools" "Removing Vue DevTools cache"

# Clear OS temporary files that might affect builds
if [ -d "/tmp/vite*" ]; then
    run_command "sudo rm -rf /tmp/vite*" "Removing Vite temporary files"
fi

# Clear Electron cache if present
if [ -d "node_modules/.cache/electron" ]; then
    run_command "rm -rf node_modules/.cache/electron" "Removing Electron cache"
fi

# Clear Terser cache
if [ -d "node_modules/.cache/terser-webpack-plugin" ]; then
    run_command "rm -rf node_modules/.cache/terser-webpack-plugin" "Removing Terser cache"
fi

echo "🔄 Running package cleanup commands..."

# Clear package-lock and reinstall to ensure clean state
if [ "$1" = "--full" ]; then
    echo "📦 Full package reinstall requested..."
    run_command "rm -rf node_modules" "Removing node_modules directory"
    run_command "rm -f package-lock.json" "Removing package-lock.json"
    run_command "npm install" "Reinstalling packages from scratch"
else
    echo "🔄 Quick package refresh..."
    run_command "npm ci --prefer-offline --no-audit" "Clean package install"
fi

echo ""
echo "=========================================="
echo "✅ AutoBot Frontend Cache Clearing COMPLETED!"
echo ""
echo "📋 What was cleared:"
echo "   • npm global and local caches"
echo "   • Vite development and build caches"
echo "   • Node.js module caches"
echo "   • Build outputs and temporary files"
echo "   • Testing and coverage caches"
echo "   • Linting and formatting caches"
echo "   • TypeScript compilation caches"
echo ""
echo "🚀 Next steps:"
echo "   • Run 'npm run dev' to start with clean cache"
echo "   • Check browser DevTools for hard refresh (Ctrl+Shift+R)"
echo "   • Clear browser cache if API issues persist"
echo ""
echo "💡 Usage:"
echo "   ./clear-cache.sh          # Quick cache clear"
echo "   ./clear-cache.sh --full   # Full reinstall"
echo ""
