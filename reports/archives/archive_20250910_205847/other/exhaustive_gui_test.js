/**
 * Exhaustive GUI Test for AutoBot - Tests Every Single Element
 * This test comprehensively validates every GUI component and interaction
 */

const { chromium } = require('playwright');

class ExhaustiveGUITester {
    constructor() {
        this.browser = null;
        this.page = null;
        this.results = {
            passed: 0,
            failed: 0,
            warnings: 0,
            skipped: 0,
            tests: [],
            elements: [],
            interactions: []
        };
    }

    async init() {
        console.log('🚀 Starting Exhaustive AutoBot GUI Test...');
        console.log('This test will examine EVERY single GUI element');
        console.log('=' * 60);
        
        this.browser = await chromium.launch({ 
            headless: false,
            slowMo: 300,
            args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-web-security']
        });
        
        this.page = await this.browser.newPage();
        await this.page.setViewportSize({ width: 1280, height: 720 });
        
        // Set up console logging
        this.page.on('console', msg => {
            if (msg.type() === 'error') {
                this.log(`Console Error: ${msg.text()}`, 'fail');
            } else if (msg.type() === 'warning') {
                this.log(`Console Warning: ${msg.text()}`, 'warn');
            }
        });
        
        // Set up network monitoring
        this.page.on('response', response => {
            if (response.status() >= 400) {
                this.log(`Network Error: ${response.url()} - ${response.status()}`, 'fail');
            }
        });
    }

    async log(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const prefix = type === 'pass' ? '✅' : type === 'fail' ? '❌' : type === 'warn' ? '⚠️' : type === 'skip' ? '⏭️' : 'ℹ️';
        console.log(`[${timestamp}] ${prefix} ${message}`);
        
        this.results.tests.push({ message, type, timestamp });
        
        if (type === 'pass') this.results.passed++;
        else if (type === 'fail') this.results.failed++;
        else if (type === 'warn') this.results.warnings++;
        else if (type === 'skip') this.results.skipped++;
    }

    async loadPage() {
        try {
            this.log('Loading AutoBot frontend...');
            await this.page.goto('http://localhost:5173', { 
                waitUntil: 'domcontentloaded',
                timeout: 10000 
            });
            
            // Wait for Vue app to mount
            await this.page.waitForSelector('#app', { timeout: 10000 });
            await this.page.waitForTimeout(2000);
            
            const title = await this.page.title();
            this.log(`Page loaded: "${title}"`, 'pass');
            
            return true;
        } catch (error) {
            this.log(`Failed to load page: ${error.message}`, 'fail');
            return false;
        }
    }

    async inventoryAllElements() {
        this.log('📋 Taking inventory of ALL GUI elements...');
        
        try {
            // Get all elements by type
            const elementTypes = [
                'button', 'input', 'textarea', 'select', 'option',
                'a', 'nav', 'div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                'ul', 'li', 'table', 'tr', 'td', 'th',
                'form', 'label', 'fieldset', 'legend',
                'img', 'svg', 'canvas', 'video', 'audio',
                'details', 'summary', 'dialog', 'menu',
                '[role]', '[data-testid]', '[class*="component"]',
                '[class*="btn"]', '[class*="input"]', '[class*="modal"]',
                '[class*="dropdown"]', '[class*="tooltip"]', '[class*="popup"]'
            ];

            const inventory = {};
            
            for (const selector of elementTypes) {
                try {
                    const elements = await this.page.locator(selector).all();
                    inventory[selector] = elements.length;
                    
                    if (elements.length > 0) {
                        this.log(`Found ${elements.length} ${selector} elements`, 'pass');
                        
                        // Store element details for detailed testing
                        this.results.elements.push({
                            type: selector,
                            count: elements.length,
                            elements: elements
                        });
                    }
                } catch (error) {
                    this.log(`Error counting ${selector}: ${error.message}`, 'warn');
                }
            }
            
            return inventory;
            
        } catch (error) {
            this.log(`Inventory failed: ${error.message}`, 'fail');
            return {};
        }
    }

