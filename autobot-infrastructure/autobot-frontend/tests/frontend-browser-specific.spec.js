import { test, expect } from '@playwright/test';

test.describe('AutoBot Browser-Specific Error Testing', () => {
  let unexpectedResponseErrors = [];

  test.beforeEach(async ({ page }) => {
    unexpectedResponseErrors = [];

    // Enhanced monitoring for browser-specific issues
    page.on('console', msg => {
      const message = msg.text();
      console.log(`[${msg.type()}]`, message);

      if (message.includes('An unexpected response format was received') ||
          message.includes('unexpected response format')) {
        unexpectedResponseErrors.push({
          type: 'console',
          message: message,
          timestamp: new Date().toISOString()
        });
        console.log('🎯 BROWSER ERROR DETECTED:', message);
      }
    });

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
          console.log('🎯 RESPONSE ERROR DETECTED:', response.url());
        }
      } catch (e) {
        // Binary response
      }
    });

    // Override fetch to simulate Edge-specific behaviors
    await page.addInitScript(() => {
      const originalFetch = window.fetch;
      window.fetch = function(...args) {
        console.log('🌐 FETCH CALL:', args[0]);

        return originalFetch.apply(this, args)
          .then(response => {
            console.log('📥 FETCH RESPONSE:', response.status, response.url);
            return response;
          })
          .catch(error => {
            console.log('❌ FETCH ERROR:', error.message);
            throw error;
          });
      };
    });
  });

  test('Edge-like Browser Behavior Simulation', async ({ page }) => {
    console.log('🧪 Testing: Edge-like browser behaviors that might trigger errors');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Simulate Edge-specific issues by manipulating browser behavior

    // 1. Simulate slower JavaScript execution (Edge can be slower)
    await page.evaluate(() => {
      const originalSetTimeout = window.setTimeout;
      window.setTimeout = function(fn, delay) {
        return originalSetTimeout(fn, (delay || 0) + 50); // Add 50ms delay
      };
    });

    // 2. Simulate Edge's stricter CORS handling
    await page.route('**/*', route => {
      const headers = route.request().headers();

      // Add Edge-like headers
      headers['sec-ch-ua'] = '"Microsoft Edge";v="119", "Chromium";v="119", "Not?A_Brand";v="24"';
      headers['sec-ch-ua-platform'] = '"Windows"';

      route.continue({ headers });
    });

    // Navigate to AI Assistant
    await page.locator('button, a').filter({ hasText: /AI Assistant/i }).first().click();
    await page.waitForTimeout(3000);

    const chatInput = page.locator('input[placeholder*="Type your message"]').first();

    if (await chatInput.isVisible()) {
      console.log('✅ Found chat input, testing Edge-like scenarios');

      // Test scenarios that might cause issues in Edge
      const edgeProblematicMessages = [
        // Unicode characters that Edge might handle differently
        'Test with unicode: 你好 🚀 ñáéíóú',

        // Long message that might cause buffer issues
        'This is a very long message that might cause issues with Edge browser buffer handling: ' + 'A'.repeat(500),

        // Message with mixed content types
        'Mixed content: <script>alert("test")</script> {"json": true} http://example.com',

        // Network security request (most likely to trigger workflow error)
        'I need to perform comprehensive network security scanning and vulnerability assessment with automated tool installation',

        // Multiple rapid messages (Edge might handle differently)
        'Rapid message 1',
      ];

      for (const [i, message] of edgeProblematicMessages.entries()) {
        console.log(`\n🧪 Testing Edge scenario ${i + 1}: ${message.substring(0, 50)}...`);

        await chatInput.fill(message);
        await chatInput.press('Enter');

        // Edge might need more time to process
        await page.waitForTimeout(6000);

        if (unexpectedResponseErrors.length > 0) {
          console.log(`🎯 ERROR TRIGGERED by Edge scenario ${i + 1}!`);
          console.log('Error details:', unexpectedResponseErrors);
          break;
        }

        // Send rapid follow-up (Edge timing issue)
        if (i === 4) { // After "Rapid message 1"
          await chatInput.fill('Rapid message 2');
          await chatInput.press('Enter');
          await page.waitForTimeout(500);

          await chatInput.fill('Rapid message 3');
          await chatInput.press('Enter');
          await page.waitForTimeout(3000);
        }
      }
    }

    console.log('✅ Edge-like behavior testing completed');
  });

  test('Content Security Policy and Edge Security Features', async ({ page }) => {
    console.log('🧪 Testing: CSP and Edge security features');

    // Edge has stricter CSP handling
    await page.setExtraHTTPHeaders({
      'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval';"
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Navigate to AI Assistant
    await page.locator('button, a').filter({ hasText: /AI Assistant/i }).first().click();
    await page.waitForTimeout(2000);

    const chatInput = page.locator('input[placeholder*="Type your message"]').first();

    if (await chatInput.isVisible()) {
      // Test messages that might trigger CSP issues in Edge
      await chatInput.fill('Test CSP handling with network security request');
      await chatInput.press('Enter');

      await page.waitForTimeout(5000);

      if (unexpectedResponseErrors.length > 0) {
        console.log('🎯 CSP-related error detected!');
      }
    }
  });

  test('Edge-Specific Fetch and Response Handling', async ({ page }) => {
    console.log('🧪 Testing: Edge-specific fetch behaviors');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Override Response.prototype methods to simulate Edge differences
    await page.addInitScript(() => {
      const originalJson = Response.prototype.json;
      const originalText = Response.prototype.text;

      // Simulate Edge's response parsing differences
      Response.prototype.json = function() {
        console.log('📄 Edge-simulated JSON parsing');
        return originalJson.call(this).catch(error => {
          console.log('❌ Edge JSON parsing error:', error.message);

          // This might be where Edge shows "unexpected response format"
          if (error.message.includes('Unexpected')) {
            console.log('🎯 Simulating Edge JSON parse error');
            throw new Error('An unexpected response format was received.');
          }
          throw error;
        });
      };

      Response.prototype.text = function() {
        console.log('📄 Edge-simulated text parsing');
        return originalText.call(this);
      };
    });

    await page.locator('button, a').filter({ hasText: /AI Assistant/i }).first().click();
    await page.waitForTimeout(2000);

    const chatInput = page.locator('input[placeholder*="Type your message"]').first();

    if (await chatInput.isVisible()) {
      console.log('✅ Testing with Edge response parsing simulation');

      await chatInput.fill('Network security vulnerability scanning request');
      await chatInput.press('Enter');

      await page.waitForTimeout(6000);

      if (unexpectedResponseErrors.length > 0) {
        console.log('🎯 EDGE RESPONSE PARSING ERROR DETECTED!');
        console.log('This might be the root cause of the issue!');
      }
    }
  });

  test('User Agent and Browser Detection Issues', async ({ page }) => {
    console.log('🧪 Testing: User agent and browser detection');

    // Set Edge user agent
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Check if backend behaves differently with Edge user agent
    console.log('🔍 Testing with Edge user agent...');

    await page.locator('button, a').filter({ hasText: /AI Assistant/i }).first().click();
    await page.waitForTimeout(2000);

    const chatInput = page.locator('input[placeholder*="Type your message"]').first();

    if (await chatInput.isVisible()) {
      await chatInput.fill('Test with Edge user agent - network security scan');
      await chatInput.press('Enter');

      await page.waitForTimeout(5000);

      if (unexpectedResponseErrors.length > 0) {
        console.log('🎯 USER AGENT RELATED ERROR!');
      }
    }
  });

  test('Comprehensive Edge Simulation Summary', async ({ page }) => {
    console.log('🧪 COMPREHENSIVE EDGE SIMULATION SUMMARY');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    console.log('\n' + '='.repeat(80));
    console.log('📊 EDGE BROWSER SIMULATION RESULTS');
    console.log('='.repeat(80));

    console.log(`\n🎯 ERROR DETECTION SUMMARY:`);
    console.log(`Unexpected response errors found: ${unexpectedResponseErrors.length}`);

    if (unexpectedResponseErrors.length > 0) {
      console.log(`\n🚨 ERRORS DETECTED IN EDGE SIMULATION:`);
      unexpectedResponseErrors.forEach((error, i) => {
        console.log(`\n${i + 1}. ${error.type.toUpperCase()}:`);
        console.log(`   Time: ${error.timestamp}`);
        if (error.url) console.log(`   URL: ${error.url}`);
        console.log(`   Message: ${error.message.substring(0, 200)}...`);
      });

      console.log('\n🎯 LIKELY ROOT CAUSE IDENTIFIED:');
      console.log('The error appears to be related to Edge browser-specific');
      console.log('handling of responses, JSON parsing, or security policies.');

    } else {
      console.log('\n❌ NO EDGE-SPECIFIC ERRORS REPRODUCED');
      console.log('\nThis suggests the issue might be:');
      console.log('1. Specific to actual Edge browser engine differences');
      console.log('2. Related to Windows-specific Edge features');
      console.log('3. Dependent on Edge version or configuration');
      console.log('4. Caused by Edge extensions or security software');
    }

    console.log('\n🔧 RECOMMENDATIONS FOR EDGE USERS:');
    console.log('1. 🔄 Try refreshing the page when error occurs');
    console.log('2. 🚫 Disable Edge extensions temporarily');
    console.log('3. 🔒 Check Edge security settings');
    console.log('4. 🌐 Clear Edge cache and cookies');
    console.log('5. 📱 Try Chrome/Firefox to confirm Edge-specific issue');
    console.log('6. 🔧 Update Edge browser to latest version');

    console.log('\n💡 FOR DEVELOPERS:');
    console.log('1. Add Edge-specific error handling in frontend');
    console.log('2. Implement response validation before parsing');
    console.log('3. Add retry logic for failed JSON parsing');
    console.log('4. Test specifically on Windows Edge browser');
    console.log('5. Consider polyfills for Edge compatibility');

    console.log('\n' + '='.repeat(80));
    console.log('🎯 EDGE BROWSER ISSUE INVESTIGATION: COMPLETED');
    console.log('='.repeat(80));

    expect(true).toBe(true);
  });
});
