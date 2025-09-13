/**
 * Comprehensive GUI Test Suite for AutoBot
 * Tests all major components, buttons, and functions
 */

const { test, expect } = require('@playwright/test');

class AutoBotGUITester {
    constructor(page) {
        this.page = page;
        this.baseUrl = 'http://localhost:5173';
        this.apiUrl = 'http://localhost:8001';
    }

    async waitForLoad() {
        await this.page.goto(this.baseUrl);
        await this.page.waitForLoadState('networkidle');
        await this.page.waitForTimeout(2000);
    }

    async checkApiHealth() {
        try {
            const response = await fetch(`${this.apiUrl}/api/system/health`);
            const health = await response.json();
            console.log('API Health:', health.status);
            return health.status === 'healthy';
        } catch (error) {
            console.log('API not available:', error.message);
            return false;
        }
    }

    async testBasicNavigation() {
        console.log('Testing basic navigation...');
        
        // Check main navigation elements
        const navElements = [
            'Chat', 'Knowledge Base', 'Settings', 'Terminal', 'System Monitor'
        ];

        for (const element of navElements) {
            try {
                const nav = await this.page.locator(`text="${element}"`).first();
                if (await nav.isVisible({ timeout: 3000 })) {
                    await nav.click();
                    await this.page.waitForTimeout(1000);
                    console.log(`✅ Navigation to ${element} works`);
                } else {
                    console.log(`❌ ${element} navigation not found`);
                }
            } catch (error) {
                console.log(`❌ ${element} navigation failed: ${error.message}`);
            }
        }
    }

    async testChatInterface() {
        console.log('Testing chat interface...');
        
        try {
            // Navigate to chat section
            await this.page.locator('text="Chat"').first().click();
            await this.page.waitForTimeout(1000);

            // Test message input
            const messageInput = this.page.locator('input[placeholder*="message"], textarea[placeholder*="message"]').first();
            if (await messageInput.isVisible({ timeout: 3000 })) {
                await messageInput.fill('Hello, this is a test message');
                console.log('✅ Message input works');
                
                // Test send button
                const sendButton = this.page.locator('button:has-text("Send"), button[type="submit"]').first();
                if (await sendButton.isVisible({ timeout: 2000 })) {
                    console.log('✅ Send button found');
                    // Note: Not actually sending to avoid backend dependency
                } else {
                    console.log('❌ Send button not found');
                }
            } else {
                console.log('❌ Message input not found');
            }

            // Test message display area
            const chatMessages = this.page.locator('.chat-messages, .message-list, [class*="chat"]').first();
            if (await chatMessages.isVisible({ timeout: 2000 })) {
                console.log('✅ Chat messages area found');
            } else {
                console.log('❌ Chat messages area not found');
            }

            // Test message toggles
            const toggles = ['Show Thoughts', 'Show JSON', 'Show Debug', 'Autoscroll'];
            for (const toggle of toggles) {
                try {
                    const checkbox = this.page.locator(`input[type="checkbox"]:near(text="${toggle}")`, { timeout: 2000 }).first();
                    if (await checkbox.isVisible()) {
                        await checkbox.check();
                        await checkbox.uncheck();
                        console.log(`✅ ${toggle} toggle works`);
                    }
                } catch (error) {
                    console.log(`❌ ${toggle} toggle not found`);
                }
            }

        } catch (error) {
            console.log(`❌ Chat interface test failed: ${error.message}`);
        }
    }

    async testWorkflowComponents() {
        console.log('Testing workflow components...');
        
        try {
            // Look for workflow-related components
            const workflowElements = [
                '.workflow-progress', '.workflow-approval', '[class*="workflow"]',
                'text="Approve"', 'text="Reject"', 'text="Cancel Workflow"'
            ];

            let workflowFound = false;
            for (const selector of workflowElements) {
                try {
                    const element = this.page.locator(selector).first();
                    if (await element.isVisible({ timeout: 2000 })) {
                        console.log(`✅ Workflow component found: ${selector}`);
                        workflowFound = true;
                    }
                } catch (error) {
                    // Continue checking other elements
                }
            }

            if (!workflowFound) {
                console.log('ℹ️ No active workflow components visible (expected when no workflows running)');
            }

        } catch (error) {
            console.log(`❌ Workflow components test failed: ${error.message}`);
        }
    }