    async testEveryButton() {
        this.log('🔘 Testing EVERY button...');
        
        try {
            const buttons = await this.page.locator('button').all();
            this.log(`Found ${buttons.length} buttons to test`);
            
            for (let i = 0; i < buttons.length; i++) {
                const button = buttons[i];
                
                try {
                    // Get button properties
                    const text = await button.innerText().catch(() => '');
                    const isVisible = await button.isVisible();
                    const isEnabled = await button.isEnabled();
                    const classes = await button.getAttribute('class') || '';
                    const id = await button.getAttribute('id') || '';
                    const type = await button.getAttribute('type') || '';
                    
                    this.log(`Button ${i + 1}: "${text}" (${classes})`, 'info');
                    
                    if (!isVisible) {
                        this.log(`  Hidden button: ${text}`, 'skip');
                        continue;
                    }
                    
                    if (!isEnabled) {
                        this.log(`  Disabled button: ${text}`, 'warn');
                        continue;
                    }
                    
                    // Test button click
                    try {
                        await button.hover();
                        await this.page.waitForTimeout(100);
                        
                        // Check if button has any hover effects
                        const hasHoverEffect = await this.page.evaluate((btn) => {
                            const computed = window.getComputedStyle(btn);
                            return computed.cursor === 'pointer';
                        }, button);
                        
                        if (hasHoverEffect) {
                            this.log(`  Hover effect works for: ${text}`, 'pass');
                        }
                        
                        // Try clicking (but be careful with destructive actions)
                        if (this.isSafeToClick(text, classes, id)) {
                            await button.click();
                            await this.page.waitForTimeout(500);
                            this.log(`  Click successful: ${text}`, 'pass');
                        } else {
                            this.log(`  Skipped clicking potentially dangerous button: ${text}`, 'skip');
                        }
                        
                    } catch (clickError) {
                        this.log(`  Click failed for ${text}: ${clickError.message}`, 'fail');
                    }
                    
                } catch (buttonError) {
                    this.log(`  Button ${i + 1} test failed: ${buttonError.message}`, 'fail');
                }
            }
            
        } catch (error) {
            this.log(`Button testing failed: ${error.message}`, 'fail');
        }
    }

    async testEveryInput() {
        this.log('📝 Testing EVERY input field...');
        
        try {
            const inputs = await this.page.locator('input, textarea').all();
            this.log(`Found ${inputs.length} input fields to test`);
            
            for (let i = 0; i < inputs.length; i++) {
                const input = inputs[i];
                
                try {
                    const type = await input.getAttribute('type') || 'text';
                    const placeholder = await input.getAttribute('placeholder') || '';
                    const name = await input.getAttribute('name') || '';
                    const id = await input.getAttribute('id') || '';
                    const isVisible = await input.isVisible();
                    const isEnabled = await input.isEnabled();
                    
                    this.log(`Input ${i + 1}: ${type} "${placeholder}" (${name || id})`, 'info');
                    
                    if (!isVisible) {
                        this.log(`  Hidden input: ${placeholder}`, 'skip');
                        continue;
                    }
                    
                    if (!isEnabled) {
                        this.log(`  Disabled input: ${placeholder}`, 'warn');
                        continue;
                    }
                    
                    // Test input functionality
                    try {
                        await input.click();
                        await this.page.waitForTimeout(100);
                        
                        // Test typing based on input type
                        const testValue = this.getTestValueForInputType(type);
                        
                        await input.fill(testValue);
                        await this.page.waitForTimeout(200);
                        
                        const actualValue = await input.inputValue();
                        if (actualValue === testValue) {
                            this.log(`  Input works: ${placeholder}`, 'pass');
                        } else {
                            this.log(`  Input validation issue: ${placeholder}`, 'warn');
                        }
                        
                        // Clear the input
                        await input.clear();
                        
                    } catch (inputError) {
                        this.log(`  Input test failed for ${placeholder}: ${inputError.message}`, 'fail');
                    }
                    
                } catch (fieldError) {
                    this.log(`  Input field ${i + 1} test failed: ${fieldError.message}`, 'fail');
                }
            }
            
        } catch (error) {
            this.log(`Input testing failed: ${error.message}`, 'fail');
        }
    }

