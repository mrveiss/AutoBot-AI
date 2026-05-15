#!/usr/bin/env node

/**
 * Browser Error Capture Script
 * Uses Puppeteer to capture console errors and network failures
 */

const puppeteer = require('puppeteer');

async function captureBrowserErrors() {
    console.log('🔍 Starting browser error capture...\n');

    const browser = await puppeteer.launch({
        headless: false,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const page = await browser.newPage();

    // Capture console messages
    const consoleErrors = [];
    page.on('console', msg => {
        if (msg.type() === 'error') {
            const error = {
                type: 'console_error',
                text: msg.text(),
                location: msg.location(),
                timestamp: new Date().toISOString()
            };
            consoleErrors.push(error);
            console.log('❌ Console Error:', error);
        } else if (msg.type() === 'warning') {
            console.log('⚠️  Console Warning:', msg.text());
        }
    });

    // Capture page errors
    page.on('pageerror', error => {
        const pageError = {
            type: 'page_error',
            message: error.message,
            stack: error.stack,
            timestamp: new Date().toISOString()
        };
        consoleErrors.push(pageError);
        console.log('💥 Page Error:', pageError);
    });

    // Capture failed requests
    const failedRequests = [];
    page.on('requestfailed', request => {
        const failure = {
            url: request.url(),
            method: request.method(),
            error: request.failure().errorText,
            timestamp: new Date().toISOString()
        };
        failedRequests.push(failure);
        console.log('🚫 Request Failed:', failure);
    });

    // Capture slow requests
    const slowRequests = [];
    page.on('response', response => {
        const timing = response.timing();
        if (timing && timing.receiveHeadersEnd > 1000) {
            const slow = {
                url: response.url(),
                status: response.status(),
                duration: timing.receiveHeadersEnd,
                timestamp: new Date().toISOString()
            };
            slowRequests.push(slow);
            console.log('🐌 Slow Request:', slow);
        }
    });

    try {
        // Navigate to AutoBot
        console.log('📍 Navigating to http://127.0.0.3:5173...\n');
        await page.goto('http://127.0.0.3:5173', {
            waitUntil: 'networkidle2',
            timeout: 30000
        });

        console.log('✅ Page loaded successfully\n');

        // Wait a bit for any async errors
        await page.waitForTimeout(5000);

        // Try to interact with main components
        console.log('🔄 Testing main components...\n');

        // Click through tabs if they exist
        const tabs = ['Knowledge', 'Chat', 'Settings', 'Validation'];
        for (const tab of tabs) {
            try {
                const selector = `button:has-text("${tab}"), a:has-text("${tab}")`;
                await page.waitForSelector(selector, { timeout: 2000 });
                await page.click(selector);
                console.log(`✅ Clicked ${tab} tab`);
                await page.waitForTimeout(1000);
            } catch (e) {
                console.log(`ℹ️  ${tab} tab not found or not clickable`);
            }
        }

    } catch (error) {
        console.error('Navigation error:', error.message);
    }

    // Summary report
    console.log('\n📊 Error Summary:');
    console.log(`   Console Errors: ${consoleErrors.length}`);
    console.log(`   Failed Requests: ${failedRequests.length}`);
    console.log(`   Slow Requests: ${slowRequests.length}`);

    if (consoleErrors.length > 0) {
        console.log('\n❌ Console Errors Detail:');
        consoleErrors.forEach((err, i) => {
            console.log(`   ${i + 1}. ${err.text || err.message}`);
        });
    }

    if (failedRequests.length > 0) {
        console.log('\n🚫 Failed Requests Detail:');
        failedRequests.forEach((req, i) => {
            console.log(`   ${i + 1}. ${req.method} ${req.url} - ${req.error}`);
        });
    }

    // Keep browser open for manual inspection
    console.log('\n👀 Browser remains open for manual inspection...');
    console.log('Press Ctrl+C to close and exit.\n');

    // Keep the script running
    await new Promise(() => {});
}

// Run the capture
captureBrowserErrors().catch(console.error);
