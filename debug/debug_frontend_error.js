#!/usr/bin/env node
/**
 * Debug frontend "unexpected response format" error
 */

// Use Node.js 18+ native fetch
const fetch = globalThis.fetch;

// Backend API configuration (matches NetworkConstants.BACKEND_PORT = 8001)
const BACKEND_URL = 'http://localhost:8001';

async function testWorkflowEndpoint() {
  console.log('🔍 Testing workflow endpoint from frontend perspective...');

  try {
    // Test the exact request the frontend makes
    const response = await fetch(`${BACKEND_URL}/api/workflow/execute`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        user_message: 'I need to scan my network for security vulnerabilities',
        auto_approve: false
      }),
    });

    console.log(`✅ Response status: ${response.status} ${response.statusText}`);
    console.log(`✅ Response headers:`, Object.fromEntries(response.headers));

    const responseText = await response.text();
    console.log(`✅ Response body length: ${responseText.length} characters`);
    console.log(`✅ Response preview: ${responseText.substring(0, 200)}...`);

    try {
      const jsonData = JSON.parse(responseText);
      console.log(`✅ Valid JSON response`);
      console.log(`✅ Response type: ${jsonData.type}`);
      console.log(`✅ Response structure:`, Object.keys(jsonData));

      if (jsonData.type === 'workflow_orchestration') {
        console.log(`✅ Workflow ID: ${jsonData.workflow_id}`);
        console.log(`✅ Planned steps: ${jsonData.workflow_response?.planned_steps}`);
      }

    } catch (parseError) {
      console.log(`❌ JSON parsing error: ${parseError.message}`);
      console.log(`❌ Raw response: ${responseText}`);
    }

  } catch (error) {
    console.log(`❌ Request failed: ${error.message}`);
  }
}

async function testSimpleMessage() {
  console.log('\n🔍 Testing simple message (should use direct execution)...');

  try {
    const response = await fetch(`${BACKEND_URL}/api/workflow/execute`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        user_message: 'What is 2+2?',
        auto_approve: false
      }),
    });

    console.log(`✅ Response status: ${response.status}`);
    const responseText = await response.text();

    try {
      const jsonData = JSON.parse(responseText);
      console.log(`✅ Response type: ${jsonData.type}`);
      console.log(`✅ Result:`, jsonData.result?.response_text || 'No response text');

    } catch (parseError) {
      console.log(`❌ JSON parsing error: ${parseError.message}`);
    }

  } catch (error) {
    console.log(`❌ Request failed: ${error.message}`);
  }
}

async function testChatEndpoint() {
  console.log('\n🔍 Testing traditional chat endpoint...');

  try {
    const response = await fetch(`${BACKEND_URL}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message: 'Hello, how are you?'
      }),
    });

    console.log(`✅ Chat endpoint status: ${response.status}`);
    const responseText = await response.text();

    try {
      const jsonData = JSON.parse(responseText);
      console.log(`✅ Chat response structure:`, Object.keys(jsonData));

    } catch (parseError) {
      console.log(`❌ Chat JSON parsing error: ${parseError.message}`);
      console.log(`❌ Raw response: ${responseText.substring(0, 200)}...`);
    }

  } catch (error) {
    console.log(`❌ Chat request failed: ${error.message}`);
  }
}

async function main() {
  console.log('🚀 Frontend Error Debug Started');
  console.log('==================================');

  await testWorkflowEndpoint();
  await testSimpleMessage();
  await testChatEndpoint();

  console.log('\n🎯 Analysis:');
  console.log('The issue may be:');
  console.log('1. Frontend expects a specific response format');
  console.log('2. Response is valid JSON but frontend parsing fails');
  console.log('3. Frontend error handling is not catching all cases');
  console.log('4. WebSocket or other async issues interfere');
}

main();