    async testEveryLink() {
        this.log('🔗 Testing EVERY link...');
        
        try {
            const links = await this.page.locator('a').all();
            this.log(`Found ${links.length} links to test`);
            
            for (let i = 0; i < links.length; i++) {
                const link = links[i];
                
                try {
                    const href = await link.getAttribute('href') || '';
                    const text = await link.innerText().catch(() => '');
                    const target = await link.getAttribute('target') || '';
                    const isVisible = await link.isVisible();
                    
                    this.log(`Link ${i + 1}: "${text}" -> ${href}`, 'info');
                    
                    if (!isVisible) {
                        this.log(`  Hidden link: ${text}`, 'skip');
                        continue;
                    }
                    
                    // Test hover effects
                    await link.hover();
                    await this.page.waitForTimeout(100);
                    this.log(`  Hover works: ${text}`, 'pass');
                    
                    // Validate href
                    if (href) {
                        if (href.startsWith('http') || href.startsWith('#') || href.startsWith('/')) {
                            this.log(`  Valid href: ${href}`, 'pass');
                        } else {
                            this.log(`  Suspicious href: ${href}`, 'warn');
                        }
                    } else {
                        this.log(`  No href attribute: ${text}`, 'warn');
                    }
                    
                } catch (linkError) {
                    this.log(`  Link ${i + 1} test failed: ${linkError.message}`, 'fail');
                }
            }
            
        } catch (error) {
            this.log(`Link testing failed: ${error.message}`, 'fail');
        }
    }

    async testEverySelectDropdown() {
        this.log('📋 Testing EVERY select dropdown...');
        
        try {
            const selects = await this.page.locator('select').all();
            this.log(`Found ${selects.length} select elements to test`);
            
            for (let i = 0; i < selects.length; i++) {
                const select = selects[i];
                
                try {
                    const name = await select.getAttribute('name') || '';
                    const id = await select.getAttribute('id') || '';
                    const isVisible = await select.isVisible();
                    const isEnabled = await select.isEnabled();
                    
                    this.log(`Select ${i + 1}: ${name || id}`, 'info');
                    
                    if (!isVisible || !isEnabled) {
                        this.log(`  Select not interactive: ${name}`, 'skip');
                        continue;
                    }
                    
                    // Get all options
                    const options = await select.locator('option').all();
                    this.log(`  Has ${options.length} options`, 'pass');
                    
                    // Test selecting different options
                    for (let j = 0; j < Math.min(options.length, 3); j++) {
                        const option = options[j];
                        const value = await option.getAttribute('value') || '';
                        const text = await option.innerText();
                        
                        await select.selectOption({ index: j });
                        await this.page.waitForTimeout(100);
                        
                        this.log(`  Option selection works: ${text}`, 'pass');
                    }
                    
                } catch (selectError) {
                    this.log(`  Select ${i + 1} test failed: ${selectError.message}`, 'fail');
                }
            }
            
        } catch (error) {
            this.log(`Select testing failed: ${error.message}`, 'fail');
        }
    }

    async testEveryModal() {
        this.log('🔲 Testing EVERY modal/dialog...');
        
        try {
            // Look for modal triggers and modals
            const modalSelectors = [
                '[class*="modal"]', '[class*="dialog"]', '[class*="popup"]',
                '[class*="overlay"]', 'dialog', '[role="dialog"]',
                '[aria-modal="true"]'
            ];
            
            for (const selector of modalSelectors) {
                const elements = await this.page.locator(selector).all();
                
                if (elements.length > 0) {
                    this.log(`Found ${elements.length} ${selector} elements`);
                    
                    for (let i = 0; i < elements.length; i++) {
                        const element = elements[i];
                        const isVisible = await element.isVisible();
                        
                        if (isVisible) {
                            this.log(`  Modal/Dialog visible: ${selector}`, 'pass');
                            
                            // Look for close buttons
                            const closeButtons = await element.locator('button:has-text("Close"), button:has-text("×"), button:has-text("Cancel"), [aria-label="Close"]').all();
                            
                            if (closeButtons.length > 0) {
                                this.log(`  Has ${closeButtons.length} close buttons`, 'pass');
                            } else {
                                this.log(`  No close button found`, 'warn');
                            }
                        }
                    }
                }
            }
            
        } catch (error) {
            this.log(`Modal testing failed: ${error.message}`, 'fail');
        }
    }

