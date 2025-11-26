#!/usr/bin/env python3
"""
Detailed Sidebar Layout Debugging
==================================
This script investigates why the sidebar is not visible despite
the w-80 class being applied.
"""

import subprocess
import sys
from pathlib import Path

def main():
    """Debug sidebar visibility issues with detailed DOM inspection."""

    # Create comprehensive debugging script
    debug_script = '''#!/usr/bin/env python3
import asyncio
from playwright.async_api import async_playwright
import json

async def debug_sidebar():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        try:
            print("🔍 Loading frontend...")
            await page.goto("http://172.16.168.21:5173", timeout=15000)
            await page.wait_for_timeout(3000)

            print("\\n=== DOM STRUCTURE ANALYSIS ===")

            # Check chat interface container
            chat_interface = await page.query_selector('.chat-interface')
            if chat_interface:
                interface_box = await chat_interface.bounding_box()
                print(f"✅ Chat interface found: {interface_box}")

                # Get all child elements
                children = await chat_interface.query_selector_all('> *')
                print(f"Chat interface has {len(children)} direct children")

                for i, child in enumerate(children):
                    class_name = await child.get_attribute('class')
                    tag_name = await child.evaluate('el => el.tagName')
                    box = await child.bounding_box()
                    print(f"  Child {i}: {tag_name} class='{class_name}' box={box}")

            # Specifically look for UnifiedLoadingView containing sidebar
            unified_views = await page.query_selector_all('div[class*="UnifiedLoadingView"], div[data-loading-key]')
            print(f"\\n=== UNIFIED LOADING VIEWS ({len(unified_views)}) ===")
            for i, view in enumerate(unified_views):
                class_name = await view.get_attribute('class')
                loading_key = await view.get_attribute('data-loading-key')
                box = await view.bounding_box()
                print(f"  View {i}: loading-key='{loading_key}' class='{class_name}' box={box}")

                # Check if this contains ChatSidebar
                sidebar = await view.query_selector('*[class*="ChatSidebar"], *[class*="sidebar"]')
                if sidebar:
                    sidebar_class = await sidebar.get_attribute('class')
                    sidebar_box = await sidebar.bounding_box()
                    print(f"    → Contains sidebar: class='{sidebar_class}' box={sidebar_box}")

            # Look for any element with w-80 class
            w80_elements = await page.query_selector_all('[class*="w-80"]')
            print(f"\\n=== ELEMENTS WITH w-80 CLASS ({len(w80_elements)}) ===")
            for i, elem in enumerate(w80_elements):
                class_name = await elem.get_attribute('class')
                tag_name = await elem.evaluate('el => el.tagName')
                box = await elem.bounding_box()
                is_visible = await elem.is_visible()
                print(f"  Element {i}: {tag_name} class='{class_name}' visible={is_visible} box={box}")

            # Check for any loading states
            loading_elements = await page.query_selector_all('[class*="loading"], [class*="spinner"]')
            print(f"\\n=== LOADING ELEMENTS ({len(loading_elements)}) ===")
            for elem in loading_elements:
                class_name = await elem.get_attribute('class')
                is_visible = await elem.is_visible()
                print(f"  Loading element: class='{class_name}' visible={is_visible}")

            # Check console errors
            print("\\n=== JAVASCRIPT CONSOLE LOGS ===")

            # Collect any console errors that might be affecting the sidebar
            def log_handler(msg):
                print(f"  Console {msg.type}: {msg.text}")

            page.on("console", log_handler)
            await page.reload()
            await page.wait_for_timeout(2000)

            # Take a detailed screenshot with debug info
            await page.screenshot(path="/tmp/sidebar_debug.png", full_page=True)
            print("\\n📸 Debug screenshot saved to /tmp/sidebar_debug.png")

        except Exception as e:
            print(f"❌ Error during debugging: {e}")
        finally:
            await browser.close()

asyncio.run(debug_sidebar())
'''

    try:
        # Write debug script to temp file
        temp_script = "/tmp/debug_sidebar.py"
        with open(temp_script, 'w') as f:
            f.write(debug_script)

        print("🔍 Starting detailed sidebar debugging...")

        # Copy script to Browser VM
        scp_cmd = [
            "scp", "-i", "/home/kali/.ssh/autobot_key",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            temp_script,
            "autobot@172.16.168.25:/tmp/debug_sidebar.py"
        ]

        subprocess.run(scp_cmd, capture_output=True, text=True)

        # Execute the debug script
        ssh_cmd = [
            "ssh", "-i", "/home/kali/.ssh/autobot_key",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "autobot@172.16.168.25",
            "cd /tmp && python3 debug_sidebar.py"
        ]

        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=90)

        print("=== DETAILED DEBUG OUTPUT ===")
        print(result.stdout)
        if result.stderr:
            print("=== ERRORS ===")
            print(result.stderr)

        # Copy debug screenshot back
        if "Debug screenshot saved" in result.stdout:
            output_dir = Path("/home/kali/Desktop/AutoBot/analysis/multimodal")
            copy_cmd = [
                "scp", "-i", "/home/kali/.ssh/autobot_key",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "autobot@172.16.168.25:/tmp/sidebar_debug.png",
                str(output_dir / "sidebar_debug_detailed.png")
            ]

            copy_result = subprocess.run(copy_cmd, capture_output=True, text=True)
            if copy_result.returncode == 0:
                print(f"\n📸 Debug screenshot saved to: {output_dir / 'sidebar_debug_detailed.png'}")

        return result.returncode

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
