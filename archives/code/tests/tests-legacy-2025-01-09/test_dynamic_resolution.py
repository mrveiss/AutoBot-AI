#!/usr/bin/env python3
"""
Test script to verify dynamic resolution detection functionality
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.display_utils import get_current_resolution, get_playwright_config

def test_resolution_detection():
    """Test that we can detect the current display resolution"""
    print("🖥️  Testing Dynamic Resolution Detection")
    print("=" * 50)

    # Test basic resolution detection
    width, height = get_current_resolution()
    print(f"📐 Detected Resolution: {width}x{height}")

    # Test Playwright configuration
    config = get_playwright_config()
    viewport = config['viewport']
    detected = config['detected_resolution']

    print(f"🎯 Optimal Viewport: {viewport['width']}x{viewport['height']}")
    print(f"📊 Screen Utilization: {(viewport['width']/detected['width']*100):.1f}% x {(viewport['height']/detected['height']*100):.1f}%")
    print(f"🔧 Browser Args: {len(config['browser_args'])} arguments")

    # Validate results
    assert width > 0 and height > 0, "Resolution must be positive"
    assert viewport['width'] > 0 and viewport['height'] > 0, "Viewport must be positive"
    assert viewport['width'] <= width, "Viewport width should not exceed screen width"
    assert viewport['height'] <= height, "Viewport height should not exceed screen height"

    print("✅ All resolution detection tests passed!")
    return config

if __name__ == "__main__":
    test_resolution_detection()