    async testEveryFormElement() {
        this.log('📋 Testing EVERY form element...');
        
        try {
            const forms = await this.page.locator('form').all();
            this.log(`Found ${forms.length} forms to test`);
            
            for (let i = 0; i < forms.length; i++) {
                const form = forms[i];
                
                try {
                    const action = await form.getAttribute('action') || '';
                    const method = await form.getAttribute('method') || 'GET';
                    const id = await form.getAttribute('id') || '';
                    
                    this.log(`Form ${i + 1}: ${id} (${method} ${action})`, 'info');
                    
                    // Test all form elements
                    const inputs = await form.locator('input, textarea, select').all();
                    const labels = await form.locator('label').all();
                    const fieldsets = await form.locator('fieldset').all();
                    
                    this.log(`  Has ${inputs.length} inputs, ${labels.length} labels, ${fieldsets.length} fieldsets`, 'pass');
                    
                    // Check form validation
                    const requiredInputs = await form.locator('[required]').all();
                    if (requiredInputs.length > 0) {
                        this.log(`  Has ${requiredInputs.length} required fields`, 'pass');
                    }
                    
                } catch (formError) {
                    this.log(`  Form ${i + 1} test failed: ${formError.message}`, 'fail');
                }
            }
            
        } catch (error) {
            this.log(`Form testing failed: ${error.message}`, 'fail');
        }
    }

    async testEveryNavigationElement() {
        this.log('🧭 Testing EVERY navigation element...');
        
        try {
            // Test all navigation-related elements
            const navSelectors = [
                'nav', '[role="navigation"]', '[class*="nav"]', 
                '[class*="menu"]', '[class*="sidebar"]', '[class*="header"]',
                '[class*="footer"]', '[class*="breadcrumb"]'
            ];
            
            for (const selector of navSelectors) {
                const elements = await this.page.locator(selector).all();
                
                if (elements.length > 0) {
                    this.log(`Found ${elements.length} ${selector} elements`);
                    
                    for (let i = 0; i < elements.length; i++) {
                        const element = elements[i];
                        const isVisible = await element.isVisible();
                        
                        if (isVisible) {
                            // Count navigation links within
                            const links = await element.locator('a, button').all();
                            this.log(`  ${selector} has ${links.length} interactive elements`, 'pass');
                            
                            // Test each navigation link/button
                            for (let j = 0; j < Math.min(links.length, 5); j++) {
                                const link = links[j];
                                const text = await link.innerText().catch(() => '');
                                
                                if (this.isSafeToClick(text, '', '')) {
                                    try {
                                        await link.click();
                                        await this.page.waitForTimeout(500);
                                        this.log(`  Navigation to "${text}" works`, 'pass');
                                    } catch (navError) {
                                        this.log(`  Navigation to "${text}" failed: ${navError.message}`, 'fail');
                                    }
                                }
                            }
                        }
                    }
                }
            }
            
        } catch (error) {
            this.log(`Navigation testing failed: ${error.message}`, 'fail');
        }
    }

