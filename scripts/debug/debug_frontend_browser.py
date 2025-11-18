#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Frontend debugging script to run on Browser VM
Analyzes the blank page issue on http://172.16.168.21:5173
"""

import json
import time
from playwright.sync_api import sync_playwright

def analyze_frontend_issue():
    """Analyze the frontend blank page issue using Playwright"""

    with sync_playwright() as p:
        # Launch browser with debug options
        browser = p.chromium.launch(
            headless=False,  # Visual debugging
            devtools=True,   # Open DevTools
            args=['--disable-web-security', '--disable-features=VizDisplayCompositor']
        )

        context = browser.new_context(
            viewport={'width': 1280, 'height': 720}
        )

        page = context.new_page()

        # Collect console logs
        console_logs = []
        errors = []
        network_requests = []

        def handle_console(msg):
            console_logs.append({
                'type': msg.type,
                'text': msg.text,
                'location': msg.location
            })
            print(f"CONSOLE [{msg.type}]: {msg.text}")

        def handle_page_error(error):
            errors.append(str(error))
            print(f"PAGE ERROR: {error}")

        def handle_request(request):
            network_requests.append({
                'url': request.url,
                'method': request.method,
                'resource_type': request.resource_type
            })
            print(f"REQUEST: {request.method} {request.url}")

        def handle_response(response):
            if response.status >= 400:
                print(f"FAILED RESPONSE: {response.status} {response.url}")

        # Set up event handlers
        page.on('console', handle_console)
        page.on('pageerror', handle_page_error)
        page.on('request', handle_request)
        page.on('response', handle_response)

        try:
            print("=" * 60)
            print("NAVIGATING TO FRONTEND: http://172.16.168.21:5173")
            print("=" * 60)

            # Navigate to frontend
            response = page.goto('http://172.16.168.21:5173', timeout=15000)
            print(f"Navigation response: {response.status if response else 'No response'}")

            # Wait for potential loading
            time.sleep(3)

            print("\n" + "=" * 60)
            print("PAGE ANALYSIS")
            print("=" * 60)

            # Get page title and content
            title = page.title()
            print(f"Page Title: '{title}'")

            # Check if Vue app mounted
            app_element = page.query_selector('#app')
            if app_element:
                app_content = app_element.inner_html()
                print(f"#app element found with content length: {len(app_content)}")
                if len(app_content) < 100:  # Show if short
                    print(f"#app content: {app_content}")
            else:
                print("ERROR: #app element NOT FOUND")

            # Check for Vue.js in global scope
            try:
                vue_available = page.evaluate("typeof Vue !== 'undefined'")
                print(f"Vue available in global scope: {vue_available}")
            except:
                print("Vue not available in global scope")

            # Check for app instance
            try:
                app_instance = page.evaluate("window.app !== undefined")
                print(f"App instance available: {app_instance}")
            except:
                print("App instance not available")

            # Get all script tags
            scripts = page.query_selector_all('script')
            print(f"\nScript tags found: {len(scripts)}")
            for i, script in enumerate(scripts[:5]):  # Show first 5
                src = script.get_attribute('src')
                if src:
                    print(f"  Script {i+1}: {src}")
                else:
                    content = script.inner_text()[:100]
                    print(f"  Script {i+1}: inline ({len(content)} chars)")

            # Check for CSS files
            stylesheets = page.query_selector_all('link[rel="stylesheet"]')
            print(f"\nStylesheet links found: {len(stylesheets)}")
            for i, link in enumerate(stylesheets[:3]):
                href = link.get_attribute('href')
                print(f"  Stylesheet {i+1}: {href}")

            # Take screenshot
            screenshot_path = '/tmp/frontend_debug_screenshot.png'
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"\nScreenshot saved to: {screenshot_path}")

            print("\n" + "=" * 60)
            print("NETWORK REQUESTS SUMMARY")
            print("=" * 60)

            js_requests = [r for r in network_requests if r['resource_type'] == 'script']
            css_requests = [r for r in network_requests if r['resource_type'] == 'stylesheet']
            api_requests = [r for r in network_requests if 'api' in r['url']]

            print(f"JavaScript requests: {len(js_requests)}")
            for req in js_requests:
                print(f"  {req['method']} {req['url']}")

            print(f"\nCSS requests: {len(css_requests)}")
            for req in css_requests:
                print(f"  {req['method']} {req['url']}")

            print(f"\nAPI requests: {len(api_requests)}")
            for req in api_requests:
                print(f"  {req['method']} {req['url']}")

            print("\n" + "=" * 60)
            print("CONSOLE LOGS SUMMARY")
            print("=" * 60)

            error_logs = [log for log in console_logs if log['type'] == 'error']
            warning_logs = [log for log in console_logs if log['type'] == 'warning']

            print(f"Error logs: {len(error_logs)}")
            for log in error_logs:
                print(f"  ERROR: {log['text']}")
                if log['location']:
                    print(f"    Location: {log['location']}")

            print(f"\nWarning logs: {len(warning_logs)}")
            for log in warning_logs:
                print(f"  WARNING: {log['text']}")

            # Check specific Vue.js errors
            print("\n" + "=" * 60)
            print("VUE.JS SPECIFIC CHECKS")
            print("=" * 60)

            try:
                # Check for Vite dev server
                vite_check = page.evaluate("""
                    window.__vite__ !== undefined ||
                    document.querySelector('script[src*="@vite"]') !== null ||
                    document.querySelector('script[src*="main.ts"]') !== null
                """)
                print(f"Vite development server detected: {vite_check}")

                # Check for module loading errors
                module_errors = page.evaluate("""
                    (() => {
                        const errors = [];
                        // Check console for module errors
                        return window.moduleLoadErrors || [];
                    })()
                """)
                print(f"Module loading errors: {module_errors}")

            except Exception as e:
                print(f"Error during Vue.js checks: {e}")

            # Keep browser open for manual inspection
            print("\n" + "=" * 60)
            print("BROWSER READY FOR MANUAL INSPECTION")
            print("=" * 60)
            print("Browser will stay open for 30 seconds for manual debugging...")
            print("Check the browser window and DevTools for additional details.")

            time.sleep(30)

        except Exception as e:
            print(f"ERROR during analysis: {e}")
            # Take screenshot even on error
            try:
                page.screenshot(path='/tmp/frontend_error_screenshot.png')
                print("Error screenshot saved to: /tmp/frontend_error_screenshot.png")
            except:
                pass

        finally:
            browser.close()

        # Return analysis summary
        return {
            'console_logs': console_logs,
            'errors': errors,
            'network_requests': network_requests,
            'analysis_complete': True
        }

if __name__ == '__main__':
    print("Starting Frontend Analysis on Browser VM...")
    result = analyze_frontend_issue()
    print("\nAnalysis complete!")