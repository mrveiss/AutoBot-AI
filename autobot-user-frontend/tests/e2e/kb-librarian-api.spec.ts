import { test, expect } from '@playwright/test';

test.describe('KB Librarian API Tests', () => {
  const baseApiUrl = 'http://127.0.0.1:8001/api';

  test.beforeEach(async ({ page }) => {
    // Ensure backend is running
    const healthResponse = await page.request.get(`${baseApiUrl}/system/health`);
    expect(healthResponse.ok()).toBeTruthy();
  });

  test('should get KB Librarian status', async ({ page }) => {
    const response = await page.request.get(`${baseApiUrl}/kb-librarian/status`);
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('enabled');
    expect(data).toHaveProperty('similarity_threshold');
    expect(data).toHaveProperty('max_results');
    expect(data).toHaveProperty('auto_summarize');
    expect(data).toHaveProperty('knowledge_base_active');

    // Verify default values
    expect(typeof data.enabled).toBe('boolean');
    expect(typeof data.similarity_threshold).toBe('number');
    expect(typeof data.max_results).toBe('number');
    expect(typeof data.auto_summarize).toBe('boolean');
  });

  test('should query knowledge base directly', async ({ page }) => {
    const queryPayload = {
      query: 'What is machine learning?',
      max_results: 3,
      similarity_threshold: 0.5,
      auto_summarize: true
    };

    const response = await page.request.post(`${baseApiUrl}/kb-librarian/query`, {
      data: queryPayload,
      headers: {
        'Content-Type': 'application/json',
      }
    });

    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('enabled');
    expect(data).toHaveProperty('is_question');
    expect(data).toHaveProperty('query');
    expect(data).toHaveProperty('documents_found');
    expect(data).toHaveProperty('documents');

    expect(data.query).toBe(queryPayload.query);
    expect(data.is_question).toBe(true);
    expect(Array.isArray(data.documents)).toBe(true);
  });

  test('should detect non-questions correctly', async ({ page }) => {
    const queryPayload = {
      query: 'Hello there, how are you today.',
      max_results: 5
    };

    const response = await page.request.post(`${baseApiUrl}/kb-librarian/query`, {
      data: queryPayload,
      headers: {
        'Content-Type': 'application/json',
      }
    });

    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.is_question).toBe(false);
  });

  test('should configure KB Librarian settings', async ({ page }) => {
    // Update configuration
    const configPayload = {
      enabled: true,
      similarity_threshold: 0.8,
      max_results: 10,
      auto_summarize: false
    };

    const updateResponse = await page.request.put(`${baseApiUrl}/kb-librarian/configure`, {
      data: configPayload,
      headers: {
        'Content-Type': 'application/json',
      }
    });

    expect(updateResponse.ok()).toBeTruthy();

    const updateData = await updateResponse.json();
    expect(updateData.message).toContain('configuration updated');
    expect(updateData.similarity_threshold).toBe(0.8);
    expect(updateData.max_results).toBe(10);
    expect(updateData.auto_summarize).toBe(false);

    // Verify the changes
    const statusResponse = await page.request.get(`${baseApiUrl}/kb-librarian/status`);
    const statusData = await statusResponse.json();

    expect(statusData.similarity_threshold).toBe(0.8);
    expect(statusData.max_results).toBe(10);
    expect(statusData.auto_summarize).toBe(false);

    // Reset to defaults
    await page.request.put(`${baseApiUrl}/kb-librarian/configure`, {
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
  });

  test('should validate configuration parameters', async ({ page }) => {
    // Test invalid similarity threshold
    const invalidConfigResponse = await page.request.put(`${baseApiUrl}/kb-librarian/configure`, {
      data: {
        similarity_threshold: 1.5  // Invalid: should be between 0.0 and 1.0
      },
      headers: {
        'Content-Type': 'application/json',
      }
    });

    expect(invalidConfigResponse.status()).toBe(400);

    // Test invalid max_results
    const invalidMaxResultsResponse = await page.request.put(`${baseApiUrl}/kb-librarian/configure`, {
      data: {
        max_results: 0  // Invalid: should be at least 1
      },
      headers: {
        'Content-Type': 'application/json',
      }
    });

    expect(invalidMaxResultsResponse.status()).toBe(400);
  });

  test('should handle different question types', async ({ page }) => {
    const testQueries = [
      'What is artificial intelligence?',
      'How do neural networks work?',
      'Why is machine learning important?',
      'When was deep learning invented?',
      'Where is AI used?',
      'Who invented the perceptron?',
      'Which algorithm is best for classification?',
      'Can you explain backpropagation?',
      'Could you help me understand transformers?',
      'Would you recommend any AI books?'
    ];

    for (const query of testQueries) {
      const response = await page.request.post(`${baseApiUrl}/kb-librarian/query`, {
        data: { query, max_results: 1 },
        headers: { 'Content-Type': 'application/json' }
      });

      expect(response.ok()).toBeTruthy();

      const data = await response.json();
      expect(data.is_question).toBe(true);
      expect(data.query).toBe(query);
    }
  });

  test('should respect max_results parameter', async ({ page }) => {
    const testCases = [1, 3, 5, 10];

    for (const maxResults of testCases) {
      const response = await page.request.post(`${baseApiUrl}/kb-librarian/query`, {
        data: {
          query: 'What is machine learning?',
          max_results: maxResults
        },
        headers: { 'Content-Type': 'application/json' }
      });

      expect(response.ok()).toBeTruthy();

      const data = await response.json();
      expect(data.documents.length).toBeLessThanOrEqual(maxResults);
    }
  });

  test('should handle empty and invalid queries', async ({ page }) => {
    // Empty query
    const emptyResponse = await page.request.post(`${baseApiUrl}/kb-librarian/query`, {
      data: { query: '' },
      headers: { 'Content-Type': 'application/json' }
    });

    expect(emptyResponse.ok()).toBeTruthy();
    const emptyData = await emptyResponse.json();
    expect(emptyData.is_question).toBe(false);

    // Very long query
    const longQuery = 'What is '.repeat(100) + 'machine learning?';
    const longResponse = await page.request.post(`${baseApiUrl}/kb-librarian/query`, {
      data: { query: longQuery },
      headers: { 'Content-Type': 'application/json' }
    });

    expect(longResponse.ok()).toBeTruthy();
  });

  test('should include metadata in document results', async ({ page }) => {
    const response = await page.request.post(`${baseApiUrl}/kb-librarian/query`, {
      data: {
        query: 'What is machine learning?',
        max_results: 2
      },
      headers: { 'Content-Type': 'application/json' }
    });

    expect(response.ok()).toBeTruthy();

    const data = await response.json();

    if (data.documents_found > 0) {
      const firstDoc = data.documents[0];
      expect(firstDoc).toHaveProperty('content');
      expect(firstDoc).toHaveProperty('metadata');
      expect(typeof firstDoc.content).toBe('string');
      expect(typeof firstDoc.metadata).toBe('object');
    }
  });

  test('should provide summaries when auto_summarize is enabled', async ({ page }) => {
    // Configure to enable auto summarization
    await page.request.put(`${baseApiUrl}/kb-librarian/configure`, {
      data: { auto_summarize: true },
      headers: { 'Content-Type': 'application/json' }
    });

    const response = await page.request.post(`${baseApiUrl}/kb-librarian/query`, {
      data: {
        query: 'What is machine learning?',
        auto_summarize: true
      },
      headers: { 'Content-Type': 'application/json' }
    });

    expect(response.ok()).toBeTruthy();

    const data = await response.json();

    if (data.documents_found > 0) {
      expect(data).toHaveProperty('summary');
      expect(typeof data.summary).toBe('string');
      expect(data.summary.length).toBeGreaterThan(0);
    }
  });
});
