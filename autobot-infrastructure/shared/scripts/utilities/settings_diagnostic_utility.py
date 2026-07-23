#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Settings Loading Fix Utility
Helps diagnose and resolve settings loading issues in AutoBot
"""

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from constants import ServiceURLs

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Browser fix script template (Issue #825: Moved to module level to reduce function length)
BROWSER_FIX_SCRIPT = """
// AutoBot Settings Fix Script
// Run this in your browser console (F12 -> Console)

// Import debugging utilities
import {
  log,
  getStorageJson,
  setStorageJson,
  validateStorageJson,
  runDiagnostics
} from '../utils/debugUtils';

log('info', '🔧 AutoBot Settings Fix Script loaded');

// Function to reset settings to defaults
function resetSettings() {
    const defaultSettings = {
        message_display: {
            show_thoughts: true,
            show_json: false,
            show_utility: false,
            show_planning: true,
            show_debug: false
        },
        chat: {
            auto_scroll: true,
            max_messages: 100,
            default_welcome_message: "Hello! How can I assist you today?"
        },
        backend: {
            use_phi2: false,
            api_endpoint: ServiceURLs.BACKEND_LOCAL,
            ollama_endpoint: ServiceURLs.OLLAMA_LOCAL,
            ollama_model: 'qwen3.5:9b',
            streaming: false
        },
        ui: {
            theme: 'light',
            font_size: 'medium'
        }
    };

    setStorageJson('chat_settings', defaultSettings);
    log('info', '✅ Settings reset to defaults');
    return defaultSettings;
}

// Function to check current settings
function checkSettings() {
    const result = validateStorageJson('chat_settings');

    if (!result.isValid) {
        log('error', '❌ Invalid settings in localStorage', result.error);
        return null;
    }

    log('info', '📋 Current settings valid');
    console.log(result.value);
    return result.value;
}

// Function to fix common issues
function fixCommonIssues() {
    const settings = getStorageJson('chat_settings', null);

    if (!settings) {
        log('warn', '🔄 No valid settings found, resetting...');
        resetSettings();
    } else {
        // Ensure backend endpoint is correct
        if (settings.backend && settings.backend.api_endpoint !== ServiceURLs.BACKEND_LOCAL) {
            log('info', '🔧 Fixing backend endpoint...');
            settings.backend.api_endpoint = ServiceURLs.BACKEND_LOCAL;
            setStorageJson('chat_settings', settings);
        }

        log('info', '✅ Settings validated and fixed');
    }

    // Reload the page to apply changes
    if (confirm('Settings have been fixed. Reload the page to apply changes?')) {
        location.reload();
    }
}

// Run diagnostics
log('info', '🔍 Running diagnostics...');
runDiagnostics();

// Provide options
console.log('\\n📋 Available commands:');
console.log('  resetSettings()     - Reset all settings to defaults');
console.log('  checkSettings()     - View current settings');
console.log('  fixCommonIssues()  - Fix common configuration issues');
console.log('  runDiagnostics()   - Run full system diagnostics');
console.log('\\nRun any command to proceed.');