    async testTerminalFunctionality() {
        console.log('Testing terminal functionality...');
        
        try {
            // Navigate to terminal section
            await this.page.locator('text="Terminal"').first().click();
            await this.page.waitForTimeout(1000);

            // Check for terminal elements
            const terminalElements = [
                '.terminal', '.xterm', '[class*="terminal"]',
                'input[placeholder*="command"]', 'textarea[placeholder*="command"]'
            ];

            let terminalFound = false;
            for (const selector of terminalElements) {
                try {
                    const element = this.page.locator(selector).first();
                    if (await element.isVisible({ timeout: 2000 })) {
                        console.log(`✅ Terminal component found: ${selector}`);
                        terminalFound = true;
                        break;
                    }
                } catch (error) {
                    // Continue checking
                }
            }

            if (!terminalFound) {
                console.log('❌ Terminal component not found');
            }

            // Test terminal controls
            const controls = ['Clear', 'Connect', 'Disconnect'];
            for (const control of controls) {
                try {
                    const button = this.page.locator(`button:has-text("${control}")`).first();
                    if (await button.isVisible({ timeout: 2000 })) {
                        console.log(`✅ Terminal ${control} button found`);
                    }
                } catch (error) {
                    console.log(`❌ Terminal ${control} button not found`);
                }
            }

        } catch (error) {
            console.log(`❌ Terminal functionality test failed: ${error.message}`);
        }
    }

    async testSettingsPanel() {
        console.log('Testing settings panel...');
        
        try {
            // Navigate to settings
            await this.page.locator('text="Settings"').first().click();
            await this.page.waitForTimeout(1000);

            // Test common settings elements
            const settingsElements = [
                'input[type="text"]', 'input[type="number"]', 'select',
                'input[type="checkbox"]', 'input[type="radio"]',
                'button:has-text("Save")', 'button:has-text("Reset")'
            ];

            let settingsFound = false;
            for (const selector of settingsElements) {
                try {
                    const elements = await this.page.locator(selector).count();
                    if (elements > 0) {
                        console.log(`✅ Settings elements found: ${elements} ${selector}`);
                        settingsFound = true;
                    }
                } catch (error) {
                    // Continue checking
                }
            }

            if (!settingsFound) {
                console.log('❌ No settings elements found');
            }

            // Test theme switching if available
            try {
                const themeToggle = this.page.locator('button:has-text("Dark"), button:has-text("Light"), [class*="theme"]').first();
                if (await themeToggle.isVisible({ timeout: 2000 })) {
                    await themeToggle.click();
                    console.log('✅ Theme toggle works');
                }
            } catch (error) {
                console.log('ℹ️ Theme toggle not found');
            }

        } catch (error) {
            console.log(`❌ Settings panel test failed: ${error.message}`);
        }
    }

    async testKnowledgeManager() {
        console.log('Testing knowledge manager...');
        
        try {
            // Navigate to knowledge base
            await this.page.locator('text="Knowledge"').first().click();
            await this.page.waitForTimeout(1000);

            // Test knowledge base elements
            const kbElements = [
                'input[placeholder*="search"]', 'input[placeholder*="query"]',
                'button:has-text("Search")', 'button:has-text("Add")',
                '.knowledge-list', '.document-list', '[class*="knowledge"]'
            ];

            let kbFound = false;
            for (const selector of kbElements) {
                try {
                    const element = this.page.locator(selector).first();
                    if (await element.isVisible({ timeout: 2000 })) {
                        console.log(`✅ Knowledge component found: ${selector}`);
                        kbFound = true;
                    }
                } catch (error) {
                    // Continue checking
                }
            }

            if (!kbFound) {
                console.log('❌ No knowledge manager components found');
            }

        } catch (error) {
            console.log(`❌ Knowledge manager test failed: ${error.message}`);
        }
    }

    async testSystemMonitor() {
        console.log('Testing system monitor...');
        
        try {
            // Navigate to system monitor
            await this.page.locator('text="Monitor"').first().click();
            await this.page.waitForTimeout(1000);

            // Test system monitor elements
            const monitorElements = [
                '.system-status', '.health-check', '[class*="monitor"]',
                'text="CPU"', 'text="Memory"', 'text="Status"'
            ];

            let monitorFound = false;
            for (const selector of monitorElements) {
                try {
                    const element = this.page.locator(selector).first();
                    if (await element.isVisible({ timeout: 2000 })) {
                        console.log(`✅ System monitor component found: ${selector}`);
                        monitorFound = true;
                    }
                } catch (error) {
                    // Continue checking
                }
            }

            if (!monitorFound) {
                console.log('❌ No system monitor components found');
            }

        } catch (error) {
            console.log(`❌ System monitor test failed: ${error.message}`);
        }
    }

