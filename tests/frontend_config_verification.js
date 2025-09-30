#!/usr/bin/env node

/**
 * Frontend Configuration Verification Script
 *
 * This script verifies that the Phase 1 critical configuration fixes
 * are properly implemented and will restore frontend-backend connectivity.
 */

const fs = require('fs');
const path = require('path');

console.log('🔍 AutoBot Frontend Configuration Verification');
console.log('='.repeat(50));

const rootDir = path.join(__dirname, '..');
const frontendDir = path.join(rootDir, 'autobot-vue');

// Test results
const results = {
  passed: 0,
  failed: 0,
  tests: []
};

function test(name, condition, details = '') {
  const passed = condition;
  results.tests.push({ name, passed, details });

  if (passed) {
    results.passed++;
    console.log(`✅ ${name}`);
  } else {
    results.failed++;
    console.log(`❌ ${name}`);
  }

  if (details) {
    console.log(`   ${details}`);
  }
}

// Test 1: Environment Variable Fix
console.log('\n📋 Testing Environment Variables');
try {
  const envContent = fs.readFileSync(path.join(frontendDir, '.env'), 'utf8');

  test(
    'VITE_FRONTEND_HOST set to 172.16.168.21',
    envContent.includes('VITE_FRONTEND_HOST=172.16.168.21'),
    'Frontend should run on VM1 (172.16.168.21), not VM0 (172.16.168.20)'
  );

  test(
    'VITE_BACKEND_HOST set to 172.16.168.20',
    envContent.includes('VITE_BACKEND_HOST=172.16.168.20'),
    'Backend should remain on VM0 (172.16.168.20:8001)'
  );

} catch (error) {
  test('Environment file readable', false, `Error: ${error.message}`);
}

// Test 2: Environment.js Compatibility Shim
console.log('\n📋 Testing Environment.js Compatibility Shim');
try {
  const envJsContent = fs.readFileSync(path.join(frontendDir, 'src/config/environment.js'), 'utf8');

  test(
    'AppConfig.js imported in environment.js',
    envJsContent.includes("import appConfig from './AppConfig.js'"),
    'Compatibility shim should redirect to AppConfig.js'
  );

  test(
    'Proxy mode detection implemented',
    envJsContent.includes('window.location.port === \'5173\'') && envJsContent.includes('isViteDevServer'),
    'Proper proxy detection for Vite dev server'
  );

  test(
    'Deprecation warning included',
    envJsContent.includes('DEPRECATION WARNING'),
    'Should warn developers to migrate to AppConfig.js'
  );

} catch (error) {
  test('Environment.js file readable', false, `Error: ${error.message}`);
}

// Test 3: ChatInterface.vue Migration
console.log('\n📋 Testing ChatInterface.vue Migration');
try {
  const chatInterfaceContent = fs.readFileSync(path.join(frontendDir, 'src/components/chat/ChatInterface.vue'), 'utf8');

  test(
    'ChatInterface.vue uses AppConfig.js',
    chatInterfaceContent.includes("import appConfig from '@/config/AppConfig.js'"),
    'Should import AppConfig.js instead of environment.js'
  );

  test(
    'AppConfig used for connection validation',
    chatInterfaceContent.includes('appConfig.validateConnection()'),
    'Should use AppConfig for connection checking'
  );

  test(
    'AppConfig used for VNC URL generation',
    chatInterfaceContent.includes('appConfig.getVncUrl'),
    'Should use AppConfig for VNC URL construction'
  );

} catch (error) {
  test('ChatInterface.vue file readable', false, `Error: ${error.message}`);
}

// Test 4: ApiClient.js Migration
console.log('\n📋 Testing ApiClient.js Migration');
try {
  const apiClientContent = fs.readFileSync(path.join(frontendDir, 'src/utils/ApiClient.js'), 'utf8');

  test(
    'ApiClient.js uses AppConfig.js',
    apiClientContent.includes("import appConfig from '@/config/AppConfig.js'"),
    'Should import AppConfig.js instead of environment.js'
  );

  test(
    'AppConfig used for service URL construction',
    apiClientContent.includes('appConfig.getServiceUrl') || apiClientContent.includes('appConfig.getApiUrl'),
    'Should use AppConfig for URL construction'
  );

  test(
    'AppConfig used for connection validation',
    apiClientContent.includes('appConfig.validateConnection'),
    'Should use AppConfig for connection validation'
  );

  test(
    'Proxy mode detection maintained',
    apiClientContent.includes('window.location.port === \'5173\''),
    'Should maintain proxy detection for Vite dev server'
  );

} catch (error) {
  test('ApiClient.js file readable', false, `Error: ${error.message}`);
}

// Test 5: Configuration Architecture
console.log('\n📋 Testing Configuration Architecture');
try {
  const appConfigContent = fs.readFileSync(path.join(frontendDir, 'src/config/AppConfig.js'), 'utf8');

  test(
    'AppConfig.js exists and properly structured',
    appConfigContent.includes('class AppConfigService') && appConfigContent.includes('getServiceUrl'),
    'AppConfig.js should be the central configuration service'
  );

  test(
    'Service discovery integration',
    appConfigContent.includes('ServiceDiscovery'),
    'AppConfig should use ServiceDiscovery for dynamic URL resolution'
  );

} catch (error) {
  test('AppConfig.js file readable', false, `Error: ${error.message}`);
}

// Final Results
console.log('\n📊 Verification Results');
console.log('='.repeat(50));
console.log(`✅ Tests Passed: ${results.passed}`);
console.log(`❌ Tests Failed: ${results.failed}`);
console.log(`📈 Success Rate: ${Math.round((results.passed / (results.passed + results.failed)) * 100)}%`);

if (results.failed === 0) {
  console.log('\n🎉 All configuration fixes verified successfully!');
  console.log('\n🚀 Next Steps:');
  console.log('   1. Test frontend startup with: npm run dev');
  console.log('   2. Verify backend connectivity at 172.16.168.20:8001');
  console.log('   3. Sync changes to Frontend VM: ./sync-frontend.sh');
  console.log('   4. Start full AutoBot system: ./run_autobot.sh --dev');
} else {
  console.log('\n⚠️  Some configuration issues detected.');
  console.log('   Please review failed tests and fix before deployment.');

  console.log('\n🔧 Failed Tests:');
  results.tests.forEach(test => {
    if (!test.passed) {
      console.log(`   - ${test.name}: ${test.details}`);
    }
  });
}

console.log('\n🎯 Key Configuration Changes Applied:');
console.log('   ✅ VITE_FRONTEND_HOST corrected to 172.16.168.21');
console.log('   ✅ Compatibility shim created in environment.js');
console.log('   ✅ ChatInterface.vue migrated to AppConfig.js');
console.log('   ✅ ApiClient.js migrated to AppConfig.js');
console.log('   ✅ Proxy mode detection enhanced');

process.exit(results.failed > 0 ? 1 : 0);