#!/usr/bin/env node

/**
 * Frontend Connectivity Test - Verify proxy mode and API connectivity
 *
 * This test validates:
 * 1. Frontend can connect to backend via Vite proxy
 * 2. No hardcoded host.docker.internal fallbacks are triggered
 * 3. Chat messages work correctly
 * 4. Settings API calls work via proxy
 * 5. Centralized configuration approach is working
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const FRONTEND_URL = 'http://172.16.168.21:5173';
const BACKEND_URL = 'http://172.16.168.20:8001';
const TEST_RESULTS_DIR = '/home/kali/Desktop/AutoBot/tests/results';

// Test configuration
const TEST_CONFIG = {
  timeout: 30000,
  navigationTimeout: 10000,
  headless: true,
  slowMo: 1000
};

class FrontendConnectivityTest {
  constructor() {
    this.browser = null;
    this.page = null;
    this.results = {
      timestamp: new Date().toISOString(),
      tests: [],
      summary: {
        total: 0,
        passed: 0,
        failed: 0,
        errors: []
      }
    };
  }

  async setup() {
    console.log('🚀 Setting up Frontend Connectivity Test...');

    this.browser = await chromium.launch({
      headless: TEST_CONFIG.headless,
      slowMo: TEST_CONFIG.slowMo,
      args: ['--disable-web-security', '--disable-features=VizDisplayCompositor']
    });

    this.page = await this.browser.newPage();

    // Set proper viewport for full page display
    await this.page.setViewportSize({ width: 1920, height: 1080 });

    // Set timeouts
    this.page.setDefaultTimeout(TEST_CONFIG.timeout);
    this.page.setDefaultNavigationTimeout(TEST_CONFIG.navigationTimeout);

    // Listen to console errors and network errors
    this.page.on('console', msg => {
      if (msg.type() === 'error') {
        console.error('❌ Console error:', msg.text());
        this.results.summary.errors.push({
          type: 'console',
          message: msg.text(),
          timestamp: new Date().toISOString()
        });
      }
    });

    this.page.on('response', response => {
      if (!response.ok() && response.url().includes('/api/')) {
        console.error(`❌ API request failed: ${response.status()} ${response.url()}`);
        this.results.summary.errors.push({
          type: 'api_error',
          status: response.status(),
          url: response.url(),
          timestamp: new Date().toISOString()
        });
      }
    });
  }

  async runTest(testName, testFn) {
    const startTime = Date.now();
    this.results.summary.total++;

    try {
      console.log(`🧪 Running test: ${testName}`);
      await testFn();

      const duration = Date.now() - startTime;
      this.results.tests.push({
        name: testName,
        status: 'PASSED',
        duration,
        timestamp: new Date().toISOString()
      });

      this.results.summary.passed++;
      console.log(`✅ ${testName} - PASSED (${duration}ms)`);

    } catch (error) {
      const duration = Date.now() - startTime;
      this.results.tests.push({
        name: testName,
        status: 'FAILED',
        error: error.message,
        duration,
        timestamp: new Date().toISOString()
      });

      this.results.summary.failed++;
      this.results.summary.errors.push({
        type: 'test_failure',
        test: testName,
        message: error.message,
        timestamp: new Date().toISOString()
      });

      console.log(`❌ ${testName} - FAILED: ${error.message}`);
    }
  }

  async testFrontendLoads() {
    await this.page.goto(FRONTEND_URL, { waitUntil: 'networkidle' });

    // Check if page loaded
    const title = await this.page.title();
    if (!title.includes('AutoBot')) {
      throw new Error(`Frontend did not load correctly. Title: ${title}`);
    }

    // Check for Vue app
    const vueApp = await this.page.locator('#app').count();
    if (vueApp === 0) {
      throw new Error('Vue app element not found');
    }
  }

  async testBackendHealthDirect() {
    // Test direct backend connection
    const response = await fetch(`${BACKEND_URL}/api/system/health`);
    if (!response.ok) {
      throw new Error(`Backend health check failed: ${response.status}`);
    }
    const health = await response.json();
    if (health.status !== 'healthy') {
      throw new Error(`Backend not healthy: ${JSON.stringify(health)}`);
    }
  }

  async testProxyConfiguration() {
    // Navigate to frontend and check that API calls are using proxy
    await this.page.goto(FRONTEND_URL);

    // Intercept network requests to check for hardcoded URLs
    const apiRequests = [];

    this.page.on('request', request => {
      if (request.url().includes('/api/')) {
        apiRequests.push({
          url: request.url(),
          method: request.method()
        });
      }
    });

    // Wait for initial load and API calls
    await this.page.waitForTimeout(3000);

    // Check that no requests are going to host.docker.internal
    const dockerInternalRequests = apiRequests.filter(req =>
      req.url.includes('host.docker.internal')
    );

    if (dockerInternalRequests.length > 0) {
      throw new Error(`Found hardcoded host.docker.internal requests: ${JSON.stringify(dockerInternalRequests)}`);
    }

    // Check that API requests are going through proxy (relative URLs or correct proxy URLs)
    const goodRequests = apiRequests.filter(req =>
      req.url.includes(FRONTEND_URL) || req.url.startsWith('/api/')
    );

    console.log(`📊 API requests found: ${apiRequests.length}, Proper proxy requests: ${goodRequests.length}`);
  }

  async testChatFunctionality() {
    await this.page.goto(FRONTEND_URL);

    // Wait for chat interface to load
    await this.page.waitForSelector('[data-testid="chat-interface"], .chat-interface, #chat-interface', { timeout: 10000 });

    // Try to find a chat input
    const chatInput = await this.page.locator('input[placeholder*="message"], textarea[placeholder*="message"], input[type="text"]').first();

    if (await chatInput.count() === 0) {
      throw new Error('Chat input not found');
    }

    // Test sending a message (this will test API connectivity)
    await chatInput.fill('Test connectivity message');

    // Find and click send button
    const sendButton = await this.page.locator('button[type="submit"], button:has-text("Send"), [data-testid="send-button"]').first();

    if (await sendButton.count() > 0) {
      // Monitor for network errors
      let hasNetworkError = false;
      let errorMessage = '';

      this.page.on('response', response => {
        if (!response.ok() && response.url().includes('/api/chat')) {
          hasNetworkError = true;
          errorMessage = `Chat API failed: ${response.status()} ${response.url()}`;
        }
      });

      await sendButton.click();

      // Wait a bit to see if there are network errors
      await this.page.waitForTimeout(3000);

      if (hasNetworkError) {
        throw new Error(errorMessage);
      }

      console.log('✅ Chat message sent without network errors');
    } else {
      console.log('⚠️ Send button not found, but chat input is available');
    }
  }

  async testSettingsAPI() {
    await this.page.goto(FRONTEND_URL);

    // Try to navigate to settings or trigger settings API call
    const settingsLink = await this.page.locator('a[href*="settings"], button:has-text("Settings"), [data-testid="settings"]').first();

    if (await settingsLink.count() > 0) {
      let hasSettingsError = false;
      let errorMessage = '';

      this.page.on('response', response => {
        if (!response.ok() && response.url().includes('/api/settings')) {
          hasSettingsError = true;
          errorMessage = `Settings API failed: ${response.status()} ${response.url()}`;
        }
      });

      await settingsLink.click();
      await this.page.waitForTimeout(3000);

      if (hasSettingsError) {
        throw new Error(errorMessage);
      }

      console.log('✅ Settings API accessible via proxy');
    } else {
      console.log('⚠️ Settings link not found, skipping settings API test');
    }
  }

  async testApiRepositoryConfiguration() {
    // Inject test script to check ApiRepository configuration
    const configCheck = await this.page.evaluate(() => {
      // This runs in browser context
      if (window.apiRepository || window.api) {
        const repo = window.apiRepository || window.api;
        return {
          baseUrl: repo.getBaseUrl ? repo.getBaseUrl() : 'unknown',
          hasTestConnection: typeof (repo.testConnection) === 'function'
        };
      }
      return { baseUrl: 'not_found', hasTestConnection: false };
    });

    console.log(`📊 ApiRepository config: ${JSON.stringify(configCheck)}`);

    // Check that baseUrl is empty (proxy mode) or correct
    if (configCheck.baseUrl.includes('host.docker.internal')) {
      throw new Error(`ApiRepository still using hardcoded host.docker.internal: ${configCheck.baseUrl}`);
    }

    if (configCheck.baseUrl === 'not_found') {
      console.log('⚠️ ApiRepository not accessible from window, but this might be expected');
    } else if (configCheck.baseUrl === '' || configCheck.baseUrl.includes(FRONTEND_URL)) {
      console.log('✅ ApiRepository using correct proxy configuration');
    }
  }

  async cleanup() {
    if (this.browser) {
      await this.browser.close();
    }
  }

  async saveResults() {
    if (!fs.existsSync(TEST_RESULTS_DIR)) {
      fs.mkdirSync(TEST_RESULTS_DIR, { recursive: true });
    }

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `frontend_connectivity_test_${timestamp}.json`;
    const filepath = path.join(TEST_RESULTS_DIR, filename);

    fs.writeFileSync(filepath, JSON.stringify(this.results, null, 2));
    console.log(`💾 Test results saved to: ${filepath}`);

    // Also save a summary text file
    const summaryFile = path.join(TEST_RESULTS_DIR, `frontend_connectivity_summary_${timestamp}.txt`);
    const summary = `
Frontend Connectivity Test Results
==================================
Timestamp: ${this.results.timestamp}
Total Tests: ${this.results.summary.total}
Passed: ${this.results.summary.passed}
Failed: ${this.results.summary.failed}

Test Details:
${this.results.tests.map(test =>
  `${test.status === 'PASSED' ? '✅' : '❌'} ${test.name} (${test.duration}ms)${test.error ? ' - ' + test.error : ''}`
).join('\n')}

${this.results.summary.errors.length > 0 ? `
Errors Found:
${this.results.summary.errors.map(error =>
  `- ${error.type}: ${error.message}`
).join('\n')}
` : 'No errors found.'}

Summary: ${this.results.summary.failed === 0 ? 'ALL TESTS PASSED ✅' : `${this.results.summary.failed} TESTS FAILED ❌`}
`;

    fs.writeFileSync(summaryFile, summary);
    console.log(`📄 Summary saved to: ${summaryFile}`);
  }

  async run() {
    try {
      await this.setup();

      // Run all tests
      await this.runTest('Frontend Loads', () => this.testFrontendLoads());
      await this.runTest('Backend Health Check', () => this.testBackendHealthDirect());
      await this.runTest('Proxy Configuration', () => this.testProxyConfiguration());
      await this.runTest('Chat Functionality', () => this.testChatFunctionality());
      await this.runTest('Settings API', () => this.testSettingsAPI());
      await this.runTest('ApiRepository Configuration', () => this.testApiRepositoryConfiguration());

      await this.saveResults();

      // Print final summary
      console.log('\n🎯 TEST SUMMARY:');
      console.log(`Total: ${this.results.summary.total}, Passed: ${this.results.summary.passed}, Failed: ${this.results.summary.failed}`);

      if (this.results.summary.failed === 0) {
        console.log('🎉 ALL TESTS PASSED! Frontend connectivity is working correctly.');
        process.exit(0);
      } else {
        console.log('💥 SOME TESTS FAILED! Check the results for details.');
        process.exit(1);
      }

    } catch (error) {
      console.error('💥 Test setup/execution failed:', error);
      await this.saveResults();
      process.exit(1);
    } finally {
      await this.cleanup();
    }
  }
}

// Run the test if called directly
if (require.main === module) {
  const test = new FrontendConnectivityTest();
  test.run().catch(console.error);
}

module.exports = FrontendConnectivityTest;