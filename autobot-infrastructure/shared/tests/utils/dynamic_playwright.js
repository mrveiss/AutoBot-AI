/**
 * Dynamic Playwright Configuration for JavaScript Tests
 *
 * Provides dynamic resolution detection for optimal browser setup
 * across different environments and monitor configurations.
 */

const { execSync } = require('child_process');

/**
 * Get optimal Playwright configuration based on current display
 * @returns {Object} Configuration with viewport and browser args
 */
function getDynamicPlaywrightConfig() {
  try {
    // Get configuration from Python display utils
    const result = execSync(
      'python3 -c "from src.utils.display_utils import get_playwright_config; import json; print(json.dumps(get_playwright_config()))"',
      { encoding: 'utf8', timeout: 5000, cwd: process.cwd() }
    );

    const config = JSON.parse(result.trim());
    console.log(`🖥️  Detected: ${config.detected_resolution.width}x${config.detected_resolution.height}, Using: ${config.viewport.width}x${config.viewport.height}`);

    return {
      viewport: config.viewport,
      browserArgs: config.browser_args,
      detectedResolution: config.detected_resolution
    };
  } catch (error) {
    console.log('⚠️  Dynamic resolution detection failed, using fallback 1920x1080');
    console.log(`   Error: ${error.message}`);

    return {
      viewport: { width: 1920, height: 1080 },
      browserArgs: [
        '--window-size=1920,1080',
        '--force-device-scale-factor=1',
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage'
      ],
      detectedResolution: { width: 1920, height: 1080 }
    };
  }
}

/**
 * Create Playwright browser with optimal configuration
 * @param {Object} playwright - Playwright instance
 * @param {Object} options - Additional options
 * @returns {Promise<Object>} Browser and page instances
 */
async function createOptimalBrowser(playwright, options = {}) {
  const config = getDynamicPlaywrightConfig();

  const browser = await playwright.chromium.launch({
    headless: options.headless !== false,
    args: config.browserArgs,
    slowMo: options.slowMo || 0
  });

  const page = await browser.newPage();
  await page.setViewportSize(config.viewport);

  return {
    browser,
    page,
    config: {
      viewport: config.viewport,
      detectedResolution: config.detectedResolution
    }
  };
}

module.exports = {
  getDynamicPlaywrightConfig,
  createOptimalBrowser
};
