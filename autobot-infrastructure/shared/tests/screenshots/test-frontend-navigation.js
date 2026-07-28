// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
const { chromium } = require('playwright');

async function testFrontendNavigation() {
  console.log('🚀 Starting comprehensive frontend navigation test...');

  // Launch browser in headed mode (visible)
  const browser = await chromium.launch({
    headless: false,
    slowMo: 1000, // Add delay between actions for visibility
    args: ['--start-maximized']
  });

  const context = await browser.newContext({
    viewport: null // Use full screen
  });

  const page = await context.newPage();

  try {
    console.log('📱 Navigating to AutoBot frontend...');
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    // Take initial screenshot
    await page.screenshot({ path: 'screenshots/01-homepage.png', fullPage: true });
    console.log('📸 Screenshot: Homepage loaded');

    // Test main navigation sections
    console.log('\n🧭 Testing main navigation sections...');

    const navItems = [
      'DASHBOARD',
      'AI ASSISTANT',
      'VOICE INTERFACE',
      'KNOWLEDGE BASE',
      'TERMINAL',
      'FILE MANAGER',
      'SYSTEM MONITOR',
      'SETTINGS'
    ];

    for (let i = 0; i < navItems.length; i++) {
      const navItem = navItems[i];
      console.log(`🔗 Testing navigation: ${navItem}`);

      try {
        // Click navigation item
        await page.getByText(navItem).click();
        await page.waitForTimeout(2000);

        // Take screenshot
        await page.screenshot({
          path: `screenshots/${String(i + 2).padStart(2, '0')}-${navItem.toLowerCase().replace(' ', '-')}.png`,
          fullPage: true
        });

        console.log(`✅ ${navItem} section loaded successfully`);
      } catch (error) {
        console.log(`❌ Failed to load ${navItem}: ${error.message}`);
      }
    }

    // Test Chat functionality
    console.log('\n💬 Testing Chat functionality...');
    await page.getByText('AI ASSISTANT').click();
    await page.waitForTimeout(2000);

    // Test chat sidebar functions
    console.log('📋 Testing chat sidebar functions...');

    // Test New Chat button
    try {
      await page.getByText('New').click();
      await page.waitForTimeout(1000);
      console.log('✅ New Chat button works');
    } catch (error) {
      console.log('❌ New Chat button failed:', error.message);
    }

    // Test message sending
    console.log('✉️ Testing message sending...');
    try {
      const messageInput = page.locator('textarea[placeholder*="Type your message"]');
      await messageInput.fill('Hello AutoBot, this is a test message');
      await page.waitForTimeout(1000);

      await page.getByText('Send').click();
      await page.waitForTimeout(3000);

      await page.screenshot({ path: 'screenshots/chat-message-sent.png', fullPage: true });
      console.log('✅ Message sent successfully');
    } catch (error) {
      console.log('❌ Message sending failed:', error.message);
    }

    // Test message display toggles
    console.log('🎛️ Testing message display toggles...');
    const toggles = [
      'Show Thoughts',
      'Show JSON Output',
      'Show Utility Messages',
      'Show Planning Messages',
      'Show Debug Messages',
      'Autoscroll'
    ];

    for (const toggle of toggles) {
      try {
        await page.locator(`input[type="checkbox"]`).locator(`.. >> text=${toggle}`).click();
        await page.waitForTimeout(500);
        console.log(`✅ Toggle '${toggle}' works`);
      } catch (error) {
        console.log(`❌ Toggle '${toggle}' failed: ${error.message}`);
      }
    }

    // Test reload system button
    console.log('🔄 Testing system reload functionality...');
    try {
      await page.getByText('Reload System').click();
      await page.waitForTimeout(3000);
      console.log('✅ System reload button works');
    } catch (error) {
      console.log('❌ System reload failed:', error.message);
    }

    // Test Settings Panel
    console.log('\n⚙️ Testing Settings Panel...');
    await page.getByText('SETTINGS').click();
    await page.waitForTimeout(2000);

    await page.screenshot({ path: 'screenshots/settings-panel.png', fullPage: true });
    console.log('📸 Screenshot: Settings panel');

    // Test Knowledge Base
    console.log('\n📚 Testing Knowledge Base...');
    await page.getByText('KNOWLEDGE BASE').click();
    await page.waitForTimeout(2000);

    await page.screenshot({ path: 'screenshots/knowledge-base.png', fullPage: true });
    console.log('📸 Screenshot: Knowledge Base');

    // Test File Manager
    console.log('\n📁 Testing File Manager...');
    await page.getByText('FILE MANAGER').click();
    await page.waitForTimeout(2000);

    await page.screenshot({ path: 'screenshots/file-manager.png', fullPage: true });
    console.log('📸 Screenshot: File Manager');

    // Test System Monitor
    console.log('\n📊 Testing System Monitor...');
    await page.getByText('SYSTEM MONITOR').click();
    await page.waitForTimeout(2000);

    await page.screenshot({ path: 'screenshots/system-monitor.png', fullPage: true });
    console.log('📸 Screenshot: System Monitor');

    // Test Terminal
    console.log('\n💻 Testing Terminal...');
    await page.getByText('TERMINAL').click();
    await page.waitForTimeout(2000);

    await page.screenshot({ path: 'screenshots/terminal.png', fullPage: true });
    console.log('📸 Screenshot: Terminal');

    // Test Voice Interface
    console.log('\n🎤 Testing Voice Interface...');
    await page.getByText('VOICE INTERFACE').click();
    await page.waitForTimeout(2000);

    await page.screenshot({ path: 'screenshots/voice-interface.png', fullPage: true });
    console.log('📸 Screenshot: Voice Interface');

    // Test responsive design
    console.log('\n📱 Testing responsive design...');

    // Test mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'screenshots/mobile-view.png', fullPage: true });
    console.log('📸 Screenshot: Mobile view');

    // Test tablet viewport
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'screenshots/tablet-view.png', fullPage: true });
    console.log('📸 Screenshot: Tablet view');

    // Return to desktop
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.waitForTimeout(1000);

    // Test hamburger menu if visible
    console.log('🍔 Testing hamburger menu...');
    try {
      const hamburgerButton = page.locator('button').filter({ has: page.locator('svg.w-6.h-6') }).first();
      if (await hamburgerButton.isVisible()) {
        await hamburgerButton.click();
        await page.waitForTimeout(1000);
        await page.screenshot({ path: 'screenshots/hamburger-menu.png', fullPage: true });
        console.log('✅ Hamburger menu works');
      }
    } catch (error) {
      console.log('ℹ️ Hamburger menu not found or not needed');
    }

    // Final screenshot
    await page.screenshot({ path: 'screenshots/final-state.png', fullPage: true });

    console.log('\n🎉 Frontend navigation test completed successfully!');
    console.log('📁 Screenshots saved in screenshots/ directory');

    // Keep browser open for manual inspection
    console.log('\n⏸️ Browser will stay open for 30 seconds for manual inspection...');
    await page.waitForTimeout(30000);

  } catch (error) {
    console.error('❌ Error during testing:', error);
    await page.screenshot({ path: 'screenshots/error-state.png', fullPage: true });
  } finally {
    await browser.close();
    console.log('🔚 Browser closed');
  }
}

// Create screenshots directory
const fs = require('fs');
if (!fs.existsSync('screenshots')) {
  fs.mkdirSync('screenshots');
}

// Run the test
testFrontendNavigation();
