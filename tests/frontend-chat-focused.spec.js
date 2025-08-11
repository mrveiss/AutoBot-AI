import { test, expect } from '@playwright/test';

test.describe('AutoBot Frontend Chat Interface Testing', () => {
  let unexpectedResponseErrors = [];
  let allConsoleMessages = [];
  let networkResponses = [];

  test.beforeEach(async ({ page }) => {
    unexpectedResponseErrors = [];
    allConsoleMessages = [];
    networkResponses = [];

    // Capture all console messages
    page.on('console', msg => {
      const message = msg.text();
      allConsoleMessages.push({
        type: msg.type(),
        message: message,
        timestamp: new Date().toISOString()
      });

      // Look for our specific error message
      if (message.includes('An unexpected response format was received')) {
        unexpectedResponseErrors.push({
          type: 'console',
          message: message,
          timestamp: new Date().toISOString()
        });
        console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR IN CONSOLE:', message);
      }

      // Also log errors and warnings
      if (msg.type() === 'error') {
        console.log('❌ Console Error:', message);
      }
    });

    // Monitor network responses
    page.on('response', async response => {
      try {
        const text = await response.text();
        const responseData = {
          url: response.url(),
          status: response.status(),
          contentType: response.headers()['content-type'] || 'unknown',
          hasUnexpectedError: text.includes('An unexpected response format was received'),
          timestamp: new Date().toISOString()
        };

        if (responseData.hasUnexpectedError) {
          responseData.content = text;
          unexpectedResponseErrors.push({
            type: 'response',
            url: response.url(),
            message: text,
            timestamp: new Date().toISOString()
          });
          console.log('🎯 FOUND UNEXPECTED RESPONSE ERROR IN RESPONSE:', response.url());
        }

        networkResponses.push(responseData);
      } catch (e) {
        // Binary responses can't be converted to text
      }
    });
  });

  test('Navigate to AI Assistant and Test Chat Input', async ({ page }) => {
    console.log('🧪 Testing: AI Assistant chat interface');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Click AI Assistant
    const aiAssistantButton = page.locator('text=AI Assistant');
    if (await aiAssistantButton.isVisible()) {
      console.log('✅ Found AI Assistant button - clicking');
      await aiAssistantButton.click();
      await page.waitForTimeout(2000);

      // Take screenshot
      await page.screenshot({ path: 'debug-ai-assistant.png' });

      // Look for text input or textarea elements (not checkboxes)
      const textInputs = page.locator('input[type="text"], textarea, input:not([type="checkbox"]):not([type="range"])');
      const textInputCount = await textInputs.count();

      console.log(`📋 Found ${textInputCount} text input elements`);

      for (let i = 0; i < textInputCount; i++) {
        const input = textInputs.nth(i);
        const type = await input.getAttribute('type') || 'text';
        const placeholder = await input.getAttribute('placeholder') || '';
        const visible = await input.isVisible();

        console.log(`  Input ${i}: type="${type}", placeholder="${placeholder}", visible=${visible}`);

        if (visible && (type === 'text' || input.locator('textarea').count() > 0)) {
          console.log(`🧪 Testing input ${i} for chat functionality`);

          // Test different types of messages
          const testMessages = [
            'Hello, can you help me?',
            'What is 2+2?',
            'I need to scan my network for security vulnerabilities',
            'Install Docker on my system',
            'Find the best Python web frameworks'
          ];

          for (const message of testMessages) {
            console.log(`  🧪 Testing message: "${message}"`);

            await input.fill(message);

            // Try sending via Enter
            try {
              await input.press('Enter');
              console.log('  ✅ Sent via Enter key');

              // Wait for response
              await page.waitForTimeout(3000);

              // Check for errors
              if (unexpectedResponseErrors.length > 0) {
                console.log(`  🎯 FOUND ERROR for message: "${message}"`);
                console.log('  Error details:', JSON.stringify(unexpectedResponseErrors.slice(-1), null, 2));
              }

            } catch (e) {
              console.log('  ❌ Enter key failed, trying send button');

              // Look for send button
              const sendButton = page.locator('button').filter({ hasText: /send|submit/i }).first();
              if (await sendButton.isVisible()) {
                await sendButton.click();
                console.log('  ✅ Sent via button click');

                await page.waitForTimeout(3000);

                if (unexpectedResponseErrors.length > 0) {
                  console.log(`  🎯 FOUND ERROR for message: "${message}"`);
                  console.log('  Error details:', JSON.stringify(unexpectedResponseErrors.slice(-1), null, 2));
                }
              }
            }

            // Clear input for next test
            await input.fill('');
            await page.waitForTimeout(1000);
          }

          break; // Only test the first viable input
        }
      }
    }

    console.log('✅ AI Assistant testing completed');
  });

  test('Test Knowledge Base Interface', async ({ page }) => {
    console.log('🧪 Testing: Knowledge Base interface');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Click Knowledge Base
    const knowledgeBaseButton = page.locator('text=Knowledge Base');
    if (await knowledgeBaseButton.isVisible()) {
      console.log('✅ Found Knowledge Base button - clicking');
      await knowledgeBaseButton.click();
      await page.waitForTimeout(2000);

      // Take screenshot
      await page.screenshot({ path: 'debug-knowledge-base.png' });

      // Look for search or input fields
      const searchInputs = page.locator('input[type="text"], input[type="search"], textarea, input[placeholder*="search"], input[placeholder*="query"]');
      const searchInputCount = await searchInputs.count();

      console.log(`📋 Found ${searchInputCount} search/input elements`);

      for (let i = 0; i < searchInputCount; i++) {
        const input = searchInputs.nth(i);
        const placeholder = await input.getAttribute('placeholder') || '';
        const visible = await input.isVisible();

        if (visible) {
          console.log(`🧪 Testing Knowledge Base input ${i}: "${placeholder}"`);

          await input.fill('network security vulnerability scanning');

          // Try submitting
          try {
            await input.press('Enter');
            console.log('✅ Submitted KB search via Enter');

            await page.waitForTimeout(3000);

            if (unexpectedResponseErrors.length > 0) {
              console.log('🎯 FOUND ERROR in Knowledge Base search!');
              console.log(JSON.stringify(unexpectedResponseErrors.slice(-1), null, 2));
            }

          } catch (e) {
            // Try clicking search button
            const searchButton = page.locator('button').filter({ hasText: /search|find|query/i }).first();
            if (await searchButton.isVisible()) {
              await searchButton.click();
              console.log('✅ Submitted KB search via button');

              await page.waitForTimeout(3000);

              if (unexpectedResponseErrors.length > 0) {
                console.log('🎯 FOUND ERROR in Knowledge Base search!');
                console.log(JSON.stringify(unexpectedResponseErrors.slice(-1), null, 2));
              }
            }
          }
        }
      }
    }

    console.log('✅ Knowledge Base testing completed');
  });

  test('Test Terminal Interface', async ({ page }) => {
    console.log('🧪 Testing: Terminal interface');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Click Terminal
    const terminalButton = page.locator('text=Terminal');
    if (await terminalButton.isVisible()) {
      console.log('✅ Found Terminal button - clicking');
      await terminalButton.click();
      await page.waitForTimeout(2000);

      // Take screenshot
      await page.screenshot({ path: 'debug-terminal.png' });

      // Look for terminal input
      const terminalInputs = page.locator('input[type="text"], textarea, [class*="terminal"] input, [class*="console"] input');
      const terminalInputCount = await terminalInputs.count();

      console.log(`📋 Found ${terminalInputCount} terminal input elements`);

      for (let i = 0; i < terminalInputCount; i++) {
        const input = terminalInputs.nth(i);
        const visible = await input.isVisible();

        if (visible) {
          console.log(`🧪 Testing Terminal input ${i}`);

          // Test some commands that might trigger the error
          const commands = [
            'help',
            'ls',
            'whoami',
            'echo "test message"'
          ];

          for (const command of commands) {
            console.log(`  🧪 Testing command: "${command}"`);

            await input.fill(command);
            await input.press('Enter');

            await page.waitForTimeout(2000);

            if (unexpectedResponseErrors.length > 0) {
              console.log(`  🎯 FOUND ERROR for command: "${command}"`);
              console.log('  Error details:', JSON.stringify(unexpectedResponseErrors.slice(-1), null, 2));
            }

            // Clear for next command
            await input.fill('');
            await page.waitForTimeout(500);
          }
        }
      }
    }

    console.log('✅ Terminal testing completed');
  });

  test('Comprehensive Error Summary and Network Analysis', async ({ page }) => {
    console.log('🧪 Testing: Comprehensive error analysis');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Go through all major interfaces one by one
    const interfaces = ['AI Assistant', 'Knowledge Base', 'Terminal'];

    for (const interfaceName of interfaces) {
      console.log(`\n🧪 Testing ${interfaceName} for errors...`);

      const button = page.locator(`text=${interfaceName}`);
      if (await button.isVisible()) {
        await button.click();
        await page.waitForTimeout(2000);

        // Try to find and interact with any input
        const inputs = page.locator('input[type="text"], textarea').filter({ hasText: '' }); // Empty filter to get all
        const inputCount = await inputs.count();

        for (let i = 0; i < inputCount; i++) {
          const input = inputs.nth(i);
          const visible = await input.isVisible();

          if (visible) {
            try {
              await input.fill('Test message for error detection');
              await input.press('Enter');
              await page.waitForTimeout(2000);

              if (unexpectedResponseErrors.length > 0) {
                console.log(`🎯 ERROR found in ${interfaceName}!`);
              }
            } catch (e) {
              // Ignore fill errors for non-text inputs
            }
          }
        }
      }
    }

    // Final comprehensive summary
    console.log('\n📋 COMPREHENSIVE TEST SUMMARY');
    console.log('==============================');
    console.log(`Total console messages: ${allConsoleMessages.length}`);
    console.log(`Total network responses: ${networkResponses.length}`);
    console.log(`Total unexpected response errors: ${unexpectedResponseErrors.length}`);

    if (unexpectedResponseErrors.length > 0) {
      console.log('\n🎯 ALL UNEXPECTED RESPONSE ERRORS FOUND:');
      console.log(JSON.stringify(unexpectedResponseErrors, null, 2));
    }

    // Analyze network responses
    const errorResponses = networkResponses.filter(r => r.hasUnexpectedError);
    const apiCalls = networkResponses.filter(r => r.url.includes('/api/'));
    const workflowCalls = apiCalls.filter(r => r.url.includes('/workflow/'));
    const chatCalls = apiCalls.filter(r => r.url.includes('/chat'));

    console.log('\n🌐 NETWORK ANALYSIS:');
    console.log(`API calls made: ${apiCalls.length}`);
    console.log(`Workflow API calls: ${workflowCalls.length}`);
    console.log(`Chat API calls: ${chatCalls.length}`);
    console.log(`Responses with errors: ${errorResponses.length}`);

    if (errorResponses.length > 0) {
      console.log('\n❌ ERROR RESPONSES:');
      errorResponses.forEach((response, i) => {
        console.log(`${i + 1}. ${response.url} (${response.status})`);
      });
    }

    // Console error analysis
    const consoleErrors = allConsoleMessages.filter(m => m.type === 'error');
    const consoleWarnings = allConsoleMessages.filter(m => m.type === 'warn');

    console.log(`\nConsole errors: ${consoleErrors.length}`);
    console.log(`Console warnings: ${consoleWarnings.length}`);

    if (consoleErrors.length > 0) {
      console.log('\n❌ CONSOLE ERRORS:');
      consoleErrors.forEach((error, i) => {
        console.log(`${i + 1}. ${error.message}`);
      });
    }

    console.log('\n✅ Comprehensive error analysis completed');

    // Test passes regardless - we're collecting data
    expect(true).toBe(true);
  });
});
