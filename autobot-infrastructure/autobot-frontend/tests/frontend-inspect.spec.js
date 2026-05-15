import { test, expect } from '@playwright/test';

test.describe('AutoBot Frontend DOM Inspection', () => {
  let consoleErrors = [];
  let unexpectedResponseErrors = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors = [];
    unexpectedResponseErrors = [];

    // Capture console messages
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
        console.log('❌ Console Error:', msg.text());
      }

      // Look for our specific error message
      if (msg.text().includes('An unexpected response format was received')) {
        unexpectedResponseErrors.push({
          type: 'console',
          message: msg.text(),
          timestamp: new Date().toISOString()
        });
        console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR IN CONSOLE:', msg.text());
      }
    });

    // Listen for responses containing the error
    page.on('response', async response => {
      try {
        const text = await response.text();
        if (text.includes('An unexpected response format was received')) {
          unexpectedResponseErrors.push({
            type: 'response',
            url: response.url(),
            message: text.substring(0, 500), // Truncate long responses
            timestamp: new Date().toISOString()
          });
          console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR IN RESPONSE:', response.url());
        }
      } catch (e) {
        // Ignore errors from binary responses
      }
    });
  });

  test('Inspect Frontend DOM Structure', async ({ page }) => {
    console.log('🧪 Testing: Frontend DOM inspection');

    await page.goto('/');

    // Wait for Vue to load
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000); // Give Vue time to render

    // Get the entire DOM structure
    const bodyHTML = await page.locator('body').innerHTML();
    console.log('📋 Page HTML (first 1000 chars):', bodyHTML.substring(0, 1000));

    // Look for common Vue app elements
    const vueApp = page.locator('#app');
    if (await vueApp.isVisible()) {
      console.log('✅ Vue app container found');
      const appHTML = await vueApp.innerHTML();
      console.log('📋 App HTML (first 1000 chars):', appHTML.substring(0, 1000));
    }

    // Find all input elements
    const inputs = page.locator('input');
    const inputCount = await inputs.count();
    console.log(`📋 Found ${inputCount} input elements`);

    for (let i = 0; i < inputCount; i++) {
      const input = inputs.nth(i);
      const type = await input.getAttribute('type') || 'text';
      const placeholder = await input.getAttribute('placeholder') || 'none';
      const visible = await input.isVisible();
      console.log(`  Input ${i}: type="${type}", placeholder="${placeholder}", visible=${visible}`);
    }

    // Find all textarea elements
    const textareas = page.locator('textarea');
    const textareaCount = await textareas.count();
    console.log(`📋 Found ${textareaCount} textarea elements`);

    for (let i = 0; i < textareaCount; i++) {
      const textarea = textareas.nth(i);
      const placeholder = await textarea.getAttribute('placeholder') || 'none';
      const visible = await textarea.isVisible();
      console.log(`  Textarea ${i}: placeholder="${placeholder}", visible=${visible}`);
    }

    // Find all buttons
    const buttons = page.locator('button');
    const buttonCount = await buttons.count();
    console.log(`📋 Found ${buttonCount} button elements`);

    for (let i = 0; i < Math.min(buttonCount, 10); i++) { // Limit to first 10 buttons
      const button = buttons.nth(i);
      const text = await button.textContent() || '';
      const visible = await button.isVisible();
      console.log(`  Button ${i}: text="${text.trim()}", visible=${visible}`);
    }

    console.log('✅ DOM inspection completed');
  });

  test('Test Chat Input Discovery and Interaction', async ({ page }) => {
    console.log('🧪 Testing: Chat input discovery and interaction');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Try different selectors to find the chat input
    const possibleInputs = [
      'input[type="text"]',
      'input[placeholder*="message"]',
      'input[placeholder*="chat"]',
      'input[placeholder*="type"]',
      'textarea',
      'textarea[placeholder*="message"]',
      '[contenteditable="true"]',
      'input[class*="chat"]',
      'input[class*="message"]'
    ];

    let chatInput = null;
    let foundSelector = '';

    for (const selector of possibleInputs) {
      const element = page.locator(selector).first();
      if (await element.isVisible()) {
        chatInput = element;
        foundSelector = selector;
        console.log(`✅ Found chat input with selector: ${selector}`);
        break;
      }
    }

    if (chatInput) {
      console.log('🧪 Testing message input...');

      // Test typing a simple message
      await chatInput.fill('Test message');
      const value = await chatInput.inputValue();
      console.log(`✅ Input value after typing: "${value}"`);

      // Look for send button
      const possibleSendButtons = [
        'button[type="submit"]',
        'button:has-text("Send")',
        'button:has-text("Submit")',
        'button[class*="send"]',
        'button[class*="submit"]',
        '[role="button"]:has-text("Send")'
      ];

      for (const selector of possibleSendButtons) {
        const button = page.locator(selector).first();
        if (await button.isVisible()) {
          console.log(`✅ Found send button with selector: ${selector}`);

          // Click the button
          await button.click();
          console.log('✅ Send button clicked');

          // Wait for any response
          await page.waitForTimeout(3000);
          break;
        }
      }

      // Check for any errors after sending
      if (unexpectedResponseErrors.length > 0) {
        console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR after sending message!');
        console.log(JSON.stringify(unexpectedResponseErrors, null, 2));
      }

    } else {
      console.log('❌ Could not find chat input element');

      // Take a screenshot for debugging
      await page.screenshot({ path: 'debug-no-input-found.png' });
      console.log('📸 Screenshot saved as debug-no-input-found.png');
    }

    console.log('✅ Chat input test completed');
  });

  test('Test Different Message Types for Error Reproduction', async ({ page }) => {
    console.log('🧪 Testing: Different message types to reproduce errors');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Find the chat input (using discovery from previous test)
    let chatInput = null;
    const selectors = ['input[type="text"]', 'textarea', '[contenteditable="true"]'];

    for (const selector of selectors) {
      const element = page.locator(selector).first();
      if (await element.isVisible()) {
        chatInput = element;
        break;
      }
    }

    if (!chatInput) {
      console.log('❌ No chat input found - skipping message tests');
      return;
    }

    const testMessages = [
      { message: 'What is 2+2?', type: 'simple' },
      { message: 'Find the best Python web frameworks', type: 'research' },
      { message: 'Install Docker on my system', type: 'install' },
      { message: 'I need to scan my network for security vulnerabilities', type: 'complex' }
    ];

    for (const test of testMessages) {
      console.log(`\n🧪 Testing ${test.type} message: "${test.message}"`);

      // Clear and fill input
      await chatInput.fill(test.message);

      // Try to send (look for various send mechanisms)
      let sent = false;

      // Try pressing Enter first
      try {
        await chatInput.press('Enter');
        sent = true;
        console.log('✅ Sent via Enter key');
      } catch (e) {
        console.log('❌ Enter key failed:', e.message);
      }

      // If Enter didn't work, try finding a send button
      if (!sent) {
        const sendButton = page.locator('button').filter({ hasText: /send|submit/i }).first();
        if (await sendButton.isVisible()) {
          await sendButton.click();
          sent = true;
          console.log('✅ Sent via button click');
        }
      }

      if (sent) {
        // Wait for response and check for errors
        await page.waitForTimeout(5000);

        if (unexpectedResponseErrors.length > 0) {
          console.log(`🎯 FOUND UNEXPECTED RESPONSE ERROR for ${test.type} message!`);
          console.log('Error details:', JSON.stringify(unexpectedResponseErrors, null, 2));

          // Don't clear errors yet - let them accumulate
        } else {
          console.log(`✅ No unexpected response error for ${test.type} message`);
        }
      } else {
        console.log(`❌ Could not send ${test.type} message`);
      }

      // Clear the input for next test
      await chatInput.fill('');
    }

    // Final summary
    console.log('\n📋 FINAL ERROR SUMMARY:');
    console.log('========================');
    console.log(`Total unexpected response errors: ${unexpectedResponseErrors.length}`);
    console.log(`Total console errors: ${consoleErrors.length}`);

    if (unexpectedResponseErrors.length > 0) {
      console.log('\n🎯 ALL UNEXPECTED RESPONSE ERRORS:');
      console.log(JSON.stringify(unexpectedResponseErrors, null, 2));
    }

    if (consoleErrors.length > 0) {
      console.log('\n❌ ALL CONSOLE ERRORS:');
      consoleErrors.forEach((error, i) => console.log(`${i + 1}. ${error}`));
    }

    console.log('✅ Message type testing completed');
  });

  test('Monitor Network Traffic for Error Patterns', async ({ page }) => {
    console.log('🧪 Testing: Network traffic monitoring');

    const requests = [];
    const responses = [];

    page.on('request', request => {
      requests.push({
        url: request.url(),
        method: request.method(),
        timestamp: new Date().toISOString()
      });
    });

    page.on('response', async response => {
      const responseData = {
        url: response.url(),
        status: response.status(),
        timestamp: new Date().toISOString()
      };

      try {
        const text = await response.text();
        responseData.hasUnexpectedError = text.includes('An unexpected response format was received');
        if (responseData.hasUnexpectedError) {
          responseData.errorContent = text.substring(0, 500);
          console.log('🎯 NETWORK RESPONSE WITH ERROR:', responseData);
        }
      } catch (e) {
        // Binary response
      }

      responses.push(responseData);
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(5000);

    console.log(`📊 Captured ${requests.length} requests and ${responses.length} responses`);

    // Look for workflow-related requests
    const workflowRequests = requests.filter(r => r.url.includes('/workflow/'));
    const chatRequests = requests.filter(r => r.url.includes('/chat'));
    const errorResponses = responses.filter(r => r.hasUnexpectedError);

    console.log(`🔄 Workflow requests: ${workflowRequests.length}`);
    console.log(`💬 Chat requests: ${chatRequests.length}`);
    console.log(`❌ Responses with unexpected error: ${errorResponses.length}`);

    if (errorResponses.length > 0) {
      console.log('\n🎯 RESPONSES WITH UNEXPECTED ERRORS:');
      errorResponses.forEach(response => {
        console.log(`- ${response.url} (${response.status})`);
        console.log(`  Content: ${response.errorContent}`);
      });
    }

    console.log('✅ Network monitoring completed');
  });
});
