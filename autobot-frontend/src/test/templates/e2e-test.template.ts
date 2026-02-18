import { test, expect } from '@playwright/test'

// E2E Test Template for AutoBot Features
test.describe('Feature Name E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the application
    await page.goto('/')

    // Wait for the app to load
    await page.waitForSelector('[data-testid="app-container"]', { timeout: 10000 })

    // Optional: Set up authentication or initial state
    // await page.click('[data-testid="login-button"]')
    // await page.fill('[data-testid="username"]', 'test-user')
    // await page.fill('[data-testid="password"]', 'test-password')
    // await page.click('[data-testid="submit-login"]')
  })

  test('Primary user workflow', async ({ page }) => {
    // Step 1: Navigate to feature
    await page.click('[data-testid="feature-nav-button"]')

    // Verify navigation worked
    await expect(page.locator('[data-testid="feature-container"]')).toBeVisible()

    // Step 2: Perform main action
    await page.fill('[data-testid="input-field"]', 'Test input')
    await page.click('[data-testid="submit-button"]')

    // Step 3: Verify results
    await expect(page.locator('[data-testid="success-message"]')).toBeVisible()
    await expect(page.locator('[data-testid="result-display"]')).toContainText('Test input')

    // Step 4: Verify state persistence
    await page.reload()
    await expect(page.locator('[data-testid="result-display"]')).toContainText('Test input')
  })

  test('Error handling workflow', async ({ page }) => {
    // Navigate to feature
    await page.click('[data-testid="feature-nav-button"]')

    // Trigger error condition
    await page.fill('[data-testid="input-field"]', 'INVALID_INPUT')
    await page.click('[data-testid="submit-button"]')

    // Verify error handling
    await expect(page.locator('[data-testid="error-message"]')).toBeVisible()
    await expect(page.locator('[data-testid="error-message"]')).toContainText(/invalid/i)

    // Verify retry functionality
    const retryButton = page.locator('[data-testid="retry-button"]')
    if (await retryButton.isVisible()) {
      await retryButton.click()
      await expect(page.locator('[data-testid="error-message"]')).not.toBeVisible()
    }

    // Test recovery
    await page.fill('[data-testid="input-field"]', 'Valid input')
    await page.click('[data-testid="submit-button"]')
    await expect(page.locator('[data-testid="success-message"]')).toBeVisible()
  })

  test('Multi-step workflow', async ({ page }) => {
    await page.click('[data-testid="feature-nav-button"]')

    // Step 1: Initial setup
    await page.click('[data-testid="start-workflow-button"]')
    await expect(page.locator('[data-testid="step-1-container"]')).toBeVisible()

    await page.fill('[data-testid="step-1-input"]', 'Step 1 data')
    await page.click('[data-testid="next-button"]')

    // Step 2: Configuration
    await expect(page.locator('[data-testid="step-2-container"]')).toBeVisible()
    await page.check('[data-testid="option-checkbox"]')
    await page.selectOption('[data-testid="dropdown-select"]', 'option-1')
    await page.click('[data-testid="next-button"]')

    // Step 3: Review and confirm
    await expect(page.locator('[data-testid="step-3-container"]')).toBeVisible()
    await expect(page.locator('[data-testid="review-step-1"]')).toContainText('Step 1 data')
    await expect(page.locator('[data-testid="review-option"]')).toContainText('option-1')

    await page.click('[data-testid="confirm-button"]')

    // Final verification
    await expect(page.locator('[data-testid="completion-message"]')).toBeVisible()
    await expect(page.locator('[data-testid="workflow-result"]')).toBeVisible()
  })

  test('Real-time updates', async ({ page }) => {
    await page.click('[data-testid="feature-nav-button"]')

    // Monitor WebSocket connections
    const wsMessages: any[] = []
    page.on('websocket', ws => {
      ws.on('framereceived', event => {
        try {
          const data = JSON.parse(event.payload.toString())
          wsMessages.push(data)
        } catch (e) {
          // Ignore non-JSON messages
        }
      })
    })

    // Trigger action that should result in real-time updates
    await page.click('[data-testid="start-realtime-button"]')

    // Wait for initial update
    await expect(page.locator('[data-testid="status-indicator"]')).toContainText('Active')

    // Wait for real-time data
    await expect(page.locator('[data-testid="realtime-data"]')).toBeVisible({ timeout: 10000 })

    // Verify updates are received
    await page.waitForTimeout(2000) // Allow time for updates

    // Stop real-time updates
    await page.click('[data-testid="stop-realtime-button"]')
    await expect(page.locator('[data-testid="status-indicator"]')).toContainText('Stopped')
  })

  test('Form validation', async ({ page }) => {
    await page.click('[data-testid="feature-nav-button"]')

    // Test required field validation
    await page.click('[data-testid="submit-button"]')
    await expect(page.locator('[data-testid="required-error"]')).toBeVisible()

    // Test field format validation
    await page.fill('[data-testid="email-field"]', 'invalid-email')
    await page.click('[data-testid="submit-button"]')
    await expect(page.locator('[data-testid="email-error"]')).toContainText(/valid email/i)

    // Test field length validation
    await page.fill('[data-testid="text-field"]', 'a'.repeat(1000))
    await page.click('[data-testid="submit-button"]')
    await expect(page.locator('[data-testid="length-error"]')).toBeVisible()

    // Test successful validation
    await page.fill('[data-testid="email-field"]', 'test@example.com')
    await page.fill('[data-testid="text-field"]', 'Valid text')
    await page.fill('[data-testid="required-field"]', 'Required value')

    await page.click('[data-testid="submit-button"]')
    await expect(page.locator('[data-testid="success-message"]')).toBeVisible()
  })

  test('Keyboard navigation', async ({ page }) => {
    await page.click('[data-testid="feature-nav-button"]')

    // Test tab navigation
    await page.keyboard.press('Tab')
    expect(await page.evaluate(() => document.activeElement?.getAttribute('data-testid')))
      .toBeTruthy()

    // Navigate through form fields
    const formFields = [
      '[data-testid="first-field"]',
      '[data-testid="second-field"]',
      '[data-testid="submit-button"]'
    ]

    for (const field of formFields) {
      await page.keyboard.press('Tab')
      await expect(page.locator(`${field}:focus`)).toBeVisible()
    }

    // Test Enter key submission
    await page.fill('[data-testid="first-field"]', 'Test value')
    await page.keyboard.press('Enter')

    await expect(page.locator('[data-testid="success-message"]')).toBeVisible()

    // Test Escape key cancellation
    await page.click('[data-testid="open-modal-button"]')
    await expect(page.locator('[data-testid="modal"]')).toBeVisible()

    await page.keyboard.press('Escape')
    await expect(page.locator('[data-testid="modal"]')).not.toBeVisible()
  })

  test('Mobile responsive behavior', async ({ page }) => {
    // Test mobile viewport
    await page.setViewportSize({ width: 375, height: 667 })
    await page.click('[data-testid="feature-nav-button"]')

    // Verify mobile layout adaptations
    await expect(page.locator('[data-testid="mobile-nav"]')).toBeVisible()
    await expect(page.locator('[data-testid="desktop-sidebar"]')).not.toBeVisible()

    // Test mobile interactions
    await page.click('[data-testid="mobile-menu-toggle"]')
    await expect(page.locator('[data-testid="mobile-menu"]')).toBeVisible()

    // Test swipe gestures (if applicable)
    const swipeElement = page.locator('[data-testid="swipeable-content"]')
    if (await swipeElement.isVisible()) {
      // Simulate swipe
      await swipeElement.hover()
      await page.mouse.down()
      await page.mouse.move(100, 0)
      await page.mouse.up()

      await expect(page.locator('[data-testid="next-content"]')).toBeVisible()
    }

    // Test tablet viewport
    await page.setViewportSize({ width: 768, height: 1024 })
    await expect(page.locator('[data-testid="tablet-layout"]')).toBeVisible()
  })

  test('Performance under load', async ({ page }) => {
    await page.click('[data-testid="feature-nav-button"]')

    const startTime = Date.now()

    // Perform multiple rapid operations
    for (let i = 0; i < 20; i++) {
      await page.fill('[data-testid="input-field"]', `Test ${i}`)
      await page.click('[data-testid="add-item-button"]')

      // Small delay to allow processing
      await page.waitForTimeout(50)
    }

    const endTime = Date.now()
    const duration = endTime - startTime

    // Verify all items were added
    const items = page.locator('[data-testid="list-item"]')
    await expect(items).toHaveCount(20)

    // Verify reasonable performance (< 10 seconds for 20 operations)
    expect(duration).toBeLessThan(10000)

    // Verify UI remains responsive
    await page.fill('[data-testid="input-field"]', 'Final test')
    await page.click('[data-testid="add-item-button"]')

    await expect(items).toHaveCount(21)
  })

  test('Data persistence across sessions', async ({ page, context }) => {
    await page.click('[data-testid="feature-nav-button"]')

    // Create some data
    await page.fill('[data-testid="persistent-field"]', 'Persistent data')
    await page.click('[data-testid="save-button"]')

    await expect(page.locator('[data-testid="save-confirmation"]')).toBeVisible()

    // Create new browser context (simulates new session)
    const newContext = await context.browser()!.newContext()
    const newPage = await newContext.newPage()

    await newPage.goto('/')
    await newPage.click('[data-testid="feature-nav-button"]')

    // Verify data persisted
    await expect(newPage.locator('[data-testid="persistent-field"]'))
      .toHaveValue('Persistent data')

    await newContext.close()
  })

  test('Accessibility compliance', async ({ page }) => {
    await page.click('[data-testid="feature-nav-button"]')

    // Test heading structure
    const headings = page.locator('h1, h2, h3, h4, h5, h6')
    const headingCount = await headings.count()
    expect(headingCount).toBeGreaterThan(0)

    // Test alt text on images
    const images = page.locator('img')
    const imageCount = await images.count()

    for (let i = 0; i < imageCount; i++) {
      const img = images.nth(i)
      const alt = await img.getAttribute('alt')
      expect(alt).toBeTruthy()
    }

    // Test form labels
    const inputs = page.locator('input[type="text"], input[type="email"], textarea')
    const inputCount = await inputs.count()

    for (let i = 0; i < inputCount; i++) {
      const input = inputs.nth(i)
      const id = await input.getAttribute('id')

      if (id) {
        const label = page.locator(`label[for="${id}"]`)
        await expect(label).toBeVisible()
      }
    }

    // Test keyboard accessibility
    await page.keyboard.press('Tab')
    const focusedElement = page.locator(':focus')
    await expect(focusedElement).toBeVisible()

    // Test ARIA attributes
    const interactiveElements = page.locator('button, [role="button"]')
    const elementCount = await interactiveElements.count()

    for (let i = 0; i < Math.min(elementCount, 5); i++) {
      const element = interactiveElements.nth(i)
      const ariaLabel = await element.getAttribute('aria-label')
      const text = await element.textContent()

      expect(ariaLabel || text).toBeTruthy()
    }
  })
})
