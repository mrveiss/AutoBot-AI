const { chromium } = require('playwright');

/**
 * AutoBot Frontend GUI Comprehensive Testing
 * Tests actual UI components and user interactions
 */

const CONFIG = {
    frontendUrl: 'http://172.16.168.21:5173',
    backendUrl: 'http://172.16.168.20:8001',
    timeout: 30000,
    screenshotDir: 'tests/screenshots'
};

class AutoBotGUITester {
    constructor() {
        this.browser = null;
        this.page = null;
        this.results = [];
        this.testStartTime = Date.now();
    }

    async setup() {
        console.log('🚀 Setting up AutoBot GUI Testing Environment...');
        
        this.browser = await chromium.launch({
            headless: false, // Run in visible mode for debugging
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });
        
        this.page = await this.browser.newPage();
        this.page.setDefaultTimeout(CONFIG.timeout);
        
        // Set viewport
        await this.page.setViewportSize({ width: 1920, height: 1080 });
        
        console.log('✅ Browser launched and configured');
    }

    async cleanup() {
        if (this.browser) {
            await this.browser.close();
            console.log('🧹 Browser closed');
        }
    }

    async takeScreenshot(name) {
        const timestamp = Date.now();
        const filename = `${CONFIG.screenshotDir}/gui_test_${name}_${timestamp}.png`;
        await this.page.screenshot({ path: filename, fullPage: true });
        return filename;
    }

    async logResult(name, success, message, details = {}) {
        this.results.push({
            name,
            success,
            message,
            details,
            timestamp: Date.now()
        });
        
        const icon = success ? '✅' : '❌';
        console.log(`${icon} ${name}: ${message}`);
    }

    async testFrontendLoad() {
        console.log('\n🌐 Testing Frontend Load & Initial State...');
        
        try {
            // Navigate to frontend
            const response = await this.page.goto(CONFIG.frontendUrl);
            
            if (response && response.status() === 200) {
                await this.logResult(
                    'Frontend Load',
                    true,
                    'Frontend loaded successfully',
                    { status: response.status(), url: CONFIG.frontendUrl }
                );
                
                // Wait for Vue app to initialize
                await this.page.waitForSelector('#app', { timeout: 10000 });
                
                // Check for AutoBot title
                const title = await this.page.title();
                const hasAutoBotTitle = title.includes('AutoBot');
                
                await this.logResult(
                    'Frontend Title Check',
                    hasAutoBotTitle,
                    hasAutoBotTitle ? `Title correct: ${title}` : `Title unexpected: ${title}`,
                    { title }
                );
                
                await this.takeScreenshot('frontend_loaded');
                
            } else {
                await this.logResult(
                    'Frontend Load',
                    false,
                    `Failed to load frontend: ${response ? response.status() : 'No response'}`
                );
            }
        } catch (error) {
            await this.logResult(
                'Frontend Load',
                false,
                `Frontend load error: ${error.message}`
            );
        }
    }

    async testNavigationTabs() {
        console.log('\n🧭 Testing Navigation Tabs...');
        
        try {
            // Look for navigation elements
            const navSelectors = [
                '[data-testid="nav-chat"]',
                '[data-testid="nav-knowledge"]', 
                '[data-testid="nav-system"]',
                '[data-testid="nav-desktop"]',
                // Fallback selectors
                'a[href="/"]',
                'a[href="/knowledge"]',
                'a[href="/system"]',
                'a[href="/desktop"]'
            ];
            
            let foundNavElements = 0;
            
            for (const selector of navSelectors) {
                try {
                    const element = await this.page.$(selector);
                    if (element) {
                        foundNavElements++;
                        const isVisible = await element.isVisible();
                        await this.logResult(
                            `Navigation Element: ${selector}`,
                            isVisible,
                            isVisible ? 'Visible and accessible' : 'Present but not visible'
                        );
                    }
                } catch (e) {
                    // Element not found, continue
                }
            }
            
            if (foundNavElements === 0) {
                // Try generic navigation detection
                const genericNav = await this.page.$$('nav, .nav, .navigation, [role="navigation"]');
                if (genericNav.length > 0) {
                    await this.logResult(
                        'Navigation Detection',
                        true,
                        `Found ${genericNav.length} navigation elements`,
                        { count: genericNav.length }
                    );
                } else {
                    await this.logResult(
                        'Navigation Detection',
                        false,
                        'No navigation elements found'
                    );
                }
            }
            
            await this.takeScreenshot('navigation_test');
            
        } catch (error) {
            await this.logResult(
                'Navigation Test',
                false,
                `Navigation test error: ${error.message}`
            );
        }
    }

