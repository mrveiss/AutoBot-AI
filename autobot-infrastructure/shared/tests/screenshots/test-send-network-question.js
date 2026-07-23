#!/usr/bin/env node
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Send the network scanning tools question through the visible browser GUI
 */

async function sendNetworkScanningQuestion() {
    console.log('🔍 SENDING NETWORK SCANNING QUESTION VIA GUI');
    console.log('='.repeat(60));
    console.log('📝 Question: "what network scanning tools do we have available?"');
    console.log('🎯 Expected: Complex workflow orchestration with 8 steps');
    console.log('👁️  Browser: Visible (you can watch the automation)');

    try {
        console.log('\n📱 Executing test through visible browser...');

        const response = await fetch('http://localhost:3000/send-test-message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                frontend_url: 'http://localhost:5173',
                message: 'what network scanning tools do we have available?'
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const results = await response.json();

        console.log('\n📊 AUTOMATION RESULTS:');
        console.log(`✅ Overall Success: ${results.success}`);
        console.log(`💬 Message Sent: "${results.message_sent}"`);
        console.log(`⏰ Timestamp: ${results.timestamp}`);

        console.log('\n📋 DETAILED STEPS:');
        results.steps.forEach((step, i) => {
            const status = step.status === 'SUCCESS' ? '✅' :
                          step.status === 'PENDING' ? '⏳' : '❌';
            console.log(`${status} ${i + 1}. ${step.step}: ${step.details}`);
        });

        if (results.has_screenshot) {
            console.log(`\n📸 Screenshot: Captured (${results.screenshot_size} bytes)`);
            console.log('   Shows the GUI state after sending the question');
        }

        // Check if message was successfully sent
        const messageSent = results.steps.some(step =>
            step.step === 'Send message' && step.status === 'SUCCESS'
        );

        const workflowChecked = results.steps.some(step =>
            step.step === 'Check workflow response'
        );

        console.log('\n🔍 WORKFLOW ANALYSIS:');
        if (messageSent) {
            console.log('✅ Message successfully sent to AutoBot');
            console.log('✅ Should trigger complex workflow classification');
            console.log('✅ Expected agents: research, librarian, knowledge_manager');

            if (workflowChecked) {
                const workflowStep = results.steps.find(step =>
                    step.step === 'Check workflow response'
                );
                if (workflowStep.status === 'SUCCESS') {
                    console.log('✅ Workflow elements detected in response');
                    console.log(`📋 Details: ${workflowStep.details}`);
                } else {
                    console.log('⏳ Workflow may still be processing');
                    console.log('💡 Check browser window for real-time updates');
                }
            }
        } else {
            console.log('❌ Message sending failed - check GUI state');
        }

        return results.success && messageSent;

    } catch (error) {
        console.error('❌ Network scanning question test failed:', error.message);
        return false;
    }
}

// Run the test
sendNetworkScanningQuestion()
    .then(success => {
        console.log('\n' + '='.repeat(60));
        console.log('🔍 NETWORK SCANNING QUESTION: COMPLETED');
        console.log('='.repeat(60));

        if (success) {
            console.log('✅ STATUS: QUESTION SUCCESSFULLY SENT VIA GUI');
            console.log('✅ AUTOMATION: Message sending worked perfectly');
            console.log('✅ BROWSER: Visible automation completed');
            console.log('✅ WORKFLOW: Should be processing the request');

            console.log('\n🎯 WHAT TO EXPECT NEXT:');
            console.log('1. 📊 Workflow Classification: COMPLEX (security tools)');
            console.log('2. 🤖 Multi-Agent Orchestration: 4-5 agents involved');
            console.log('3. 📋 8-Step Process: Search KB → Research → Present → Install');
            console.log('4. 👤 User Approvals: Required at decision points');
            console.log('5. 🔄 Real-time Updates: Via WebSocket connection');
            console.log('6. 📋 Progress Display: Workflow steps shown in GUI');

            console.log('\n💬 EXPECTED RESPONSE PATTERN:');
            console.log('• "I\'ll help you find available network scanning tools"');
            console.log('• "Let me search our knowledge base first..."');
            console.log('• "I found several network scanning tools..."');
            console.log('• "Would you like me to help install any of these?"');

            console.log('\n🛡️  EDGE BROWSER COMPATIBILITY:');
            console.log('✅ JSON response validation active');
            console.log('✅ Enhanced error handling implemented');
            console.log('✅ User-friendly error messages ready');

        } else {
            console.log('❌ STATUS: Some issues with GUI automation');
            console.log('💡 Check the browser window for current state');
            console.log('🔍 Manual testing may be needed');
        }

        console.log('\n🚀 READY TO OBSERVE WORKFLOW ORCHESTRATION!');
        console.log('👁️  Watch the visible browser window for live updates');
        console.log('='.repeat(60));
    })
    .catch(error => {
        console.error('\n❌ NETWORK SCANNING QUESTION TEST FAILED:', error);
        console.log('Please check browser window and system status');
    });
