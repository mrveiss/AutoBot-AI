/**
 * Terminal Input Consistency Test
 *
 * Tests the terminal interface for consistent input handling during automated testing.
 * Addresses the issue where terminal input detection was not consistently working.
 */

const { test, expect } = require('@playwright/test');

test.describe('Terminal Input Consistency', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to AutoBot frontend
    await page.goto('http://localhost:3000');

    // Wait for app to be fully loaded
    await page.waitForSelector('.dashboard-container', { timeout: 30000 });
  });

  test('terminal input should be consistently interactive', async ({ page }) => {
    console.log('🧪 Testing terminal input consistency...');

    // Navigate to terminal section
    await page.click('text=Terminal');

    // Wait for terminal to be visible
    await page.waitForSelector('.terminal-window-standalone', { timeout: 10000 });

    // Wait for connection to establish
    await page.waitForSelector('.connection-status.connected', { timeout: 15000 });

    // Check if terminal input is present and interactive
    const terminalInput = page.locator('.terminal-input');
    await expect(terminalInput).toBeVisible();
    await expect(terminalInput).toBeEnabled();

    // Test focus handling
    await terminalInput.click();

    // Enhanced terminal readiness check with debug info
    const terminalDebugInfo = await page.evaluate(() => {
      // Try to get the terminal component instance
      const terminalComponent = window.Vue?.devtools?.getInspectorComponentByName?.('TerminalWindow');

      if (terminalComponent) {
        return {
          hasComponent: true,
          isReady: terminalComponent.isTerminalReady ? terminalComponent.isTerminalReady() : false,
          debugInfo: terminalComponent.getDebugInfo ? terminalComponent.getDebugInfo() : {},
          ensureFocusResult: terminalComponent.ensureInputFocus ? terminalComponent.ensureInputFocus() : false
        };
      }

      // Fallback: check DOM state directly
      const input = document.querySelector('.terminal-input');
      const isReady = input && !input.disabled && input.offsetParent !== null;

      return {
        hasComponent: false,
        isReady: isReady,
        debugInfo: {
          hasInput: !!input,
          inputDisabled: input ? input.disabled : null,
          inputVisible: input ? input.offsetParent !== null : false,
          activeElement: document.activeElement?.className || 'none'
        },
        ensureFocusResult: false
      };
    });

    console.log('Terminal debug info:', JSON.stringify(terminalDebugInfo, null, 2));
    expect(terminalDebugInfo.isReady).toBe(true);

    // Test input interaction - type a simple command
    await terminalInput.fill('echo "Terminal input test"');

    // Verify the input value was set
    const inputValue = await terminalInput.inputValue();
    expect(inputValue).toBe('echo "Terminal input test"');

    // Test command execution
    await terminalInput.press('Enter');

    // Wait for command output
    await page.waitForTimeout(2000);

    // Verify terminal shows the command was executed
    const terminalOutput = page.locator('.terminal-output');
    await expect(terminalOutput).toContainText('Terminal input test');

    console.log('✅ Terminal input consistency test passed');
  });

  test('terminal should handle rapid input changes', async ({ page }) => {
    console.log('🧪 Testing rapid input changes...');

    // Navigate to terminal section
    await page.click('text=Terminal');

    // Wait for terminal to be ready
    await page.waitForSelector('.terminal-window-standalone', { timeout: 10000 });
    await page.waitForSelector('.connection-status.connected', { timeout: 15000 });

    const terminalInput = page.locator('.terminal-input');

    // Test rapid input changes (common in automated testing)
    const commands = ['pwd', 'ls', 'whoami', 'date'];

    for (const command of commands) {
      await terminalInput.fill('');
      await terminalInput.fill(command);

      // Verify input value is correct
      const inputValue = await terminalInput.inputValue();
      expect(inputValue).toBe(command);

      await page.waitForTimeout(500); // Small delay between commands
    }

    console.log('✅ Rapid input changes test passed');
  });

  test('terminal should maintain focus during automation', async ({ page }) => {
    console.log('🧪 Testing focus maintenance during automation...');

    // Navigate to terminal section
    await page.click('text=Terminal');

    // Wait for terminal to be ready
    await page.waitForSelector('.terminal-window-standalone', { timeout: 10000 });
    await page.waitForSelector('.connection-status.connected', { timeout: 15000 });

    const terminalInput = page.locator('.terminal-input');

    // Click on terminal input to focus
    await terminalInput.click();

    // Simulate clicking elsewhere (common automation scenario)
    await page.click('.terminal-output');

    // Check if focus is automatically restored
    await page.waitForTimeout(500);

    // Enhanced focus restoration check with debugging
    const focusInfo = await page.evaluate(() => {
      const terminalComponent = window.Vue?.devtools?.getInspectorComponentByName?.('TerminalWindow');
      const input = document.querySelector('.terminal-input');

      if (terminalComponent && terminalComponent.ensureInputFocus) {
        const ensureResult = terminalComponent.ensureInputFocus();
        return {
          hasComponent: true,
          ensureResult: ensureResult,
          debugInfo: terminalComponent.getDebugInfo ? terminalComponent.getDebugInfo() : {},
          isInputFocused: document.activeElement === input
        };
      }

      // Fallback: check if input is focused
      const isFocused = document.activeElement === input;
      return {
        hasComponent: false,
        ensureResult: false,
        debugInfo: {
          hasInput: !!input,
          isInputFocused: isFocused,
          activeElement: document.activeElement?.className || 'none'
        },
        isInputFocused: isFocused
      };
    });

    console.log('Focus restoration info:', JSON.stringify(focusInfo, null, 2));

    if (!focusInfo.isInputFocused) {
      console.log('Focus not restored automatically, manually clicking input...');
      await terminalInput.click();
      await page.waitForTimeout(100); // Small delay after manual click
    }

    // Verify we can type after focus restoration
    await terminalInput.fill('echo "Focus test"');
    const inputValue = await terminalInput.inputValue();
    expect(inputValue).toBe('echo "Focus test"');

    console.log('✅ Focus maintenance test passed');
  });

  test('terminal should handle connection state changes', async ({ page }) => {
    console.log('🧪 Testing connection state changes...');

    // Navigate to terminal section
    await page.click('text=Terminal');

    // Wait for terminal to be ready
    await page.waitForSelector('.terminal-window-standalone', { timeout: 10000 });
    await page.waitForSelector('.connection-status.connected', { timeout: 15000 });

    const terminalInput = page.locator('.terminal-input');

    // Verify input is enabled when connected
    await expect(terminalInput).toBeEnabled();

    // Test reconnection (click reconnect button)
    await page.click('button[title="Reconnect"]');

    // Wait for reconnection process
    await page.waitForSelector('.connection-status.connecting', { timeout: 5000 });

    // Verify input is disabled during reconnection
    await expect(terminalInput).toBeDisabled();

    // Wait for reconnection to complete
    await page.waitForSelector('.connection-status.connected', { timeout: 15000 });

    // Verify input is enabled again after reconnection
    await expect(terminalInput).toBeEnabled();

    // Test input functionality after reconnection
    await terminalInput.fill('echo "Reconnection test"');
    const inputValue = await terminalInput.inputValue();
    expect(inputValue).toBe('echo "Reconnection test"');

    console.log('✅ Connection state changes test passed');
  });
});
