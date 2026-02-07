#!/usr/bin/env node
/**
 * Reproduce the specific frontend error "An unexpected response format was received"
 */

async function testFrontendErrorConditions() {
    console.log('🔍 Testing Frontend Error Conditions');
    console.log('================================');

    // Test normal workflow execution
    try {
        console.log('\n1. Testing normal workflow execution...');
        const workflowResponse = await fetch('http://localhost:8001/api/workflow/execute', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                user_message: 'I need to scan my network for security vulnerabilities',
                auto_approve: false
            }),
        });

        console.log(`   Status: ${workflowResponse.status}`);

        if (workflowResponse.ok) {
            const workflowResult = await workflowResponse.json();
            console.log(`   ✅ Response type: ${workflowResult.type}`);
            console.log(`   ✅ Has workflow_id: ${!!workflowResult.workflow_id}`);
            console.log(`   ✅ Has workflow_response: ${!!workflowResult.workflow_response}`);

            // Test the specific conditions the frontend checks
            if (workflowResult.type === 'workflow_orchestration') {
                console.log(`   ✅ Workflow orchestration detected`);

                // Test if workflow_response.workflow_preview exists
                if (workflowResult.workflow_response && workflowResult.workflow_response.workflow_preview) {
                    console.log(`   ✅ Has workflow_preview: ${workflowResult.workflow_response.workflow_preview.length} steps`);
                } else {
                    console.log(`   ❌ Missing workflow_preview!`);
                }
            } else {
                // Test direct execution path
                console.log(`   ✅ Direct execution detected`);
                const responseText = workflowResult.result?.response || workflowResult.result?.response_text || 'No response received';
                console.log(`   ✅ Response text: ${responseText.substring(0, 50)}...`);
            }
        } else {
            console.log(`   ❌ HTTP Error: ${workflowResponse.status}`);
            const errorText = await workflowResponse.text();
            console.log(`   ❌ Error response: ${errorText.substring(0, 100)}...`);
        }

    } catch (error) {
        console.log(`   ❌ Exception caught: ${error.message}`);
        console.log(`   ❌ Error type: ${error.constructor.name}`);
        console.log(`   ❌ Full error:`, error);

        // Test the specific error conditions from frontend
        if (error.message && (
            error.message.includes('Unsupported LLM model type') ||
            error.message.includes('model type') ||
            error.message.includes('LLM') ||
            error.response?.status === 500  // This line might be the problem!
        )) {
            console.log(`   ❌ LLM error detected - would set reload needed`);
        }

        // Check if this could be the "unexpected response format" error
        if (error.message.includes('Unexpected token') || error.message.includes('JSON')) {
            console.log(`   ❌ JSON parsing error - this could be the frontend issue!`);
        }
    }

    // Test invalid JSON response simulation
    console.log('\n2. Testing malformed response handling...');
    try {
        // Test what happens with a malformed response
        const response = await fetch('http://localhost:8001/api/system/health');
        const responseText = await response.text();
        console.log(`   Health endpoint raw response: ${responseText.substring(0, 100)}...`);

        // Try to parse it as JSON like the frontend does
        const jsonData = JSON.parse(responseText);
        console.log(`   ✅ JSON parsing successful`);

    } catch (jsonError) {
        console.log(`   ❌ JSON parsing failed: ${jsonError.message}`);
        console.log(`   This could cause "unexpected response format" error!`);
    }
}

testFrontendErrorConditions().catch(console.error);
