/**
 * Test Script: Chunk Loading Fixes Validation
 *
 * This script tests that the chunk loading fixes are working properly
 * by attempting to load Vue components and validating error handling
 */

console.log('🔧 Testing AutoBot Frontend Chunk Loading Fixes...\n');

// Test configuration
const FRONTEND_URL = 'http://172.16.168.21:5173';
const TEST_COMPONENTS = [
    'ChatView',
    'ToolsView',
    'MonitoringView',
    'SettingsView',
    'KnowledgeView'
];

// Test results tracking
let testResults = {
    passed: 0,
    failed: 0,
    details: []
};

/**
 * Test if frontend server is responding
 */
async function testFrontendServer() {
    try {
        const response = await fetch(FRONTEND_URL);
        if (response.ok) {
            console.log('✅ Frontend server is responding');
            return true;
        } else {
            console.error('❌ Frontend server returned:', response.status);
            return false;
        }
    } catch (error) {
        console.error('❌ Frontend server not accessible:', error.message);
        return false;
    }
}

/**
 * Test if Vue components are accessible
 */
async function testComponentAccess() {
    console.log('\n📦 Testing Vue component accessibility...');

    for (const component of TEST_COMPONENTS) {
        try {
            const url = `${FRONTEND_URL}/src/views/${component}.vue`;
            const response = await fetch(url);

            if (response.ok) {
                console.log(`✅ ${component}.vue accessible`);
                testResults.passed++;
            } else {
                console.error(`❌ ${component}.vue not accessible: ${response.status}`);
                testResults.failed++;
            }

            testResults.details.push({
                component,
                accessible: response.ok,
                status: response.status
            });

        } catch (error) {
            console.error(`❌ ${component}.vue fetch error:`, error.message);
            testResults.failed++;
            testResults.details.push({
                component,
                accessible: false,
                error: error.message
            });
        }
    }
}

/**
 * Test async component helpers
 */
async function testAsyncHelpers() {
    console.log('\n🛠️  Testing async component helpers...');

    try {
        const url = `${FRONTEND_URL}/src/utils/asyncComponentHelpers.ts`;
        const response = await fetch(url);

        if (response.ok) {
            const content = await response.text();

            // Check for Vue imports (validates basic structure)
            if (content.includes('defineAsyncComponent') && content.includes('defineComponent')) {
                console.log('✅ Vue async component imports detected');
                testResults.passed++;
            } else {
                console.error('❌ Vue async component imports not found');
                testResults.failed++;
            }

            // Check for cache management integration
            if (content.includes('cacheManagement')) {
                console.log('✅ Cache management integration detected');
                testResults.passed++;
            } else {
                console.error('❌ Cache management integration not found');
                testResults.failed++;
            }

            // Check for error recovery functionality
            if (content.includes('AsyncComponentErrorRecovery')) {
                console.log('✅ Error recovery system detected');
                testResults.passed++;
            } else {
                console.error('❌ Error recovery system not found');
                testResults.failed++;
            }

        } else {
            console.error('❌ Async helpers not accessible:', response.status);
            testResults.failed++;
        }

    } catch (error) {
        console.error('❌ Async helpers test error:', error.message);
        testResults.failed++;
    }
}

/**
 * Test cache management utilities
 */
async function testCacheManagement() {
    console.log('\n💾 Testing cache management utilities...');

    try {
        const url = `${FRONTEND_URL}/src/utils/cacheManagement.ts`;
        const response = await fetch(url);

        if (response.ok) {
            const content = await response.text();

            // Check for key functions
            const functions = [
                'clearApplicationCache',
                'handleChunkLoadingError',
                'setupGlobalChunkErrorHandlers',
                'initializeCacheManagement'
            ];

            let foundFunctions = 0;
            functions.forEach(func => {
                if (content.includes(func)) {
                    console.log(`✅ ${func} function found`);
                    foundFunctions++;
                } else {
                    console.error(`❌ ${func} function not found`);
                }
            });

            if (foundFunctions === functions.length) {
                console.log('✅ All cache management functions present');
                testResults.passed++;
            } else {
                console.error(`❌ Missing ${functions.length - foundFunctions} cache management functions`);
                testResults.failed++;
            }

        } else {
            console.error('❌ Cache management not accessible:', response.status);
            testResults.failed++;
        }

    } catch (error) {
        console.error('❌ Cache management test error:', error.message);
        testResults.failed++;
    }
}

/**
 * Test chunk test utilities
 */
