// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Global Setup for Playwright Tests
 *
 * Ensures proper browser configuration and viewport settings
 * for all AutoBot Playwright test scripts.
 */

async function globalSetup(config) {
  console.log('🔧 Setting up Playwright global configuration...');

  // Ensure proper viewport settings are applied
  const defaultViewport = { width: 1920, height: 1080 };

  // Log configuration
  console.log(`📐 Default viewport: ${defaultViewport.width}x${defaultViewport.height}`);
  console.log('✅ Playwright global setup complete');

  return {
    viewport: defaultViewport
  };
}

module.exports = globalSetup;
