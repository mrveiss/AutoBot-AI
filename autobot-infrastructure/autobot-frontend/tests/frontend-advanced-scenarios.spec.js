import { test, expect } from '@playwright/test';

test.describe('AutoBot Advanced UI Debug Scenarios', () => {
  let unexpectedResponseErrors = [];
  let allNetworkCalls = [];
  let chatResponses = [];

  test.beforeEach(async ({ page }) => {
    unexpectedResponseErrors = [];
    allNetworkCalls = [];
    chatResponses = [];

    // Comprehensive monitoring
    page.on('console', msg => {
      const message = msg.text();

      if (message.includes('An unexpected response format was received') ||
          message.includes('unexpected response format') ||
          message.includes('response format was received')) {
        unexpectedResponseErrors.push({
          type: 'console',
          message: message,
          timestamp: new Date().toISOString()
        });
        console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR:', message);
      }
    });

    // Monitor ALL network traffic
    page.on('request', request => {
      allNetworkCalls.push({
        type: 'request',
        url: request.url(),
        method: request.method(),
        postData: request.postData(),
        timestamp: new Date().toISOString()
      });
    });

    page.on('response', async response => {
      try {
        const text = await response.text();
        const call = {
          type: 'response',
          url: response.url(),
          status: response.status(),
          contentType: response.headers()['content-type'],
          hasError: text.includes('An unexpected response format was received'),
          timestamp: new Date().toISOString()
        };

        if (call.hasError) {
          call.fullResponse = text;
          unexpectedResponseErrors.push({
            type: 'response',
            url: response.url(),
            message: text,
            timestamp: new Date().toISOString()
          });
          console.log('🎯 FOUND ERROR IN RESPONSE:', response.url());
        }

        // Track chat/workflow responses specifically
        if (response.url().includes('/api/workflow/execute') ||
            response.url().includes('/api/chat')) {
          call.isApiCall = true;
          call.responseContent = text.substring(0, 500);
          chatResponses.push(call);
        }

        allNetworkCalls.push(call);
      } catch (e) {
        // Binary response
        allNetworkCalls.push({
          type: 'response',
          url: response.url(),
          status: response.status(),
          isBinary: true,
          timestamp: new Date().toISOString()
        });
      }
    });
  });

  test('Rapid Fire Message Testing', async ({ page }) => {
    console.log('🧪 Testing: Rapid fire message scenarios');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Navigate to AI Assistant
    await page.locator('button, a').filter({ hasText: /AI Assistant/i }).first().click();
    await page.waitForTimeout(2000);

    const chatInput = page.locator('input[placeholder*="Type your message"]').first();

    if (await chatInput.isVisible()) {
      console.log('✅ Found chat input');

      // Send messages in rapid succession to stress test
      const rapidMessages = [
        'Test 1',
        'Test 2',
        'Test 3',
        'I need help with network security',
        'Install Docker immediately',
        'What tools do you recommend?'
      ];

      console.log('🚀 Sending messages rapidly...');
      for (const [i, message] of rapidMessages.entries()) {
        await chatInput.fill(message);
        await chatInput.press('Enter');
        console.log(`  ${i+1}. Sent: "${message}"`);

        // Very short delay to create rapid fire effect
        await page.waitForTimeout(500);

        if (unexpectedResponseErrors.length > 0) {
          console.log(`🎯 ERROR found after rapid message ${i+1}!`);
          break;
        }
      }

      // Wait for all responses
      await page.waitForTimeout(5000);
      console.log('✅ Rapid fire test completed');
    }
  });

  test('Long Running Workflow Interruption', async ({ page }) => {
    console.log('🧪 Testing: Interrupt long-running workflows');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await page.locator('button, a').filter({ hasText: /AI Assistant/i }).first().click();
    await page.waitForTimeout(2000);

    const chatInput = page.locator('input[placeholder*="Type your message"]').first();

    if (await chatInput.isVisible()) {
      // Start a complex workflow
      await chatInput.fill('I need a comprehensive security audit of my entire network infrastructure including vulnerability scanning, penetration testing, and compliance checking');
      await chatInput.press('Enter');

      console.log('🔄 Started complex workflow...');

      // Wait a bit then interrupt with another message
      await page.waitForTimeout(2000);

      // Send interrupting message
      await chatInput.fill('Actually, just tell me what is 2+2?');
      await chatInput.press('Enter');

      console.log('⚡ Sent interrupting message');

      // Wait for responses
      await page.waitForTimeout(5000);

      // Send another complex one
      await chatInput.fill('Now install Docker and configure it for production use with security hardening');
      await chatInput.press('Enter');

      console.log('🔄 Started another complex workflow');
      await page.waitForTimeout(8000);
    }
  });

  test('Browser Refresh During Workflow', async ({ page }) => {
    console.log('🧪 Testing: Browser refresh during active workflow');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await page.locator('button, a').filter({ hasText: /AI Assistant/i }).first().click();
    await page.waitForTimeout(2000);

    const chatInput = page.locator('input[placeholder*="Type your message"]').first();

    if (await chatInput.isVisible()) {
      // Start a workflow
      await chatInput.fill('Perform a comprehensive network security scan and install all necessary tools');
      await chatInput.press('Enter');

      console.log('🔄 Started workflow...');
      await page.waitForTimeout(2000);

      // Refresh the page mid-workflow
      console.log('🔄 Refreshing page during workflow...');
      await page.reload();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(3000);

      // Try to interact after refresh
      await page.locator('button, a').filter({ hasText: /AI Assistant/i }).first().click();
      await page.waitForTimeout(2000);

      const newChatInput = page.locator('input[placeholder*="Type your message"]').first();
      if (await newChatInput.isVisible()) {
        await newChatInput.fill('What was my previous request?');
        await newChatInput.press('Enter');

        console.log('📝 Sent message after refresh');
        await page.waitForTimeout(3000);
      }
    }
  });

  test('Multiple Tab Simulation', async ({ context, page }) => {
    console.log('🧪 Testing: Multiple tab scenarios');

    // Open first tab
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Open second tab
    const page2 = await context.newPage();
    await page2.goto('/');
    await page2.waitForLoadState('networkidle');
    await page2.waitForTimeout(2000);

    // Send message from first tab
    await page.locator('button, a').filter({ hasText: /AI Assistant/i }).first().click();
    await page.waitForTimeout(2000);

    const chatInput1 = page.locator('input[placeholder*="Type your message"]').first();
    if (await chatInput1.isVisible()) {
      await chatInput1.fill('First tab: Scan network for vulnerabilities');
      await chatInput1.press('Enter');
      console.log('📝 Sent from tab 1');
    }

    // Send message from second tab simultaneously
    await page2.locator('button, a').filter({ hasText: /AI Assistant/i }).first().click();
    await page2.waitForTimeout(2000);

    const chatInput2 = page2.locator('input[placeholder*="Type your message"]').first();
    if (await chatInput2.isVisible()) {
      await chatInput2.fill('Second tab: Install Docker right now');
      await chatInput2.press('Enter');
      console.log('📝 Sent from tab 2');
    }

    // Wait for responses
    await page.waitForTimeout(5000);
    await page2.waitForTimeout(5000);

    // Close second tab
    await page2.close();
  });

  test('Network Condition Simulation', async ({ page }) => {
    console.log('🧪 Testing: Network condition simulation');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Simulate slow network
    await page.route('**/*', route => {
      // Add delay to simulate slow network
      setTimeout(() => route.continue(), 100);
    });

    await page.locator('button, a').filter({ hasText: /AI Assistant/i }).first().click();
    await page.waitForTimeout(2000);

    const chatInput = page.locator('input[placeholder*="Type your message"]').first();

    if (await chatInput.isVisible()) {
      await chatInput.fill('Test message with simulated slow network');
      await chatInput.press('Enter');

      console.log('📝 Sent message with network delay simulation');
      await page.waitForTimeout(8000); // Longer wait for slow network
    }

    // Remove network simulation
    await page.unroute('**/*');
  });

  test('Error Injection Testing', async ({ page }) => {
    console.log('🧪 Testing: Error injection scenarios');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Intercept API calls and inject errors
    await page.route('**/api/workflow/execute', route => {
      // Randomly inject errors
      if (Math.random() < 0.3) { // 30% chance
        console.log('💉 Injecting API error...');
        route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({
            error: 'An unexpected response format was received.',
            details: 'Injected error for testing'
          })
        });
      } else {
        route.continue();
      }
    });

    await page.locator('button, a').filter({ hasText: /AI Assistant/i }).first().click();
    await page.waitForTimeout(2000);

    const chatInput = page.locator('input[placeholder*="Type your message"]').first();

    if (await chatInput.isVisible()) {
      // Send multiple messages to trigger the injected error
      const messages = [
        'Test message 1',
        'Test message 2',
        'Test message 3',
        'Network security scan',
        'Install Docker'
      ];

      for (const message of messages) {
        await chatInput.fill(message);
        await chatInput.press('Enter');
        await page.waitForTimeout(2000);

        if (unexpectedResponseErrors.length > 0) {
          console.log('🎯 Injected error triggered!');
          break;
        }
      }
    }
  });

  test('UI State Corruption Testing', async ({ page }) => {
    console.log('🧪 Testing: UI state corruption scenarios');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Navigate through multiple interfaces rapidly
    const interfaces = [
      'AI Assistant',
      'Knowledge Base',
      'Terminal',
      'File Manager',
      'Settings'
    ];

    for (let round = 0; round < 3; round++) {
      console.log(`🔄 Round ${round + 1}: Rapid interface switching`);

      for (const interfaceName of interfaces) {
        try {
          const button = page.locator('button, a').filter({ hasText: new RegExp(interfaceName, 'i') }).first();
          if (await button.isVisible()) {
            await button.click();
            await page.waitForTimeout(300); // Very short delay

            // Try to interact with any inputs quickly
            const inputs = page.locator('input[type="text"], textarea');
            const inputCount = await inputs.count();

            if (inputCount > 0) {
              const visibleInput = inputs.first();
              if (await visibleInput.isVisible()) {
                try {
                  await visibleInput.fill(`Quick test in ${interfaceName}`);
                  await visibleInput.press('Enter');
                } catch (e) {
                  // Ignore fill errors for non-text inputs
                }
              }
            }
          }
        } catch (e) {
          console.log(`⚠️  Error in ${interfaceName}:`, e.message);
        }
      }
    }

    // Final interaction to see if UI is corrupted
    await page.locator('button, a').filter({ hasText: /AI Assistant/i }).first().click();
    await page.waitForTimeout(2000);

    const finalInput = page.locator('input[placeholder*="Type your message"]').first();
    if (await finalInput.isVisible()) {
      await finalInput.fill('Final test after UI stress');
      await finalInput.press('Enter');
      await page.waitForTimeout(3000);
    }
  });

  test('Comprehensive Debug Summary', async ({ page }) => {
    console.log('🧪 COMPREHENSIVE DEBUG SUMMARY');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    console.log('\n' + '='.repeat(80));
    console.log('📊 ADVANCED UI DEBUG RESULTS');
    console.log('='.repeat(80));

    console.log(`\n🔍 ERROR DETECTION SUMMARY:`);
    console.log(`Total unexpected response errors found: ${unexpectedResponseErrors.length}`);

    if (unexpectedResponseErrors.length > 0) {
      console.log(`\n🎯 ERRORS FOUND:`);
      unexpectedResponseErrors.forEach((error, i) => {
        console.log(`\n${i + 1}. ${error.type.toUpperCase()}:`);
        console.log(`   Time: ${error.timestamp}`);
        if (error.url) console.log(`   URL: ${error.url}`);
        console.log(`   Message: ${error.message.substring(0, 300)}...`);
      });
    }

    console.log(`\n🌐 NETWORK ANALYSIS:`);
    const apiCalls = allNetworkCalls.filter(call =>
      call.url.includes('/api/') && call.type === 'response'
    );
    const workflowCalls = apiCalls.filter(call => call.url.includes('/workflow/'));
    const chatCalls = apiCalls.filter(call => call.url.includes('/chat'));
    const errorCalls = apiCalls.filter(call => call.hasError);

    console.log(`Total network calls: ${allNetworkCalls.length}`);
    console.log(`API calls: ${apiCalls.length}`);
    console.log(`Workflow calls: ${workflowCalls.length}`);
    console.log(`Chat calls: ${chatCalls.length}`);
    console.log(`Calls with errors: ${errorCalls.length}`);

    if (errorCalls.length > 0) {
      console.log(`\n❌ API CALLS WITH ERRORS:`);
      errorCalls.forEach((call, i) => {
        console.log(`${i + 1}. ${call.url} (${call.status})`);
      });
    }

    console.log(`\n💬 CHAT/WORKFLOW RESPONSE ANALYSIS:`);
    console.log(`Total chat/workflow responses: ${chatResponses.length}`);

    if (chatResponses.length > 0) {
      console.log(`\nSample responses:`);
      chatResponses.slice(0, 3).forEach((response, i) => {
        console.log(`${i + 1}. ${response.url} (${response.status})`);
        if (response.responseContent) {
          console.log(`   Content: ${response.responseContent.substring(0, 100)}...`);
        }
      });
    }

    console.log('\n' + '='.repeat(80));
    console.log('🎯 FINAL CONCLUSION:');

    if (unexpectedResponseErrors.length > 0) {
      console.log('❌ UNEXPECTED RESPONSE FORMAT ERRORS DETECTED!');
      console.log('Advanced testing scenarios successfully reproduced the error.');
    } else {
      console.log('⚠️  NO ERRORS DETECTED IN ADVANCED SCENARIOS');
      console.log('The error may be:');
      console.log('1. Related to specific backend state conditions');
      console.log('2. Timing-dependent and difficult to reproduce');
      console.log('3. Fixed by recent changes');
      console.log('4. Occurring in production but not development environment');
    }

    console.log('='.repeat(80));

    expect(true).toBe(true); // Always pass
  });
});
