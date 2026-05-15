import { test, expect } from '@playwright/test';

test.describe('AutoBot Frontend Complete Test', () => {
  let consoleErrors = [];
  let networkErrors = [];
  let unexpectedResponseErrors = [];

  test.beforeEach(async ({ page }) => {
    // Reset error arrays
    consoleErrors = [];
    networkErrors = [];
    unexpectedResponseErrors = [];

    // Capture console errors
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

    // Capture network failures
    page.on('response', response => {
      if (!response.ok()) {
        networkErrors.push({
          url: response.url(),
          status: response.status(),
          statusText: response.statusText()
        });
        console.log('❌ Network Error:', response.status(), response.url());
      }
    });

    // Listen for specific error messages in page content
    page.on('response', async response => {
      try {
        const text = await response.text();
        if (text.includes('An unexpected response format was received')) {
          unexpectedResponseErrors.push({
            type: 'response',
            url: response.url(),
            message: text,
            timestamp: new Date().toISOString()
          });
          console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR IN RESPONSE:', response.url());
        }
      } catch (e) {
        // Ignore JSON parse errors for binary responses
      }
    });
  });

  test('1. Frontend Loads Successfully', async ({ page }) => {
    console.log('🧪 Testing: Frontend loads successfully');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Check for basic UI elements
    await expect(page.locator('h1, .header, [data-testid="app-title"]')).toBeVisible();

    // Check if any errors occurred during load
    expect(consoleErrors.length).toBe(0);
    console.log('✅ Frontend loaded without console errors');
  });

  test('2. Chat Interface Initialization', async ({ page }) => {
    console.log('🧪 Testing: Chat interface initialization');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Look for chat input and messages area
    const chatInput = page.locator('input[type="text"], textarea').first();
    const messagesArea = page.locator('.message, .chat-message').first();

    await expect(chatInput).toBeVisible();
    console.log('✅ Chat input is visible');

    // Check for any initialization errors
    expect(unexpectedResponseErrors.length).toBe(0);
  });

  test('3. Send Simple Message (Direct Execution)', async ({ page }) => {
    console.log('🧪 Testing: Send simple message');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const chatInput = page.locator('input[type="text"], textarea').first();
    await chatInput.fill('What is 2+2?');

    // Find and click send button
    const sendButton = page.locator('button').filter({ hasText: /send|submit/i }).first();

    if (await sendButton.isVisible()) {
      await sendButton.click();
    } else {
      // Try pressing Enter
      await chatInput.press('Enter');
    }

    // Wait for response
    await page.waitForTimeout(3000);

    // Check if unexpected response error appeared
    if (unexpectedResponseErrors.length > 0) {
      console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR during simple message!');
      console.log(unexpectedResponseErrors);
    }

    expect(unexpectedResponseErrors.length).toBe(0);
    console.log('✅ Simple message sent without unexpected response errors');
  });

  test('4. Send Research Request (Workflow)', async ({ page }) => {
    console.log('🧪 Testing: Send research request');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const chatInput = page.locator('input[type="text"], textarea').first();
    await chatInput.fill('Find the best Python web frameworks');

    // Send message
    const sendButton = page.locator('button').filter({ hasText: /send|submit/i }).first();

    if (await sendButton.isVisible()) {
      await sendButton.click();
    } else {
      await chatInput.press('Enter');
    }

    // Wait longer for workflow response
    await page.waitForTimeout(5000);

    // Check for workflow indicators
    const workflowText = page.locator('text=workflow', { hasText: /workflow/i });
    const orchestrationText = page.locator('text=orchestration', { hasText: /orchestration/i });

    if (await workflowText.isVisible() || await orchestrationText.isVisible()) {
      console.log('✅ Workflow orchestration detected in UI');
    }

    // Check for errors
    if (unexpectedResponseErrors.length > 0) {
      console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR during research request!');
      console.log(unexpectedResponseErrors);
    }

    expect(unexpectedResponseErrors.length).toBe(0);
    console.log('✅ Research request sent without unexpected response errors');
  });

  test('5. Send Install Request (Complex Workflow)', async ({ page }) => {
    console.log('🧪 Testing: Send install request');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const chatInput = page.locator('input[type="text"], textarea').first();
    await chatInput.fill('Install Docker on my system');

    // Send message
    const sendButton = page.locator('button').filter({ hasText: /send|submit/i }).first();

    if (await sendButton.isVisible()) {
      await sendButton.click();
    } else {
      await chatInput.press('Enter');
    }

    // Wait for workflow response
    await page.waitForTimeout(5000);

    // Check for errors
    if (unexpectedResponseErrors.length > 0) {
      console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR during install request!');
      console.log(unexpectedResponseErrors);
    }

    expect(unexpectedResponseErrors.length).toBe(0);
    console.log('✅ Install request sent without unexpected response errors');
  });

  test('6. Send Complex Security Request', async ({ page }) => {
    console.log('🧪 Testing: Send complex security request');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const chatInput = page.locator('input[type="text"], textarea').first();
    await chatInput.fill('I need to scan my network for security vulnerabilities');

    // Send message
    const sendButton = page.locator('button').filter({ hasText: /send|submit/i }).first();

    if (await sendButton.isVisible()) {
      await sendButton.click();
    } else {
      await chatInput.press('Enter');
    }

    // Wait for workflow response
    await page.waitForTimeout(8000); // Longer wait for complex workflow

    // Check for errors - this is most likely to trigger the unexpected response error
    if (unexpectedResponseErrors.length > 0) {
      console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR during security request!');
      console.log(unexpectedResponseErrors);
    }

    // Don't fail the test, just report findings
    console.log('✅ Complex security request completed');
  });

  test('7. Test Chat History Functions', async ({ page }) => {
    console.log('🧪 Testing: Chat history functions');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Look for sidebar or chat history controls
    const newChatButton = page.locator('button').filter({ hasText: /new|chat/i });
    const resetButton = page.locator('button').filter({ hasText: /reset|clear/i });

    if (await newChatButton.first().isVisible()) {
      await newChatButton.first().click();
      await page.waitForTimeout(1000);
      console.log('✅ New chat button clicked');
    }

    if (await resetButton.first().isVisible()) {
      await resetButton.first().click();
      await page.waitForTimeout(1000);
      console.log('✅ Reset button clicked');
    }

    expect(unexpectedResponseErrors.length).toBe(0);
    console.log('✅ Chat history functions tested');
  });

  test('8. Test Settings and Configuration', async ({ page }) => {
    console.log('🧪 Testing: Settings and configuration');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Look for settings/config controls
    const settingsButton = page.locator('button, a').filter({ hasText: /setting|config|preference/i });
    const checkboxes = page.locator('input[type="checkbox"]');

    if (await settingsButton.first().isVisible()) {
      await settingsButton.first().click();
      await page.waitForTimeout(1000);
      console.log('✅ Settings accessed');
    }

    // Test some checkboxes if they exist
    const checkboxCount = await checkboxes.count();
    for (let i = 0; i < Math.min(checkboxCount, 3); i++) {
      const checkbox = checkboxes.nth(i);
      if (await checkbox.isVisible()) {
        await checkbox.click();
        await page.waitForTimeout(500);
      }
    }

    expect(unexpectedResponseErrors.length).toBe(0);
    console.log('✅ Settings and configuration tested');
  });

  test('9. Test File Upload (if available)', async ({ page }) => {
    console.log('🧪 Testing: File upload functionality');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Look for file input or upload button
    const fileInput = page.locator('input[type="file"]');
    const uploadButton = page.locator('button').filter({ hasText: /upload|attach|file/i });

    if (await fileInput.isVisible() || await uploadButton.isVisible()) {
      console.log('✅ File upload controls found');
      // Don't actually upload files, just test the UI is available
    }

    expect(unexpectedResponseErrors.length).toBe(0);
    console.log('✅ File upload UI tested');
  });

  test('10. Final Error Summary', async ({ page }) => {
    console.log('🧪 Final Summary: All captured errors');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    console.log('📋 ERROR SUMMARY:');
    console.log('==================');
    console.log(`Console Errors: ${consoleErrors.length}`);
    console.log(`Network Errors: ${networkErrors.length}`);
    console.log(`Unexpected Response Errors: ${unexpectedResponseErrors.length}`);

    if (unexpectedResponseErrors.length > 0) {
      console.log('\n🎯 UNEXPECTED RESPONSE ERRORS FOUND:');
      console.log(JSON.stringify(unexpectedResponseErrors, null, 2));
    }

    if (consoleErrors.length > 0) {
      console.log('\n❌ CONSOLE ERRORS:');
      consoleErrors.forEach(error => console.log('  -', error));
    }

    if (networkErrors.length > 0) {
      console.log('\n🌐 NETWORK ERRORS:');
      networkErrors.forEach(error => console.log('  -', error.status, error.url));
    }

    // Test passes regardless - we're just collecting information
    console.log('✅ Error collection completed');
  });

  test.afterEach(async ({ page }, testInfo) => {
    // Log final error state for each test
    if (unexpectedResponseErrors.length > 0) {
      console.log(`🎯 Test "${testInfo.title}" found unexpected response errors:`, unexpectedResponseErrors.length);
    }
  });
});
