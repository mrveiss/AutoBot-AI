#!/usr/bin/env python3
"""
Simple remote script to verify chat layout via Browser VM
"""

import subprocess
import sys
from pathlib import Path

def main():
    """Execute verification on Browser VM using a proper file transfer method."""

    # Create the verification script content
    script_content = '''#!/usr/bin/env python3
import asyncio
from playwright.async_api import async_playwright
import json

async def verify_layout():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        try:
            await page.goto("http://172.16.168.21:5173", timeout=15000)
            await page.wait_for_timeout(3000)

            # Check for sidebar with w-80 class
            sidebar = await page.query_selector('div[class*="w-80"]')
            sidebar_found = sidebar is not None

            # Check chat interface
            chat_interface = await page.query_selector('.chat-interface')
            interface_found = chat_interface is not None

            # Take screenshot
            await page.screenshot(path="/tmp/layout_check.png", full_page=True)

            print(f"Sidebar found: {sidebar_found}")
            print(f"Chat interface found: {interface_found}")
            print("Screenshot saved to /tmp/layout_check.png")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

asyncio.run(verify_layout())
'''

    try:
        # Write script to a local temp file
        temp_script = "/tmp/remote_verify.py"
        with open(temp_script, 'w') as f:
            f.write(script_content)

        print("📡 Copying verification script to Browser VM...")

        # Copy script to Browser VM
        scp_cmd = [
            "scp", "-i", "/home/kali/.ssh/autobot_key",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            temp_script,
            "autobot@172.16.168.25:/tmp/verify_layout.py"
        ]

        scp_result = subprocess.run(scp_cmd, capture_output=True, text=True)
        if scp_result.returncode != 0:
            print(f"❌ Failed to copy script: {scp_result.stderr}")
            return 1

        print("✅ Script copied successfully")
        print("🎭 Running Playwright verification on Browser VM...")

        # Execute the script on Browser VM
        ssh_cmd = [
            "ssh", "-i", "/home/kali/.ssh/autobot_key",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "autobot@172.16.168.25",
            "cd /tmp && python3 verify_layout.py"
        ]

        ssh_result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=60)

        print("=== Browser VM Output ===")
        print(ssh_result.stdout)
        if ssh_result.stderr:
            print("=== Errors ===")
            print(ssh_result.stderr)

        # Copy screenshot back
        if ssh_result.returncode == 0:
            print("\n📸 Copying screenshot back...")
            output_dir = Path("/home/kali/Desktop/AutoBot/analysis/multimodal")
            output_dir.mkdir(parents=True, exist_ok=True)

            copy_cmd = [
                "scp", "-i", "/home/kali/.ssh/autobot_key",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "autobot@172.16.168.25:/tmp/layout_check.png",
                str(output_dir / "chat_layout_verification.png")
            ]

            copy_result = subprocess.run(copy_cmd, capture_output=True, text=True)
            if copy_result.returncode == 0:
                print(f"✅ Screenshot saved to: {output_dir / 'chat_layout_verification.png'}")
            else:
                print(f"⚠️ Failed to copy screenshot: {copy_result.stderr}")

        return ssh_result.returncode

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