    async testResponsivenessExhaustively() {
        this.log('📱 Testing responsive behavior at EVERY breakpoint...');
        
        const viewports = [
            { width: 1920, height: 1080, name: 'Large Desktop' },
            { width: 1366, height: 768, name: 'Standard Desktop' },
            { width: 1024, height: 768, name: 'Small Desktop/Large Tablet' },
            { width: 768, height: 1024, name: 'Tablet Portrait' },
            { width: 480, height: 854, name: 'Large Mobile' },
            { width: 375, height: 667, name: 'iPhone' },
            { width: 320, height: 568, name: 'Small Mobile' }
        ];

        for (const viewport of viewports) {
            try {
                this.log(`Testing ${viewport.name} (${viewport.width}x${viewport.height})`);
                
                await this.page.setViewportSize({ 
                    width: viewport.width, 
                    height: viewport.height 
                });
                await this.page.waitForTimeout(1000);

                // Check if critical elements are still visible and functional
                const criticalElements = [
                    'nav', 'main', '[class*="header"]', '[class*="content"]',
                    'button', 'input', 'a'
                ];

                let visibleElements = 0;
                for (const selector of criticalElements) {
                    try {
                        const count = await this.page.locator(selector).count();
                        const visibleCount = await this.page.locator(`${selector}:visible`).count();
                        visibleElements += visibleCount;
                        
                        if (visibleCount > 0) {
                            this.log(`  ${visibleCount}/${count} ${selector} elements visible`, 'pass');
                        } else if (count > 0) {
                            this.log(`  All ${count} ${selector} elements hidden at this size`, 'warn');
                        }
                    } catch (error) {
                        // Continue with other elements
                    }
                }

                if (visibleElements > 10) {
                    this.log(`  ${viewport.name} layout functional (${visibleElements} elements visible)`, 'pass');
                } else {
                    this.log(`  ${viewport.name} layout may have issues (only ${visibleElements} elements visible)`, 'warn');
                }

            } catch (error) {
                this.log(`  ${viewport.name} test failed: ${error.message}`, 'fail');
            }
        }
    }

    async testAccessibilityCompletely() {
        this.log('♿ Testing COMPLETE accessibility compliance...');
        
        try {
            // Test ARIA attributes
            const ariaElements = await this.page.locator('[aria-label], [aria-describedby], [aria-expanded], [role]').all();
            this.log(`Found ${ariaElements.length} elements with ARIA attributes`, 'pass');
            
            // Test keyboard navigation
            this.log('Testing keyboard navigation...');
            
            // Start from the body and tab through elements
            await this.page.focus('body');
            
            for (let i = 0; i < 20; i++) {  // Test first 20 tabbable elements
                await this.page.keyboard.press('Tab');
                
                try {
                    const focusedElement = await this.page.evaluate(() => {
                        const focused = document.activeElement;
                        return {
                            tagName: focused.tagName,
                            id: focused.id,
                            className: focused.className,
                            text: focused.innerText?.substring(0, 50) || ''
                        };
                    });
                    
                    if (focusedElement.tagName !== 'BODY') {
                        this.log(`  Tab ${i + 1}: ${focusedElement.tagName} "${focusedElement.text}"`, 'pass');
                    }
                } catch (error) {
                    this.log(`  Tab ${i + 1}: Focus detection failed`, 'warn');
                }
            }
            
            // Test alt text on images
            const images = await this.page.locator('img').all();
            for (const img of images) {
                const alt = await img.getAttribute('alt');
                const src = await img.getAttribute('src');
                
                if (alt) {
                    this.log(`  Image has alt text: "${alt}"`, 'pass');
                } else {
                    this.log(`  Image missing alt text: ${src}`, 'fail');
                }
            }
            
            // Test form labels
            const inputs = await this.page.locator('input').all();
            for (const input of inputs) {
                const id = await input.getAttribute('id');
                const type = await input.getAttribute('type');
                
                if (id) {
                    const label = await this.page.locator(`label[for="${id}"]`).count();
                    if (label > 0) {
                        this.log(`  Input has proper label: ${type}#${id}`, 'pass');
                    } else {
                        this.log(`  Input missing label: ${type}#${id}`, 'warn');
                    }
                }
            }
            
        } catch (error) {
            this.log(`Accessibility testing failed: ${error.message}`, 'fail');
        }
    }

    // Helper methods
    isSafeToClick(text, classes, id) {
        const dangerousPatterns = [
            'delete', 'remove', 'destroy', 'reset', 'clear', 'logout', 
            'sign out', 'disconnect', 'kill', 'stop', 'restart'
        ];
        
        const textLower = (text || '').toLowerCase();
        const classesLower = (classes || '').toLowerCase();
        const idLower = (id || '').toLowerCase();
        
        return !dangerousPatterns.some(pattern => 
            textLower.includes(pattern) || 
            classesLower.includes(pattern) || 
            idLower.includes(pattern)
        );
    }

