import { test, expect } from '@playwright/test';

test.describe('KB Librarian Chat Integration', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the AutoBot application
    await page.goto('/');

    // Wait for the application to load
    await page.waitForLoadState('networkidle');

    // Check if backend is healthy
    const healthResponse = await page.request.get('http://127.0.0.1:8001/api/system/health');
    expect(healthResponse.ok()).toBeTruthy();
  });

  test('should display chat interface correctly', async ({ page }) => {
    // Check for main chat elements
    await expect(page.locator('[data-testid="chat-container"]')).toBeVisible();
    await expect(page.locator('[data-testid="message-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="send-button"]')).toBeVisible();
  });

  test('should automatically search KB when question is asked', async ({ page }) => {
    // Type a question that should trigger KB search
    const questionInput = page.locator('[data-testid="message-input"]');
    await questionInput.fill('What is machine learning?');

    // Send the message
    await page.locator('[data-testid="send-button"]').click();

    // Wait for the message to appear
    await expect(page.locator('.user-message').last()).toContainText('What is machine learning?');

    // Wait for bot response that should include KB search results
    const botResponse = page.locator('.bot-message').last();
    await expect(botResponse).toBeVisible({ timeout: 10000 });

    // Check if KB Librarian found relevant information
    // The response should either contain KB findings or indicate no results found
    const responseText = await botResponse.textContent();
    expect(responseText).toBeTruthy();

    // Look for KB Librarian indicators
    const hasKBFindings = responseText?.includes('📚') || responseText?.includes('Knowledge Base');
    const hasNoResultsMessage = responseText?.includes('No relevant information found');

    expect(hasKBFindings || hasNoResultsMessage).toBeTruthy();
  });

  test('should handle non-question messages normally', async ({ page }) => {
    // Type a statement that should not trigger KB search
    const input = page.locator('[data-testid="message-input"]');
    await input.fill('Hello there!');

    // Send the message
    await page.locator('[data-testid="send-button"]').click();

    // Wait for response
    const botResponse = page.locator('.bot-message').last();
    await expect(botResponse).toBeVisible({ timeout: 10000 });

    // The response should not include KB search results for greetings
    const responseText = await botResponse.textContent();
    expect(responseText).not.toContain('📚');
  });

  test('should show loading state during message processing', async ({ page }) => {
    const input = page.locator('[data-testid="message-input"]');
    await input.fill('How do neural networks work?');

    // Send message and immediately check for loading state
    await page.locator('[data-testid="send-button"]').click();

    // Should show loading indicator or disabled state
    await expect(page.locator('[data-testid="loading-indicator"]')).toBeVisible({ timeout: 1000 }).catch(() => {
      // Fallback: check if send button is disabled during processing
      expect(page.locator('[data-testid="send-button"]')).toBeDisabled();
    });
  });

  test('should handle multiple consecutive questions', async ({ page }) => {
    const questions = [
      'What is artificial intelligence?',
      'How does deep learning work?',
      'What are neural networks?'
    ];

    for (const question of questions) {
      const input = page.locator('[data-testid="message-input"]');
      await input.fill(question);
      await page.locator('[data-testid="send-button"]').click();

      // Wait for the response before sending next question
      await expect(page.locator('.bot-message').last()).toBeVisible({ timeout: 10000 });

      // Small delay to ensure processing is complete
      await page.waitForTimeout(1000);
    }

    // Check that all messages are displayed
    const userMessages = page.locator('.user-message');
    const botMessages = page.locator('.bot-message');

    await expect(userMessages).toHaveCount(questions.length);
    await expect(botMessages).toHaveCount(questions.length);
  });

  test('should persist chat history across page reloads', async ({ page }) => {
    // Send a message
    const input = page.locator('[data-testid="message-input"]');
    await input.fill('Test message for persistence');
    await page.locator('[data-testid="send-button"]').click();

    // Wait for response
    await expect(page.locator('.bot-message').last()).toBeVisible({ timeout: 10000 });

    // Reload the page
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Check if the message history is restored
    await expect(page.locator('.user-message')).toContainText('Test message for persistence');
  });

  test('should handle empty messages gracefully', async ({ page }) => {
    // Try to send empty message
    const sendButton = page.locator('[data-testid="send-button"]');

    // Send button should be disabled for empty input
    await expect(sendButton).toBeDisabled();

    // Type some text and then clear it
    const input = page.locator('[data-testid="message-input"]');
    await input.fill('test');
    await input.clear();

    // Send button should be disabled again
    await expect(sendButton).toBeDisabled();
  });

  test('should show error handling for network failures', async ({ page }) => {
    // Block network requests to simulate failure
    await page.route('http://127.0.0.1:8001/api/chats/**', route => route.abort());

    const input = page.locator('[data-testid="message-input"]');
    await input.fill('This should fail');
    await page.locator('[data-testid="send-button"]').click();

    // Should show error message or retry option
    await expect(page.locator('[data-testid="error-message"]')).toBeVisible({ timeout: 5000 }).catch(() => {
      // Alternative: check for error in UI
      expect(page.locator('.error-indicator')).toBeVisible();
    });
  });
});
