#!/bin/bash

# Setup script for Tier 2 Advanced Web Research capabilities
# This installs Playwright, configures browsers, and sets up dependencies

set -e

echo "🚀 Setting up Tier 2 Advanced Web Research capabilities..."

# Check if we're in a virtual environment
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "⚠️  Warning: Not in a virtual environment. Consider activating venv first."
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install playwright aiohttp pyyaml

# Install Playwright browsers
echo "🌐 Installing Playwright browsers..."
playwright install

# Install only Chromium for minimal setup (optional)
# playwright install chromium

# Install system dependencies for Playwright
echo "🔧 Installing system dependencies..."
if command -v apt-get &> /dev/null; then
    # Ubuntu/Debian
    playwright install-deps
elif command -v yum &> /dev/null; then
    # CentOS/RHEL
    echo "⚠️  Please install browser dependencies manually for your system"
    echo "See: https://playwright.dev/python/docs/browsers#system-requirements"
elif command -v pacman &> /dev/null; then
    # Arch Linux
    echo "⚠️  Please install browser dependencies manually for your system"
    echo "See: https://playwright.dev/python/docs/browsers#system-requirements"
fi

# Create directories for configuration and cache
echo "📁 Creating configuration directories..."
mkdir -p config/
mkdir -p data/cache/web_research/
mkdir -p logs/web_research/

# Copy configuration file if it doesn't exist
if [ ! -f config/web_research.yaml ]; then
    cp config/web_research_config.yaml config/web_research.yaml
    echo "📝 Configuration file created at config/web_research.yaml"
    echo "✏️  Edit this file to configure CAPTCHA services, proxies, etc."
fi

# Create a test script
cat > test_tier2_research.py << 'EOF'
#!/usr/bin/env python3
"""
Test script for Tier 2 Advanced Web Research capabilities
"""

import asyncio
import json
from src.agents.advanced_web_research import AdvancedWebResearcher

async def test_advanced_research():
    print("🧪 Testing Advanced Web Research...")

    config = {
        'headless': True,
        'captcha': {
            'enabled': False  # Set to True and add API key to test CAPTCHA solving
        }
    }

    async with AdvancedWebResearcher(config) as researcher:
        # Test search
        results = await researcher.search_web("python web scraping tutorial", max_results=3)

        print(f"✅ Search completed!")
        print(f"Status: {results['status']}")
        print(f"Results found: {len(results.get('results', []))}")
        print(f"Search engines used: {results.get('search_engines_used', 0)}")

        # Display first result
        if results.get('results'):
            first_result = results['results'][0]
            print(f"\n📄 First result:")
            print(f"Title: {first_result['title']}")
            print(f"URL: {first_result['url']}")
            print(f"Quality Score: {first_result.get('quality_score', 'N/A')}")
            print(f"Content Length: {first_result.get('content_length', 0)} chars")
            print(f"Search Engine: {first_result.get('search_engine', 'Unknown')}")

if __name__ == "__main__":
    asyncio.run(test_advanced_research())
EOF

chmod +x test_tier2_research.py

# Create a simple enable/disable script
cat > toggle_tier2_research.py << 'EOF'
#!/usr/bin/env python3
"""
Script to enable/disable Tier 2 Advanced Web Research
"""

import yaml
import sys

def toggle_advanced_research(enable=None):
    config_path = 'config/web_research.yaml'

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"❌ Configuration file not found: {config_path}")
        return

    current_status = config.get('enable_advanced_research', False)

    if enable is None:
        # Toggle current status
        new_status = not current_status
    else:
        new_status = enable

    config['enable_advanced_research'] = new_status

    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=True)

    status_text = "ENABLED" if new_status else "DISABLED"
    print(f"🔧 Advanced Web Research is now {status_text}")

    if new_status:
        print("📋 To configure CAPTCHA solving:")
        print("   1. Edit config/web_research.yaml")
        print("   2. Set captcha.enabled: true")
        print("   3. Add your API key to captcha.api_key")
        print("   4. Choose service: 2captcha, anticaptcha, etc.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        action = sys.argv[1].lower()
        if action == 'enable':
            toggle_advanced_research(True)
        elif action == 'disable':
            toggle_advanced_research(False)
        else:
            print("Usage: python toggle_tier2_research.py [enable|disable]")
    else:
        toggle_advanced_research()  # Toggle current status
EOF

chmod +x toggle_tier2_research.py

echo ""
echo "✅ Tier 2 Advanced Web Research setup completed!"
echo ""
echo "📋 Next steps:"
echo "1. Test the installation:"
echo "   python test_tier2_research.py"
echo ""
echo "2. Enable advanced research:"
echo "   python toggle_tier2_research.py enable"
echo ""
echo "3. Configure CAPTCHA solving (optional):"
echo "   - Edit config/web_research.yaml"
echo "   - Set captcha.enabled: true"
echo "   - Add your CAPTCHA service API key"
echo "   - Supported services: 2captcha.com, anti-captcha.com"
echo ""
echo "4. Configure proxies (optional):"
echo "   - Edit config/web_research.yaml"
echo "   - Set proxy configuration for residential proxies"
echo ""
echo "⚠️  Note: Advanced research includes browser automation"
echo "   This may trigger anti-bot measures on some websites"
echo "   Always respect robots.txt and terms of service"
echo ""
echo "🔒 CAPTCHA Service Setup:"
echo "   2captcha.com - $3-5 per 1000 CAPTCHAs"
echo "   anti-captcha.com - $2-4 per 1000 CAPTCHAs"
echo "   capsolver.com - $0.8-2 per 1000 CAPTCHAs"
