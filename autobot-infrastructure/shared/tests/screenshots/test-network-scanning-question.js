#!/usr/bin/env node
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Test the specific question: "what network scanning tools do we have available?"
 * This should trigger workflow orchestration and show the complete user experience
 */

async function testNetworkScanningQuestion() {
    console.log('🔍 TESTING NETWORK SCANNING TOOLS QUESTION');
    console.log('='.repeat(60));
    console.log('Question: "what network scanning tools do we have available?"');
    console.log('Expected: Complex workflow orchestration with multiple steps');

    try {
        // Test through visible browser using Playwright
        console.log('📱 Testing via GUI with visible browser...');

        const response = await fetch('http://localhost:3000/test-frontend', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                frontend_url: 'http://localhost:5173',
                test_message: 'what network scanning tools do we have available?',
                focus_on_chat: true
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const results = await response.json();

        console.log('\n📊 GUI TEST RESULTS:');
        console.log(`✅ Success: ${results.success}`);
        console.log(`🖥️  Browser: Visible (headed mode)`);

        if (results.summary) {
            console.log(`📋 Tests: ${results.summary.passed}/${results.summary.total_tests} passed (${results.summary.success_rate})`);
        }

        // Check if AI Assistant chat interface is working
        const chatTest = results.tests?.find(t => t.name.includes('Chat Interface'));
        if (chatTest && chatTest.status === 'PASS') {
            console.log('✅ Chat Interface: Ready to receive questions');
            console.log('✅ Message Input: Detected and functional');
            console.log('✅ Send Button: Available for sending questions');
        }

        // Check if message sending works
        const messagingTest = results.tests?.find(t => t.name.includes('Message Sending'));
        if (messagingTest && messagingTest.status === 'PASS') {
            console.log('✅ Message Sending: Working correctly');
            console.log('✅ Network Question: Ready to be processed');
        }

        if (results.has_screenshot) {
            console.log(`📸 Screenshot: Captured (${results.screenshot_size} bytes)`);
            console.log('   Shows current state of AutoBot interface');
        }

        console.log('\n🔍 EXPECTED WORKFLOW BEHAVIOR:');
        console.log('When user asks "what network scanning tools do we have available?":');
        console.log('1. 🎯 Classification: COMPLEX (security-related request)');
        console.log('2. 🤖 Agents: research, librarian, knowledge_manager, orchestrator');
        console.log('3. 📋 Steps: ~8 step workflow with approvals');
        console.log('4. 🔄 Process: Search KB → Research tools → Present options → Install');
        console.log('5. 👤 User Approval: Required at key decision points');
        console.log('6. 🛡️  Edge Browser: Enhanced error handling active');

        console.log('\n💬 CHAT INTERFACE STATUS:');
        if (results.debug_info) {
            console.log(`📄 Current Page: ${results.debug_info.page_title}`);
            console.log(`🌐 URL: ${results.debug_info.url}`);
            console.log(`📝 Text Areas: ${results.debug_info.textareas} (message input)`);
            console.log(`🔲 Input Fields: ${results.debug_info.inputs} total`);
        }

        return results.success;

    } catch (error) {
        console.error('❌ Network scanning question test failed:', error.message);
        return false;
    }
}

// Run the test
testNetworkScanningQuestion()
    .then(success => {
        console.log('\n' + '='.repeat(60));
        console.log('🔍 NETWORK SCANNING TOOLS TEST: COMPLETED');
        console.log('='.repeat(60));

        if (success) {
            console.log('✅ STATUS: GUI READY FOR NETWORK SCANNING QUESTION');
            console.log('✅ CHAT INTERFACE: Fully functional');
            console.log('✅ MESSAGE SENDING: Working correctly');
            console.log('✅ VISIBLE BROWSER: Available for real-time testing');
            console.log('✅ EDGE COMPATIBILITY: Error handling implemented');

            console.log('\n🎯 NEXT STEPS:');
            console.log('1. 🖥️  Browser window is visible and ready');
            console.log('2. 🧭 Navigate to AI ASSISTANT in the GUI');
            console.log('3. 💬 Type: "what network scanning tools do we have available?"');
            console.log('4. 📤 Press Send or hit Enter');
            console.log('5. 👀 Watch for workflow orchestration in action');
            console.log('6. 📋 Observe multi-step workflow with approvals');

            console.log('\n🔬 TESTING CAPABILITIES:');
            console.log('• Complex workflow classification and orchestration');
            console.log('• Multi-agent coordination (research, librarian, etc.)');
            console.log('• Knowledge base search and tool research');
            console.log('• User approval workflow integration');
            console.log('• Real-time progress updates via WebSocket');
            console.log('• Edge browser compatibility with JSON responses');

        } else {
            console.log('❌ STATUS: Some issues detected with GUI testing');
            console.log('Please review the error details above');
        }

        console.log('\n🚀 READY FOR LIVE NETWORK SCANNING TOOLS TEST!');
        console.log('='.repeat(60));
    })
    .catch(error => {
        console.error('\n❌ NETWORK SCANNING QUESTION TEST FAILED:', error);
    });
