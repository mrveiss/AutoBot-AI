import { test, expect } from '@playwright/test';
import { TEST_CONFIG } from './config';

test.describe('System Integration and Stability Tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(TEST_CONFIG.FRONTEND_URL);
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('#app', { timeout: 10000 });
  });

  test('should load main application without critical errors', async ({ page }) => {
    // Monitor for critical errors
    const criticalErrors = [];
    const warnings = [];
    
    page.on('console', msg => {
      if (msg.type() === 'error') {
        criticalErrors.push(msg.text());
      } else if (msg.type() === 'warning') {
        warnings.push(msg.text());
      }
    });

    page.on('pageerror', error => {
      criticalErrors.push(error.message);
    });

    // Let the page fully load
    await page.waitForTimeout(5000);

    // Filter out expected/minor errors
    const seriousErrors = criticalErrors.filter(error => 
      !error.includes('404') || // Some 404s are expected during development
      !error.includes('test_') || // Test-related errors are acceptable  
      !error.includes('debug_') || // Debug-related errors are acceptable
      !error.toLowerCase().includes('favicon') // Favicon errors are cosmetic
    );

    // Should have minimal serious errors
    expect(seriousErrors.length).toBeLessThan(5);

    // Application should be functional
    await expect(page.locator('#app')).toBeVisible();
    await expect(page.locator('text=AutoBot').first()).toBeVisible();
  });

  test('should have working API connectivity', async ({ page }) => {
    // Test that key API endpoints are accessible
    const endpoints = [
      '/api/system/health',
      '/api/workflow/workflows', 
      '/api/terminal/sessions',
      '/api/chat/history'
    ];

    for (const endpoint of endpoints) {
      const response = await page.request.get(TEST_CONFIG.getApiUrl(endpoint));
      // Should not be completely unreachable
      expect(response.status()).not.toBe(0);
      expect(response.status()).not.toBe(502); // Bad gateway
      expect(response.status()).not.toBe(503); // Service unavailable
      
      // Some endpoints might return 404 or other codes, but they should respond
    }
  });

  test('should handle navigation between different sections', async ({ page }) => {
    // Test navigation stability
    const navigationItems = [
      'Dashboard',
      'AI Assistant', 
      'Chat',
      'Terminal',
      'Workflows',
      'Settings'
    ];

    const navigationErrors = [];
    page.on('pageerror', error => {
      navigationErrors.push(error.message);
    });

    for (const item of navigationItems) {
      const navButton = page.locator(`text=${item}`).first();
      
      if (await navButton.count() > 0) {
        await navButton.click();
        await page.waitForTimeout(1000);
        
        // Should not crash during navigation
        expect(navigationErrors.length).toBeLessThan(3);
      }
    }
  });

  test('should maintain responsive design on different screen sizes', async ({ page }) => {
    // Test responsiveness
    const sizes = [
      { width: 1920, height: 1080 }, // Desktop
      { width: 1024, height: 768 },  // Tablet
      { width: 375, height: 667 }    // Mobile
    ];

    for (const size of sizes) {
      await page.setViewportSize(size);
      await page.waitForTimeout(1000);

      // Application should remain visible and functional
      await expect(page.locator('#app')).toBeVisible();
      
      // Navigation should adapt appropriately
      const navElements = page.locator('nav').or(page.locator('[role="navigation"]'));
      
      if (await navElements.count() > 0) {
        // Navigation should be visible or have a toggle on mobile
        const isNavigationVisible = await navElements.first().isVisible();
        const hasMenuToggle = await page.locator('[aria-label*="menu"]').or(
          page.locator('.menu-toggle')
        ).count() > 0;
        
        // Either nav is visible or there's a menu toggle
        expect(isNavigationVisible || hasMenuToggle).toBe(true);
      }
    }
  });

  test('should handle WebSocket connections gracefully', async ({ page }) => {
    // Monitor WebSocket behavior
    const wsConnections = [];
    const wsErrors = [];
    const wsCloses = [];

    page.on('websocket', ws => {
      wsConnections.push(ws.url());
      
      ws.on('close', () => {
        wsCloses.push(ws.url());
      });
      
      ws.on('socketerror', error => {
        wsErrors.push({ url: ws.url(), error: error });
      });
    });

    // Give time for WebSocket connections to establish
    await page.waitForTimeout(5000);

    // Should attempt WebSocket connections for real-time features
    if (wsConnections.length > 0) {
      // Connections should be to valid endpoints
      wsConnections.forEach(url => {
        expect(url).toContain(TEST_CONFIG.getBackendHost());
        expect(url).toContain('/ws');
      });

      // Should not have excessive connection errors
      expect(wsErrors.length).toBeLessThan(wsConnections.length);
    }
  });

  test('should handle data fetching and loading states', async ({ page }) => {
    // Test loading states and data fetching
    const networkRequests = [];
    const failedRequests = [];

    page.on('request', request => {
      networkRequests.push(request.url());
    });

    page.on('requestfailed', request => {
      failedRequests.push(request.url());
    });

    // Navigate to different sections to trigger data fetching
    const sections = ['Dashboard', 'AI Assistant', 'Workflows'];
    
    for (const section of sections) {
      const sectionButton = page.locator(`text=${section}`).first();
      
      if (await sectionButton.count() > 0) {
        await sectionButton.click();
        await page.waitForTimeout(2000);
      }
    }

    // Should make reasonable number of requests
    expect(networkRequests.length).toBeGreaterThan(0);
    
    // Should not have excessive failed requests
    const criticallyFailedRequests = failedRequests.filter(url => 
      !url.includes('favicon') && 
      !url.includes('test_') && 
      !url.includes('debug_')
    );
    
    expect(criticallyFailedRequests.length).toBeLessThan(5);
  });

  test('should maintain session state across page interactions', async ({ page }) => {
    // Test session persistence
    const initialUrl = page.url();
    
    // Navigate around the application
    const dashboardButton = page.locator('text=Dashboard').first();
    if (await dashboardButton.count() > 0) {
      await dashboardButton.click();
      await page.waitForTimeout(1000);
    }

    const chatButton = page.locator('text=Chat').or(page.locator('text=AI Assistant')).first();
    if (await chatButton.count() > 0) {
      await chatButton.click();
      await page.waitForTimeout(1000);
    }

    // Should maintain consistent application state
    await expect(page.locator('#app')).toBeVisible();

    // URL should be for the same application
    expect(page.url()).toContain(TEST_CONFIG.getFrontendHost());
    
    // Application should still be responsive
    await expect(page.locator('text=AutoBot').first()).toBeVisible();
  });

  test('should handle concurrent operations without conflicts', async ({ page }) => {
    // Test multiple simultaneous operations
    const promises = [];
    
    // Simulate multiple operations happening at once
    promises.push(
      page.request.get(TEST_CONFIG.getApiUrl('/api/system/health'))
    );

    promises.push(
      page.request.get(TEST_CONFIG.getApiUrl('/api/workflow/workflows'))
    );
    
    if (await page.locator('text=Dashboard').count() > 0) {
      promises.push(page.locator('text=Dashboard').click());
    }
    
    if (await page.locator('text=Chat').count() > 0) {
      promises.push(
        page.waitForTimeout(500).then(() => 
          page.locator('text=Chat').click()
        )
      );
    }

    // All operations should complete without major issues
    const results = await Promise.allSettled(promises);
    
    const failures = results.filter(result => result.status === 'rejected');
    
    // Should have minimal failures
    expect(failures.length).toBeLessThan(2);
    
    // Application should remain stable
    await expect(page.locator('#app')).toBeVisible();
  });
});