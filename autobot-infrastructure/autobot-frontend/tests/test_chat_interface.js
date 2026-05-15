#!/usr/bin/env node

/**
 * Test Chat Interface - Navigate to chat and test functionality
 */

const { chromium } = require('playwright');

async function testChatInterface() {
    console.log('🧪 Testing Chat Interface Navigation and Functionality\n');

    const browser = await chromium.launch({ headless: false, slowMo: 1000 });
    const page = await browser.newPage();

    try {
        // Load the page
        console.log('📱 Loading page...');
        await page.goto('http://localhost:5173', {
            waitUntil: 'domcontentloaded',
            timeout: 15000
        });

        await page.waitForSelector('#app', { timeout: 5000 });
        console.log('✅ Page loaded successfully');

        // Check if we're on dashboard
        const isDashboard = await page.locator('h6:has-text("System Overview")').isVisible();
        console.log(`Current view: ${isDashboard ? 'Dashboard' : 'Other'}`);

        // Navigate to chat interface
        console.log('\n📱 Navigating to Chat Interface...');
        const chatNavButton = page.locator('a:has-text("AI Assistant")');
        const chatNavExists = await chatNavButton.count();
        console.log(`Chat nav button count: ${chatNavExists}`);

        if (chatNavExists > 0) {
            await chatNavButton.first().click();
            console.log('✅ Clicked AI Assistant button');

            // Wait for chat interface to load
            await page.waitForTimeout(2000);

            // Now test chat interface elements
            console.log('\n📱 Testing Chat Interface Elements...');

            const testResults = {};

            // Test sidebar visibility
            const sidebar = page.locator('.w-80.bg-blueGray-100');
            testResults.sidebarVisible = await sidebar.count() > 0;
            console.log(`Sidebar visible: ${testResults.sidebarVisible}`);

            // Test settings checkboxes
            const checkboxCount = await page.locator('input[type="checkbox"]').count();
            testResults.settingsCheckboxes = checkboxCount;
            console.log(`Settings checkboxes found: ${checkboxCount}`);

            // Test chat input
            const chatInput = page.locator('textarea[placeholder*="Type your message"]');
            testResults.chatInputVisible = await chatInput.isVisible();
            console.log(`Chat input visible: ${testResults.chatInputVisible}`);

            // Test send button
            const sendButton = page.locator('button:has-text("Send")');
            testResults.sendButtonVisible = await sendButton.isVisible();
            console.log(`Send button visible: ${testResults.sendButtonVisible}`);

            // Test tab switching
            const terminalTab = page.locator('button:has-text("Terminal")');
            const chatTab = page.locator('button:has-text("Chat")');
            testResults.tabsVisible = (await terminalTab.count() > 0) && (await chatTab.count() > 0);
            console.log(`Chat/Terminal tabs visible: ${testResults.tabsVisible}`);

            // Test chat history area
            const chatHistory = page.locator('h3:has-text("Chat History")');
            testResults.chatHistoryVisible = await chatHistory.isVisible();
            console.log(`Chat history section visible: ${testResults.chatHistoryVisible}`);

            // Take screenshot for verification
            await page.screenshot({ path: '/tmp/chat_interface.png', fullPage: true });
            console.log('📸 Screenshot saved to /tmp/chat_interface.png');

            // Summary
            console.log('\n📊 CHAT INTERFACE TEST RESULTS');
            console.log('='.repeat(40));
            Object.entries(testResults).forEach(([test, result]) => {
                console.log(`${result ? '✅' : '❌'} ${test}: ${result}`);
            });

            const passed = Object.values(testResults).filter(r => r === true || (typeof r === 'number' && r > 0)).length;
            const total = Object.keys(testResults).length;

            console.log(`\n🎯 Score: ${passed}/${total} tests passed`);

            return passed === total;

        } else {
            console.log('❌ Chat navigation button not found');
            return false;
        }

    } catch (error) {
        console.log(`❌ Test error: ${error.message}`);
        return false;
    } finally {
        await browser.close();
    }
}

testChatInterface().catch(console.error);