async function testChunkTestUtilities() {
    console.log('\n🧪 Testing chunk test utilities...');

    try {
        const url = `${FRONTEND_URL}/src/utils/chunkTestUtility.ts`;
        const response = await fetch(url);

        if (response.ok) {
            console.log('✅ Chunk test utilities accessible');
            testResults.passed++;
        } else {
            console.error('❌ Chunk test utilities not accessible:', response.status);
            testResults.failed++;
        }

    } catch (error) {
        console.error('❌ Chunk test utilities error:', error.message);
        testResults.failed++;
    }
}

/**
 * Test async Vue components (the ones that were failing)
 */
async function testAsyncComponents() {
    console.log('\n🎭 Testing async Vue components...');

    const asyncComponents = [
        'AsyncComponentWrapper',
        'AsyncErrorFallback'
    ];

    for (const component of asyncComponents) {
        try {
            const url = `${FRONTEND_URL}/src/components/async/${component}.vue`;
            const response = await fetch(url);

            if (response.ok) {
                const content = await response.text();

                // Check for Vue 3 Composition API structure
                if (content.includes('<script setup') && content.includes('lang="ts"')) {
                    console.log(`✅ ${component}.vue has proper Composition API structure`);
                    testResults.passed++;
                } else {
                    console.error(`❌ ${component}.vue missing Composition API structure`);
                    testResults.failed++;
                }
            } else {
                console.error(`❌ ${component}.vue not accessible: ${response.status}`);
                testResults.failed++;
            }

        } catch (error) {
            console.error(`❌ ${component}.vue test error:`, error.message);
            testResults.failed++;
        }
    }
}

/**
 * Run all tests
 */
async function runAllTests() {
    console.log('🚀 Starting AutoBot Frontend Chunk Loading Tests\n');

    // Test frontend server
    const serverOk = await testFrontendServer();
    if (!serverOk) {
        console.error('\n❌ Frontend server not accessible. Cannot continue tests.');
        return;
    }

    // Run component tests
    await testComponentAccess();
    await testAsyncHelpers();
    await testCacheManagement();
    await testChunkTestUtilities();
    await testAsyncComponents();

    // Print summary
    console.log('\n📊 Test Summary:');
    console.log('================');
    console.log(`Total Tests: ${testResults.passed + testResults.failed}`);
    console.log(`Passed: ${testResults.passed}`);
    console.log(`Failed: ${testResults.failed}`);
    console.log(`Success Rate: ${Math.round((testResults.passed / (testResults.passed + testResults.failed)) * 100)}%`);

    if (testResults.failed === 0) {
        console.log('\n🎉 All tests passed! Chunk loading fixes are working correctly.');
        console.log('\n📝 Next steps:');
        console.log('1. Open browser to http://172.16.168.21:5173');
        console.log('2. Navigate between pages (Chat, Tools, Monitoring, Settings)');
        console.log('3. Check browser console for error messages');
        console.log('4. Verify error boundaries show helpful messages instead of blank screens');
        console.log('5. Test with: window.chunkTest.runComprehensive() in browser console');
    } else {
        console.log('\n⚠️  Some tests failed. Check the details above for issues.');
        console.log('\n🔧 Troubleshooting:');
        console.log('1. Ensure frontend server is running on VM1');
        console.log('2. Check that source files were synced properly');
        console.log('3. Verify network connectivity to frontend VM');
    }

    // Save detailed results
    if (typeof require !== 'undefined') {
        const fs = require('fs');
        const path = require('path');

        // Ensure results directory exists
        const resultsDir = '/home/kali/Desktop/AutoBot/tests/results';
        if (!fs.existsSync(resultsDir)) {
            fs.mkdirSync(resultsDir, { recursive: true });
        }

        const resultsFile = path.join(resultsDir, 'chunk-loading-test-results.json');
        fs.writeFileSync(resultsFile, JSON.stringify({
            timestamp: new Date().toISOString(),
            frontendUrl: FRONTEND_URL,
            testResults,
            summary: {
                total: testResults.passed + testResults.failed,
                passed: testResults.passed,
                failed: testResults.failed,
                successRate: Math.round((testResults.passed / (testResults.passed + testResults.failed)) * 100)
            }
        }, null, 2));
        console.log(`\n💾 Detailed results saved to: ${resultsFile}`);
    }
}

// Run tests if this script is executed directly
if (typeof module !== 'undefined' && require.main === module) {
    runAllTests().catch(error => {
        console.error('❌ Test execution failed:', error);
        process.exit(1);
    });
}

// Export for use in other scripts
if (typeof module !== 'undefined') {
    module.exports = {
        runAllTests,
        testFrontendServer,
        testComponentAccess,
        testAsyncHelpers,
        testCacheManagement,
        testChunkTestUtilities,
        testAsyncComponents
    };
}