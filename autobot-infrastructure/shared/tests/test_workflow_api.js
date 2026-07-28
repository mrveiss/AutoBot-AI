#!/usr/bin/env node
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Simple test to verify WorkflowApproval API fix
 * Tests the specific 404 error we fixed
 */

const fetch = require('node-fetch');

async function testWorkflowApiFix() {
    console.log('🧪 Testing WorkflowApproval API Fix');
    console.log('=' * 40);

    try {
        // Test the FIXED endpoint (should work)
        console.log('📡 Testing FIXED endpoint: /api/workflow/workflows');
        const response = await fetch('http://localhost:8001/api/workflow/workflows');

        console.log(`Status: ${response.status}`);

        if (response.status === 404) {
            console.log('❌ FIXED endpoint still returns 404 - API might be down');
            return false;
        } else if (response.status === 200) {
            console.log('✅ FIXED endpoint working correctly!');
            const data = await response.json();
            console.log('Response data:', JSON.stringify(data, null, 2));
            return true;
        } else {
            console.log(`⚠️ FIXED endpoint returns ${response.status} - unusual but not 404`);
            return true;
        }

    } catch (error) {
        console.log('❌ Error testing API:', error.message);
        return false;
    }
}

async function testOldBrokenEndpoint() {
    console.log('\n📡 Testing OLD BROKEN endpoint (should return 404): /api/workflow/workflow/workflows');

    try {
        const response = await fetch('http://localhost:8001/api/workflow/workflow/workflows');
        console.log(`Status: ${response.status}`);

        if (response.status === 404) {
            console.log('✅ OLD endpoint correctly returns 404 (as expected)');
            return true;
        } else {
            console.log(`⚠️ OLD endpoint returns ${response.status} - unexpected`);
            return false;
        }

    } catch (error) {
        console.log('❌ Error testing old endpoint:', error.message);
        return false;
    }
}

async function main() {
    console.log('🚀 WorkflowApproval 404 Fix Verification');
    console.log('====================================================');

    const fixedEndpointWorks = await testWorkflowApiFix();
    const oldEndpointBroken = await testOldBrokenEndpoint();

    console.log('\n📊 TEST RESULTS:');
    console.log('====================================================');

    if (fixedEndpointWorks && oldEndpointBroken) {
        console.log('✅ PASS: WorkflowApproval 404 fix is working correctly!');
        console.log('   └─ Fixed endpoint works, old broken endpoint properly returns 404');
        return true;
    } else if (fixedEndpointWorks && !oldEndpointBroken) {
        console.log('⚠️ PARTIAL: Fixed endpoint works, but old endpoint behavior unexpected');
        console.log('   └─ The fix is working, but old endpoint response is unusual');
        return true;
    } else if (!fixedEndpointWorks) {
        console.log('❌ FAIL: Fixed endpoint not working - backend might be down');
        console.log('   └─ Make sure AutoBot backend is running on localhost:8001');
        return false;
    }
}

if (require.main === module) {
    main().then(success => {
        process.exit(success ? 0 : 1);
    }).catch(error => {
        console.error('💥 Test failed with error:', error.message);
        process.exit(1);
    });
}
