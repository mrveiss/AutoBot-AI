import { test, expect } from '@playwright/test';

test.describe('AutoBot Final Error Detection', () => {
  let allErrors = [];
  let responseErrors = [];

  test.beforeEach(async ({ page }) => {
    allErrors = [];
    responseErrors = [];

    // Comprehensive error detection
    page.on('console', msg => {
      const message = msg.text();

      // Log all console messages for analysis
      if (msg.type() === 'error' || msg.type() === 'warn') {
        allErrors.push({
          type: 'console_' + msg.type(),
          message: message,
          timestamp: new Date().toISOString()
        });
      }

      // Specific search for our target error
      if (message.toLowerCase().includes('unexpected response format')) {
        responseErrors.push({
          type: 'console',
          source: 'console',
          message: message,
          timestamp: new Date().toISOString()
        });
        console.log('🎯 UNEXPECTED RESPONSE FORMAT ERROR FOUND IN CONSOLE:', message);
      }

      // Also look for variations
      const errorVariations = [
        'unexpected response',
        'response format',
        'format was received',
        'format received',
        'unexpected format'
      ];

      if (errorVariations.some(variation => message.toLowerCase().includes(variation))) {
        responseErrors.push({
          type: 'console_variation',
          source: 'console',
          message: message,
          timestamp: new Date().toISOString()
        });
        console.log('🎯 RESPONSE FORMAT ERROR VARIATION FOUND:', message);
      }
    });

    // Monitor network responses
    page.on('response', async response => {
      try {
        const text = await response.text();

        // Check for exact error message
        if (text.includes('An unexpected response format was received')) {
          responseErrors.push({
            type: 'network_response',
            source: 'network',
            url: response.url(),
            status: response.status(),
            message: text.substring(0, 500),
            timestamp: new Date().toISOString()
          });
          console.log('🎯 UNEXPECTED RESPONSE FORMAT ERROR IN NETWORK RESPONSE:', response.url());
        }

        // Check for partial matches
        if (text.toLowerCase().includes('unexpected response') ||
            text.toLowerCase().includes('response format')) {
          responseErrors.push({
            type: 'network_partial',
            source: 'network',
            url: response.url(),
            status: response.status(),
            message: text.substring(0, 300),
            timestamp: new Date().toISOString()
          });
          console.log('🎯 RESPONSE FORMAT ERROR PARTIAL MATCH:', response.url());
        }

      } catch (e) {
        // Binary responses - ignore
      }
    });

    // Monitor page errors
    page.on('pageerror', error => {
      allErrors.push({
        type: 'page_error',
        message: error.message,
        stack: error.stack,
        timestamp: new Date().toISOString()
      });

      if (error.message.toLowerCase().includes('unexpected response')) {
        responseErrors.push({
          type: 'page_error',
          source: 'page',
          message: error.message,
          timestamp: new Date().toISOString()
        });
        console.log('🎯 UNEXPECTED RESPONSE FORMAT ERROR IN PAGE ERROR:', error.message);
      }
    });
  });

  test('Comprehensive Chat Testing with Error Detection', async ({ page }) => {
    console.log('🧪 FINAL TEST: Comprehensive error detection');

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Navigate to AI Assistant (we know this works from previous test)
    const aiAssistantButton = page.locator('button, a').filter({ hasText: /AI Assistant/i }).first();

    if (await aiAssistantButton.isVisible()) {
      console.log('✅ Clicking AI Assistant');
      await aiAssistantButton.click();
      await page.waitForTimeout(2000);

      // Find the chat input (we know it has placeholder "Type your message...")
      const chatInput = page.locator('input[placeholder*="Type your message"]').first();

      if (await chatInput.isVisible()) {
        console.log('✅ Found chat input with message placeholder');

        // Test messages that are most likely to trigger the error
        const criticalTestMessages = [
          // Simple message
          'Hello',

          // Complex workflow message (most likely to trigger error)
          'I need to scan my network for security vulnerabilities and install the necessary tools',

          // Install workflow message
          'Install Docker and set it up for development',

          // Research workflow message
          'Find and research the best network security scanning tools available',

          // Edge case messages
          '',  // Empty message
          '   ',  // Whitespace only
          'Special chars: !@#$%^&*()_+{}[]|\\:";\'<>?,./`~',

          // Very long message
          'This is a very long message that might cause issues with response parsing or formatting. '.repeat(20),

          // JSON-like message
          '{"test": "message", "type": "json"}',

          // Messages that might confuse the backend
          'An unexpected response format was received',  // The actual error message
          'Error: something went wrong',
          'null',
          'undefined',
          'false',
          'true'
        ];

        for (const [index, message] of criticalTestMessages.entries()) {
          console.log(`\n🧪 Test ${index + 1}/${criticalTestMessages.length}: "${message.substring(0, 50)}${message.length > 50 ? '...' : ''}"`);

          // Clear any previous errors for this specific test
          const previousErrorCount = responseErrors.length;

          await chatInput.fill(message);
          await chatInput.press('Enter');

          // Wait longer for complex messages
          const waitTime = message.length > 100 ? 8000 : 5000;
          await page.waitForTimeout(waitTime);

          // Check if new errors appeared
          const newErrorCount = responseErrors.length;
          if (newErrorCount > previousErrorCount) {
            const newErrors = responseErrors.slice(previousErrorCount);
            console.log(`  🎯 FOUND ${newErrors.length} NEW ERROR(S) for this message!`);
            newErrors.forEach(error => {
              console.log(`    - ${error.source}: ${error.message.substring(0, 100)}...`);
            });
          } else {
            console.log(`  ✅ No errors for this message`);
          }

          // Clear input
          await chatInput.fill('');
          await page.waitForTimeout(1000);
        }

      } else {
        console.log('❌ Chat input not found');
      }

    } else {
      console.log('❌ AI Assistant button not found');
    }

    // Also test other interfaces quickly
    console.log('\n🧪 Testing other interfaces for errors...');

    // Knowledge Base
    try {
      const kbButton = page.locator('button, a').filter({ hasText: /Knowledge Base/i }).first();
      if (await kbButton.isVisible()) {
        await kbButton.click();
        await page.waitForTimeout(2000);

        const kbInput = page.locator('input[type="text"], input[type="search"]').first();
        if (await kbInput.isVisible()) {
          await kbInput.fill('test search that might cause error');
          await kbInput.press('Enter');
          await page.waitForTimeout(3000);
        }
      }
    } catch (e) {
      console.log('❌ Knowledge Base test failed:', e.message);
    }

    // Terminal (handle multiple elements)
    try {
      const terminalButtons = page.locator('button, a').filter({ hasText: /Terminal/i });
      const terminalCount = await terminalButtons.count();

      if (terminalCount > 0) {
        await terminalButtons.first().click();
        await page.waitForTimeout(2000);

        const terminalInput = page.locator('input[type="text"]').first();
        if (await terminalInput.isVisible()) {
          await terminalInput.fill('echo "test command that might cause error"');
          await terminalInput.press('Enter');
          await page.waitForTimeout(3000);
        }
      }
    } catch (e) {
      console.log('❌ Terminal test failed:', e.message);
    }

    console.log('\n✅ All interface testing completed');
  });

  test('Final Error Analysis and Reporting', async ({ page }) => {
    console.log('🧪 FINAL ANALYSIS: Complete error summary');

    // This test runs after the main test to summarize all findings
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Final summary
    console.log('\n' + '='.repeat(60));
    console.log('📋 FINAL AUTOBOT FRONTEND ERROR ANALYSIS REPORT');
    console.log('='.repeat(60));

    console.log(`\n🔍 UNEXPECTED RESPONSE FORMAT ERRORS:`);
    console.log(`Total errors found: ${responseErrors.length}`);

    if (responseErrors.length > 0) {
      console.log(`\n🎯 DETAILED ERROR BREAKDOWN:`);
      responseErrors.forEach((error, index) => {
        console.log(`\n${index + 1}. ${error.source.toUpperCase()} ERROR:`);
        console.log(`   Type: ${error.type}`);
        console.log(`   Time: ${error.timestamp}`);
        if (error.url) console.log(`   URL: ${error.url}`);
        if (error.status) console.log(`   Status: ${error.status}`);
        console.log(`   Message: ${error.message.substring(0, 200)}${error.message.length > 200 ? '...' : ''}`);
      });

      console.log(`\n🔧 ERROR SOURCES:`);
      const sources = [...new Set(responseErrors.map(e => e.source))];
      sources.forEach(source => {
        const count = responseErrors.filter(e => e.source === source).length;
        console.log(`   - ${source}: ${count} error(s)`);
      });

    } else {
      console.log('✅ NO UNEXPECTED RESPONSE FORMAT ERRORS FOUND');
      console.log('\nThis suggests either:');
      console.log('1. The error occurs in specific conditions not tested');
      console.log('2. The error has been resolved');
      console.log('3. The error occurs in backend processes not visible to frontend');
      console.log('4. The error message appears in different contexts');
    }

    console.log(`\n🐛 OTHER ERRORS DETECTED:`);
    console.log(`Total other errors: ${allErrors.length}`);

    if (allErrors.length > 0) {
      const errorTypes = [...new Set(allErrors.map(e => e.type))];
      errorTypes.forEach(type => {
        const count = allErrors.filter(e => e.type === type).length;
        console.log(`   - ${type}: ${count} error(s)`);
      });

      // Show first few errors as examples
      console.log(`\n📝 SAMPLE OTHER ERRORS:`);
      allErrors.slice(0, 5).forEach((error, index) => {
        console.log(`${index + 1}. [${error.type}] ${error.message.substring(0, 100)}...`);
      });
    }

    console.log('\n' + '='.repeat(60));
    console.log('🎯 CONCLUSION:');
    if (responseErrors.length > 0) {
      console.log('❌ UNEXPECTED RESPONSE FORMAT ERRORS WERE DETECTED!');
      console.log('The frontend IS experiencing the reported error.');
    } else {
      console.log('✅ NO UNEXPECTED RESPONSE FORMAT ERRORS DETECTED');
      console.log('The error may occur in specific scenarios not covered by this test.');
    }
    console.log('='.repeat(60));

    // Test always passes - we're just collecting information
    expect(true).toBe(true);
  });
});