// Auto-fix if settings are missing
const validation = validateStorageJson('chat_settings');
if (!validation.isValid) {
    log('warn', '⚠️ No valid settings found, auto-fixing...');
    fixCommonIssues();
}
"""


class SettingsLoadingFixer:
    """Diagnose and fix settings loading issues"""

    def __init__(self):
        """Initialize settings fixer with service URLs and issue tracking."""
        self.backend_url = ServiceURLs.BACKEND_LOCAL
        self.frontend_url = ServiceURLs.FRONTEND_LOCAL
        self.settings_file = Path("config/settings.json")
        self.issues_found = []
        self.fixes_applied = []

    def check_backend_health(self) -> bool:
        """Check if backend is responding to health checks"""
        try:
            logger.info("🔍 Checking backend health endpoint...")
            response = requests.get(f"{self.backend_url}/api/system/health", timeout=5)

            if response.status_code == 200:
                logger.info("✅ Backend health check passed")
                return True
            else:
                logger.error("❌ Backend health check failed: %s", response.status_code)
                self.issues_found.append("Backend health endpoint not responding correctly")
                return False

        except requests.exceptions.Timeout:
            logger.error("❌ Backend health check timed out")
            self.issues_found.append("Backend API timeout - server may be blocked")
            return False
        except requests.exceptions.ConnectionError:
            logger.error("❌ Backend not reachable")
            self.issues_found.append("Backend server not running or not accessible")
            return False

    def check_settings_endpoint(self) -> Optional[Dict[str, Any]]:
        """Check if settings endpoint is accessible"""
        try:
            logger.info("🔍 Testing settings endpoint...")
            response = requests.get(f"{self.backend_url}/api/settings", timeout=5)

            if response.status_code == 200:
                settings = response.json()
                logger.info("✅ Settings endpoint accessible")
                logger.info("📋 Retrieved %s setting categories", len(settings))
                return settings
            else:
                logger.error("❌ Settings endpoint returned: %s", response.status_code)
                self.issues_found.append(f"Settings endpoint error: {response.status_code}")
                return None

        except requests.exceptions.Timeout:
            logger.error("❌ Settings endpoint timed out")
            self.issues_found.append("Settings endpoint timeout")
            return None
        except Exception as e:
            logger.error("❌ Settings endpoint error: %s", e)
            self.issues_found.append(f"Settings endpoint error: {str(e)}")
            return None

    def check_settings_file(self) -> bool:
        """Check if settings.json file exists and is valid"""
        try:
            logger.info("🔍 Checking settings.json file...")

            if not self.settings_file.exists():
                logger.error("❌ settings.json file not found")
                self.issues_found.append("settings.json file missing")
                return False

            with open(self.settings_file, "r") as f:
                settings = json.load(f)

            # Check for required sections
            required_sections = ["backend", "chat", "message_display", "ui"]
            missing_sections = [s for s in required_sections if s not in settings]

            if missing_sections:
                logger.error("❌ Missing sections in settings.json: %s", missing_sections)
                self.issues_found.append(f"Missing settings sections: {missing_sections}")
                return False

            logger.info("✅ settings.json file is valid")
            return True

        except json.JSONDecodeError as e:
            logger.error("❌ Invalid JSON in settings.json: %s", e)
            self.issues_found.append("settings.json contains invalid JSON")
            return False
        except Exception as e:
            logger.error("❌ Error reading settings.json: %s", e)
            self.issues_found.append(f"Error reading settings file: {str(e)}")
            return False

    def check_frontend_processes(self) -> bool:
        """Check if frontend dev server is running"""
        try:
            logger.info("🔍 Checking frontend processes...")
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True)

            vite_processes = [line for line in result.stdout.split("\n") if "vite" in line.lower() and "node" in line]

            if vite_processes:
                logger.info(f"✅ Frontend dev server running ({len(vite_processes)} processes)")
                return True
            else:
                logger.warning("⚠️ Frontend dev server not detected")
                self.issues_found.append("Frontend development server not running")
                return False

        except Exception as e:
            logger.error("❌ Error checking frontend processes: %s", e)
            return False

    def restart_backend(self) -> bool:
        """Attempt to restart the backend server"""
        try:
            logger.info("🔄 Attempting to restart backend server...")

            # First, kill existing backend processes
            subprocess.run(["pkill", "-", "uvicorn.*main:app"], check=False)
            time.sleep(2)

            # Start backend in background
            env = os.environ.copy()
            env["PYTHONPATH"] = os.getcwd()

            process = subprocess.Popen(
                ["python", "main.py"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )

            # Wait for startup
            logger.info("⏳ Waiting for backend to start...")
            time.sleep(5)

            # Check if it started successfully
            if self.check_backend_health():
                logger.info("✅ Backend restarted successfully")
                self.fixes_applied.append("Backend server restarted")
                return True
            else:
                logger.error("❌ Backend restart failed")
                return False

        except Exception as e:
            logger.error("❌ Error restarting backend: %s", e)
            return False

    def _generate_browser_script_content(self) -> str:
        """
        Generate JavaScript content for browser fix script.

        Helper for generate_browser_fix_script (#825).

        Returns:
            JavaScript code string
        """
        return BROWSER_FIX_SCRIPT

    def _display_browser_instructions(self):
        """
        Display browser fix instructions.

        Helper for generate_browser_fix_script (#825).
        """
        logger.info("\n" + "=" * 70)
        logger.info("🌐 BROWSER FIX INSTRUCTIONS:")
        logger.info("=" * 70)
        logger.info("1. Open AutoBot in your browser: ServiceURLs.FRONTEND_LOCAL")
        logger.info("2. Press F12 to open Developer Tools")
        logger.info("3. Go to the Console tab")
        logger.info("4. Copy and paste the script from: scripts/utilities/browser_settings_utility.js")
        logger.info("5. Press Enter to run the script")
        logger.info("6. Follow the on-screen instructions")
        logger.info("=" * 70)

    def generate_browser_fix_script(self):
        """Generate JavaScript to fix settings in browser"""
        logger.info("📝 Generating browser fix script...")

        script = self._generate_browser_script_content()

        # Save script to file
        script_file = Path("scripts/utilities/browser_settings_utility.js")
        script_file.write_text(script)
        logger.info("✅ Browser fix script saved to: %s", script_file)

        # Display instructions
        self._display_browser_instructions()

    def run_diagnostics(self) -> bool:
        """Run complete diagnostics"""
        logger.info("🚀 Starting Settings Loading Diagnostics...")
        logger.info("=" * 70)

        # Check backend health
        backend_healthy = self.check_backend_health()

        # Check settings endpoint
        settings_data = self.check_settings_endpoint()

        # Check settings file
        settings_file_valid = self.check_settings_file()

        # Check frontend
        frontend_running = self.check_frontend_processes()

        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("📊 DIAGNOSTIC SUMMARY")
        logger.info("=" * 70)

        all_good = True

        if backend_healthy and settings_data:
            logger.info("✅ Backend API: Functional")
        else:
            logger.error("❌ Backend API: Not responding")
            all_good = False

        if settings_file_valid:
            logger.info("✅ Settings File: Valid")
        else:
            logger.error("❌ Settings File: Issues found")
            all_good = False

        if frontend_running:
            logger.info("✅ Frontend Server: Running")
        else:
            logger.warning("⚠️ Frontend Server: Not detected")

        if self.issues_found:
            logger.info("\n🔍 Issues Found (%s):", len(self.issues_found))
            for issue in self.issues_found:
                logger.info("  • %s", issue)

        return all_good

    def apply_fixes(self):
        """Apply automatic fixes where possible"""
        logger.info("\n🔧 APPLYING FIXES...")
        logger.info("=" * 70)

        # If backend is not responding, try to restart it
        if "Backend API timeout" in str(self.issues_found) or "Backend server not running" in str(self.issues_found):
            if self.restart_backend():
                logger.info("✅ Backend server restarted")
            else:
                logger.error("❌ Could not restart backend automatically")
                logger.info("💡 Try running: ./run_agent.sh")

        # Generate browser fix script
        self.generate_browser_fix_script()

        # Summary
        if self.fixes_applied:
            logger.info("\n✅ Fixes Applied (%s):", len(self.fixes_applied))
            for fix in self.fixes_applied:
                logger.info("  • %s", fix)

        logger.info("\n💡 RECOMMENDED ACTIONS:")
        logger.info("1. If backend is still not responding:")
        logger.info("   - Run: pkill -f uvicorn")
        logger.info("   - Run: ./run_agent.sh")
        logger.info("2. Clear browser cache and localStorage")
        logger.info("3. Use the browser fix script as instructed above")


def main():
    """Main function"""
    fixer = SettingsLoadingFixer()

    # Run diagnostics
    all_good = fixer.run_diagnostics()

    if not all_good:
        # Apply fixes
        fixer.apply_fixes()
    else:
        logger.info("\n✅ All systems operational! Settings should load correctly.")
        logger.info("💡 If you still have issues, try:")
        logger.info("   1. Clear browser cache (Ctrl+Shift+Delete)")
        logger.info("   2. Use incognito/private browsing mode")
        logger.info("   3. Check browser console for errors (F12)")


if __name__ == "__main__":
    main()
