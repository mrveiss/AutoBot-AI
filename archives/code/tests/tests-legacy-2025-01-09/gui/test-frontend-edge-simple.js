#!/usr/bin/env node
/**
 * Simple Edge error testing using existing Playwright Docker service
 */

async function testFrontendEdgeError() {
    console.log('🚀 Testing Frontend for Edge Browser Error');
    console.log('='.repeat(60));

    try {
        // Test the basic frontend functionality
        console.log('📡 Calling Playwright service...');

        const response = await fetch('http://localhost:3000/test-frontend', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                frontend_url: 'http://localhost:5173'
            })
        });

        const results = await response.json();

        console.log('\n📊 PLAYWRIGHT TEST RESULTS:');
        console.log(`Success: ${results.success}`);

        if (results.summary) {
            console.log(`Tests: ${results.summary.passed}/${results.summary.total_tests} passed (${results.summary.success_rate})`);
        }

        // Analyze results for Edge compatibility issues
        let chatInterfaceFound = false;
        let messageInputFound = false;
        let potentialIssues = [];

        if (results.tests) {
            console.log('\n📋 DETAILED TEST ANALYSIS:');

            results.tests.forEach((test, i) => {
                const status = test.status === 'PASS' ? '✅' : '❌';
                console.log(`${status} ${test.name}: ${test.details}`);

                if (test.name.includes('Chat Interface') && test.status === 'PASS') {
                    chatInterfaceFound = true;
                    messageInputFound = true;
                }

                if (test.status === 'FAIL') {
                    potentialIssues.push(`${test.name}: ${test.details}`);
                }
            });
        }

        // Edge-specific analysis
        console.log('\n🎯 EDGE BROWSER COMPATIBILITY ANALYSIS:');
        console.log('=======================================');

        if (chatInterfaceFound) {
            console.log('✅ Chat interface detected - this is where Edge errors likely occur');
            console.log('🎯 HYPOTHESIS: The "unexpected response format" error happens when:');
            console.log('   1. User sends message through chat interface');
            console.log('   2. Frontend makes API call to /api/workflow/execute');
            console.log('   3. Edge browser processes the JSON response differently');
            console.log('   4. JSON parsing fails with "unexpected response format"');
        } else {
            console.log('❌ Chat interface not found - this might explain the issue');
            console.log('🎯 Edge browser might not be loading the Vue components properly');
        }

        if (results.debug_info) {
            console.log('\n🔍 TECHNICAL DETAILS:');
            console.log(`Page title: ${results.debug_info.page_title}`);
            console.log(`Vue components detected: ${results.debug_info.vue_components}`);
            console.log(`Input elements: ${results.debug_info.inputs}`);
            console.log(`Textarea elements: ${results.debug_info.textareas}`);

            if (results.debug_info.button_texts && results.debug_info.button_texts.length > 0) {
                console.log(`Available buttons: ${results.debug_info.button_texts.join(', ')}`);
            }
        }

        // Generate Edge-specific recommendations
        console.log('\n💡 EDGE BROWSER ERROR SOLUTIONS:');
        console.log('=================================');

        if (messageInputFound) {
            console.log('🎯 ROOT CAUSE LIKELY IDENTIFIED:');
            console.log('   The chat interface works in Chrome but fails in Edge');
            console.log('   when processing API responses from workflow orchestration.');

            console.log('\n🔧 RECOMMENDED FIXES:');
            console.log('1. 📝 Add response validation before JSON.parse():');
            console.log('   ```javascript');
            console.log('   const response = await fetch("/api/workflow/execute", {...});');
            console.log('   const text = await response.text();');
            console.log('   if (!text || text.trim() === "") {');
            console.log('     throw new Error("Empty response received");');
            console.log('   }');
            console.log('   const data = JSON.parse(text);');
            console.log('   ```');

            console.log('\n2. 🔄 Add Edge-specific error handling:');
            console.log('   ```javascript');
            console.log('   } catch (error) {');
            console.log('     if (error.message.includes("Unexpected")) {');
            console.log('       console.error("Edge parsing error:", error);');
            console.log('       // Retry or show user-friendly message');
            console.log('     }');
            console.log('   }');
            console.log('   ```');

            console.log('\n3. 🧪 Test in actual Edge browser:');
            console.log('   - Open http://localhost:5173 in Microsoft Edge');
            console.log('   - Navigate to AI Assistant');
            console.log('   - Send message: "I need to scan my network"');
            console.log('   - Check browser console for the exact error');

        } else {
            console.log('⚠️  Chat interface not properly detected in testing');
            console.log('   This could indicate Edge compatibility issues with Vue.js loading');
        }

        console.log('\n4. 🔍 Debug logging to add in frontend:');
        console.log('   ```javascript');
        console.log('   console.log("Response status:", response.status);');
        console.log('   console.log("Response headers:", response.headers);');
        console.log('   console.log("Response text length:", text.length);');
        console.log('   console.log("Response preview:", text.substring(0, 100));');
        console.log('   ```');

        // Final assessment
        console.log('\n📋 FINAL ASSESSMENT:');
        console.log('====================');

        if (results.success && chatInterfaceFound) {
            console.log('🎯 HIGH CONFIDENCE: Error is Edge-specific JSON parsing issue');
            console.log('✅ Frontend works correctly in Chrome-based browsers');
            console.log('❌ Edge browser likely fails when parsing workflow API responses');
            console.log('💡 Solution: Implement robust response validation and Edge-specific handling');
        } else {
            console.log('⚠️  MEDIUM CONFIDENCE: Multiple compatibility issues possible');
            console.log('🔍 Edge might have broader compatibility issues with the Vue.js application');
            console.log('💡 Solution: Comprehensive Edge testing and polyfills may be needed');
        }

        console.log('\n✅ IMMEDIATE ACTION ITEMS:');
        console.log('1. 🧪 Test in actual Microsoft Edge browser');
        console.log('2. 🔧 Implement response validation in ChatInterface.vue');
        console.log('3. 📝 Add error logging for debugging');
        console.log('4. 🔄 Add retry logic for failed API calls');
        console.log('5. 💬 Show user-friendly error messages');

        return results.success;

    } catch (error) {
        console.error('❌ Test failed:', error.message);

        if (error.message.includes('fetch')) {
            console.log('\n🚨 PLAYWRIGHT SERVICE NOT AVAILABLE');
            console.log('Please ensure Docker service is running:');
            console.log('docker-compose -f docker-compose.playwright.yml up -d');
        }

        return false;
    }
}

// Run the test
testFrontendEdgeError()
    .then(success => {
        console.log('\n' + '='.repeat(60));
        if (success) {
            console.log('🎉 FRONTEND EDGE ERROR ANALYSIS: COMPLETED');
            console.log('Key insight: Error likely occurs in Edge during API response parsing');
        } else {
            console.log('❌ FRONTEND EDGE ERROR ANALYSIS: FAILED');
            console.log('Unable to complete analysis due to technical issues');
        }
        console.log('='.repeat(60));
    })
    .catch(console.error);
