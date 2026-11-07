// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { ApiClient } from '@/utils/ApiClient';
import { CircuitBreakerError, resetCircuitBreakers } from '@/utils/apiCircuitBreaker';

describe('ApiClient.rawRequest circuitBreaker option (#11682)', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    resetCircuitBreakers();
    fetchMock = vi.fn().mockRejectedValue(new Error('network down'));
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('fails fast once the keyed circuit is open', async () => {
    const client = new ApiClient();
    for (let i = 0; i < 3; i++) {
      await expect(client.rawRequest('/x', { circuitBreaker: 'dep' })).rejects.toThrow('network down');
    }
    const calls = fetchMock.mock.calls.length;
    await expect(client.rawRequest('/x', { circuitBreaker: 'dep' })).rejects.toBeInstanceOf(CircuitBreakerError);
    expect(fetchMock.mock.calls.length).toBe(calls);
  });

  it('contrast: without the option every call reaches fetch', async () => {
    const client = new ApiClient();
    for (let i = 0; i < 5; i++) await client.rawRequest('/x').catch(() => {});
    expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(5);
  });
});