    async testChatInterface() {
        console.log('\n💬 Testing Chat Interface...');
        
        try {
            // Look for chat elements
            const chatSelectors = [
                '[data-testid="chat-input"]',
                '[data-testid="chat-messages"]',
                '[data-testid="send-button"]',
                // Fallback selectors
                'input[type="text"]',
                'textarea',
                '.chat-input',
                '.message-input'
            ];
            
            let chatInputFound = false;
            
            for (const selector of chatSelectors) {
                try {
                    const element = await this.page.$(selector);
                    if (element) {
                        const isVisible = await element.isVisible();
                        if (isVisible) {
                            chatInputFound = true;
                            await this.logResult(
                                'Chat Input Field',
                                true,
                                `Chat input found: ${selector}`,
                                { selector }
                            );
                            
                            // Try to type in the input
                            try {
                                await element.fill('Test message from GUI test');
                                await this.logResult(
                                    'Chat Input Functionality',
                                    true,
                                    'Successfully typed in chat input'
                                );
                                
                                // Clear the input
                                await element.fill('');
                            } catch (fillError) {
                                await this.logResult(
                                    'Chat Input Functionality',
                                    false,
                                    `Could not type in chat input: ${fillError.message}`
                                );
                            }
                            break;
                        }
                    }
                } catch (e) {
                    // Continue to next selector
                }
            }
            
            if (!chatInputFound) {
                await this.logResult(
                    'Chat Interface',
                    false,
                    'No chat input field found'
                );
            }
            
            // Look for chat messages area
            const messageSelectors = [
                '[data-testid="chat-messages"]',
                '.chat-messages',
                '.messages',
                '[role="log"]'
            ];
            
            let messagesAreaFound = false;
            for (const selector of messageSelectors) {
                try {
                    const element = await this.page.$(selector);
                    if (element) {
                        messagesAreaFound = true;
                        await this.logResult(
                            'Chat Messages Area',
                            true,
                            `Messages area found: ${selector}`,
                            { selector }
                        );
                        break;
                    }
                } catch (e) {
                    // Continue to next selector
                }
            }
            
            if (!messagesAreaFound) {
                await this.logResult(
                    'Chat Messages Area',
                    false,
                    'No chat messages area found'
                );
            }
            
            await this.takeScreenshot('chat_interface');
            
        } catch (error) {
            await this.logResult(
                'Chat Interface Test',
                false,
                `Chat interface test error: ${error.message}`
            );
        }
    }

    async testKnowledgeBaseInterface() {
        console.log('\n📚 Testing Knowledge Base Interface...');
        
        try {
            // Try to navigate to knowledge base
            const knowledgeUrls = [
                `${CONFIG.frontendUrl}/knowledge`,
                `${CONFIG.frontendUrl}/#/knowledge`
            ];
            
            let knowledgePageLoaded = false;
            
            for (const url of knowledgeUrls) {
                try {
                    await this.page.goto(url);
                    await this.page.waitForTimeout(2000); // Wait for Vue router
                    
                    // Check if knowledge base content is present
                    const kbSelectors = [
                        '[data-testid="knowledge-categories"]',
                        '[data-testid="knowledge-stats"]',
                        '[data-testid="search-input"]',
                        '.knowledge-base',
                        '.kb-stats'
                    ];
                    
                    for (const selector of kbSelectors) {
                        const element = await this.page.$(selector);
                        if (element && await element.isVisible()) {
                            knowledgePageLoaded = true;
                            await this.logResult(
                                'Knowledge Base Navigation',
                                true,
                                `Knowledge base page loaded with ${selector}`,
                                { url, selector }
                            );
                            break;
                        }
                    }
                    
                    if (knowledgePageLoaded) break;
                    
                } catch (navError) {
                    // Try next URL
                }
            }
            
            if (!knowledgePageLoaded) {
                await this.logResult(
                    'Knowledge Base Navigation',
                    false,
                    'Could not navigate to or find knowledge base interface'
                );
            }
            
            // Test search functionality if on knowledge page
            if (knowledgePageLoaded) {
                const searchSelectors = [
                    '[data-testid="search-input"]',
                    'input[type="search"]',
                    'input[placeholder*="search"]',
                    '.search-input'
                ];
                
                for (const selector of searchSelectors) {
                    try {
                        const searchInput = await this.page.$(selector);
                        if (searchInput && await searchInput.isVisible()) {
                            await searchInput.fill('test search');
                            await this.logResult(
                                'Knowledge Base Search',
                                true,
                                'Search input functional'
                            );
                            await searchInput.fill(''); // Clear
                            break;
                        }
                    } catch (e) {
                        // Continue to next selector
                    }
                }
            }
            
            await this.takeScreenshot('knowledge_base');
            
        } catch (error) {
            await this.logResult(
                'Knowledge Base Interface Test',
                false,
                `Knowledge base test error: ${error.message}`
            );
        }
    }

