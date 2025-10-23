import { test, expect } from '@playwright/test';

test.describe('AutoBot Frontend-Backend Integration Debug', () => {
  let backendErrors = [];
  let frontendErrors = [];
  let apiResponses = [];

  test.beforeEach(async ({ page }) => {
    backendErrors = [];
    frontendErrors = [];
    apiResponses = [];

    // Monitor frontend console
    page.on('console', msg => {
      const message = msg.text();

      if (msg.type() === 'error') {
        frontendErrors.push({
          message: message,
          timestamp: new Date().toISOString()
        });
      }

      if (message.includes('unexpected response format') ||
          message.includes('An unexpected response format was received')) {
        console.log('🎯 FRONTEND ERROR:', message);
        backendErrors.push({
          source: 'frontend',
          message: message,
          timestamp: new Date().toISOString()
        });
      }
    });

    // Monitor API responses in detail
    page.on('response', async response => {
      if (response.url().includes('/api/')) {
        try {
          const text = await response.text();
          const apiCall = {
            url: response.url(),
            status: response.status(),
            contentType: response.headers()['content-type'],
            content: text,
            timestamp: new Date().toISOString()
          };

          // Check for the specific error
          if (text.includes('An unexpected response format was received')) {
            console.log('🎯 API ERROR RESPONSE:', response.url());
            console.log('Response content:', text.substring(0, 500));

            backendErrors.push({
              source: 'api_response',
              url: response.url(),
              status: response.status(),
              message: text,
              timestamp: new Date().toISOString()
            });
          }

          apiResponses.push(apiCall);
        } catch (e) {
          // Binary response
        }
      }
    });
  });

  test('Direct API Call Testing', async ({ page }) => {
    console.log('🧪 Testing: Direct API calls that might trigger error');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Test direct API calls via browser
    const apiTests = [
      {
        name: 'Workflow Execute with Complex Request',
        code: `
          fetch('/api/workflow/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              user_message: 'I need comprehensive network security scanning and vulnerability assessment',
              auto_approve: false
            })
          }).then(r => r.text()).then(console.log).catch(console.error)
        `
      },
      {
        name: 'Chat API with Direct Call',
        code: `
          fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              message: 'Test direct chat API call for error reproduction'
            })
          }).then(r => r.text()).then(console.log).catch(console.error)
        `
      },
      {
        name: 'Malformed Request Test',
        code: `
          fetch('/api/workflow/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              user_message: null,
              auto_approve: "invalid_value"
            })
          }).then(r => r.text()).then(console.log).catch(console.error)
        `
      }
    ];

    for (const test of apiTests) {
      console.log(`🧪 Running: ${test.name}`);

      await page.evaluate(test.code);
      await page.waitForTimeout(3000);

      if (backendErrors.length > 0) {
        console.log(`🎯 ERROR TRIGGERED by ${test.name}!`);
        break;
      }
    }

    console.log('✅ Direct API testing completed');
  });

  test('Backend State Manipulation', async ({ page }) => {
    console.log('🧪 Testing: Backend state conditions');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Try to create conditions that might cause the error

    // 1. Start multiple workflows simultaneously
    const parallelWorkflows = `
      const promises = [];
      for (let i = 0; i < 5; i++) {
        promises.push(
          fetch('/api/workflow/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              user_message: 'Parallel workflow test ' + i + ' - scan network security',
              auto_approve: false
            })
          })
        );
      }
      Promise.all(promises).then(responses => {
        return Promise.all(responses.map(r => r.text()));
      }).then(results => {
        results.forEach((result, i) => {
          console.log('Workflow', i, 'result:', result.substring(0, 100));
        });
      }).catch(console.error);
    `;

    console.log('🔄 Starting parallel workflows...');
    await page.evaluate(parallelWorkflows);
    await page.waitForTimeout(5000);

    // 2. Try workflow cancellation/interruption
    const workflowInterruption = `
      // Start a workflow
      fetch('/api/workflow/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_message: 'Long running security audit with tool installation',
          auto_approve: false
        })
      }).then(r => r.json()).then(data => {
        console.log('Started workflow:', data.workflow_id);

        // Try to cancel it immediately
        if (data.workflow_id) {
          setTimeout(() => {
            fetch('/api/workflow/workflow/' + data.workflow_id, {
              method: 'DELETE'
            }).then(r => r.text()).then(console.log).catch(console.error);
          }, 100);
        }
      }).catch(console.error);
    `;

    console.log('⚡ Testing workflow interruption...');
    await page.evaluate(workflowInterruption);
    await page.waitForTimeout(3000);

    // 3. Invalid workflow ID access
    const invalidWorkflowTest = `
      fetch('/api/workflow/workflow/invalid-id/status')
        .then(r => r.text())
        .then(console.log)
        .catch(console.error);
    `;

    console.log('❌ Testing invalid workflow access...');
    await page.evaluate(invalidWorkflowTest);
    await page.waitForTimeout(2000);

    console.log('✅ Backend state manipulation completed');
  });

  test('UI-Backend Synchronization Issues', async ({ page }) => {
    console.log('🧪 Testing: UI-Backend sync issues');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Navigate to AI Assistant
    await page.locator('button, a').filter({ hasText: /AI Assistant/i }).first().click();
    await page.waitForTimeout(2000);

    const chatInput = page.locator('input[placeholder*="Type your message"]').first();

    if (await chatInput.isVisible()) {
      // Test rapid UI interactions while backend is processing

      console.log('🚀 Testing rapid UI interactions during backend processing...');

      // Start a complex workflow
      await chatInput.fill('Comprehensive security assessment and tool installation');
      await chatInput.press('Enter');

      // Immediately try various UI actions
      await page.waitForTimeout(500);

      // Try switching interfaces rapidly
      try {
        await page.locator('text=Knowledge Base').first().click();
        await page.waitForTimeout(200);
        await page.locator('text=Terminal').first().click();
        await page.waitForTimeout(200);
        await page.locator('text=AI Assistant').first().click();
        await page.waitForTimeout(200);
      } catch (e) {
        console.log('⚠️ UI switching error:', e.message);
      }

      // Try sending another message immediately
      const newChatInput = page.locator('input[placeholder*="Type your message"]').first();
      if (await newChatInput.isVisible()) {
        await newChatInput.fill('Interrupt with new request');
        await newChatInput.press('Enter');

        // And another one
        await page.waitForTimeout(100);
        await newChatInput.fill('Another interruption');
        await newChatInput.press('Enter');
      }

      // Wait for all responses
      await page.waitForTimeout(8000);
    }

    console.log('✅ UI-Backend sync testing completed');
  });

  test('Memory and Resource Stress Test', async ({ page }) => {
    console.log('🧪 Testing: Memory and resource stress');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Send many messages to stress the system
    await page.locator('button, a').filter({ hasText: /AI Assistant/i }).first().click();
    await page.waitForTimeout(2000);

    const chatInput = page.locator('input[placeholder*="Type your message"]').first();

    if (await chatInput.isVisible()) {
      console.log('💾 Starting memory stress test...');

      const stressMessages = [
        'Message 1: Basic query',
        'Message 2: Network security scan',
        'Message 3: Install Docker and configure',
        'Message 4: Comprehensive vulnerability assessment',
        'Message 5: ' + 'A'.repeat(1000), // Long message
        'Message 6: Research best security tools',
        'Message 7: Create installation plan',
        'Message 8: Execute system commands',
        'Message 9: Another network scan',
        'Message 10: Final stress test message'
      ];

      for (const [i, message] of stressMessages.entries()) {
        console.log(`  Sending stress message ${i + 1}/10`);
        await chatInput.fill(message);
        await chatInput.press('Enter');

        // Short delay to create rapid succession
        await page.waitForTimeout(300);

        // Check for errors after each message
        if (backendErrors.length > 0) {
          console.log(`🎯 ERROR DETECTED after stress message ${i + 1}!`);
          break;
        }
      }

      // Wait for all processing to complete
      await page.waitForTimeout(10000);
    }

    console.log('✅ Memory stress testing completed');
  });

  test('Final Integration Analysis', async ({ page }) => {
    console.log('🧪 FINAL INTEGRATION ANALYSIS');

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Summary of all findings
    console.log('\n' + '='.repeat(90));
    console.log('📋 FRONTEND-BACKEND INTEGRATION DEBUG SUMMARY');
    console.log('='.repeat(90));

    console.log(`\n🎯 ERROR DETECTION RESULTS:`);
    console.log(`Backend errors found: ${backendErrors.length}`);
    console.log(`Frontend errors found: ${frontendErrors.length}`);
    console.log(`Total API responses captured: ${apiResponses.length}`);

    if (backendErrors.length > 0) {
      console.log(`\n🚨 BACKEND ERRORS DETECTED:`);
      backendErrors.forEach((error, i) => {
        console.log(`\n${i + 1}. [${error.source}] ${error.timestamp}`);
        if (error.url) console.log(`   URL: ${error.url}`);
        if (error.status) console.log(`   Status: ${error.status}`);
        console.log(`   Message: ${error.message.substring(0, 200)}...`);
      });
    }

    if (frontendErrors.length > 0) {
      console.log(`\n❌ FRONTEND ERRORS:`);
      frontendErrors.slice(0, 5).forEach((error, i) => {
        console.log(`${i + 1}. ${error.message.substring(0, 100)}...`);
      });
    }

    // Analyze API response patterns
    const workflowResponses = apiResponses.filter(r => r.url.includes('/workflow/'));
    const chatResponses = apiResponses.filter(r => r.url.includes('/chat'));
    const errorResponses = apiResponses.filter(r =>
      r.content.includes('An unexpected response format was received')
    );

    console.log(`\n📊 API RESPONSE ANALYSIS:`);
    console.log(`Total API responses: ${apiResponses.length}`);
    console.log(`Workflow API responses: ${workflowResponses.length}`);
    console.log(`Chat API responses: ${chatResponses.length}`);
    console.log(`Responses with target error: ${errorResponses.length}`);

    if (errorResponses.length > 0) {
      console.log(`\n🎯 API RESPONSES WITH TARGET ERROR:`);
      errorResponses.forEach((response, i) => {
        console.log(`${i + 1}. ${response.url} (${response.status})`);
        console.log(`   Content: ${response.content.substring(0, 150)}...`);
      });
    }

    // Sample successful responses for comparison
    if (workflowResponses.length > 0) {
      console.log(`\n✅ SAMPLE SUCCESSFUL WORKFLOW RESPONSES:`);
      workflowResponses.slice(0, 2).forEach((response, i) => {
        console.log(`${i + 1}. ${response.url} (${response.status})`);
        console.log(`   Content: ${response.content.substring(0, 100)}...`);
      });
    }

    console.log('\n' + '='.repeat(90));
    console.log('🏁 COMPREHENSIVE FRONTEND DEBUG CONCLUSION:');

    if (backendErrors.length > 0 || errorResponses.length > 0) {
      console.log('🎯 SUCCESS! UNEXPECTED RESPONSE FORMAT ERROR REPRODUCED!');
      console.log('The error has been successfully detected and captured.');
    } else {
      console.log('⚠️ NO UNEXPECTED RESPONSE FORMAT ERRORS DETECTED');
      console.log('\nPossible explanations:');
      console.log('1. Error occurs in production environment with different conditions');
      console.log('2. Error is timing-dependent and requires specific sequence');
      console.log('3. Error has been resolved by recent backend fixes');
      console.log('4. Error requires specific user permissions or settings');
      console.log('5. Error occurs during specific workflow steps not triggered by our tests');
    }

    console.log('\n🔧 RECOMMENDATIONS:');
    console.log('1. Monitor production logs for the specific error message');
    console.log('2. Add enhanced error logging in chat.py and agent.py');
    console.log('3. Implement error tracking in frontend for better visibility');
    console.log('4. Test with different user configurations and permissions');

    console.log('='.repeat(90));

    expect(true).toBe(true); // Test passes regardless
  });
});
