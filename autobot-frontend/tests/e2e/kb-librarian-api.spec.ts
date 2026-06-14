// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * E2E tests for the KB Librarian HTTP surface.
 *
 * Covers the three endpoints registered at /api/kb-librarian (issue #3402):
 *   GET  /api/kb-librarian/status    — agent singleton runtime config
 *   POST /api/kb-librarian/query     — intent-detect + similarity search + summarise
 *   PUT  /api/kb-librarian/configure — update agent runtime parameters
 *
 * Auth: all three endpoints require a valid bearer token.  Tests that omit
 * a token verify that the backend returns 401/403.
 */

import { test, expect } from '@playwright/test';
import { TEST_CONFIG } from './config';

test.describe('KB Librarian API', () => {
  // ---------------------------------------------------------------------------
  // GET /api/kb-librarian/status
  // ---------------------------------------------------------------------------
  test.describe('GET /api/kb-librarian/status', () => {
    test('returns 401 when no auth token is provided', async ({ request }) => {
      const response = await request.get(
        TEST_CONFIG.getApiUrl('/api/kb-librarian/status'),
      );
      expect([401, 403]).toContain(response.status());
    });

    test('returns agent runtime config when authenticated', async ({ request }) => {
      // Skip if no test token is configured — auth smoke test above is sufficient
      const token = process.env.E2E_AUTH_TOKEN;
      test.skip(!token, 'E2E_AUTH_TOKEN not set — skipping authenticated status test');

      const response = await request.get(
        TEST_CONFIG.getApiUrl('/api/kb-librarian/status'),
        { headers: { Authorization: `Bearer ${token}` } },
      );
      expect(response.status()).toBe(200);

      const body = await response.json();
      expect(typeof body.enabled).toBe('boolean');
      expect(typeof body.similarity_threshold).toBe('number');
      expect(typeof body.max_results).toBe('number');
      expect(typeof body.auto_summarize).toBe('boolean');
      expect(typeof body.knowledge_base_active).toBe('boolean');
    });
  });

  // ---------------------------------------------------------------------------
  // POST /api/kb-librarian/query
  // ---------------------------------------------------------------------------
  test.describe('POST /api/kb-librarian/query', () => {
    test('returns 401 when no auth token is provided', async ({ request }) => {
      const response = await request.post(
        TEST_CONFIG.getApiUrl('/api/kb-librarian/query'),
        { data: { query: 'What is machine learning?' } },
      );
      expect([401, 403]).toContain(response.status());
    });

    test('returns 422 when query field is missing', async ({ request }) => {
      const token = process.env.E2E_AUTH_TOKEN;
      test.skip(!token, 'E2E_AUTH_TOKEN not set');

      const response = await request.post(
        TEST_CONFIG.getApiUrl('/api/kb-librarian/query'),
        {
          headers: { Authorization: `Bearer ${token}` },
          data: {},
        },
      );
      expect(response.status()).toBe(422);
    });

    test('returns structured response for a valid query', async ({ request }) => {
      const token = process.env.E2E_AUTH_TOKEN;
      test.skip(!token, 'E2E_AUTH_TOKEN not set');

      const response = await request.post(
        TEST_CONFIG.getApiUrl('/api/kb-librarian/query'),
        {
          headers: { Authorization: `Bearer ${token}` },
          data: { query: 'What is AutoBot?' },
        },
      );
      expect(response.status()).toBe(200);

      const body = await response.json();
      expect(typeof body.enabled).toBe('boolean');
      expect(typeof body.is_question).toBe('boolean');
      expect(typeof body.query).toBe('string');
      expect(typeof body.documents_found).toBe('number');
      expect(Array.isArray(body.documents)).toBe(true);
    });

    test('accepts per-request parameter overrides', async ({ request }) => {
      const token = process.env.E2E_AUTH_TOKEN;
      test.skip(!token, 'E2E_AUTH_TOKEN not set');

      const response = await request.post(
        TEST_CONFIG.getApiUrl('/api/kb-librarian/query'),
        {
          headers: { Authorization: `Bearer ${token}` },
          data: {
            query: 'How does the knowledge base work?',
            max_results: 3,
            similarity_threshold: 0.8,
            auto_summarize: false,
          },
        },
      );
      expect(response.status()).toBe(200);

      const body = await response.json();
      // auto_summarize was false so summary should be absent or null
      expect(body.summary == null || body.summary === undefined).toBeTruthy();
    });
  });

  // ---------------------------------------------------------------------------
  // PUT /api/kb-librarian/configure
  // ---------------------------------------------------------------------------
  test.describe('PUT /api/kb-librarian/configure', () => {
    test('returns 401 when no auth token is provided', async ({ request }) => {
      const response = await request.put(
        TEST_CONFIG.getApiUrl('/api/kb-librarian/configure'),
        { data: { enabled: true } },
      );
      expect([401, 403]).toContain(response.status());
    });

    test('returns 400 when similarity_threshold is out of range', async ({ request }) => {
      const token = process.env.E2E_AUTH_TOKEN;
      test.skip(!token, 'E2E_AUTH_TOKEN not set');

      const response = await request.put(
        TEST_CONFIG.getApiUrl('/api/kb-librarian/configure'),
        {
          headers: { Authorization: `Bearer ${token}` },
          // similarity_threshold must be 0.0–1.0; 1.5 is invalid
          params: { similarity_threshold: '1.5' },
        },
      );
      expect(response.status()).toBe(400);
    });

    test('returns 400 when max_results is less than 1', async ({ request }) => {
      const token = process.env.E2E_AUTH_TOKEN;
      test.skip(!token, 'E2E_AUTH_TOKEN not set');

      const response = await request.put(
        TEST_CONFIG.getApiUrl('/api/kb-librarian/configure'),
        {
          headers: { Authorization: `Bearer ${token}` },
          params: { max_results: '0' },
        },
      );
      expect(response.status()).toBe(400);
    });

    test('updates agent config and echoes new values', async ({ request }) => {
      const token = process.env.E2E_AUTH_TOKEN;
      test.skip(!token, 'E2E_AUTH_TOKEN not set');

      const response = await request.put(
        TEST_CONFIG.getApiUrl('/api/kb-librarian/configure'),
        {
          headers: { Authorization: `Bearer ${token}` },
          params: { max_results: '7', similarity_threshold: '0.65' },
        },
      );
      expect(response.status()).toBe(200);

      const body = await response.json();
      expect(body.message).toBe('KB Librarian configuration updated');
      expect(body.max_results).toBe(7);
      expect(body.similarity_threshold).toBeCloseTo(0.65);
    });
  });
});
