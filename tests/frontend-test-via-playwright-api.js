// Frontend testing script that uses the existing Playwright Docker service
const http = require('http');

async function makeRequest(options, data = null) {
  return new Promise((resolve, reject) => {
    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(body);
          resolve(parsed);
        } catch (e) {
          resolve({ body, status: res.statusCode });
        }
      });
    });
    
    req.on('error', reject);
    
    if (data) {
      req.write(JSON.stringify(data));
    }
    req.end();
  });
}

async function testFrontendWithPlaywright() {
  console.log('🚀 Testing AutoBot Frontend with Playwright Docker Service...');
  
  // Test 1: Check service health
  console.log('\n1. 📊 Checking Playwright service health...');
  try {
    const healthResponse = await makeRequest({
      hostname: 'localhost',
      port: 3000,
      path: '/health',
      method: 'GET'
    });
    console.log('✅ Playwright service status:', healthResponse.status);
    console.log('   Browser connected:', healthResponse.browser_connected);
  } catch (error) {
    console.log('❌ Playwright service health check failed:', error.message);
  }
  
  // Test 2: Check frontend accessibility
  console.log('\n2. 🌐 Checking frontend accessibility...');
  try {
    const frontendResponse = await makeRequest({
      hostname: 'localhost', 
      port: 5173,
      path: '/',
      method: 'GET'
    });
    console.log('✅ Frontend is accessible (status:', frontendResponse.status, ')');
  } catch (error) {
    console.log('❌ Frontend not accessible:', error.message);
  }
  
  // Test 3: Check backend API
  console.log('\n3. ⚙️ Checking backend API...');
  try {
    const apiResponse = await makeRequest({
      hostname: 'localhost',
      port: 8001,
      path: '/api/system/health',
      method: 'GET'
    });
    console.log('✅ Backend API is accessible (status:', apiResponse.status, ')');
  } catch (error) {
    console.log('❌ Backend API not accessible:', error.message);
  }
  
  console.log('\n🎯 FRONTEND TESTING GUIDE');
  console.log('='.repeat(50));
  console.log('\n✨ Open http://localhost:5173 in your browser');
  
  console.log('\n📋 Navigation Testing Checklist:');
  const testSections = [
    {
      name: 'DASHBOARD',
      tests: [
        'System overview cards display correctly',
        'Performance metrics are visible', 
        'Quick actions work properly'
      ]
    },
    {
      name: 'AI ASSISTANT',
      tests: [
        'Chat interface loads',
        'Message input field is functional',
        'Send button works',
        'Message history displays',
        'New chat button creates new conversation',
        'Toggle switches work (Show Thoughts, JSON Output, etc.)',
        'Reload System button is present and functional'
      ]
    },
    {
      name: 'VOICE INTERFACE', 
      tests: [
        'Voice input controls are present',
        'Microphone permissions work',
        'Voice feedback displays'
      ]
    },
    {
      name: 'KNOWLEDGE BASE',
      tests: [
        'Search interface loads',
        'Document list displays',
        'Upload functionality works',
        'Search results are formatted correctly'
      ]
    },
    {
      name: 'TERMINAL',
      tests: [
        'Terminal interface loads',
        'Command input is functional',
        'Command history works',
        'Output displays properly'
      ]
    },
    {
      name: 'FILE MANAGER',
      tests: [
        'File tree displays',
        'File navigation works',
        'File operations (view, edit) function',
        'Directory structure is correct'
      ]
    },
    {
      name: 'SYSTEM MONITOR',
      tests: [
        'CPU usage displays',
        'Memory usage displays', 
        'Process list updates',
        'System health metrics show'
      ]
    },
    {
      name: 'SETTINGS',
      tests: [
        'Configuration panels load',
        'Settings can be modified',
        'Save/apply buttons work',
        'API configuration is accessible'
      ]
    }
  ];
  
  testSections.forEach((section, index) => {
    console.log(`\n${index + 1}. 🔍 ${section.name}`);
    section.tests.forEach(test => {
      console.log(`   ☐ ${test}`);
    });
  });
  
  console.log('\n🧪 Additional Testing Areas:');
  console.log('   ☐ Responsive design (resize browser window)');
  console.log('   ☐ Error handling (test with backend offline)');
  console.log('   ☐ WebSocket connections (real-time updates)'); 
  console.log('   ☐ Form validation and user input');
  console.log('   ☐ Dark/light theme switching (if available)');
  console.log('   ☐ Keyboard shortcuts and accessibility');
  
  console.log('\n🚨 Critical Functions to Test:');
  console.log('   🔄 System Reload Button - Should reload backend modules');
  console.log('   💬 Chat Message Sending - Core AI interaction');
  console.log('   📁 File Operations - Upload, download, management');
  console.log('   ⚙️ Settings Persistence - Configuration changes save');
  
  console.log('\n📱 Browser Testing:');
  console.log('   • Test in different browsers (Chrome, Firefox, Safari)');
  console.log('   • Test on mobile devices or mobile view');
  console.log('   • Test with browser dev tools open');
  
  console.log('\n🎉 Testing complete! Use the checklist above to manually verify all functions.');
}

// Run the test
testFrontendWithPlaywright().catch(console.error);