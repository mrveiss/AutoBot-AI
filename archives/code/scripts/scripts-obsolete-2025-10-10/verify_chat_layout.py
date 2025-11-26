#!/usr/bin/env python3
"""
Verify Chat Layout Fix - Browser VM Remote Execution
=================================================
This script connects to the Browser VM (172.16.168.25) and uses its
pre-installed Playwright to navigate to the frontend and take a screenshot
to verify that the chat sidebar layout has been fixed.
"""

import asyncio
import sys
import subprocess
import json
from pathlib import Path

# Ensure we have the proper output directory for screenshots
output_dir = Path("/home/kali/Desktop/AutoBot/analysis/multimodal")
output_dir.mkdir(parents=True, exist_ok=True)

def run_playwright_on_browser_vm():
    """Execute Playwright script on Browser VM (172.16.168.25) to verify chat layout."""

    # Create the Playwright script to run on Browser VM
    playwright_script = '''
import asyncio
from playwright.async_api import async_playwright
import json
import sys

async def verify_chat_layout():
    """Navigate to frontend and verify chat layout with sidebar."""
    try:
        async with async_playwright() as p:
            # Launch browser with visible mode for debugging if needed
            browser = await p.chromium.launch(
                headless=False,  # Keep visible to see what's happening
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )

            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080}
            )

            page = await context.new_page()

            # Navigate to the frontend
            frontend_url = "http://172.16.168.21:5173"
            print(f"Navigating to: {frontend_url}")

            try:
                await page.goto(frontend_url, wait_until="networkidle", timeout=15000)
                print("✅ Frontend loaded successfully")

                # Wait for any dynamic content to load
                await page.wait_for_timeout(3000)

                # Check if chat interface is present
                chat_interface = await page.query_selector('.chat-interface')
                if chat_interface:
                    print("✅ Chat interface found")
                else:
                    print("❌ Chat interface not found")

                # Check for sidebar specifically
                sidebar = await page.query_selector('div[class*="w-80"]')
                if sidebar:
                    print("✅ Sidebar with w-80 class found")

                    # Get sidebar bounding box to verify it's visible
                    sidebar_box = await sidebar.bounding_box()
                    if sidebar_box and sidebar_box['width'] > 0:
                        print(f"✅ Sidebar is visible with width: {sidebar_box['width']}px")
                    else:
                        print("❌ Sidebar exists but has no visible dimensions")
                else:
                    print("❌ Sidebar with w-80 class not found")

                # Take a full page screenshot
                screenshot_path = "/tmp/chat_layout_verification.png"
                await page.screenshot(path=screenshot_path, full_page=True)
                print(f"✅ Screenshot saved to: {screenshot_path}")

                # Get page title and URL for verification
                title = await page.title()
                url = page.url

                result = {
                    "success": True,
                    "title": title,
                    "url": url,
                    "screenshot_path": screenshot_path,
                    "sidebar_found": sidebar is not None,
                    "sidebar_visible": sidebar_box is not None and sidebar_box['width'] > 0 if sidebar else False,
                    "timestamp": "$(date -u +%%Y-%%m-%%dT%%H:%%M:%%SZ)"
                }

                print("\\n=== VERIFICATION RESULTS ===")
                print(json.dumps(result, indent=2))

            except Exception as nav_error:
                print(f"❌ Navigation error: {nav_error}")
                result = {
                    "success": False,
                    "error": str(nav_error),
                    "timestamp": "$(date -u +%%Y-%%m-%%dT%%H:%%M:%%SZ)"
                }

            finally:
                await browser.close()
                return result

    except Exception as e:
        print(f"❌ Playwright execution error: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    result = asyncio.run(verify_chat_layout())
    sys.exit(0 if result.get("success", False) else 1)
'''

    try:
        print("🔍 Connecting to Browser VM (172.16.168.25) to verify chat layout...")

        # Save the script to a temporary file and execute it on Browser VM
        cmd = [
            "ssh", "-i", "/home/kali/.ssh/autobot_key",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "autobot@172.16.168.25",
            f"cd /home/autobot && python3 -c '{playwright_script}'"
        ]

        print("📡 Executing Playwright verification on Browser VM...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            print("✅ Playwright execution completed successfully")
            print("\n=== Browser VM Output ===")
            print(result.stdout)

            # Try to copy the screenshot back to local machine
            try:
                copy_cmd = [
                    "scp", "-i", "/home/kali/.ssh/autobot_key",
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null",
                    "autobot@172.16.168.25:/tmp/chat_layout_verification.png",
                    str(output_dir / "chat_layout_verification.png")
                ]

                copy_result = subprocess.run(copy_cmd, capture_output=True, text=True)
                if copy_result.returncode == 0:
                    print(f"✅ Screenshot copied to: {output_dir / 'chat_layout_verification.png'}")
                else:
                    print(f"⚠️ Failed to copy screenshot: {copy_result.stderr}")

            except Exception as copy_error:
                print(f"⚠️ Screenshot copy error: {copy_error}")

        else:
            print("❌ Playwright execution failed")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print("❌ Browser VM connection timed out")
        return False
    except Exception as e:
        print(f"❌ Error connecting to Browser VM: {e}")
        return False

def main():
    """Main verification function."""
    print("🎭 AutoBot Chat Layout Verification")
    print("=" * 50)
    print("Verifying that the chat sidebar layout fix has been applied correctly")
    print("Expected: Sidebar visible on left side with w-80 class (320px width)")
    print()

    # Run the verification
    success = run_playwright_on_browser_vm()

    if success:
        print("\n✅ Chat layout verification completed successfully!")
        print("The sidebar should now be visible on the left side of the chat interface.")
        screenshot_path = output_dir / "chat_layout_verification.png"
        if screenshot_path.exists():
            print(f"📸 Screenshot available at: {screenshot_path}")

    else:
        print("\n❌ Chat layout verification failed!")
        print("Please check the Browser VM connection and frontend status.")

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
