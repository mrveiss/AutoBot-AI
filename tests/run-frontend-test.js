const http = require('http');

async function testFrontendEndpoint() {
  console.log('🚀 Running automated frontend tests via Playwright Docker...');
  
  const requestData = JSON.stringify({
    frontend_url: 'http://localhost:5173'
  });
  
  const options = {
    hostname: 'localhost',
    port: 3000,
    path: '/test-frontend',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(requestData)
    }
  };
  
  return new Promise((resolve, reject) => {
    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(body);
          resolve(result);
        } catch (e) {
          reject(new Error('Failed to parse response: ' + body));
        }
      });
    });
    
    req.on('error', reject);
    req.write(requestData);
    req.end();
  });
}

async function main() {
  try {
    const result = await testFrontendEndpoint();
    
    console.log('\n🎯 FRONTEND TEST RESULTS');
    console.log('='.repeat(50));
    console.log(`📊 Summary: ${result.summary.success_rate} (${result.summary.passed}/${result.summary.total_tests})`);
    console.log(`🕐 Tested at: ${result.timestamp}`);
    console.log(`🌐 Frontend URL: ${result.frontend_url}`);
    
    console.log('\n📋 Detailed Results:');
    result.tests.forEach((test, index) => {
      const status = test.status === 'PASS' ? '✅' : '❌';
      console.log(`${index + 1}. ${status} ${test.name}`);
      console.log(`   ${test.details}`);
    });
    
    // Show debug information if available
    if (result.debug_info) {
      console.log('\n🔍 Debug Information:');
      console.log(`   Page Title: ${result.debug_info.page_title}`);
      console.log(`   URL: ${result.debug_info.url}`);
      console.log(`   Form Elements: ${result.debug_info.textareas} textareas, ${result.debug_info.inputs} inputs, ${result.debug_info.forms} forms`);
      console.log(`   Vue Components: ${result.debug_info.vue_components} elements with data-v-`);
      console.log(`   App Element: ${result.debug_info.app_element} #app containers`);
      if (result.debug_info.button_texts.length > 0) {
        console.log(`   Button texts: ${result.debug_info.button_texts.join(', ')}`);
      }
      if (result.debug_info.navigation_texts.length > 0) {
        console.log(`   Navigation texts: ${result.debug_info.navigation_texts.join(', ')}`);
      }
      console.log(`   Body classes: ${result.debug_info.body_classes}`);
    }
    
    if (result.has_screenshot) {
      console.log(`\n📸 Screenshot captured (${result.screenshot_size} bytes)`);
    }
    
    console.log('\n🎉 Automated frontend testing completed!');
    
    if (result.summary.failed > 0) {
      console.log(`\n⚠️  ${result.summary.failed} tests failed - review the results above.`);
    } else {
      console.log('\n🌟 All tests passed! Frontend is working correctly.');
    }
    
  } catch (error) {
    console.error('❌ Error running frontend tests:', error.message);
  }
}

main();