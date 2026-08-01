#!/usr/bin/env node
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Test the exact frontend workflow integration scenario
 */

const BACKEND_URL = process.env.BACKEND_URL || 'https://172.16.168.20:8443';

async function testFrontendWorkflowIntegration() {
    console.log('🧪 Testing Frontend Workflow Integration');
    console.log('=====================================');

    const testMessages = [
        'I need to scan my network for security vulnerabilities',
        'Install Docker on my system',
        'Find the best Python web frameworks',
        'What is 2+2?'
    ];

    for (const [index, userMessage] of testMessages.entries()) {
        console.log(`\n${index + 1}. Testing message: "${userMessage}"`);
        console.log('-'.repeat(50));

        try {
            // Exact same call as ChatInterface.vue makes
            const workflowResponse = await fetch(`${BACKEND_URL}/api/workflow/execute`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_message: userMessage,
                    auto_approve: false
                }),
            });

            console.log(`   Status: ${workflowResponse.status}`);

            if (workflowResponse.ok) {
                const workflowResult = await workflowResponse.json();
                console.log(`   ✅ Type: ${workflowResult.type}`);

                if (workflowResult.type === 'workflow_orchestration') {
                    console.log(`   ✅ Workflow ID: ${workflowResult.workflow_id}`);

                    // Test the exact frontend parsing logic
                    if (workflowResult.workflow_response && workflowResult.workflow_response.workflow_preview) {
                        const workflowPreview = workflowResult.workflow_response.workflow_preview;
                        console.log(`   ✅ Workflow preview: ${workflowPreview.length} steps`);

                        // This is exactly what the frontend does
                        const stepsList = workflowPreview
                            .map((step, i) => `${i + 1}. ${step}`)
                            .join('\n');

                        console.log(`   ✅ Steps list formatted successfully`);

                    } else {
                        console.log(`   ❌ Missing workflow_preview in response!`);
                        console.log(`   Response keys:`, Object.keys(workflowResult));
                        if (workflowResult.workflow_response) {
                            console.log(`   Workflow response keys:`, Object.keys(workflowResult.workflow_response));
                        }
                    }
                } else {
                    // Direct execution path
                    console.log(`   ✅ Direct execution detected`);
                    const responseText = workflowResult.result?.response ||
                                       workflowResult.result?.response_text ||
                                       'No response received';
                    console.log(`   ✅ Response text: ${responseText.substring(0, 50)}...`);
                }

                // Wait for workflow execution to complete (if it's a workflow)
                if (workflowResult.type === 'workflow_orchestration') {
                    console.log(`   🔄 Checking workflow status...`);
                    await new Promise(resolve => setTimeout(resolve, 2000)); // Wait 2 seconds

                    const statusResponse = await fetch(`${BACKEND_URL}/api/workflow/workflow/${workflowResult.workflow_id}/status`);
                    if (statusResponse.ok) {
                        const statusData = await statusResponse.json();
                        console.log(`   ✅ Workflow status: ${statusData.status}`);
                    }
                }

            } else {
                console.log(`   ❌ HTTP Error: ${workflowResponse.status}`);
                const errorText = await workflowResponse.text();
                console.log(`   ❌ Error response: ${errorText.substring(0, 200)}...`);

                // Check if this contains our target error message
                if (errorText.includes('An unexpected response format was received')) {
                    console.log(`   🎯 FOUND IT! This is where the error comes from!`);
                    console.log(`   Full error response:`, errorText);
                }
            }

        } catch (error) {
            console.log(`   ❌ Exception: ${error.message}`);
            console.log(`   Exception type: ${error.constructor.name}`);

            // Check if the error message itself contains our target
            if (error.message.includes('An unexpected response format was received')) {
                console.log(`   🎯 FOUND IT! The error is in the exception message!`);
            }
        }
    }

    console.log('\n🎯 Test Results Summary:');
    console.log('========================');
    console.log('If no "FOUND IT!" messages appeared above, the error may occur:');
    console.log('1. During actual workflow step execution (background processing)');
    console.log('2. In WebSocket event handling');
    console.log('3. In specific error conditions not triggered by these tests');
}

testFrontendWorkflowIntegration().catch(console.error);
