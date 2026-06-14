#!/usr/bin/env node
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0

/**
 * Debug Frontend Rendering - Capture console errors and component state
 */

const { chromium } = require('playwright');

// Frontend URL (matches NetworkConstants.FRONTEND_PORT)
const FRONTEND_URL = 'http://localhost:5173';

async function debugRendering() {
    console.log('🔍 Debugging Frontend Rendering Issues\n');
    
    const browser = await chromium.launch({ headless: false, slowMo: 500 });
    const page = await browser.newPage();
    
    const consoleMessages = [];
    const errors = [];
    
    // Capture console messages
    page.on('console', msg => {
        const text = msg.text();
        consoleMessages.push({ type: msg.type(), text });
        console.log(`🟡 CONSOLE [${msg.type()}]: ${text}`);
    });
    
    // Capture page errors  
    page.on('pageerror', error => {
        errors.push(error.message);
        console.log(`🔴 PAGE ERROR: ${error.message}`);
    });
    
    // Capture network failures
    page.on('requestfailed', request => {
        console.log(`🔴 NETWORK FAIL: ${request.url()} - ${request.failure()?.errorText}`);
    });
    
    try {
        console.log('📱 Loading page...');
        await page.goto(FRONTEND_URL, { 
            waitUntil: 'domcontentloaded',
            timeout: 15000 
        });
        
        // Wait for Vue app to mount
        await page.waitForSelector('#app', { timeout: 5000 });
        console.log('✅ App div found\n');
        
        // Check app content
        const appContent = await page.locator('#app').innerHTML();
        console.log(`📋 App content length: ${appContent.length} characters`);
        
        if (appContent.length < 100) {
            console.log('❌ App appears to be empty or not rendered');
            console.log('App content:', appContent);
        } else {
            console.log('✅ App has content');
        }
        
        // Check for specific components
        const components = {
            sidebar: '.w-80.bg-blueGray-100',
            chatMessages: '.flex-1.overflow-y-auto',
            chatInput: 'textarea[placeholder*="Type your message"]',
            settingsCheckboxes: 'input[type="checkbox"]',
            sendButton: 'button:has-text("Send")',
            newChatButton: 'button:has-text("New")'
        };
        
        console.log('\n📱 Component visibility check:');
        for (const [name, selector] of Object.entries(components)) {
            try {
                const count = await page.locator(selector).count();
                const visible = count > 0;
                console.log(`${visible ? '✅' : '❌'} ${name}: ${count} elements found`);
            } catch (error) {
                console.log(`❌ ${name}: Error checking - ${error.message}`);
            }
        }
        
        // Check Vue app state
        const vueState = await page.evaluate(() => {
            // Try to access Vue app instance
            if (window.__VUE_DEVTOOLS_GLOBAL_HOOK__) {
                return 'Vue DevTools available';
            }
            
            // Check if there are any Vue components
            const vueElements = document.querySelectorAll('[data-v-*]');
            return `Vue elements found: ${vueElements.length}`;
        });
        
        console.log(`\n📋 Vue state: ${vueState}`);
        
        // Wait a bit more to see if components load asynchronously
        console.log('\n⏳ Waiting 5 seconds for async loading...');
        await page.waitForTimeout(5000);
        
        // Check again
        const finalCheckboxCount = await page.locator('input[type="checkbox"]').count();
        const finalChatInput = await page.locator('textarea[placeholder*="Type your message"]').isVisible();
        
        console.log(`\n📋 Final check:`);
        console.log(`Settings checkboxes: ${finalCheckboxCount}`);
        console.log(`Chat input visible: ${finalChatInput}`);
        
        // Take screenshot for debugging
        await page.screenshot({ path: '/tmp/frontend_debug.png', fullPage: true });
        console.log('📸 Screenshot saved to /tmp/frontend_debug.png');
        
    } catch (error) {
        console.log(`❌ Debug error: ${error.message}`);
    } finally {
        // Summary
        console.log('\n📊 DEBUG SUMMARY');
        console.log('='.repeat(40));
        console.log(`Total console messages: ${consoleMessages.length}`);
        console.log(`Errors: ${errors.length}`);
        
        if (errors.length > 0) {
            console.log('\nErrors found:');
            errors.forEach((error, i) => console.log(`${i + 1}. ${error}`));
        }
        
        const errorMessages = consoleMessages.filter(m => m.type === 'error');
        if (errorMessages.length > 0) {
            console.log('\nConsole errors:');
            errorMessages.forEach((msg, i) => console.log(`${i + 1}. ${msg.text}`));
        }
        
        await browser.close();
    }
}

debugRendering().catch(console.error);