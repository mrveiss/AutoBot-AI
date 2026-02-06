/**
 * Simple GUI Test for AutoBot - Standalone Version
 * Tests basic functionality without Playwright test runner
 */

const { chromium } = require('playwright');

class SimpleGUITester {
    constructor() {
        this.browser = null;
        this.page = null;
        this.results = {
            passed: 0,
            failed: 0,
            warnings: 0,
            tests: []
        };
    }

    async init() {
        console.log('🚀 Starting AutoBot GUI Test...');
        this.browser = await chromium.launch({
            headless: false,
            slowMo: 500,
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });
        this.page = await this.browser.newPage();

        // Set viewport
        await this.page.setViewportSize({ width: 1280, height: 720 });
    }

    async log(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const prefix = type === 'pass' ? '✅' : type === 'fail' ? '❌' : type === 'warn' ? '⚠️' : 'ℹ️';
        console.log(`[${timestamp}] ${prefix} ${message}`);

        this.results.tests.push({ message, type, timestamp });

        if (type === 'pass') this.results.passed++;
        else if (type === 'fail') this.results.failed++;
        else if (type === 'warn') this.results.warnings++;
    }

    async testPageLoad() {
        try {
            this.log('Testing page load...');
            await this.page.goto('http://localhost:5173', { waitUntil: 'networkidle' });

            const title = await this.page.title();
            if (title && title.length > 0) {
                this.log(`Page loaded successfully: "${title}"`, 'pass');
            } else {
                this.log('Page loaded but no title found', 'warn');
            }

            // Check if main elements are present
            const body = await this.page.locator('body').count();
            if (body > 0) {
                this.log('Page body rendered', 'pass');
            } else {
                this.log('Page body not found', 'fail');
            }

        } catch (error) {
            this.log(`Page load failed: ${error.message}`, 'fail');
        }
    }

    async testBasicElements() {
        try {
            this.log('Testing basic UI elements...');

            // Common UI elements to check
            const elements = [
                { selector: 'button', name: 'buttons' },
                { selector: 'input', name: 'input fields' },
                { selector: 'nav', name: 'navigation' },
                { selector: '[class*="chat"]', name: 'chat components' },
                { selector: '[class*="terminal"]', name: 'terminal components' },
                { selector: '[class*="workflow"]', name: 'workflow components' }
            ];

            for (const element of elements) {
                try {
                    const count = await this.page.locator(element.selector).count();
                    if (count > 0) {
                        this.log(`Found ${count} ${element.name}`, 'pass');
                    } else {
                        this.log(`No ${element.name} found`, 'warn');
                    }
                } catch (error) {
                    this.log(`Error checking ${element.name}: ${error.message}`, 'fail');
                }
            }

        } catch (error) {
            this.log(`Basic elements test failed: ${error.message}`, 'fail');
        }
    }

    async testNavigation() {
        try {
            this.log('Testing navigation...');

            // Look for navigation links/buttons
            const navItems = ['Chat', 'Terminal', 'Settings', 'Knowledge', 'Monitor'];

            for (const item of navItems) {
                try {
                    const element = this.page.locator(`text="${item}"`).first();
                    if (await element.isVisible({ timeout: 3000 })) {
                        this.log(`Navigation item "${item}" found`, 'pass');

                        // Try clicking it
                        await element.click();
                        await this.page.waitForTimeout(1000);
                        this.log(`Navigation to "${item}" successful`, 'pass');
                    } else {
                        this.log(`Navigation item "${item}" not found`, 'warn');
                    }
                } catch (error) {
                    this.log(`Navigation to "${item}" failed: ${error.message}`, 'fail');
                }
            }

        } catch (error) {
            this.log(`Navigation test failed: ${error.message}`, 'fail');
        }
    }

