#!/usr/bin/env node

/**
 * Test Chat Responses and History Persistence
 */

const { chromium } = require('playwright');

async function testChatResponses() {
    console.log('🧪 Testing Chat Responses and History Persistence\n');
    
    const browser = await chromium.launch({ headless: false, slowMo: 1000 });
    const page = await browser.newPage();
    
    try {
        // Load and navigate to chat
        console.log('📱 Loading page and navigating to chat...');
        await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded' });
        await page.waitForSelector('#app');
        
        // Navigate to chat
        await page.click('a:has-text("AI Assistant")');
        await page.waitForTimeout(2000);
        console.log('✅ Navigated to chat interface');
        
        // Test 1: Send a simple message
        console.log('\n📱 Test 1: Sending a test message...');
        const chatInput = page.locator('textarea[placeholder*="Type your message"]');
        const sendButton = page.locator('button:has-text("Send")');
        
        await chatInput.fill('Hello, this is a test message. Please respond with "Test received".');
        await sendButton.click();
        console.log('✅ Message sent');
        
        // Wait for response (with timeout)
        try {
            await page.waitForSelector('.justify-start', { timeout: 15000 });
            console.log('✅ Response received');
            
            // Check message content
            const messages = await page.locator('.flex.justify-start, .flex.justify-end').count();
            console.log(`Messages visible: ${messages}`);
            
            // Get the latest response
            const lastMessage = page.locator('.justify-start').last();
            const responseVisible = await lastMessage.isVisible();
            console.log(`Latest response visible: ${responseVisible}`);
            
        } catch (error) {
            console.log('❌ No response received within timeout');
        }
        
        // Test 2: Create new chat and test navigation
        console.log('\n📱 Test 2: Testing chat history and navigation...');
        const newChatButton = page.locator('button:has-text("New")');
        const newChatExists = await newChatButton.count();
        
        if (newChatExists > 0) {
            await newChatButton.click();
            console.log('✅ Created new chat');
            
            // Send message in new chat
            await chatInput.fill('This is a message in the new chat');
            await sendButton.click();
            console.log('✅ Sent message in new chat');
            
            // Wait a bit
            await page.waitForTimeout(3000);
            
            // Check if chat appears in history
            const chatHistoryEntries = await page.locator('.space-y-2 .p-3').count();
            console.log(`Chat history entries: ${chatHistoryEntries}`);
            
            if (chatHistoryEntries > 0) {
                console.log('✅ Chat history is populated');
                
                // Click on first chat in history to test navigation
                const firstChatEntry = page.locator('.space-y-2 .p-3').first();
                await firstChatEntry.click();
                console.log('✅ Navigated to previous chat');
                
                // Check if messages persist
                await page.waitForTimeout(2000);
                const messagesAfterNavigation = await page.locator('.flex.justify-start, .flex.justify-end').count();
                console.log(`Messages after navigation: ${messagesAfterNavigation}`);
                
                if (messagesAfterNavigation > 0) {
                    console.log('✅ Chat history persists between navigation');
                } else {
                    console.log('❌ Chat messages not persisting');
                }
            } else {
                console.log('❌ Chat history not showing');
            }
        } else {
            console.log('❌ New chat button not found');
        }
        
        // Test 3: Settings functionality
        console.log('\n📱 Test 3: Testing settings functionality...');
        const settingsCheckboxes = await page.locator('input[type="checkbox"]').count();
        
        if (settingsCheckboxes > 0) {
            // Test toggling a setting
            const firstCheckbox = page.locator('input[type="checkbox"]').first();
            const initialState = await firstCheckbox.isChecked();
            
            await firstCheckbox.click();
            const newState = await firstCheckbox.isChecked();
            
            if (initialState !== newState) {
                console.log('✅ Settings are interactive');
            } else {
                console.log('❌ Settings not responding to clicks');
            }
        }
        
        // Final screenshot
        await page.screenshot({ path: '/tmp/chat_functionality_test.png', fullPage: true });
        console.log('\n📸 Final screenshot saved to /tmp/chat_functionality_test.png');
        
        console.log('\n🎉 Chat functionality testing completed');
        
    } catch (error) {
        console.log(`❌ Test error: ${error.message}`);
    } finally {
        await browser.close();
    }
}

testChatResponses().catch(console.error);