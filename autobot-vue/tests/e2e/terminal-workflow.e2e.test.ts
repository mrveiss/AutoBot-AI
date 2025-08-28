import { test, expect } from '@playwright/test'

// E2E tests for terminal functionality
test.describe('Terminal Workflow E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the application
    await page.goto('/')

    // Navigate to terminal view or wait for terminal component to load
    await page.waitForSelector('[data-testid="terminal-window"]', { timeout: 10000 })
  })

  test('Basic terminal functionality', async ({ page }) => {
    // Verify terminal window is visible
    await expect(page.locator('[data-testid="terminal-window"]')).toBeVisible()

    // Verify terminal header
    await expect(page.locator('[data-testid="terminal-title"]')).toContainText('Terminal')

    // Verify control buttons are present
    await expect(page.locator('[data-testid="emergency-kill-button"]')).toBeVisible()
    await expect(page.locator('[data-testid="interrupt-button"]')).toBeVisible()
    await expect(page.locator('[data-testid="reconnect-button"]')).toBeVisible()
    await expect(page.locator('[data-testid="clear-button"]')).toBeVisible()
  })

  test('Terminal command execution', async ({ page }) => {
    // Locate command input
    const commandInput = page.locator('[data-testid="terminal-input"]')
    const sendButton = page.locator('[data-testid="terminal-send"]')

    // Test basic command
    await commandInput.fill('echo "Hello Terminal"')
    await sendButton.click()

    // Verify command appears in terminal output
    await expect(page.locator('[data-testid="terminal-output"]')).toContainText('echo "Hello Terminal"')

    // Test Enter key shortcut
    await commandInput.fill('pwd')
    await commandInput.press('Enter')

    // Verify input is cleared after sending
    await expect(commandInput).toHaveValue('')
  })

  test('Terminal control buttons', async ({ page }) => {
    // Test clear button
    const clearButton = page.locator('[data-testid="clear-button"]')
    await clearButton.click()

    // Terminal output should be empty or show cleared state
    const terminalOutput = page.locator('[data-testid="terminal-output"]')

    // Test reconnect button
    const reconnectButton = page.locator('[data-testid="reconnect-button"]')
    await reconnectButton.click()

    // Should show reconnecting state or successful reconnection
    await expect(reconnectButton).toBeVisible()
  })

  test('Terminal process management', async ({ page }) => {
    const commandInput = page.locator('[data-testid="terminal-input"]')
    const killButton = page.locator('[data-testid="emergency-kill-button"]')
    const interruptButton = page.locator('[data-testid="interrupt-button"]')

    // Start a long-running command (if backend is available)
    await commandInput.fill('sleep 10')
    await commandInput.press('Enter')

    // Wait a moment for process to start
    await page.waitForTimeout(1000)

    // Try to interrupt the process
    if (await interruptButton.isEnabled()) {
      await interruptButton.click()

      // Should show interruption in terminal output
      await expect(page.locator('[data-testid="terminal-output"]')).toContainText(/interrupt|ctrl\+c/i)
    }

    // Test emergency kill (should always be available for testing)
    if (await killButton.isEnabled()) {
      await killButton.click()

      // Should show confirmation or immediate effect
      await expect(page.locator('[data-testid="terminal-output"]')).toBeVisible()
    }
  })

  test('Terminal session management', async ({ page }) => {
    // Test session takeover/pause functionality
    const pauseButton = page.locator('[data-testid="automation-pause-button"]')

    if (await pauseButton.isVisible()) {
      const initialText = await pauseButton.textContent()
      await pauseButton.click()

      // Button text should change (PAUSE ↔ RESUME)
      await expect(pauseButton).not.toContainText(initialText)

      // Click again to toggle back
      await pauseButton.click()
      await expect(pauseButton).toContainText(initialText)
    }
  })

  test('Terminal output handling', async ({ page }) => {
    const commandInput = page.locator('[data-testid="terminal-input"]')
    const terminalOutput = page.locator('[data-testid="terminal-output"]')

    // Send multiple commands to test output accumulation
    const commands = ['echo "Line 1"', 'echo "Line 2"', 'echo "Line 3"']

    for (const command of commands) {
      await commandInput.fill(command)
      await commandInput.press('Enter')
      await page.waitForTimeout(500) // Small delay between commands
    }

    // Verify all commands appear in output
    for (const command of commands) {
      await expect(terminalOutput).toContainText(command)
    }

    // Test terminal scrolling - output should be scrollable
    const outputHeight = await terminalOutput.boundingBox()
    expect(outputHeight?.height).toBeGreaterThan(0)
  })

  test('Terminal error handling', async ({ page }) => {
    const commandInput = page.locator('[data-testid="terminal-input"]')

    // Test invalid command (if backend is available)
    await commandInput.fill('nonexistentcommand12345')
    await commandInput.press('Enter')

    // Should handle gracefully - either show error in output or handle silently
    await expect(page.locator('[data-testid="terminal-output"]')).toBeVisible()

    // Test empty command (should not send)
    await commandInput.fill('')
    await commandInput.press('Enter')

    // Should not add empty line to output unnecessarily
    await expect(commandInput).toHaveValue('')
  })

  test('Terminal WebSocket connection', async ({ page }) => {
    // Monitor WebSocket connections for terminal
    const wsConnections = []

    page.on('websocket', ws => {
      if (ws.url().includes('terminal')) {
        wsConnections.push(ws)
      }
    })

    // Trigger WebSocket connection by interacting with terminal
    const commandInput = page.locator('[data-testid="terminal-input"]')
    await commandInput.fill('echo "WebSocket test"')
    await commandInput.press('Enter')

    // Wait for potential WebSocket activity
    await page.waitForTimeout(2000)

    // Verify terminal remains functional even with connection issues
    await expect(page.locator('[data-testid="terminal-window"]')).toBeVisible()
    await expect(commandInput).toBeVisible()
  })

  test('Terminal command history', async ({ page }) => {
    const commandInput = page.locator('[data-testid="terminal-input"]')

    // Send a few commands to build history
    const commands = ['ls', 'pwd', 'echo "test"']

    for (const command of commands) {
      await commandInput.fill(command)
      await commandInput.press('Enter')
      await page.waitForTimeout(200)
    }

    // Test history navigation with arrow keys
    await commandInput.press('ArrowUp')
    await expect(commandInput).toHaveValue('echo "test"')

    await commandInput.press('ArrowUp')
    await expect(commandInput).toHaveValue('pwd')

    await commandInput.press('ArrowUp')
    await expect(commandInput).toHaveValue('ls')

    // Test going back down in history
    await commandInput.press('ArrowDown')
    await expect(commandInput).toHaveValue('pwd')
  })

  test('Terminal responsive design', async ({ page }) => {
    // Test terminal on different screen sizes

    // Mobile view
    await page.setViewportSize({ width: 375, height: 667 })
    await expect(page.locator('[data-testid="terminal-window"]')).toBeVisible()

    // Control buttons should be accessible on mobile
    await expect(page.locator('[data-testid="emergency-kill-button"]')).toBeVisible()

    // Tablet view
    await page.setViewportSize({ width: 768, height: 1024 })
    await expect(page.locator('[data-testid="terminal-window"]')).toBeVisible()

    // Desktop view
    await page.setViewportSize({ width: 1920, height: 1080 })
    await expect(page.locator('[data-testid="terminal-window"]')).toBeVisible()

    // Terminal should utilize available space effectively
    const terminalRect = await page.locator('[data-testid="terminal-window"]').boundingBox()
    expect(terminalRect?.width).toBeGreaterThan(800) // Should use desktop space
  })

  test('Terminal accessibility', async ({ page }) => {
    // Test keyboard navigation
    await page.keyboard.press('Tab')

    // Should be able to navigate to terminal controls
    const focusedElement = page.locator(':focus')
    await expect(focusedElement).toBeVisible()

    // Navigate to command input
    let tabCount = 0
    while (tabCount < 10) {
      await page.keyboard.press('Tab')
      const currentFocus = await page.evaluate(() => document.activeElement?.getAttribute('data-testid'))
      if (currentFocus === 'terminal-input') {
        break
      }
      tabCount++
    }

    // Verify command input is accessible
    await expect(page.locator('[data-testid="terminal-input"]:focus')).toBeVisible()

    // Test ARIA labels and roles
    const killButton = page.locator('[data-testid="emergency-kill-button"]')
    const ariaLabel = await killButton.getAttribute('aria-label')
    expect(ariaLabel).toBeTruthy()
    expect(ariaLabel).toContain('kill')
  })

  test('Terminal integration with chat', async ({ page }) => {
    // Test terminal notifications and integration with chat system

    // If there's a notification system, terminal events should appear
    const commandInput = page.locator('[data-testid="terminal-input"]')
    await commandInput.fill('echo "Integration test"')
    await commandInput.press('Enter')

    // Check if terminal activity is reflected in any status indicators
    const statusIndicators = page.locator('[data-testid*="status"]')
    if (await statusIndicators.count() > 0) {
      await expect(statusIndicators.first()).toBeVisible()
    }

    // Verify terminal window remains independent
    await expect(page.locator('[data-testid="terminal-window"]')).toBeVisible()
  })

  test('Terminal performance with rapid input', async ({ page }) => {
    const commandInput = page.locator('[data-testid="terminal-input"]')

    const startTime = Date.now()

    // Send rapid commands
    for (let i = 0; i < 10; i++) {
      await commandInput.fill(`echo "Rapid test ${i}"`)
      await commandInput.press('Enter')
      // Minimal delay to simulate rapid typing
      await page.waitForTimeout(10)
    }

    const endTime = Date.now()
    const duration = endTime - startTime

    // Should handle rapid input efficiently (< 5 seconds for 10 commands)
    expect(duration).toBeLessThan(5000)

    // Terminal should remain responsive
    await commandInput.fill('final test')
    await expect(commandInput).toHaveValue('final test')

    // Clear input
    await commandInput.press('Escape')
    await expect(commandInput).toHaveValue('')
  })
})
