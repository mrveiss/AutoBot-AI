import { test, expect } from '@playwright/test';

test.describe('AutoBot Frontend Navigation and Chat Access', () => {
  let unexpectedResponseErrors = [];

  test.beforeEach(async ({ page }) => {
    unexpectedResponseErrors = [];

    // Monitor for unexpected response errors
    page.on('console', msg => {
      if (msg.text().includes('An unexpected response format was received')) {
        unexpectedResponseErrors.push({
          type: 'console',
          message: msg.text(),
          timestamp: new Date().toISOString()
        });
        console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR IN CONSOLE:', msg.text());
      }
    });

    page.on('response', async response => {
      try {
        const text = await response.text();
        if (text.includes('An unexpected response format was received')) {
          unexpectedResponseErrors.push({
            type: 'response',
            url: response.url(),
            message: text.substring(0, 200),
            timestamp: new Date().toISOString()
          });
          console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR IN RESPONSE:', response.url());
        }
      } catch (e) {
        // Ignore binary responses
      }
    });
  });

  test('Navigate to Chat Interface', async ({ page }) => {
    console.log('🧪 Testing: Navigate to chat interface');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Take initial screenshot
    await page.screenshot({ path: 'debug-initial-page.png' });
    console.log('📸 Initial page screenshot saved');

    // Look for navigation links or buttons that might lead to chat
    const navigationElements = [
      'a[href*="chat"]',
      'button:has-text("Chat")',
      'button:has-text("New Chat")',
      'a:has-text("Chat")',
      '[role="button"]:has-text("Chat")',
      'nav a',
      'nav button'
    ];

    for (const selector of navigationElements) {
      const elements = page.locator(selector);
      const count = await elements.count();

      if (count > 0) {
        console.log(`📋 Found ${count} elements matching: ${selector}`);
        for (let i = 0; i < count; i++) {
          const element = elements.nth(i);
          const text = await element.textContent() || '';
          const visible = await element.isVisible();
          console.log(`  ${i}: "${text.trim()}" (visible: ${visible})`);
        }
      }
    }

    // Try clicking "New Chat" button if it exists
    const newChatButton = page.locator('button:has-text("New Chat")');
    if (await newChatButton.isVisible()) {
      console.log('✅ Found "New Chat" button - clicking it');
      await newChatButton.click();
      await page.waitForTimeout(2000);

      // Take screenshot after clicking
      await page.screenshot({ path: 'debug-after-new-chat.png' });
      console.log('📸 After new chat screenshot saved');

      // Check if input elements appeared
      const inputs = page.locator('input, textarea');
      const inputCount = await inputs.count();
      console.log(`📋 After clicking New Chat: found ${inputCount} input elements`);
    }

    // Look for any expandable sections or panels
    const expandButtons = page.locator('[aria-expanded], .collapsed, .toggle, button[class*="expand"]');
    const expandCount = await expandButtons.count();
    console.log(`📋 Found ${expandCount} potentially expandable elements`);

    // Check current URL for routing
    const currentUrl = page.url();
    console.log(`📋 Current URL: ${currentUrl}`);

    console.log('✅ Navigation exploration completed');
  });

  test('Search for Chat Interface in All Views', async ({ page }) => {
    console.log('🧪 Testing: Search for chat interface across views');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Try different potential routes
    const potentialRoutes = [
      '/',
      '/chat',
      '/dashboard',
      '/agent',
      '/interface',
      '/main'
    ];

    for (const route of potentialRoutes) {
      console.log(`\n🧪 Testing route: ${route}`);

      try {
        await page.goto(`http://localhost:5173${route}`);
        await page.waitForTimeout(2000);

        // Check for input elements
        const inputs = page.locator('input, textarea, [contenteditable="true"]');
        const inputCount = await inputs.count();

        if (inputCount > 0) {
          console.log(`✅ Found ${inputCount} input elements on ${route}`);

          for (let i = 0; i < inputCount; i++) {
            const input = inputs.nth(i);
            const type = await input.getAttribute('type') || 'unknown';
            const placeholder = await input.getAttribute('placeholder') || 'none';
            const visible = await input.isVisible();
            console.log(`  Input ${i}: type="${type}", placeholder="${placeholder}", visible=${visible}`);

            if (visible && (type === 'text' || input.locator('textarea').count() > 0 || placeholder.toLowerCase().includes('message'))) {
              console.log('🎯 This looks like a chat input - testing it!');

              // Test sending a message
              await input.fill('Test message to find unexpected response error');

              // Try different ways to send
              try {
                await input.press('Enter');
                console.log('✅ Sent message via Enter key');
                await page.waitForTimeout(3000);

                if (unexpectedResponseErrors.length > 0) {
                  console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR!');
                  console.log(JSON.stringify(unexpectedResponseErrors, null, 2));
                }
              } catch (e) {
                console.log('❌ Enter key failed, looking for send button');

                const sendButton = page.locator('button').filter({ hasText: /send|submit/i });
                if (await sendButton.first().isVisible()) {
                  await sendButton.first().click();
                  console.log('✅ Sent message via button');
                  await page.waitForTimeout(3000);

                  if (unexpectedResponseErrors.length > 0) {
                    console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR!');
                    console.log(JSON.stringify(unexpectedResponseErrors, null, 2));
                  }
                }
              }

              break; // Found and tested a chat input
            }
          }
        } else {
          console.log(`❌ No input elements found on ${route}`);
        }

      } catch (e) {
        console.log(`❌ Error loading ${route}: ${e.message}`);
      }
    }

    console.log('✅ Route exploration completed');
  });

  test('Interact with All Clickable Elements to Find Chat', async ({ page }) => {
    console.log('🧪 Testing: Interact with all clickable elements');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Get all clickable elements
    const clickableElements = page.locator('button, a, [role="button"], [onclick], .cursor-pointer');
    const count = await clickableElements.count();

    console.log(`📋 Found ${count} clickable elements`);

    // Try clicking each one to see if it reveals a chat interface
    for (let i = 0; i < Math.min(count, 15); i++) { // Limit to first 15 to avoid infinite loops
      try {
        const element = clickableElements.nth(i);
        const text = await element.textContent() || '';
        const visible = await element.isVisible();

        if (visible && text.trim()) {
          console.log(`\n🖱️  Clicking element ${i}: "${text.trim()}"`);

          // Take screenshot before clicking
          await page.screenshot({ path: `debug-before-click-${i}.png` });

          await element.click();
          await page.waitForTimeout(1500);

          // Check if input elements appeared after clicking
          const newInputs = page.locator('input, textarea, [contenteditable="true"]');
          const newInputCount = await newInputs.count();

          if (newInputCount > 0) {
            console.log(`🎯 After clicking "${text.trim()}", found ${newInputCount} inputs!`);

            // Test the inputs
            for (let j = 0; j < newInputCount; j++) {
              const input = newInputs.nth(j);
              const inputVisible = await input.isVisible();

              if (inputVisible) {
                console.log(`🧪 Testing input ${j} that appeared after click`);

                await input.fill('Testing for unexpected response error after UI interaction');

                try {
                  await input.press('Enter');
                  await page.waitForTimeout(3000);

                  if (unexpectedResponseErrors.length > 0) {
                    console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR after UI interaction!');
                    console.log(`Triggered by clicking: "${text.trim()}"`);
                    console.log(JSON.stringify(unexpectedResponseErrors, null, 2));
                  }

                  // Clear for next test
                  await input.fill('');

                } catch (e) {
                  // Try clicking a send button instead
                  const sendBtn = page.locator('button').filter({ hasText: /send|submit/i }).first();
                  if (await sendBtn.isVisible()) {
                    await sendBtn.click();
                    await page.waitForTimeout(3000);

                    if (unexpectedResponseErrors.length > 0) {
                      console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR after UI interaction!');
                      console.log(`Triggered by clicking: "${text.trim()}"`);
                      console.log(JSON.stringify(unexpectedResponseErrors, null, 2));
                    }
                  }
                }
              }
            }

            // Take screenshot after finding inputs
            await page.screenshot({ path: `debug-after-click-${i}-with-inputs.png` });
          }
        }

      } catch (e) {
        console.log(`❌ Error clicking element ${i}: ${e.message}`);
      }
    }

    // Final summary
    console.log('\n📋 FINAL TEST SUMMARY:');
    console.log('======================');
    console.log(`Total unexpected response errors found: ${unexpectedResponseErrors.length}`);

    if (unexpectedResponseErrors.length > 0) {
      console.log('\n🎯 ALL UNEXPECTED RESPONSE ERRORS:');
      console.log(JSON.stringify(unexpectedResponseErrors, null, 2));
    }

    console.log('✅ Comprehensive UI interaction testing completed');
  });
});
