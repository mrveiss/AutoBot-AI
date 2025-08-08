import { test, expect } from '@playwright/test';

test.describe('Message Display Toggles', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the chat interface
    await page.goto('http://localhost:5173');

    // Wait for the chat interface to load
    await page.waitForSelector('.chat-interface', { timeout: 10000 });

    // Open sidebar if collapsed
    const sidebarContent = page.locator('.sidebar-content');
    const sidebarContentVisible = await sidebarContent.isVisible();
    if (!sidebarContentVisible) {
      await page.locator('.toggle-sidebar').click();
      await page.waitForSelector('.sidebar-content', { state: 'visible' });
    }
  });

  test('should have all message display toggle options visible', async ({ page }) => {
    // Check that all toggle checkboxes exist
    const toggles = [
      'Show Thoughts',
      'Show JSON Output',
      'Show Utility Messages',
      'Show Planning Messages',
      'Show Debug Messages',
      'Autoscroll'
    ];

    for (const toggleText of toggles) {
      const toggle = page.locator('label').filter({ hasText: toggleText });
      await expect(toggle).toBeVisible();

      const checkbox = toggle.locator('input[type="checkbox"]');
      await expect(checkbox).toBeVisible();
    }
  });

  test('should toggle Show Thoughts checkbox', async ({ page }) => {
    const thoughtsToggle = page.locator('label').filter({ hasText: 'Show Thoughts' }).locator('input[type="checkbox"]');

    // Get initial state
    const initialState = await thoughtsToggle.isChecked();

    // Click to toggle
    await thoughtsToggle.click();

    // Verify state changed
    const newState = await thoughtsToggle.isChecked();
    expect(newState).toBe(!initialState);

    // Click again to toggle back
    await thoughtsToggle.click();

    // Verify state returned to original
    const finalState = await thoughtsToggle.isChecked();
    expect(finalState).toBe(initialState);
  });

  test('should toggle Show JSON Output checkbox', async ({ page }) => {
    const jsonToggle = page.locator('label').filter({ hasText: 'Show JSON Output' }).locator('input[type="checkbox"]');

    // Get initial state
    const initialState = await jsonToggle.isChecked();

    // Click to toggle
    await jsonToggle.click();

    // Verify state changed
    const newState = await jsonToggle.isChecked();
    expect(newState).toBe(!initialState);
  });

  test('should toggle Show Debug Messages checkbox', async ({ page }) => {
    const debugToggle = page.locator('label').filter({ hasText: 'Show Debug Messages' }).locator('input[type="checkbox"]');

    // Get initial state
    const initialState = await debugToggle.isChecked();

    // Click to toggle
    await debugToggle.click();

    // Verify state changed
    const newState = await debugToggle.isChecked();
    expect(newState).toBe(!initialState);
  });

  test('should toggle Autoscroll checkbox', async ({ page }) => {
    const autoscrollToggle = page.locator('label').filter({ hasText: 'Autoscroll' }).locator('input[type="checkbox"]');

    // Get initial state
    const initialState = await autoscrollToggle.isChecked();

    // Click to toggle
    await autoscrollToggle.click();

    // Verify state changed
    const newState = await autoscrollToggle.isChecked();
    expect(newState).toBe(!initialState);
  });

  test('should persist toggle state after page reload', async ({ page }) => {
    const thoughtsToggle = page.locator('label').filter({ hasText: 'Show Thoughts' }).locator('input[type="checkbox"]');

    // Set a specific state
    if (await thoughtsToggle.isChecked()) {
      await thoughtsToggle.click(); // Uncheck if checked
    }

    // Verify it's unchecked
    await expect(thoughtsToggle).not.toBeChecked();

    // Reload page
    await page.reload();
    await page.waitForSelector('.chat-interface', { timeout: 10000 });

    // Open sidebar again after reload
    const sidebarContent = page.locator('.sidebar-content');
    const sidebarContentVisible = await sidebarContent.isVisible();
    if (!sidebarContentVisible) {
      await page.locator('.toggle-sidebar').click();
      await page.waitForSelector('.sidebar-content', { state: 'visible' });
    }

    // Verify state persisted
    const reloadedToggle = page.locator('label').filter({ hasText: 'Show Thoughts' }).locator('input[type="checkbox"]');
    await expect(reloadedToggle).not.toBeChecked();
  });

  test('should send a message and verify message filtering works', async ({ page }) => {
    // First, ensure all toggle options are in a known state
    const debugToggle = page.locator('label').filter({ hasText: 'Show Debug Messages' }).locator('input[type="checkbox"]');

    // Make sure debug messages are initially hidden
    if (await debugToggle.isChecked()) {
      await debugToggle.click();
      await expect(debugToggle).not.toBeChecked();
    }

    // Send a test message
    const messageInput = page.locator('input[type="text"]', { hasText: /type.*message/i }).or(page.locator('.message-input')).or(page.locator('[placeholder*="message"]'));
    await messageInput.fill('Hello, this is a test message');

    // Submit the message
    const sendButton = page.locator('button').filter({ hasText: /send/i });
    await sendButton.click();

    // Wait for response
    await page.waitForTimeout(2000);

    // Count visible messages before showing debug
    const messagesBefore = await page.locator('.message').count();

    // Now enable debug messages
    await debugToggle.check();
    await expect(debugToggle).toBeChecked();

    // Count visible messages after showing debug
    await page.waitForTimeout(500); // Give time for filtering to apply
    const messagesAfter = await page.locator('.message').count();

    // There should be the same or more messages visible after enabling debug
    // (might be the same if no debug messages were generated)
    expect(messagesAfter).toBeGreaterThanOrEqual(messagesBefore);
  });
});
