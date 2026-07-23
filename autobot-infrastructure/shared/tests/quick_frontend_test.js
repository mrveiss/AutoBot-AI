#!/usr/bin/env node
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0

/**
 * Quick Frontend Test - Check if key issues are resolved
 */

const { chromium } = require('playwright');

async function quickTest() {
    console.log('🚀 Quick Frontend Test Started\n');

    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    const results = {
        pageLoads: false,
        settingsVisible: false,
        chatInputVisible: false,
        backendConnectable: false
    };

    try {
        // Test 1: Page loads without timeout
        console.log('📱 Testing page load...');
        await page.goto('http://localhost:5173', {
            waitUntil: 'domcontentloaded',
            timeout: 15000
        });

        await page.waitForSelector('#app', { timeout: 5000 });
        results.pageLoads = true;
        console.log('✅ Page loads successfully');

        // Test 2: Settings checkboxes visible
        console.log('📱 Testing settings visibility...');
        const checkboxes = await page.locator('input[type="checkbox"]').count();
        if (checkboxes > 0) {
            results.settingsVisible = true;
            console.log(`✅ Found ${checkboxes} settings checkboxes`);
        } else {
            console.log('❌ No settings checkboxes found');
        }

        // Test 3: Chat input visible
        console.log('📱 Testing chat interface...');
        const chatInput = await page.locator('textarea[placeholder*="Type your message"]').isVisible();
        if (chatInput) {
            results.chatInputVisible = true;
            console.log('✅ Chat input is visible');
        } else {
            console.log('❌ Chat input not found');
        }

        // Test 4: Backend connectivity
        console.log('📱 Testing backend connectivity...');
        const backendTest = await page.evaluate(async () => {
            try {
                const controller = new AbortController();
                setTimeout(() => controller.abort(), 5000);

                const res = await fetch('http://localhost:8001/api/system/health', {
                    signal: controller.signal
                });
                return res.ok;
            } catch (error) {
                return false;
            }
        });

        if (backendTest) {
            results.backendConnectable = true;
            console.log('✅ Backend is reachable');
        } else {
            console.log('❌ Backend not reachable');
        }

    } catch (error) {
        console.log(`❌ Test error: ${error.message}`);
    } finally {
        await browser.close();
    }

    // Summary
    console.log('\n📊 QUICK TEST RESULTS');
    console.log('='.repeat(30));
    console.log(`Page Loads: ${results.pageLoads ? '✅' : '❌'}`);
    console.log(`Settings Visible: ${results.settingsVisible ? '✅' : '❌'}`);
    console.log(`Chat Input Visible: ${results.chatInputVisible ? '✅' : '❌'}`);
    console.log(`Backend Reachable: ${results.backendConnectable ? '✅' : '❌'}`);

    const passed = Object.values(results).filter(r => r).length;
    const total = Object.keys(results).length;

    console.log(`\n🎯 Score: ${passed}/${total} tests passed`);

    if (passed === total) {
        console.log('🎉 All critical issues resolved!');
    } else {
        console.log('⚠️  Some issues remain, see details above');
    }

    return passed === total;
}

quickTest().catch(console.error);
