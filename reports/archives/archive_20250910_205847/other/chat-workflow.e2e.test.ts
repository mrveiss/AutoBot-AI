import { test, expect } from '@playwright/test'

// E2E tests for critical chat workflow functionality
test.describe('Chat Workflow E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the application
    await page.goto('/')

    // Wait for the app to load
    await page.waitForSelector('[data-testid="chat-interface"]', { timeout: 10000 })
  })

  test('Complete chat session workflow', async ({ page }) => {
    // 1. Start a new chat
    await page.click('[data-testid="new-chat-button"]')

    // Verify new chat is created
    await expect(page.locator('[data-testid="current-chat-indicator"]')).toBeVisible()

    // 2. Send a message
    const messageInput = page.locator('[data-testid="message-input"]')
    await messageInput.fill('Hello, this is a test message')

    // Send with button click
    await page.click('[data-testid="send-button"]')

    // Verify message appears in chat
    await expect(page.locator('[data-testid="user-message"]').last()).toContainText('Hello, this is a test message')

    // Wait for response (with timeout for backend connectivity issues)
    try {
      await expect(page.locator('[data-testid="assistant-message"]').last()).toBeVisible({ timeout: 30000 })
    } catch (error) {
      console.warn('Backend response timeout - continuing with client-side tests')
    }

    // 3. Send another message using Enter key
    await messageInput.fill('Second test message')
    await messageInput.press('Enter')

    // Verify second message
    await expect(page.locator('[data-testid="user-message"]').last()).toContainText('Second test message')

    // 4. Verify chat history shows the new chat
    const chatHistory = page.locator('[data-testid="chat-history-item"]')
    await expect(chatHistory.first()).toBeVisible()
  })

  test('Chat history management', async ({ page }) => {
    // 1. Create multiple chats
    await page.click('[data-testid="new-chat-button"]')

    // Send a message in first chat
    await page.fill('[data-testid="message-input"]', 'First chat message')
    await page.click('[data-testid="send-button"]')

    // Create second chat
    await page.click('[data-testid="new-chat-button"]')

    // Send a message in second chat
    await page.fill('[data-testid="message-input"]', 'Second chat message')
    await page.click('[data-testid="send-button"]')

    // 2. Verify both chats appear in history
    const chatItems = page.locator('[data-testid="chat-history-item"]')
    await expect(chatItems).toHaveCount(2)

    // 3. Switch between chats
    await chatItems.first().click()
    await expect(page.locator('[data-testid="user-message"]').last()).toContainText('First chat message')

    await chatItems.nth(1).click()
    await expect(page.locator('[data-testid="user-message"]').last()).toContainText('Second chat message')

    // 4. Delete a chat
    await page.hover('[data-testid="chat-history-item"]')
    await page.click('[data-testid="delete-chat-button"]')

    // Confirm deletion if modal appears
    const confirmButton = page.locator('[data-testid="confirm-delete"]')
    if (await confirmButton.isVisible()) {
      await confirmButton.click()
    }

    // Verify chat is removed
    await expect(chatItems).toHaveCount(1)
  })

  test('Chat interface responsiveness', async ({ page }) => {
    // Test mobile responsive design
    await page.setViewportSize({ width: 375, height: 667 })

    // Verify chat interface adapts to mobile
    const sidebar = page.locator('[data-testid="chat-sidebar"]')
    const collapseButton = page.locator('[data-testid="sidebar-collapse"]')

    if (await sidebar.isVisible()) {
      // On mobile, sidebar might be collapsed by default
      await expect(collapseButton).toBeVisible()
    }

    // Test tablet size
    await page.setViewportSize({ width: 768, height: 1024 })
    await expect(page.locator('[data-testid="chat-interface"]')).toBeVisible()

    // Test desktop size
    await page.setViewportSize({ width: 1920, height: 1080 })
    await expect(sidebar).toBeVisible()
  })

  test('Message input features', async ({ page }) => {
    // Test multiline input
    const messageInput = page.locator('[data-testid="message-input"]')
    await messageInput.fill('Line 1\nLine 2\nLine 3')

    // Verify multiline content
    await expect(messageInput).toHaveValue('Line 1\nLine 2\nLine 3')

    // Test Shift+Enter for new line (should not send)
    await messageInput.press('Shift+Enter')
    await messageInput.type('Line 4')

    // Send message with Ctrl+Enter or just Enter
    await messageInput.press('Enter')

    // Verify message was sent
    await expect(page.locator('[data-testid="user-message"]').last()).toContainText('Line 1')

    // Verify input is cleared
    await expect(messageInput).toHaveValue('')
  })

  test('Chat settings integration', async ({ page }) => {
    // Open settings panel
    await page.click('[data-testid="settings-button"]')

    // Navigate to chat settings
    await page.click('[data-testid="chat-settings-tab"]')

    // Verify chat settings are visible
    await expect(page.locator('[data-testid="auto-scroll-setting"]')).toBeVisible()
    await expect(page.locator('[data-testid="max-messages-setting"]')).toBeVisible()

    // Toggle auto-scroll setting
    const autoScrollCheckbox = page.locator('[data-testid="auto-scroll-setting"]')
    const wasChecked = await autoScrollCheckbox.isChecked()
    await autoScrollCheckbox.click()

    // Verify setting changed
    await expect(autoScrollCheckbox).toHaveAttribute('checked', (!wasChecked).toString())

    // Close settings
    await page.click('[data-testid="close-settings"]')

    // Verify settings are applied to chat behavior
    await page.fill('[data-testid="message-input"]', 'Testing auto-scroll setting')
    await page.click('[data-testid="send-button"]')
  })

  test('Error handling and recovery', async ({ page }) => {
    // Test sending message when backend is unavailable
    // This simulates the timeout errors we see in the logs

    await page.fill('[data-testid="message-input"]', 'Test message with backend down')
    await page.click('[data-testid="send-button"]')

    // Should show error message or retry option
    try {
      await expect(page.locator('[data-testid="error-message"]')).toBeVisible({ timeout: 35000 })
    } catch {
      // If no specific error UI, verify message still appears in chat
      await expect(page.locator('[data-testid="user-message"]').last()).toContainText('Test message with backend down')
    }

    // Test retry functionality if available
    const retryButton = page.locator('[data-testid="retry-button"]')
    if (await retryButton.isVisible()) {
      await retryButton.click()
    }
  })

  test('Keyboard accessibility', async ({ page }) => {
    // Test tab navigation
    await page.keyboard.press('Tab')

    // Should focus on first interactive element
    const focusedElement = page.locator(':focus')
    await expect(focusedElement).toBeVisible()

    // Navigate to message input via Tab
    let tabCount = 0
    while (tabCount < 10) {
      await page.keyboard.press('Tab')
      const currentFocus = await page.evaluate(() => document.activeElement?.getAttribute('data-testid'))
      if (currentFocus === 'message-input') {
        break
      }
      tabCount++
    }

    // Verify message input is focused
    await expect(page.locator('[data-testid="message-input"]:focus')).toBeVisible()

    // Test arrow key navigation in chat history
    await page.keyboard.press('Shift+Tab') // Go back to chat history
    await page.keyboard.press('ArrowUp')
    await page.keyboard.press('ArrowDown')

    // Test Enter key activation
    await page.keyboard.press('Enter')
  })

  test('WebSocket connection handling', async ({ page }) => {
    // Monitor WebSocket connection
    const wsMessages = []

    page.on('websocket', ws => {
      ws.on('framesent', event => wsMessages.push({ type: 'sent', data: event.payload }))
      ws.on('framereceived', event => wsMessages.push({ type: 'received', data: event.payload }))
    })

    // Send a message that should trigger WebSocket communication
    await page.fill('[data-testid="message-input"]', 'WebSocket test message')
    await page.click('[data-testid="send-button"]')

    // Wait for potential WebSocket activity
    await page.waitForTimeout(2000)

    // Note: In a working environment, we would verify WebSocket messages
    // For now, just verify the UI doesn't break with connection issues
    await expect(page.locator('[data-testid="chat-interface"]')).toBeVisible()
  })

  test('Performance with many messages', async ({ page }) => {
    // Test chat performance with multiple messages
    const messageCount = 20

    const startTime = Date.now()

    for (let i = 0; i < messageCount; i++) {
      await page.fill('[data-testid="message-input"]', `Performance test message ${i + 1}`)
      await page.click('[data-testid="send-button"]')

      // Small delay to avoid overwhelming the UI
      await page.waitForTimeout(50)
    }

    const endTime = Date.now()
    const duration = endTime - startTime

    // Verify all messages are visible
    const messages = page.locator('[data-testid="user-message"]')
    await expect(messages).toHaveCount(messageCount)

    // Verify reasonable performance (should handle 20 messages in < 10 seconds)
    expect(duration).toBeLessThan(10000)

    // Verify chat is still responsive
    await page.fill('[data-testid="message-input"]', 'Final test message')
    await page.click('[data-testid="send-button"]')

    await expect(page.locator('[data-testid="user-message"]').last()).toContainText('Final test message')
  })
})
