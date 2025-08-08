import { test, expect } from '@playwright/test';

test.describe('AutoBot GUI Functionality', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('should load application correctly', async ({ page }) => {
    // Check page title
    await expect(page).toHaveTitle(/AutoBot/);

    // Check main application container
    await expect(page.locator('#app')).toBeVisible();

    // Check if main navigation/header is present
    const navigation = page.locator('nav, header, [data-testid="navigation"]').first();
    await expect(navigation).toBeVisible();
  });

  test('should display main dashboard elements', async ({ page }) => {
    // Look for common dashboard elements
    const dashboardElements = [
      '.dashboard',
      '.main-content',
      '.sidebar',
      '[data-testid="dashboard"]',
      '.control-panel'
    ];

    let foundDashboard = false;
    for (const selector of dashboardElements) {
      try {
        await expect(page.locator(selector)).toBeVisible({ timeout: 2000 });
        foundDashboard = true;
        break;
      } catch (e) {
        // Continue to next selector
      }
    }

    expect(foundDashboard).toBeTruthy();
  });

  test('should have responsive design', async ({ page }) => {
    // Test desktop view
    await page.setViewportSize({ width: 1200, height: 800 });
    await page.waitForLoadState('networkidle');

    // Main content should be visible in desktop
    await expect(page.locator('#app')).toBeVisible();

    // Test tablet view
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500);

    await expect(page.locator('#app')).toBeVisible();

    // Test mobile view
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);

    await expect(page.locator('#app')).toBeVisible();
  });

  test('should handle navigation between sections', async ({ page }) => {
    // Look for navigation links
    const navLinks = page.locator('a, [role="button"], .nav-item, .menu-item');
    const linkCount = await navLinks.count();

    if (linkCount > 0) {
      // Click on first navigation link
      const firstLink = navLinks.first();
      await firstLink.click();

      // Wait for navigation to complete
      await page.waitForLoadState('networkidle');

      // Verify we're still in the application
      await expect(page.locator('#app')).toBeVisible();
    }
  });

  test('should handle theme switching if available', async ({ page }) => {
    // Look for theme toggle button
    const themeButtons = [
      '[data-testid="theme-toggle"]',
      '.theme-toggle',
      '.dark-mode-toggle',
      'button[aria-label*="theme"]',
      'button[title*="theme"]'
    ];

    for (const selector of themeButtons) {
      const themeButton = page.locator(selector);
      if (await themeButton.isVisible()) {
        await themeButton.click();

        // Wait for theme change
        await page.waitForTimeout(500);

        // Verify theme changed (look for dark/light class changes)
        const bodyClasses = await page.locator('body').getAttribute('class');
        const htmlClasses = await page.locator('html').getAttribute('class');

        const hasThemeClass = (bodyClasses && (bodyClasses.includes('dark') || bodyClasses.includes('light'))) ||
                             (htmlClasses && (htmlClasses.includes('dark') || htmlClasses.includes('light')));

        expect(hasThemeClass).toBeTruthy();
        break;
      }
    }
  });

  test('should display system status information', async ({ page }) => {
    // Look for system status indicators
    const statusElements = [
      '[data-testid="system-status"]',
      '.system-status',
      '.status-indicator',
      '.health-check',
      '.connection-status'
    ];

    let foundStatus = false;
    for (const selector of statusElements) {
      if (await page.locator(selector).isVisible()) {
        foundStatus = true;
        break;
      }
    }

    // If no explicit status elements, check for general status in UI
    if (!foundStatus) {
      // Look for any indicators of system health
      const statusText = await page.textContent('body');
      const hasStatusInfo = statusText?.includes('connected') ||
                           statusText?.includes('online') ||
                           statusText?.includes('ready') ||
                           statusText?.includes('status');

      expect(hasStatusInfo).toBeTruthy();
    } else {
      expect(foundStatus).toBeTruthy();
    }
  });

  test('should handle errors gracefully', async ({ page }) => {
    // Block all API requests to simulate backend failure
    await page.route('**/api/**', route => route.abort());

    // Reload page to trigger error state
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Should still show basic UI structure
    await expect(page.locator('#app')).toBeVisible();

    // Look for error handling indicators
    const errorElements = [
      '[data-testid="error-message"]',
      '.error-message',
      '.connection-error',
      '.offline-indicator'
    ];

    let foundError = false;
    for (const selector of errorElements) {
      if (await page.locator(selector).isVisible()) {
        foundError = true;
        break;
      }
    }

    // Alternative: check for error text in UI
    if (!foundError) {
      const bodyText = await page.textContent('body');
      const hasErrorText = bodyText?.includes('error') ||
                          bodyText?.includes('connection') ||
                          bodyText?.includes('offline');

      expect(hasErrorText).toBeTruthy();
    }
  });

  test('should maintain accessibility standards', async ({ page }) => {
    // Check for proper heading structure
    const h1Count = await page.locator('h1').count();
    expect(h1Count).toBeGreaterThanOrEqual(1);

    // Check for alt text on images
    const images = page.locator('img');
    const imageCount = await images.count();

    for (let i = 0; i < imageCount; i++) {
      const img = images.nth(i);
      const alt = await img.getAttribute('alt');
      const ariaLabel = await img.getAttribute('aria-label');

      // Images should have alt text or aria-label
      expect(alt !== null || ariaLabel !== null).toBeTruthy();
    }

    // Check for proper button labeling
    const buttons = page.locator('button');
    const buttonCount = await buttons.count();

    for (let i = 0; i < Math.min(buttonCount, 5); i++) { // Check first 5 buttons
      const button = buttons.nth(i);
      const text = await button.textContent();
      const ariaLabel = await button.getAttribute('aria-label');
      const title = await button.getAttribute('title');

      // Buttons should have text, aria-label, or title
      expect(text?.trim() || ariaLabel || title).toBeTruthy();
    }
  });

  test('should support keyboard navigation', async ({ page }) => {
    // Test tab navigation
    await page.keyboard.press('Tab');

    // Check if focus is visible
    const focusedElement = page.locator(':focus');
    await expect(focusedElement).toBeVisible();

    // Tab through a few more elements
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');

    // Should still have focused element
    await expect(page.locator(':focus')).toBeVisible();

    // Test escape key (should not break anything)
    await page.keyboard.press('Escape');
    await expect(page.locator('#app')).toBeVisible();
  });

  test('should handle page refresh correctly', async ({ page }) => {
    // Navigate around if possible
    const links = page.locator('a[href^="/"], a[href^="#"]');
    if (await links.count() > 0) {
      await links.first().click();
      await page.waitForLoadState('networkidle');
    }

    // Refresh the page
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Application should still load correctly
    await expect(page.locator('#app')).toBeVisible();
    await expect(page).not.toHaveURL(/.*error.*/);
  });
});