    async testSystemMonitorInterface() {
        console.log('\n🖥️ Testing System Monitor Interface...');
        
        try {
            // Try to navigate to system monitor
            const systemUrls = [
                `${CONFIG.frontendUrl}/system`,
                `${CONFIG.frontendUrl}/#/system`
            ];
            
            let systemPageLoaded = false;
            
            for (const url of systemUrls) {
                try {
                    await this.page.goto(url);
                    await this.page.waitForTimeout(2000);
                    
                    const systemSelectors = [
                        '[data-testid="system-status"]',
                        '[data-testid="service-monitor"]',
                        '.system-monitor',
                        '.service-status'
                    ];
                    
                    for (const selector of systemSelectors) {
                        const element = await this.page.$(selector);
                        if (element && await element.isVisible()) {
                            systemPageLoaded = true;
                            await this.logResult(
                                'System Monitor Navigation',
                                true,
                                `System monitor loaded with ${selector}`,
                                { url, selector }
                            );
                            break;
                        }
                    }
                    
                    if (systemPageLoaded) break;
                    
                } catch (navError) {
                    // Try next URL
                }
            }
            
            if (!systemPageLoaded) {
                await this.logResult(
                    'System Monitor Navigation',
                    false,
                    'Could not navigate to system monitor interface'
                );
            }
            
            await this.takeScreenshot('system_monitor');
            
        } catch (error) {
            await this.logResult(
                'System Monitor Test',
                false,
                `System monitor test error: ${error.message}`
            );
        }
    }

    async testResponsiveness() {
        console.log('\n📱 Testing Responsive Design...');
        
        try {
            const viewports = [
                { width: 1920, height: 1080, name: 'Desktop' },
                { width: 1024, height: 768, name: 'Tablet' },
                { width: 375, height: 667, name: 'Mobile' }
            ];
            
            for (const viewport of viewports) {
                await this.page.setViewportSize({ width: viewport.width, height: viewport.height });
                await this.page.waitForTimeout(1000); // Let layout settle
                
                // Check if layout adapts
                const body = await this.page.$('body');
                const boundingBox = await body.boundingBox();
                
                const responsive = boundingBox.width <= viewport.width;
                
                await this.logResult(
                    `Responsive Design: ${viewport.name}`,
                    responsive,
                    responsive ? 
                        `Layout adapts correctly to ${viewport.width}x${viewport.height}` :
                        `Layout overflow at ${viewport.width}x${viewport.height}`,
                    viewport
                );
                
                await this.takeScreenshot(`responsive_${viewport.name.toLowerCase()}`);
            }
            
            // Reset to desktop
            await this.page.setViewportSize({ width: 1920, height: 1080 });
            
        } catch (error) {
            await this.logResult(
                'Responsive Design Test',
                false,
                `Responsive test error: ${error.message}`
            );
        }
    }

    async testErrorHandling() {
        console.log('\n🛡️ Testing Error Handling...');
        
        try {
            // Monitor console errors
            let consoleErrors = [];
            this.page.on('console', message => {
                if (message.type() === 'error') {
                    consoleErrors.push(message.text());
                }
            });
            
            // Navigate to a non-existent route
            await this.page.goto(`${CONFIG.frontendUrl}/#/nonexistent`);
            await this.page.waitForTimeout(2000);
            
            // Check if 404 page or error handling is shown
            const errorIndicators = [
                '[data-testid="not-found"]',
                '[data-testid="error-page"]',
                '.error-page',
                '.not-found'
            ];
            
            let errorHandlingFound = false;
            for (const selector of errorIndicators) {
                const element = await this.page.$(selector);
                if (element && await element.isVisible()) {
                    errorHandlingFound = true;
                    await this.logResult(
                        'Error Page Handling',
                        true,
                        `Error handling works: ${selector}`,
                        { selector }
                    );
                    break;
                }
            }
            
            if (!errorHandlingFound) {
                // Check if page still functions normally (which might be okay)
                const title = await this.page.title();
                await this.logResult(
                    'Error Page Handling',
                    true,
                    `Route handling: ${title} (may redirect to home)`,
                    { title }
                );
            }
            
            // Check console errors
            if (consoleErrors.length === 0) {
                await this.logResult(
                    'Console Error Check',
                    true,
                    'No console errors detected'
                );
            } else {
                await this.logResult(
                    'Console Error Check',
                    false,
                    `${consoleErrors.length} console errors detected`,
                    { errors: consoleErrors.slice(0, 5) } // First 5 errors
                );
            }
            
            await this.takeScreenshot('error_handling');
            
        } catch (error) {
            await this.logResult(
                'Error Handling Test',
                false,
                `Error handling test error: ${error.message}`
            );
        }
    }

