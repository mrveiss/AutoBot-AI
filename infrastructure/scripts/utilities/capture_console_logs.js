/**
 * Console log capture script for Browser VM
 * Captures browser console warnings and errors from chat view
 */

const puppeteer = require('puppeteer');

async function captureConsoleLogs() {
    let browser;
    try {
        // Launch browser with proper settings
        browser = await puppeteer.launch({
            headless: false, // Show browser for debugging
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--allow-running-insecure-content'
            ]
        });

        const page = await browser.newPage();

        // Set viewport
        await page.setViewport({ width: 1920, height: 1080 });

        // Capture console messages
        const consoleMessages = [];
        page.on('console', msg => {
            const type = msg.type();
            const text = msg.text();
            const location = msg.location();

            // Only capture warnings and errors
            if (['warning', 'error'].includes(type)) {
                consoleMessages.push({
                    type,
                    text,
                    location,
                    timestamp: new Date().toISOString()
                });
                console.log(`[${type.toUpperCase()}] ${text}`);
                if (location.url) {
                    console.log(`  Location: ${location.url}:${location.lineNumber}:${location.columnNumber}`);
                }
            }
        });

        // Capture page errors
        page.on('pageerror', error => {
            consoleMessages.push({
                type: 'page-error',
                text: error.message,
                stack: error.stack,
                timestamp: new Date().toISOString()
            });
            console.log(`[PAGE ERROR] ${error.message}`);
        });

        // Navigate to chat view
        console.log('Navigating to chat view...');
        await page.goto('http://172.16.168.21:5173/chat', {
            waitUntil: 'networkidle2',
            timeout: 30000
        });

        // Wait for page to fully load
        console.log('Waiting for page to load...');
        await page.waitForTimeout(5000);

        // Try to interact with chat interface to trigger any dynamic warnings
        try {
            // Wait for chat input to appear
            await page.waitForSelector('textarea, input[type="text"]', { timeout: 10000 });
            console.log('Chat input found, clicking to trigger any warnings...');

            // Click on input to trigger any validation or interaction warnings
            await page.click('textarea, input[type="text"]');
            await page.waitForTimeout(2000);

            // Type a test message to trigger any typing-related warnings
            await page.type('textarea, input[type="text"]', 'test message');
            await page.waitForTimeout(2000);

        } catch (error) {
            console.log('Could not interact with chat input:', error.message);
        }

        // Wait a bit more for any delayed warnings
        await page.waitForTimeout(3000);

        // Output results
        console.log('\n=== CONSOLE ANALYSIS RESULTS ===');
        if (consoleMessages.length === 0) {
            console.log('✅ No console warnings or errors detected');
        } else {
            console.log(`❌ Found ${consoleMessages.length} console issues:`);
            consoleMessages.forEach((msg, index) => {
                console.log(`\n${index + 1}. [${msg.type.toUpperCase()}] ${msg.text}`);
                if (msg.location && msg.location.url) {
                    console.log(`   Source: ${msg.location.url}:${msg.location.lineNumber}`);
                }
                if (msg.stack) {
                    console.log(`   Stack: ${msg.stack.split('\n')[0]}`);
                }
            });
        }

        // Save results to file
        const fs = require('fs');
        const resultsPath = '/tmp/console_analysis_results.json';
        fs.writeFileSync(resultsPath, JSON.stringify({
            timestamp: new Date().toISOString(),
            url: 'http://172.16.168.21:5173/chat',
            totalIssues: consoleMessages.length,
            messages: consoleMessages
        }, null, 2));

        console.log(`\nResults saved to: ${resultsPath}`);

    } catch (error) {
        console.error('Browser automation failed:', error);
    } finally {
        if (browser) {
            await browser.close();
        }
    }
}

// Run the capture
captureConsoleLogs().catch(console.error);
