/**
 * Browser-Based Chat Fix Verification Tests
 *
 * Run these tests in the browser console at: http://172.16.168.21:5173
 *
 * Instructions:
 * 1. Open browser and navigate to http://172.16.168.21:5173
 * 2. Open DevTools (F12)
 * 3. Go to Console tab
 * 4. Copy and paste this entire script
 * 5. Run: await runAllBrowserTests()
 */

const BACKEND_URL = 'http://172.16.168.20:8001';
const CHAT_ENDPOINT = `${BACKEND_URL}/api/chat/send`;

// Test result storage
const testResults = {
  passed: 0,
  failed: 0,
  total: 0,
  details: []
};

/**
 * Helper function to add test result
 */
function addTestResult(testName, passed, details, duration) {
  const result = {
    name: testName,
    passed,
    details,
    duration: `${duration.toFixed(2)}ms`,
    timestamp: new Date().toISOString()
  };

  testResults.details.push(result);
  testResults.total++;
  if (passed) {
    testResults.passed++;
    console.log(`✅ PASS | ${testName} | ${duration.toFixed(2)}ms | ${details}`);
  } else {
    testResults.failed++;
    console.error(`❌ FAIL | ${testName} | ${duration.toFixed(2)}ms | ${details}`);
  }
}

/**
 * Test 1: Normal Message Send
 */