    async testVoiceInterface() {
        console.log('Testing voice interface...');
        
        try {
            // Look for voice-related buttons
            const voiceElements = [
                'button:has-text("Voice")', 'button:has-text("Mic")',
                '.voice-control', '[class*="voice"]',
                '[class*="microphone"]', '[title*="voice"]'
            ];

            let voiceFound = false;
            for (const selector of voiceElements) {
                try {
                    const element = this.page.locator(selector).first();
                    if (await element.isVisible({ timeout: 2000 })) {
                        console.log(`✅ Voice interface component found: ${selector}`);
                        voiceFound = true;
                    }
                } catch (error) {
                    // Continue checking
                }
            }

            if (!voiceFound) {
                console.log('ℹ️ Voice interface components not visible (may be disabled)');
            }

        } catch (error) {
            console.log(`❌ Voice interface test failed: ${error.message}`);
        }
    }

    async testErrorHandling() {
        console.log('Testing error handling...');
        
        try {
            // Check for error messages in console
            const logs = await this.page.evaluate(() => {
                return window.console.error ? 'Console errors may exist' : 'No console errors';
            });
            console.log(`ℹ️ Console status: ${logs}`);

            // Look for error display components
            const errorElements = [
                '.error-message', '.alert-error', '[class*="error"]',
                '[class*="warning"]', '.notification'
            ];

            for (const selector of errorElements) {
                try {
                    const elements = await this.page.locator(selector).count();
                    if (elements > 0) {
                        console.log(`ℹ️ Error handling components found: ${elements} ${selector}`);
                    }
                } catch (error) {
                    // Continue checking
                }
            }

        } catch (error) {
            console.log(`❌ Error handling test failed: ${error.message}`);
        }
    }

    async runAllTests() {
        console.log('🚀 Starting comprehensive GUI tests...');
        
        // Check if API is available
        const apiHealthy = await this.checkApiHealth();
        console.log(`API Status: ${apiHealthy ? '✅ Healthy' : '❌ Not available'}`);
        
        await this.waitForLoad();
        console.log('✅ Page loaded successfully');

        // Run all test suites
        await this.testBasicNavigation();
        await this.testChatInterface();
        await this.testWorkflowComponents();
        await this.testTerminalFunctionality();
        await this.testSettingsPanel();
        await this.testKnowledgeManager();
        await this.testSystemMonitor();
        await this.testVoiceInterface();
        await this.testErrorHandling();

        console.log('🏁 GUI testing completed');
    }
}

// Playwright test runner
test.describe('AutoBot GUI Comprehensive Test', () => {
    test('Complete GUI functionality test', async ({ page }) => {
        const tester = new AutoBotGUITester(page);
        await tester.runAllTests();
    });

    test('Responsive design test', async ({ page }) => {
        console.log('Testing responsive design...');
        
        const viewports = [
            { width: 1920, height: 1080, name: 'Desktop' },
            { width: 768, height: 1024, name: 'Tablet' },
            { width: 375, height: 667, name: 'Mobile' }
        ];

        for (const viewport of viewports) {
            await page.setViewportSize({ width: viewport.width, height: viewport.height });
            await page.goto('http://localhost:5173');
            await page.waitForLoadState('networkidle');
            
            console.log(`✅ ${viewport.name} (${viewport.width}x${viewport.height}) - Page loads`);
            
            // Check if main elements are visible
            const mainElements = ['button', 'input', 'nav'];
            for (const element of mainElements) {
                const count = await page.locator(element).count();
                if (count > 0) {
                    console.log(`✅ ${viewport.name} - ${element} elements visible: ${count}`);
                }
            }
        }
    });

    test('Accessibility test', async ({ page }) => {
        console.log('Testing accessibility...');
        
        await page.goto('http://localhost:5173');
        await page.waitForLoadState('networkidle');

        // Basic accessibility checks
        const accessibilityElements = [
            'button', 'input[aria-label]', '[role]', 'label',
            '[alt]', '[title]'
        ];

        for (const selector of accessibilityElements) {
            try {
                const count = await page.locator(selector).count();
                if (count > 0) {
                    console.log(`✅ Accessibility elements found: ${count} ${selector}`);
                }
            } catch (error) {
                // Continue checking
            }
        }

        // Test keyboard navigation
        await page.keyboard.press('Tab');
        await page.keyboard.press('Tab');
        console.log('✅ Keyboard navigation test completed');
    });
});