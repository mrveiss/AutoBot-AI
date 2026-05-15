/**
 * Playwright Test Setup
 *
 * This file contains setup utilities and helper functions for testing
 * the AutoBot application with the KB Librarian Agent integration.
 */

import { expect } from '@playwright/test';

// Custom matchers for AutoBot-specific assertions
expect.extend({
  async toHaveKBLibrarianResponse(page, message: string) {
    // Wait for bot response containing KB Librarian indicators
    const botMessages = page.locator('.bot-message');
    const lastMessage = botMessages.last();

    await expect(lastMessage).toBeVisible({ timeout: 15000 });
    const content = await lastMessage.textContent();

    const hasKBIndicator = content?.includes('📚') ||
                          content?.includes('Knowledge Base') ||
                          content?.includes('No relevant information found');

    return {
      message: () => `Expected response to ${hasKBIndicator ? 'not ' : ''}contain KB Librarian indicators`,
      pass: hasKBIndicator || false,
    };
  },

  async toBeValidApiResponse(response) {
    const isOk = response.ok();
    const contentType = response.headers()['content-type'];
    const isJson = contentType?.includes('application/json');

    return {
      message: () => `Expected response to be valid JSON API response (status: ${response.status()}, content-type: ${contentType})`,
      pass: isOk && isJson,
    };
  }
});

// Declare the extended matchers
declare global {
  namespace PlaywrightTest {
    interface Matchers<R> {
      toHaveKBLibrarianResponse(message: string): R;
      toBeValidApiResponse(): R;
    }
  }
}

// Helper functions for common operations
export class AutoBotTestHelpers {

  /**
   * Send a chat message and wait for response
   */
  static async sendChatMessage(page: any, message: string) {
    const input = page.locator('[data-testid="message-input"]');
    const sendButton = page.locator('[data-testid="send-button"]');

    await input.fill(message);
    await sendButton.click();

    // Wait for the message to appear in chat
    await expect(page.locator('.user-message').last()).toContainText(message);

    // Wait for bot response
    await expect(page.locator('.bot-message').last()).toBeVisible({ timeout: 15000 });

    return page.locator('.bot-message').last();
  }

  /**
   * Check if KB Librarian is enabled via API
   */
  static async isKBLibrarianEnabled(page: any) {
    const response = await page.request.get('http://127.0.0.1:8001/api/kb-librarian/status');
    if (!response.ok()) return false;

    const data = await response.json();
    return data.enabled === true;
  }

  /**
   * Wait for backend to be ready
   */
  static async waitForBackend(page: any, timeout: number = 30000) {
    let attempts = 0;
    const maxAttempts = timeout / 1000;

    while (attempts < maxAttempts) {
      try {
        const response = await page.request.get('http://127.0.0.1:8001/api/system/health');
        if (response.ok()) {
          return true;
        }
      } catch (error) {
        // Backend not ready yet
      }

      await page.waitForTimeout(1000);
      attempts++;
    }

    throw new Error(`Backend not ready after ${timeout}ms`);
  }

  /**
   * Add some test data to knowledge base (if needed)
   */
  static async seedKnowledgeBase(page: any) {
    // This would typically add some test documents to the knowledge base
    // For now, we'll just verify the KB is accessible
    try {
      const response = await page.request.get('http://127.0.0.1:8001/api/knowledge_base/search?query=test&limit=1');
      return response.ok();
    } catch {
      return false;
    }
  }

  /**
   * Clean up test data
   */
  static async cleanupTestData(page: any) {
    // Clean up any test-specific data if needed
    // This could include clearing test chats, resetting configurations, etc.
    try {
      // Reset KB Librarian to default settings
      await page.request.put('http://127.0.0.1:8001/api/kb-librarian/configure', {
        data: {
          enabled: true,
          similarity_threshold: 0.7,
          max_results: 5,
          auto_summarize: true
        },
        headers: {
          'Content-Type': 'application/json',
        }
      });
    } catch {
      // Ignore cleanup errors
    }
  }

  /**
   * Take screenshot with timestamp for debugging
   */
  static async takeDebugScreenshot(page: any, name: string) {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    await page.screenshot({
      path: `test-results/screenshots/${name}-${timestamp}.png`,
      fullPage: true
    });
  }

  /**
   * Get test selectors based on common AutoBot patterns
   */
  static getSelectors() {
    return {
      chatInput: '[data-testid="message-input"], .message-input, input[placeholder*="message"], textarea[placeholder*="message"]',
      sendButton: '[data-testid="send-button"], .send-button, button[type="submit"]',
      userMessage: '.user-message, .message.user, [data-type="user"]',
      botMessage: '.bot-message, .message.bot, [data-type="bot"]',
      loadingIndicator: '[data-testid="loading"], .loading, .spinner',
      errorMessage: '[data-testid="error"], .error, .error-message',
      chatContainer: '[data-testid="chat"], .chat-container, .messages'
    };
  }
}

// Export test data for consistent testing
export const testQuestions = [
  'What is machine learning?',
  'How do neural networks work?',
  'What are the types of artificial intelligence?',
  'Explain deep learning algorithms',
  'What is the difference between supervised and unsupervised learning?'
];

export const testStatements = [
  'Hello there!',
  'Thank you for your help.',
  'This is a test message.',
  'Good morning!',
  'I appreciate your assistance.'
];

export const testConfiguration = {
  defaultSimilarityThreshold: 0.7,
  defaultMaxResults: 5,
  defaultAutoSummarize: true,
  testTimeout: 15000,
  apiTimeout: 10000
};
