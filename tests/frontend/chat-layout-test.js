// Chat Layout Test - Verify CSS fixes for misplaced layout
const { test, expect } = require('@playwright/test');

test('Chat layout should be properly positioned after fixes', async ({ page }) => {
  // Navigate to the frontend
  await page.goto('http://172.16.168.21:5173');

  // Wait for the app to load
  await page.waitForSelector('#app', { timeout: 10000 });

  // Navigate to chat interface
  await page.goto('http://172.16.168.21:5173/chat');

  // Wait for chat interface to load
  await page.waitForSelector('.chat-interface', { timeout: 15000 });

  // Check that main app container has correct styles
  const appContainer = await page.locator('#app');
  const appStyles = await appContainer.evaluate(el => {
    const computed = window.getComputedStyle(el);
    return {
      display: computed.display,
      flexDirection: computed.flexDirection,
      minHeight: computed.minHeight
    };
  });

  expect(appStyles.display).toBe('flex');
  expect(appStyles.flexDirection).toBe('column');
  expect(appStyles.minHeight).toBe('100vh');

  // Check that main content area has correct height calculation
  const mainContent = await page.locator('#main-content');
  const mainStyles = await mainContent.evaluate(el => {
    const computed = window.getComputedStyle(el);
    return {
      flex: computed.flex,
      overflow: computed.overflow,
      height: computed.height
    };
  });

  expect(mainStyles.flex).toBe('1 1 0%'); // flex-1
  expect(mainStyles.overflow).toBe('hidden');

  // Check chat view container height
  const chatView = await page.locator('.chat-view');
  const chatViewStyles = await chatView.evaluate(el => {
    const computed = window.getComputedStyle(el);
    return {
      height: computed.height,
      display: computed.display,
      flexDirection: computed.flexDirection
    };
  });

  expect(chatViewStyles.display).toBe('flex');
  expect(chatViewStyles.flexDirection).toBe('column');
  // Height should be calc(100vh - 64px) but computed style will show pixel value
  expect(chatViewStyles.height).toMatch(/^\d+px$/);

  // Check chat interface container
  const chatInterface = await page.locator('.chat-interface');
  const chatInterfaceStyles = await chatInterface.evaluate(el => {
    const computed = window.getComputedStyle(el);
    return {
      display: computed.display,
      height: computed.height,
      overflow: computed.overflow
    };
  });

  expect(chatInterfaceStyles.display).toBe('flex');
  expect(chatInterfaceStyles.overflow).toBe('hidden');
  // Should NOT have height: 100vh anymore, should inherit from parent

  // Verify no layout overflow issues
  const bodyScrollHeight = await page.evaluate(() => document.body.scrollHeight);
  const windowHeight = await page.evaluate(() => window.innerHeight);

  // Should not have significant overflow (allow small margin for browser differences)
  expect(bodyScrollHeight).toBeLessThanOrEqual(windowHeight + 10);

  // Check that sidebar is visible and properly sized
  const sidebar = await page.locator('.chat-interface > div:first-child');
  await expect(sidebar).toBeVisible();

  // Check that main chat area is visible
  const mainChatArea = await page.locator('.chat-interface > div:nth-child(2)');
  await expect(mainChatArea).toBeVisible();

  const mainChatStyles = await mainChatArea.evaluate(el => {
    const computed = window.getComputedStyle(el);
    return {
      flex: computed.flex,
      display: computed.display,
      flexDirection: computed.flexDirection
    };
  });

  expect(mainChatStyles.flex).toBe('1 1 0%'); // flex-1
  expect(mainChatStyles.display).toBe('flex');
  expect(mainChatStyles.flexDirection).toBe('column');

  console.log('✅ All chat layout tests passed - layout is properly positioned');
});

test('Header height calculation should be consistent', async ({ page }) => {
  await page.goto('http://172.16.168.21:5173');
  await page.waitForSelector('header', { timeout: 10000 });

  // Measure actual header height
  const header = await page.locator('header');
  const headerHeight = await header.evaluate(el => el.getBoundingClientRect().height);

  // Header should be 64px (h-16 class)
  expect(headerHeight).toBe(64);

  console.log(`✅ Header height is correct: ${headerHeight}px`);
});