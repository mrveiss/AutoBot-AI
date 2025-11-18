#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Frontend debugging script to run on Browser VM (headless)
Analyzes the blank page issue on http://172.16.168.21:5173
"""

import json
import time
from playwright.sync_api import sync_playwright

def analyze_frontend_issue():
    """Analyze the frontend blank page issue using Playwright"""

    with sync_playwright() as p:
        # Launch browser in headless mode
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-web-security', '--no-sandbox']
        )

        context = browser.new_context(
            viewport={'width': 1280, 'height': 720}
        )

        page = context.new_page()

        # Collect console logs
        console_logs = []
        errors = []
        network_requests = []
        network_responses = []

        def handle_console(msg):
            log_entry = {
                'type': msg.type,
                'text': msg.text,
                'location': msg.location if msg.location else None
            }
            console_logs.append(log_entry)
            print(f"CONSOLE [{msg.type}]: {msg.text}")
            if msg.location:
                print(f"  Location: {msg.location}")

        def handle_page_error(error):
            error_str = str(error)
            errors.append(error_str)
            print(f"PAGE ERROR: {error_str}")

        def handle_request(request):
            request_info = {
                'url': request.url,
                'method': request.method,
                'resource_type': request.resource_type,
                'headers': dict(request.headers)
            }
            network_requests.append(request_info)
            print(f"REQUEST: {request.method} {request.resource_type} {request.url}")

        def handle_response(response):
            response_info = {
                'url': response.url,
                'status': response.status,
                'ok': response.ok,
                'headers': dict(response.headers)
            }
            network_responses.append(response_info)
            if response.status >= 400:
                print(f"FAILED RESPONSE: {response.status} {response.url}")
            elif response.url.endswith(('.js', '.ts', '.vue')):
                print(f"JS RESPONSE: {response.status} {response.url}")

        # Set up event handlers
        page.on('console', handle_console)
        page.on('pageerror', handle_page_error)
        page.on('request', handle_request)
        page.on('response', handle_response)

        try:
            print("=" * 80)
            print("NAVIGATING TO FRONTEND: http://172.16.168.21:5173")
            print("=" * 80)

            # Navigate to frontend with extended timeout
            response = page.goto('http://172.16.168.21:5173',
                               wait_until='networkidle',
                               timeout=20000)

            print(f"Navigation response: {response.status if response else 'No response'}")

            # Wait for additional loading
            print("Waiting for page to fully load...")
            time.sleep(5)

            print("\n" + "=" * 80)
            print("PAGE CONTENT ANALYSIS")
            print("=" * 80)

            # Get page title and basic info
            title = page.title()
            url = page.url
            print(f"Page Title: '{title}'")
            print(f"Current URL: {url}")

            # Get HTML content
            html_content = page.content()
            print(f"HTML Content Length: {len(html_content)} characters")

            # Check if Vue app mounted
            app_element = page.query_selector('#app')
            if app_element:
                app_content = app_element.inner_html()
                print(f"#app element FOUND with content length: {len(app_content)}")

                # Show app content if it's not empty
                if app_content.strip():
                    if len(app_content) < 500:  # Show if reasonably short
                        print(f"#app content:\n{app_content}")
                    else:
                        print(f"#app content (first 500 chars):\n{app_content[:500]}...")
                else:
                    print("WARNING: #app element is empty!")
            else:
                print("CRITICAL ERROR: #app element NOT FOUND")

            # Check document body content
            body_element = page.query_selector('body')
            if body_element:
                body_content = body_element.inner_html()
                print(f"Body content length: {len(body_content)} characters")

            # Look for specific Vue.js indicators
            print("\n" + "=" * 80)
            print("VUE.JS FRAMEWORK ANALYSIS")
            print("=" * 80)

            try:
                # Check for Vue in global scope
                vue_check = page.evaluate("""
                    () => {
                        const checks = {
                            vue_available: typeof Vue !== 'undefined',
                            vue3_app: typeof window.__VUE__ !== 'undefined',
                            vite_client: typeof window.__vite_plugin_vue_export_helper !== 'undefined',
                            app_instance: typeof window.app !== 'undefined',
                            vue_devtools: typeof window.__VUE_DEVTOOLS_GLOBAL_HOOK__ !== 'undefined'
                        };
                        return checks;
                    }
                """)

                for check, result in vue_check.items():
                    print(f"{check}: {result}")

                # Check for errors in Vue mounting
                mount_errors = page.evaluate("""
                    () => {
                        const errors = [];

                        // Check if main.ts loaded
                        const scripts = Array.from(document.querySelectorAll('script'));
                        const hasMain = scripts.some(s => s.src && s.src.includes('main.ts'));

                        // Check for Vite HMR
                        const hasVite = !!window.__vite__;

                        return {
                            main_script_found: hasMain,
                            vite_hmr_available: hasVite,
                            script_count: scripts.length,
                            script_sources: scripts.map(s => s.src).filter(s => s)
                        };
                    }
                """)

                print(f"\nScript loading analysis:")
                for key, value in mount_errors.items():
                    print(f"  {key}: {value}")

            except Exception as e:
                print(f"Error during Vue.js analysis: {e}")

            # Analyze all script tags
            print("\n" + "=" * 80)
            print("SCRIPT TAGS ANALYSIS")
            print("=" * 80)

            scripts = page.query_selector_all('script')
            print(f"Total script tags found: {len(scripts)}")

            for i, script in enumerate(scripts):
                src = script.get_attribute('src')
                script_type = script.get_attribute('type')
                if src:
                    print(f"  Script {i+1}: {src} (type: {script_type})")
                else:
                    content = script.inner_text()
                    content_preview = content[:150].replace('\n', ' ') if content else 'empty'
                    print(f"  Script {i+1}: inline ({len(content)} chars) - {content_preview}...")

            # Check CSS files
            print("\n" + "=" * 80)
            print("STYLESHEET ANALYSIS")
            print("=" * 80)

            stylesheets = page.query_selector_all('link[rel="stylesheet"]')
            print(f"Stylesheet links found: {len(stylesheets)}")
            for i, link in enumerate(stylesheets):
                href = link.get_attribute('href')
                print(f"  Stylesheet {i+1}: {href}")

            # Take screenshot for debugging
            screenshot_path = '/tmp/frontend_debug_screenshot.png'
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"\nScreenshot saved to: {screenshot_path}")

            print("\n" + "=" * 80)
            print("NETWORK REQUESTS ANALYSIS")
            print("=" * 80)

            # Categorize requests
            js_requests = [r for r in network_requests if r['resource_type'] == 'script']
            css_requests = [r for r in network_requests if r['resource_type'] == 'stylesheet']
            doc_requests = [r for r in network_requests if r['resource_type'] == 'document']
            api_requests = [r for r in network_requests if '/api/' in r['url']]
            failed_requests = [r for r in network_responses if not r['ok']]

            print(f"Document requests: {len(doc_requests)}")
            for req in doc_requests:
                print(f"  {req['method']} {req['url']}")

            print(f"\nJavaScript requests: {len(js_requests)}")
            for req in js_requests:
                status = next((r['status'] for r in network_responses if r['url'] == req['url']), 'pending')
                print(f"  {req['method']} {req['url']} -> {status}")

            print(f"\nCSS requests: {len(css_requests)}")
            for req in css_requests:
                status = next((r['status'] for r in network_responses if r['url'] == req['url']), 'pending')
                print(f"  {req['method']} {req['url']} -> {status}")

            print(f"\nAPI requests: {len(api_requests)}")
            for req in api_requests:
                status = next((r['status'] for r in network_responses if r['url'] == req['url']), 'pending')
                print(f"  {req['method']} {req['url']} -> {status}")

            print(f"\nFailed requests: {len(failed_requests)}")
            for req in failed_requests:
                print(f"  {req['status']} {req['url']}")

            print("\n" + "=" * 80)
            print("CONSOLE LOGS ANALYSIS")
            print("=" * 80)

            error_logs = [log for log in console_logs if log['type'] == 'error']
            warning_logs = [log for log in console_logs if log['type'] == 'warning']
            info_logs = [log for log in console_logs if log['type'] == 'log' or log['type'] == 'info']

            print(f"Console Errors ({len(error_logs)}):")
            for i, log in enumerate(error_logs):
                print(f"  Error {i+1}: {log['text']}")
                if log['location']:
                    print(f"    Location: {log['location']}")

            print(f"\nConsole Warnings ({len(warning_logs)}):")
            for i, log in enumerate(warning_logs):
                print(f"  Warning {i+1}: {log['text']}")

            print(f"\nConsole Info/Log ({len(info_logs)}):")
            for i, log in enumerate(info_logs[:10]):  # Show first 10
                print(f"  Info {i+1}: {log['text']}")

            # Check if page is actually loading anything
            print("\n" + "=" * 80)
            print("PAGE LOADING STATUS")
            print("=" * 80)

            # Final check of page state
            final_state = page.evaluate("""
                () => {
                    return {
                        ready_state: document.readyState,
                        scripts_loaded: document.scripts.length,
                        stylesheets_loaded: document.styleSheets.length,
                        body_children: document.body.children.length,
                        app_children: document.getElementById('app') ? document.getElementById('app').children.length : 0,
                        has_vue_app: !!document.querySelector('[data-v-app]') || !!document.querySelector('.vue-app'),
                        page_height: document.body.scrollHeight,
                        visible_text: document.body.innerText.length
                    };
                }
            """)

            print("Final page state:")
            for key, value in final_state.items():
                print(f"  {key}: {value}")

        except Exception as e:
            print(f"CRITICAL ERROR during analysis: {e}")
            # Take screenshot even on error
            try:
                page.screenshot(path='/tmp/frontend_error_screenshot.png')
                print("Error screenshot saved to: /tmp/frontend_error_screenshot.png")
            except:
                pass

        finally:
            browser.close()

        # Return comprehensive analysis
        return {
            'console_logs': console_logs,
            'errors': errors,
            'network_requests': network_requests,
            'network_responses': network_responses,
            'analysis_complete': True
        }

if __name__ == '__main__':
    print("Starting Headless Frontend Analysis on Browser VM...")
    print("Target: http://172.16.168.21:5173")
    print("="*80)

    try:
        result = analyze_frontend_issue()
        print("\n" + "="*80)
        print("ANALYSIS COMPLETE!")
        print(f"Console logs captured: {len(result['console_logs'])}")
        print(f"Errors captured: {len(result['errors'])}")
        print(f"Network requests: {len(result['network_requests'])}")
        print("="*80)
    except Exception as e:
        print(f"Failed to complete analysis: {e}")