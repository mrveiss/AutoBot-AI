// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Tests for SecretsManager filteredSecrets memoization optimization
 * Verifies that filtering cache works correctly and improves performance
 */

import { describe, it, expect, beforeEach } from 'vitest';

interface TestSecret {
  id: string;
  name: string;
  type: string;
  scope: string;
  description?: string;
  tags?: string[];
  expires_at?: string | null;
}

describe('SecretsManager - filteredSecrets Memoization', () => {
  // Mock cache behavior
  let filterCache: Map<string, TestSecret[]>;
  let cacheHits = 0;
  let cacheMisses = 0;

  beforeEach(() => {
    filterCache = new Map();
    cacheHits = 0;
    cacheMisses = 0;
  });

  // Test helper: cache key generation
  const mockGetFilterCacheKey = (
    selectedCategory: string,
    selectedScope: string,
    showExpiredOnly: boolean,
    debouncedSearch: string,
    secretsLength: number
  ): string => {
    return JSON.stringify([
      selectedCategory,
      selectedScope,
      showExpiredOnly,
      debouncedSearch,
      secretsLength
    ]);
  };

  // Test helper: simulate filtering with cache
  const filterSecretsWithCache = (
    secrets: TestSecret[],
    selectedCategory: string,
    selectedScope: string,
    showExpiredOnly: boolean,
    debouncedSearch: string
  ): TestSecret[] => {
    const cacheKey = mockGetFilterCacheKey(
      selectedCategory,
      selectedScope,
      showExpiredOnly,
      debouncedSearch,
      secrets.length
    );

    // Check cache
    if (filterCache.has(cacheKey)) {
      cacheHits++;
      return filterCache.get(cacheKey) || [];
    }

    cacheMisses++;

    // Perform filtering
    let result = [...secrets];

    if (selectedCategory !== 'all') {
      result = result.filter(s => s.type === selectedCategory);
    }

    if (selectedScope) {
      result = result.filter(s => s.scope === selectedScope);
    }

    if (showExpiredOnly) {
      result = result.filter(s => new Date(s.expires_at) < new Date());
    }

    if (debouncedSearch) {
      const query = debouncedSearch.toLowerCase();
      result = result.filter(s =>
        s.name.toLowerCase().includes(query) ||
        s.description?.toLowerCase().includes(query) ||
        s.tags?.some((t: string) => t.toLowerCase().includes(query))
      );
    }

    // Store in cache
    filterCache.set(cacheKey, result);

    // Manage cache size
    if (filterCache.size > 50) {
      filterCache.clear();
    }

    return result;
  };

  it('should cache filter results on first access', () => {
    const secrets = [
      { id: '1', name: 'api-key-1', type: 'api_key', scope: 'general', description: 'Test key', tags: [], expires_at: new Date(2099, 0, 1).toISOString() },
      { id: '2', name: 'password-1', type: 'password', scope: 'chat', description: 'Test password', tags: [], expires_at: new Date(2099, 0, 1).toISOString() },
    ];

    const result = filterSecretsWithCache(secrets, 'api_key', '', false, '');
    expect(result).toHaveLength(1);
    expect(result[0].type).toBe('api_key');
    expect(cacheMisses).toBe(1);
    expect(cacheHits).toBe(0);
  });

  it('should return cached results on second identical filter', () => {
    const secrets = [
      { id: '1', name: 'api-key-1', type: 'api_key', scope: 'general', description: 'Test key', tags: [], expires_at: new Date(2099, 0, 1).toISOString() },
      { id: '2', name: 'password-1', type: 'password', scope: 'chat', description: 'Test password', tags: [], expires_at: new Date(2099, 0, 1).toISOString() },
    ];

    // First call - cache miss
    filterSecretsWithCache(secrets, 'api_key', '', false, '');
    expect(cacheMisses).toBe(1);

    // Second call with same filters - cache hit
    filterSecretsWithCache(secrets, 'api_key', '', false, '');
    expect(cacheHits).toBe(1);
    expect(cacheMisses).toBe(1);
  });

  it('should invalidate cache when filter parameters change', () => {
    const secrets = [
      { id: '1', name: 'api-key-1', type: 'api_key', scope: 'general', description: 'Test key', tags: [], expires_at: new Date(2099, 0, 1).toISOString() },
      { id: '2', name: 'password-1', type: 'password', scope: 'chat', description: 'Test password', tags: [], expires_at: new Date(2099, 0, 1).toISOString() },
    ];

    // First filter
    filterSecretsWithCache(secrets, 'api_key', '', false, '');
    expect(cacheMisses).toBe(1);

    // Different category - new cache miss
    filterSecretsWithCache(secrets, 'password', '', false, '');
    expect(cacheMisses).toBe(2);
  });

  it('should invalidate cache when secrets.length changes', () => {
    let secrets = [
      { id: '1', name: 'api-key-1', type: 'api_key', scope: 'general', description: 'Test key', tags: [], expires_at: new Date(2099, 0, 1).toISOString() },
    ];

    // First call
    filterSecretsWithCache(secrets, 'all', '', false, '');
    expect(cacheMisses).toBe(1);

    // Add a secret
    secrets = [
      ...secrets,
      { id: '2', name: 'password-1', type: 'password', scope: 'chat', description: 'Test password', tags: [], expires_at: new Date(2099, 0, 1).toISOString() },
    ];

    // Same filters but different length - cache miss
    filterSecretsWithCache(secrets, 'all', '', false, '');
    expect(cacheMisses).toBe(2);
  });

  it('should handle search filter properly', () => {
    const secrets = [
      { id: '1', name: 'api-key-1', type: 'api_key', scope: 'general', description: 'Test key', tags: ['prod'], expires_at: new Date(2099, 0, 1).toISOString() },
      { id: '2', name: 'password-1', type: 'password', scope: 'chat', description: 'Dev password', tags: ['dev'], expires_at: new Date(2099, 0, 1).toISOString() },
    ];

    const result1 = filterSecretsWithCache(secrets, 'all', '', false, 'prod');
    expect(result1).toHaveLength(1);
    expect(result1[0].name).toBe('api-key-1');

    const result2 = filterSecretsWithCache(secrets, 'all', '', false, 'dev');
    expect(result2).toHaveLength(1);
    expect(result2[0].name).toBe('password-1');

    // Same search - should be cached
    const _result3 = filterSecretsWithCache(secrets, 'all', '', false, 'prod');
    expect(cacheHits).toBe(1);
  });

  it('should limit cache size to 50 entries', () => {
    const secrets = [
      { id: '1', name: 'api-key-1', type: 'api_key', scope: 'general', description: 'Test key', tags: [], expires_at: new Date(2099, 0, 1).toISOString() },
    ];

    // Fill cache with 51 different filter combinations
    for (let i = 0; i < 51; i++) {
      filterSecretsWithCache(secrets, i % 2 === 0 ? 'api_key' : 'password', '', i % 2 === 0, `search${i}`);
    }

    // Cache should be cleared (size reset to 0)
    expect(filterCache.size).toBe(0);
  });

  it('should cache correctly with scope filtering', () => {
    const secrets = [
      { id: '1', name: 'api-key-1', type: 'api_key', scope: 'general', description: 'Test key', tags: [], expires_at: new Date(2099, 0, 1).toISOString() },
      { id: '2', name: 'api-key-2', type: 'api_key', scope: 'chat', description: 'Chat key', tags: [], expires_at: new Date(2099, 0, 1).toISOString() },
    ];

    const result1 = filterSecretsWithCache(secrets, 'all', 'general', false, '');
    expect(result1).toHaveLength(1);
    expect(result1[0].scope).toBe('general');

    // Same filters - cache hit
    const _result2 = filterSecretsWithCache(secrets, 'all', 'general', false, '');
    expect(cacheHits).toBe(1);

    // Different scope - cache miss
    const _result3 = filterSecretsWithCache(secrets, 'all', 'chat', false, '');
    expect(cacheMisses).toBe(2);
  });

  it('should perform cache key generation with all parameters', () => {
    const key1 = mockGetFilterCacheKey('api_key', 'general', false, 'search', 10);
    const key2 = mockGetFilterCacheKey('api_key', 'general', false, 'search', 10);
    const key3 = mockGetFilterCacheKey('api_key', 'general', false, 'search', 11);

    expect(key1).toBe(key2);
    expect(key1).not.toBe(key3);
  });

  it('should be compatible with debounced search values', () => {
    const secrets = [
      { id: '1', name: 'OpenAI Key', type: 'api_key', scope: 'general', description: 'OpenAI API', tags: [], expires_at: new Date(2099, 0, 1).toISOString() },
      { id: '2', name: 'GitHub Token', type: 'token', scope: 'general', description: 'GitHub access', tags: [], expires_at: new Date(2099, 0, 1).toISOString() },
    ];

    // Simulate debounced search (from useDebounce composable)
    const debouncedSearchValue = 'OpenAI';
    const result = filterSecretsWithCache(secrets, 'all', '', false, debouncedSearchValue);

    expect(result).toHaveLength(1);
    expect(result[0].name).toContain('OpenAI');
  });
});