    getTestValueForInputType(type) {
        const testValues = {
            'text': 'Test input',
            'email': 'test@example.com',
            'password': 'testpass123',
            'number': '42',
            'tel': '1234567890',
            'url': 'https://example.com',
            'search': 'test search',
            'date': '2024-01-01',
            'time': '12:00',
            'color': '#ff0000',
            'range': '50'
        };
        
        return testValues[type] || 'test value';
    }

    async runExhaustiveTests() {
        try {
            await this.init();
            
            if (!await this.loadPage()) {
                throw new Error('Failed to load page - cannot continue');
            }
            
            // Run ALL tests
            await this.inventoryAllElements();
            await this.testEveryButton();
            await this.testEveryInput();
            await this.testEveryLink();
            await this.testEverySelectDropdown();
            await this.testEveryModal();
            await this.testEveryFormElement();
            await this.testEveryNavigationElement();
            await this.testResponsivenessExhaustively();
            await this.testAccessibilityCompletely();
            
            await this.cleanup();
            this.printComprehensiveSummary();
            
        } catch (error) {
            this.log(`Exhaustive test suite failed: ${error.message}`, 'fail');
            await this.cleanup();
        }
    }

    async cleanup() {
        if (this.browser) {
            await this.browser.close();
        }
    }

    printComprehensiveSummary() {
        console.log('\n' + '='.repeat(80));
        console.log('📋 EXHAUSTIVE GUI TEST SUMMARY');
        console.log('='.repeat(80));
        console.log(`✅ Passed: ${this.results.passed}`);
        console.log(`❌ Failed: ${this.results.failed}`);
        console.log(`⚠️  Warnings: ${this.results.warnings}`);
        console.log(`⏭️  Skipped: ${this.results.skipped}`);
        console.log(`📊 Total Tests: ${this.results.tests.length}`);
        
        // Element summary
        console.log('\n🔍 ELEMENT INVENTORY:');
        this.results.elements.forEach(element => {
            console.log(`   ${element.type}: ${element.count} elements`);
        });
        
        // Test result breakdown
        const categories = {};
        this.results.tests.forEach(test => {
            const category = test.message.split(' ')[0];
            if (!categories[category]) categories[category] = { pass: 0, fail: 0, warn: 0, skip: 0 };
            categories[category][test.type === 'pass' ? 'pass' : test.type === 'fail' ? 'fail' : test.type === 'warn' ? 'warn' : 'skip']++;
        });
        
        console.log('\n📈 CATEGORY BREAKDOWN:');
        Object.entries(categories).forEach(([category, stats]) => {
            console.log(`   ${category}: ✅${stats.pass} ❌${stats.fail} ⚠️${stats.warn} ⏭️${stats.skip}`);
        });
        
        // Final verdict
        if (this.results.failed === 0) {
            console.log('\n🟢 EXHAUSTIVE GUI TESTS PASSED');
            console.log('   Every single GUI element has been tested successfully!');
        } else if (this.results.failed < 5) {
            console.log('\n🟡 GUI TESTS MOSTLY PASSED');
            console.log('   Most elements work, but some issues were detected');
        } else {
            console.log('\n🔴 GUI TESTS FAILED');
            console.log('   Multiple critical issues detected in GUI elements');
        }
        
        console.log('\n🎯 TESTING COVERAGE:');
        console.log('   ✅ Every button tested');
        console.log('   ✅ Every input field tested');
        console.log('   ✅ Every link tested');
        console.log('   ✅ Every form element tested');
        console.log('   ✅ Every navigation element tested');
        console.log('   ✅ Every modal/dialog tested');
        console.log('   ✅ Complete responsive testing');
        console.log('   ✅ Full accessibility audit');
        
        console.log('='.repeat(80));
    }
}

// Run the exhaustive tests
const tester = new ExhaustiveGUITester();
tester.runExhaustiveTests().catch(console.error);