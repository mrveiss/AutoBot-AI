const axios = require('axios');

// Test frontend navigation using the Docker Playwright service
async function testFrontendViaDocker() {
  console.log('🚀 Starting frontend navigation test via Docker Playwright...');
  
  const playwrightUrl = 'http://localhost:3000';
  const frontendUrl = 'http://localhost:5173';
  
  try {
    // Check if Playwright service is available
    console.log('🔍 Checking Playwright service health...');
    const healthResponse = await axios.get(`${playwrightUrl}/health`);
    console.log('✅ Playwright service is healthy:', healthResponse.data);
    
    // Since we can't directly control the browser via the current service,
    // let's modify the approach to use curl to test the frontend endpoints
    console.log('\n📱 Testing frontend accessibility...');
    
    // Test if frontend is running
    const testEndpoints = [
      { name: 'Frontend Home', url: frontendUrl },
      { name: 'API Health', url: 'http://localhost:8001/api/system/health' }
    ];
    
    for (const endpoint of testEndpoints) {
      try {
        const response = await axios.get(endpoint.url, { 
          timeout: 5000,
          validateStatus: () => true // Accept any status code
        });
        console.log(`✅ ${endpoint.name}: Status ${response.status}`);
      } catch (error) {
        console.log(`❌ ${endpoint.name}: ${error.message}`);
      }
    }
    
    console.log('\n💡 Manual testing required:');
    console.log('Since the Playwright service is designed for web scraping,');
    console.log('we need to manually test the frontend functions.');
    console.log(`\nPlease open: ${frontendUrl}`);
    console.log('\nTest the following sections:');
    
    const sectionsToTest = [
      '1. DASHBOARD - Check if metrics and overview display correctly',
      '2. AI ASSISTANT - Test chat functionality and message sending',
      '3. VOICE INTERFACE - Check voice input/output controls',
      '4. KNOWLEDGE BASE - Test search and document management',
      '5. TERMINAL - Test command execution interface',
      '6. FILE MANAGER - Test file browsing and operations',
      '7. SYSTEM MONITOR - Check resource usage displays',
      '8. SETTINGS - Test configuration panels and toggles'
    ];
    
    sectionsToTest.forEach(section => console.log(`   ${section}`));
    
    console.log('\n🔧 Additional tests to perform:');
    console.log('   - Test "Reload System" button functionality');
    console.log('   - Test responsive design on different screen sizes');
    console.log('   - Test error handling and notifications');
    console.log('   - Test WebSocket connections for real-time updates');
    
  } catch (error) {
    console.error('❌ Error during testing:', error.message);
  }
}

// Check if axios is available
try {
  testFrontendViaDocker();
} catch (error) {
  console.log('📝 Manual testing guide for AutoBot frontend:');
  console.log('\n1. Open http://localhost:5173 in your browser');
  console.log('2. Navigate through each section in the sidebar:');
  console.log('   - DASHBOARD, AI ASSISTANT, VOICE INTERFACE');
  console.log('   - KNOWLEDGE BASE, TERMINAL, FILE MANAGER');
  console.log('   - SYSTEM MONITOR, SETTINGS');
  console.log('3. Test chat functionality in AI ASSISTANT');
  console.log('4. Test the "Reload System" button');
  console.log('5. Verify all UI components are responsive');
}