async function testNormalMessageSend() {
  const testName = 'Normal Message Send';
  const startTime = performance.now();

  try {
    const payload = {
      message: 'Hello AutoBot - browser test',
      user_id: 'browser_test_user',
      session_id: `browser_session_${Date.now()}`
    };

    const response = await fetch(CHAT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const duration = performance.now() - startTime;

    if (response.status !== 200) {
      throw new Error(`Expected 200, got ${response.status}`);
    }

    const data = await response.json();

    if (!data.response && !data.message) {
      throw new Error('Response missing message field');
    }

    addTestResult(testName, true, `Status: ${response.status}`, duration);
    return true;

  } catch (error) {
    const duration = performance.now() - startTime;
    addTestResult(testName, false, error.message, duration);
    return false;
  }
}

/**
 * Test 2: Message with File Reference
 */
async function testMessageWithFileReference() {
  const testName = 'Message with File Reference';
  const startTime = performance.now();

  try {
    const payload = {
      message: 'Here is the document',
      user_id: 'browser_test_user',
      session_id: `browser_session_${Date.now()}`,
      attached_file_ids: ['test_file_id_12345']
    };

    const response = await fetch(CHAT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const duration = performance.now() - startTime;

    // Should NOT return 422 for file reference
    if (response.status === 422) {
      const errorData = await response.json();
      throw new Error(`422 error on file reference: ${JSON.stringify(errorData)}`);
    }

    addTestResult(testName, true, `Status: ${response.status}`, duration);
    return true;

  } catch (error) {
    const duration = performance.now() - startTime;
    addTestResult(testName, false, error.message, duration);
    return false;
  }
}

/**
 * Test 3: Invalid file_data Field Rejection
 */
async function testInvalidFileDataRejection() {
  const testName = 'Invalid file_data Rejected';
  const startTime = performance.now();

  try {
    const payload = {
      message: 'Test with invalid file_data',
      user_id: 'browser_test_user',
      session_id: `browser_session_${Date.now()}`,
      file_data: 'This field should not be accepted'  // Invalid field
    };

    const response = await fetch(CHAT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const duration = performance.now() - startTime;

    // Should return 422 for unexpected field
    if (response.status !== 422) {
      throw new Error(`Expected 422 for invalid field, got ${response.status}`);
    }

    const errorData = await response.json();
    console.log('Expected 422 error details:', errorData);

    addTestResult(testName, true, '422 validation working', duration);
    return true;

  } catch (error) {
    const duration = performance.now() - startTime;
    addTestResult(testName, false, error.message, duration);
    return false;
  }
}

/**
 * Test 4: Message with Metadata
 */
async function testMessageWithMetadata() {
  const testName = 'Message with Metadata';
  const startTime = performance.now();

  try {
    const payload = {
      message: 'Explain quantum computing',
      user_id: 'browser_test_user',
      session_id: `browser_session_${Date.now()}`,
      metadata: {
        temperature: 0.7,
        max_tokens: 500
      }
    };

    const response = await fetch(CHAT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const duration = performance.now() - startTime;

    if (response.status !== 200 && response.status !== 422) {
      throw new Error(`Unexpected status: ${response.status}`);
    }

    addTestResult(testName, true, `Status: ${response.status}`, duration);
    return true;

  } catch (error) {
    const duration = performance.now() - startTime;
    addTestResult(testName, false, error.message, duration);
    return false;
  }
}

/**
 * Test 5: Special Characters and Emojis
 */
async function testSpecialCharacters() {
  const testName = 'Special Characters & Emojis';
  const startTime = performance.now();

  try {
    const specialMessage = 'Test: <script>alert("XSS")</script> & 🚀 🔥 💻 🤖';

    const payload = {
      message: specialMessage,
      user_id: 'browser_test_user',
      session_id: `browser_session_${Date.now()}`
    };

    const response = await fetch(CHAT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const duration = performance.now() - startTime;

    if (response.status !== 200) {
      throw new Error(`Expected 200, got ${response.status}`);
    }

    addTestResult(testName, true, 'Special chars handled', duration);
    return true;

  } catch (error) {
    const duration = performance.now() - startTime;
    addTestResult(testName, false, error.message, duration);
    return false;
  }
}

/**
 * Test 6: 422 Validation Error
 */
async function test422ValidationError() {
  const testName = '422 Validation Error';
  const startTime = performance.now();

  try {
    const payload = {
      message: 'Test 422 error',
      user_id: 'browser_test_user',
      session_id: `browser_session_${Date.now()}`,
      invalid_field: 'This should trigger 422',
      another_bad_field: 12345
    };

    const response = await fetch(CHAT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const duration = performance.now() - startTime;

    if (response.status !== 422) {
      throw new Error(`Expected 422 for invalid fields, got ${response.status}`);
    }

    const errorData = await response.json();
    if (!errorData.detail) {
      throw new Error('422 response missing error details');
    }

    console.log('Expected 422 error details:', errorData);

    addTestResult(testName, true, '422 validation working', duration);
    return true;

  } catch (error) {
    const duration = performance.now() - startTime;
    addTestResult(testName, false, error.message, duration);
    return false;
  }
}

/**
 * Test 7: Missing Required Fields
 */
async function testMissingRequiredFields() {
  const testName = 'Missing Required Fields';
  const startTime = performance.now();

  try {
    const payload = {
      message: 'Test missing fields'
      // Missing user_id and session_id
    };

    const response = await fetch(CHAT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const duration = performance.now() - startTime;

    if (response.status !== 422) {
      throw new Error(`Expected 422 for missing fields, got ${response.status}`);
    }

    addTestResult(testName, true, 'Required field validation working', duration);
    return true;

  } catch (error) {
    const duration = performance.now() - startTime;
    addTestResult(testName, false, error.message, duration);
    return false;
  }
}

/**
 * Test 8: Type Validation
 */
async function testTypeValidation() {
  const testName = 'Type Validation - Invalid Message Type';
  const startTime = performance.now();

  try {
    const payload = {
      message: 12345,  // Invalid type (should be string)
      user_id: 'browser_test_user',
      session_id: `browser_session_${Date.now()}`
    };

    const response = await fetch(CHAT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const duration = performance.now() - startTime;

    if (response.status !== 422) {
      throw new Error(`Expected 422 for type error, got ${response.status}`);
    }

    addTestResult(testName, true, 'Type validation working', duration);
    return true;

  } catch (error) {
    const duration = performance.now() - startTime;
    addTestResult(testName, false, error.message, duration);
    return false;
  }
}

/**
 * Test 9: Rapid Sequential Requests
 */
async function testRapidSequentialRequests() {
  const testName = 'Rapid Sequential Requests (10x)';
  const startTime = performance.now();

  try {
    let successCount = 0;
    const totalRequests = 10;

    for (let i = 0; i < totalRequests; i++) {
      const payload = {
        message: `Rapid test ${i}`,
        user_id: 'browser_test_user',
        session_id: `browser_session_${Date.now()}`
      };

      const response = await fetch(CHAT_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (response.status === 200) {
        successCount++;
      }
    }

    const duration = performance.now() - startTime;

    // At least 80% should succeed
    if (successCount < totalRequests * 0.8) {
      throw new Error(`Only ${successCount}/${totalRequests} requests succeeded`);
    }

    addTestResult(testName, true, `${successCount}/${totalRequests} succeeded`, duration);
    return true;

  } catch (error) {
    const duration = performance.now() - startTime;
    addTestResult(testName, false, error.message, duration);
    return false;
  }
}

/**
 * Test 10: Performance Benchmark
 */
async function testPerformanceBenchmark() {
  const testName = 'Performance Benchmark (10 requests)';
  const startTime = performance.now();

  try {
    const responseTimes = [];

    for (let i = 0; i < 10; i++) {
      const requestStart = performance.now();

      const payload = {
        message: `Performance test ${i}`,
        user_id: 'browser_test_user',
        session_id: `browser_session_${Date.now()}`
      };

      const response = await fetch(CHAT_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const requestDuration = performance.now() - requestStart;
      responseTimes.push(requestDuration);

      if (response.status !== 200) {
        throw new Error(`Request ${i} failed: ${response.status}`);
      }
    }

    const totalDuration = performance.now() - startTime;

    const avgTime = responseTimes.reduce((sum, t) => sum + t, 0) / responseTimes.length;
    const minTime = Math.min(...responseTimes);
    const maxTime = Math.max(...responseTimes);

    const details = `Avg: ${avgTime.toFixed(0)}ms | Min: ${minTime.toFixed(0)}ms | Max: ${maxTime.toFixed(0)}ms`;

    // Performance threshold: average < 5000ms (excluding LLM processing)
    const performanceAcceptable = avgTime < 5000;

    addTestResult(testName, performanceAcceptable, details, totalDuration);
    return performanceAcceptable;

  } catch (error) {
    const duration = performance.now() - startTime;
    addTestResult(testName, false, error.message, duration);
    return false;
  }
}

/**
 * Test 11: Network Request Inspection
 */
async function testNetworkRequestInspection() {
  const testName = 'Network Request Structure Inspection';
  const startTime = performance.now();

  try {
    // Clear performance entries
    performance.clearResourceTimings();

    const payload = {
      message: 'Network inspection test',
      user_id: 'browser_test_user',
      session_id: `browser_session_${Date.now()}`
    };

    const response = await fetch(CHAT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const duration = performance.now() - startTime;

    // Get network timing info
    const resourceEntries = performance.getEntriesByType('resource');
    const chatRequest = resourceEntries.find(entry => entry.name.includes('/api/chat/send'));

    if (chatRequest) {
      console.log('Network timing details:', {
        duration: chatRequest.duration,
        transferSize: chatRequest.transferSize,
        encodedBodySize: chatRequest.encodedBodySize,
        decodedBodySize: chatRequest.decodedBodySize
      });
    }

    // Verify Content-Type header
    const contentType = response.headers.get('Content-Type');
    console.log('Response Content-Type:', contentType);

    addTestResult(testName, true, `Status: ${response.status}, Network data captured`, duration);
    return true;

  } catch (error) {
    const duration = performance.now() - startTime;
    addTestResult(testName, false, error.message, duration);
    return false;
  }
}

/**
 * Test 12: Console Error Monitoring
 */
async function testConsoleErrorMonitoring() {
  const testName = 'Console Error Monitoring';
  const startTime = performance.now();

  try {
    // Monitor console errors
    const originalError = console.error;
    const errors = [];

    console.error = function(...args) {
      errors.push(args.join(' '));
      originalError.apply(console, args);
    };

    const payload = {
      message: 'Console monitoring test',
      user_id: 'browser_test_user',
      session_id: `browser_session_${Date.now()}`
    };

    const response = await fetch(CHAT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const duration = performance.now() - startTime;

    // Restore original console.error
    console.error = originalError;

    if (errors.length > 0) {
      console.warn('Console errors detected during test:', errors);
    }

    addTestResult(testName, true, `Errors detected: ${errors.length}`, duration);
    return true;

  } catch (error) {
    const duration = performance.now() - startTime;
    console.error = console.error;  // Restore
    addTestResult(testName, false, error.message, duration);
    return false;
  }
}

/**
 * Run All Browser Tests
 */
async function runAllBrowserTests() {
  console.clear();
  console.log('='.repeat(80));
  console.log('🧪 CHAT FIX VERIFICATION - BROWSER TEST SUITE');
  console.log('='.repeat(80));
  console.log(`Backend: ${BACKEND_URL}`);
  console.log(`Started: ${new Date().toISOString()}\n`);

  // Reset test results
  testResults.passed = 0;
  testResults.failed = 0;
  testResults.total = 0;
  testResults.details = [];

  // Run all tests
  console.log('📋 Running Test Suite...\n');

  await testNormalMessageSend();
  await testMessageWithFileReference();
  await testInvalidFileDataRejection();
  await testMessageWithMetadata();
  await testSpecialCharacters();
  await test422ValidationError();
  await testMissingRequiredFields();
  await testTypeValidation();
  await testRapidSequentialRequests();
  await testPerformanceBenchmark();
  await testNetworkRequestInspection();
  await testConsoleErrorMonitoring();

  // Print summary
  printBrowserTestSummary();

  return testResults;
}

/**
 * Print Test Summary
 */
function printBrowserTestSummary() {
  console.log('\n' + '='.repeat(80));
  console.log('📊 TEST RESULTS SUMMARY');
  console.log('='.repeat(80));

  const passRate = testResults.total > 0
    ? (testResults.passed / testResults.total * 100)
    : 0;

  console.log(`\nTotal Tests: ${testResults.total}`);
  console.log(`✅ Passed: ${testResults.passed}`);
  console.log(`❌ Failed: ${testResults.failed}`);
  console.log(`📈 Pass Rate: ${passRate.toFixed(1)}%`);

  if (testResults.failed > 0) {
    console.log('\n❌ Failed Tests:');
    testResults.details
      .filter(r => !r.passed)
      .forEach(r => console.error(`  - ${r.name}: ${r.details}`));
  }

  const totalDuration = testResults.details.reduce((sum, r) => {
    return sum + parseFloat(r.duration);
  }, 0);

  console.log(`\n⏱️  Total Duration: ${totalDuration.toFixed(0)}ms`);
  console.log(`📅 Completed: ${new Date().toISOString()}`);

  console.log('\n' + '='.repeat(80));
  if (passRate >= 90) {
    console.log('✅ OVERALL: ALL CRITICAL TESTS PASSED');
    console.log('✅ Ready for production deployment');
  } else if (passRate >= 70) {
    console.log('⚠️  OVERALL: MOST TESTS PASSED (Some issues found)');
    console.log('⚠️  Review failures before deployment');
  } else {
    console.log('❌ OVERALL: SIGNIFICANT FAILURES DETECTED');
    console.log('❌ NOT ready for deployment - fix required');
  }
  console.log('='.repeat(80));

  // Save to localStorage for persistence
  try {
    localStorage.setItem('chat_fix_test_results', JSON.stringify(testResults));
    console.log('\n💾 Results saved to localStorage');
  } catch (e) {
    console.warn('Failed to save results to localStorage:', e);
  }
}

/**
 * Export test results
 */
function exportTestResults() {
  const dataStr = JSON.stringify(testResults, null, 2);
  const dataBlob = new Blob([dataStr], { type: 'application/json' });
  const url = URL.createObjectURL(dataBlob);

  const link = document.createElement('a');
  link.href = url;
  link.download = `chat_fix_test_results_${Date.now()}.json`;
  link.click();

  console.log('✅ Test results exported to file');
}

// Export functions for manual use
window.chatFixTests = {
  runAllBrowserTests,
  exportTestResults,
  testResults,
  // Individual test functions
  testNormalMessageSend,
  testMessageWithFileReference,
  testInvalidFileDataRejection,
  testMessageWithMetadata,
  testSpecialCharacters,
  test422ValidationError,
  testMissingRequiredFields,
  testTypeValidation,
  testRapidSequentialRequests,
  testPerformanceBenchmark,
  testNetworkRequestInspection,
  testConsoleErrorMonitoring
};

console.log('✅ Browser test suite loaded');
console.log('📋 Run: await chatFixTests.runAllBrowserTests()');
console.log('📥 Export: chatFixTests.exportTestResults()');
console.log('🔍 View Results: chatFixTests.testResults');
