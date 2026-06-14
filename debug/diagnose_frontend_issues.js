#!/usr/bin/env node
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0

/**
 * Frontend Diagnostic Script
 * Identifies specific GUI issues: settings display, chat responses, history persistence
 */

const { chromium } = require('playwright');

// Service URLs (match NetworkConstants)
const FRONTEND_URL = 'http://localhost:5173';  // NetworkConstants.FRONTEND_PORT
const BACKEND_URL = 'http://localhost:8001';   // NetworkConstants.BACKEND_PORT

async function diagnoseFrontendIssues() {
    console.log('🔍 Starting Frontend Diagnostics...\n');
    
    const browser = await chromium.launch({ 
        headless: false, // Show browser for debugging
        slowMo: 1000    // Slow down for observation
    });
    
    const page = await browser.newPage();
    
    // Enable console logging
    page.on('console', msg => {
        console.log(`🟡 BROWSER: ${msg.type()}: ${msg.text()}`);
    });
    
    // Enable error logging
    page.on('pageerror', error => {
        console.log(`🔴 PAGE ERROR: ${error.message}`);
    });
    
    try {
        // Test 1: Basic page load
        console.log('📱 TEST 1: Basic Page Load');
        await page.goto(FRONTEND_URL, { waitUntil: 'networkidle' });
        
        // Wait for Vue app to mount
        await page.waitForSelector('#app', { timeout: 10000 });
        console.log('✅ Page loaded successfully\n');
        
        // Test 2: Settings visibility
        console.log('📱 TEST 2: Settings Visibility');
        
        // Check if sidebar exists
        const sidebarExists = await page.locator('.w-80.bg-blueGray-100').isVisible();
        console.log(`Sidebar visible: ${sidebarExists}`);
        
        // Look for settings section
        const settingsSection = await page.locator('h3:has-text("Message Display")').isVisible();
        console.log(`Settings section visible: ${settingsSection}`);
        
        // Check individual settings checkboxes
        const settingsCheckboxes = await page.locator('input[type="checkbox"]').count();
        console.log(`Settings checkboxes found: ${settingsCheckboxes}`);
        
        if (settingsCheckboxes === 0) {
            console.log('❌ ISSUE: Settings checkboxes not found\n');
        } else {
            console.log('✅ Settings checkboxes are present\n');
        }
        
        // Test 3: Chat functionality
        console.log('📱 TEST 3: Chat Functionality');
        
        // Check if chat input exists
        const chatInput = await page.locator('textarea[placeholder*="Type your message"]').isVisible();
        console.log(`Chat input visible: ${chatInput}`);
        
        // Check if send button exists
        const sendButton = await page.locator('button:has-text("Send")').isVisible();
        console.log(`Send button visible: ${sendButton}`);
        
        // Test sending a message
        if (chatInput && sendButton) {
            await page.fill('textarea[placeholder*="Type your message"]', 'Hello, this is a test message');
            await page.click('button:has-text("Send")');
            
            // Wait for response (with timeout)
            try {
                await page.waitForSelector('.justify-start', { timeout: 10000 });
                console.log('✅ Chat response received');
            } catch (error) {
                console.log('❌ ISSUE: No chat response received within 10 seconds');
            }
        }
        
        console.log('');
        
        // Test 4: Chat history
        console.log('📱 TEST 4: Chat History Persistence');
        
        // Create a new chat
        const newChatButton = await page.locator('button:has-text("New")').isVisible();
        if (newChatButton) {
            await page.click('button:has-text("New")');
            console.log('✅ New chat created');
            
            // Send a message in new chat
            await page.fill('textarea[placeholder*="Type your message"]', 'Test message in new chat');
            await page.click('button:has-text("Send")');
            
            // Check if chat appears in history
            const chatHistory = await page.locator('.space-y-2 .p-3').count();
            console.log(`Chat history entries: ${chatHistory}`);
            
            if (chatHistory === 0) {
                console.log('❌ ISSUE: Chat history not showing');
            } else {
                console.log('✅ Chat history is visible');
                
                // Test navigation between chats
                const firstChatEntry = page.locator('.space-y-2 .p-3').first();
                if (await firstChatEntry.isVisible()) {
                    await firstChatEntry.click();
                    console.log('✅ Navigated to different chat');
                    
                    // Check if messages persist
                    const messages = await page.locator('.flex.justify-start, .flex.justify-end').count();
                    console.log(`Messages in chat: ${messages}`);
                    
                    if (messages === 0) {
                        console.log('❌ ISSUE: Chat messages not persisting when navigating');
                    } else {
                        console.log('✅ Chat messages persist when navigating');
                    }
                }
            }
        }
        
        console.log('');
        
        // Test 5: Backend connectivity
        console.log('📱 TEST 5: Backend Connectivity');
        
        // Check network requests
        const response = await page.evaluate(async (backendUrl) => {
            try {
                const res = await fetch(`${backendUrl}/api/system/health`);
                return {
                    status: res.status,
                    ok: res.ok,
                    text: await res.text()
                };
            } catch (error) {
                return {
                    error: error.message
                };
            }
        }, BACKEND_URL);

        if (response.ok) {
            console.log('✅ Backend connectivity working');
        } else {
            console.log('❌ ISSUE: Backend connectivity problem:', response.error || response.status);
        }
        
        console.log('');
        
        // Test 6: JavaScript errors
        console.log('📱 TEST 6: JavaScript Console Errors');
        
        const consoleErrors = [];
        page.on('console', msg => {
            if (msg.type() === 'error') {
                consoleErrors.push(msg.text());
            }
        });
        
        // Give some time for errors to appear
        await page.waitForTimeout(2000);
        
        if (consoleErrors.length > 0) {
            console.log('❌ JavaScript Errors Found:');
            consoleErrors.forEach(error => console.log(`   - ${error}`));
        } else {
            console.log('✅ No JavaScript errors detected');
        }
        
    } catch (error) {
        console.log(`❌ DIAGNOSTIC ERROR: ${error.message}`);
    } finally {
        await browser.close();
    }
    
    console.log('\n🏁 Frontend Diagnostics Complete');
}

// Run diagnostics
diagnoseFrontendIssues().catch(console.error);