    async testChatInterface() {
        try {
            this.log('Testing chat interface...');

            // Look for chat input
            const inputSelectors = [
                'input[placeholder*="message"]',
                'textarea[placeholder*="message"]',
                'input[type="text"]',
                '.chat-input input'
            ];

            let inputFound = false;
            for (const selector of inputSelectors) {
                try {
                    const input = this.page.locator(selector).first();
                    if (await input.isVisible({ timeout: 2000 })) {
                        await input.fill('Test message');
                        this.log('Chat input field works', 'pass');
                        inputFound = true;
                        break;
                    }
                } catch (error) {
                    // Continue checking other selectors
                }
            }

            if (!inputFound) {
                this.log('Chat input field not found', 'warn');
            }

            // Look for send button
            const sendSelectors = [
                'button:has-text("Send")',
                'button[type="submit"]',
                '.send-button',
                '[class*="send"]'
            ];

            let sendFound = false;
            for (const selector of sendSelectors) {
                try {
                    const button = this.page.locator(selector).first();
                    if (await button.isVisible({ timeout: 2000 })) {
                        this.log('Send button found', 'pass');
                        sendFound = true;
                        break;
                    }
                } catch (error) {
                    // Continue checking other selectors
                }
            }

            if (!sendFound) {
                this.log('Send button not found', 'warn');
            }

        } catch (error) {
            this.log(`Chat interface test failed: ${error.message}`, 'fail');
        }
    }

    async testResponsiveness() {
        try {
            this.log('Testing responsive design...');

            const viewports = [
                { width: 1920, height: 1080, name: 'Desktop' },
                { width: 768, height: 1024, name: 'Tablet' },
                { width: 375, height: 667, name: 'Mobile' }
            ];

            for (const viewport of viewports) {
                await this.page.setViewportSize({
                    width: viewport.width,
                    height: viewport.height
                });
                await this.page.waitForTimeout(1000);

                // Check if page is still functional
                const bodyVisible = await this.page.locator('body').isVisible();
                if (bodyVisible) {
                    this.log(`${viewport.name} viewport (${viewport.width}x${viewport.height}) works`, 'pass');
                } else {
                    this.log(`${viewport.name} viewport has issues`, 'fail');
                }
            }

        } catch (error) {
            this.log(`Responsiveness test failed: ${error.message}`, 'fail');
        }
    }

    async testConsoleErrors() {
        try {
            this.log('Checking for console errors...');

            const errors = [];
            this.page.on('console', msg => {
                if (msg.type() === 'error') {
                    errors.push(msg.text());
                }
            });

            // Reload page to catch any console errors
            await this.page.reload({ waitUntil: 'networkidle' });
            await this.page.waitForTimeout(3000);

            if (errors.length === 0) {
                this.log('No console errors detected', 'pass');
            } else {
                this.log(`Found ${errors.length} console errors`, 'warn');
                errors.forEach(error => {
                    this.log(`Console error: ${error.substring(0, 100)}...`, 'fail');
                });
            }

        } catch (error) {
            this.log(`Console error check failed: ${error.message}`, 'fail');
        }
    }

    async runAllTests() {
        try {
            await this.init();

            await this.testPageLoad();
            await this.testBasicElements();
            await this.testNavigation();
            await this.testChatInterface();
            await this.testResponsiveness();
            await this.testConsoleErrors();

            await this.cleanup();
            this.printSummary();

        } catch (error) {
            this.log(`Test suite failed: ${error.message}`, 'fail');
            await this.cleanup();
        }
    }

    async cleanup() {
        if (this.browser) {
            await this.browser.close();
        }
    }

    printSummary() {
        console.log('\n' + '='.repeat(60));
        console.log('📋 GUI TEST SUMMARY');
        console.log('='.repeat(60));
        console.log(`✅ Passed: ${this.results.passed}`);
        console.log(`❌ Failed: ${this.results.failed}`);
        console.log(`⚠️  Warnings: ${this.results.warnings}`);
        console.log(`📊 Total Tests: ${this.results.tests.length}`);

        if (this.results.failed === 0) {
            console.log('\n🟢 GUI TESTS PASSED - Interface working correctly');
        } else if (this.results.failed < 3) {
            console.log('\n🟡 GUI TESTS PARTIAL - Some issues detected');
        } else {
            console.log('\n🔴 GUI TESTS FAILED - Major issues detected');
        }

        console.log('='.repeat(60));
    }
}

// Run the tests
const tester = new SimpleGUITester();
tester.runAllTests().catch(console.error);