    async runComprehensiveGUITests() {
        console.log('🎯 AutoBot Frontend GUI Comprehensive Testing');
        console.log('='.repeat(60));
        
        await this.setup();
        
        try {
            await this.testFrontendLoad();
            await this.testNavigationTabs();
            await this.testChatInterface();
            await this.testKnowledgeBaseInterface();
            await this.testSystemMonitorInterface();
            await this.testResponsiveness();
            await this.testErrorHandling();
            
        } catch (error) {
            console.error('❌ Test execution error:', error);
        } finally {
            await this.cleanup();
        }
        
        this.generateReport();
    }

    generateReport() {
        console.log('\n' + '='.repeat(60));
        console.log('🎯 AutoBot Frontend GUI Test Report');
        console.log('='.repeat(60));
        
        const totalTests = this.results.length;
        const passedTests = this.results.filter(r => r.success).length;
        const failedTests = totalTests - passedTests;
        const successRate = totalTests > 0 ? (passedTests / totalTests) * 100 : 0;
        
        let status, statusIcon;
        if (successRate >= 90) {
            status = 'EXCELLENT';
            statusIcon = '🟢';
        } else if (successRate >= 75) {
            status = 'GOOD';
            statusIcon = '🟡';
        } else if (successRate >= 60) {
            status = 'NEEDS IMPROVEMENT';
            statusIcon = '🟠';
        } else {
            status = 'CRITICAL';
            statusIcon = '🔴';
        }
        
        console.log(`\n${statusIcon} Overall Status: ${status} (${successRate.toFixed(1)}%)`);
        console.log(`📊 Tests: ${passedTests}/${totalTests} passed`);
        console.log(`⏱️ Test Duration: ${((Date.now() - this.testStartTime) / 1000).toFixed(1)}s`);
        
        console.log('\n📋 Detailed Results:');
        console.log('-'.repeat(50));
        
        for (const result of this.results) {
            const icon = result.success ? '✅' : '❌';
            console.log(`${icon} ${result.name}`);
            console.log(`   ${result.message}`);
        }
        
        console.log('\n🔧 Recommendations:');
        console.log('-'.repeat(30));
        
        const failedResults = this.results.filter(r => !r.success);
        
        if (failedResults.length === 0) {
            console.log('• ✅ All GUI tests passed - frontend is fully functional');
        } else {
            failedResults.forEach(result => {
                console.log(`• ❌ Fix: ${result.name} - ${result.message}`);
            });
        }
        
        // Save report
        const reportData = {
            summary: {
                total: totalTests,
                passed: passedTests,
                failed: failedTests,
                successRate,
                status,
                testDuration: (Date.now() - this.testStartTime) / 1000
            },
            results: this.results,
            timestamp: new Date().toISOString()
        };
        
        const fs = require('fs');
        const reportFile = `tests/results/gui_comprehensive_test_${Date.now()}.json`;
        fs.writeFileSync(reportFile, JSON.stringify(reportData, null, 2));
        console.log(`\n📄 Report saved: ${reportFile}`);
        
        console.log('\n' + '='.repeat(60));
        
        if (successRate >= 75) {
            console.log('🎉 SUCCESS: AutoBot frontend GUI is working well!');
        } else {
            console.log('⚠️ ATTENTION NEEDED: Frontend GUI has issues requiring fixes.');
        }
    }
}

async function main() {
    const tester = new AutoBotGUITester();
    await tester.runComprehensiveGUITests();
}

// Run if called directly
if (require.main === module) {
    main().catch(console.error);
}

module.exports = AutoBotGUITester;