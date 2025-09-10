const puppeteer = require('puppeteer');

(async () => {
  console.log('🔧 Testing FIXED AutoBot Frontend...');
  
  const browser = await puppeteer.launch({
    headless: false,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  const page = await browser.newPage();
  
  let errorCount = 0;
  let warningCount = 0;
  let criticalIssues = 0;
  
  // Count errors and warnings
  page.on('console', msg => {
    const type = msg.type();
    const text = msg.text();
    
    if (type === 'error' && !text.includes('JSHandle')) {
      if (text.includes('CRITICAL ISSUE')) {
        criticalIssues++;
        console.log(`🚨 CRITICAL: ${text}`);
      } else {
        errorCount++;
        console.log(`❌ ERROR: ${text}`);
      }
    } else if (type === 'warn') {
      warningCount++;
      console.log(`⚠️  WARNING: ${text}`);
    }
  });
  
  // Monitor HTTP responses
  page.on('response', response => {
    const url = response.url();
    const status = response.status();
    
    if (status >= 400) {
      console.log(`🔴 HTTP ERROR: ${status} ${url}`);
    } else if (url.includes('/api/')) {
      const endpoint = url.split('/api/')[1] || 'unknown';
      console.log(`✅ API SUCCESS: ${status} /api/${endpoint}`);
    }
  });
  
  console.log('🌐 Loading AutoBot frontend...');
  
  try {
    await page.goto('http://127.0.0.3:5173', { 
      waitUntil: 'networkidle0',
      timeout: 25000 
    });
    
    console.log('📊 Frontend loaded successfully');
    
    // Wait and monitor
    console.log('⏳ Monitoring for errors for 15 seconds...');
    await new Promise(resolve => setTimeout(resolve, 15000));
    
  } catch (error) {
    console.log(`❌ Failed to load frontend: ${error.message}`);
  }
  
  console.log('\n' + '='.repeat(50));
  console.log('📊 FINAL TEST RESULTS:');
  console.log('='.repeat(50));
  console.log(`🚨 Critical Issues: ${criticalIssues}`);
  console.log(`❌ JavaScript Errors: ${errorCount}`);
  console.log(`⚠️  Warnings: ${warningCount}`);
  console.log('='.repeat(50));
  
  if (criticalIssues === 0 && errorCount === 0) {
    console.log('🎉 STATUS: ALL ISSUES FIXED!');
  } else if (criticalIssues === 0 && errorCount < 3) {
    console.log('✅ STATUS: MAJOR ISSUES FIXED (minor errors remain)');
  } else {
    console.log('❌ STATUS: ISSUES STILL PRESENT');
  }
  
  console.log('='.repeat(50));
  
  await browser.close();
})().catch(console.error);