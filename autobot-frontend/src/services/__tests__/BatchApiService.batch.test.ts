// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** #18765: BatchApiService sends GETs to the one server batch endpoint and reads per-slot status. */
import { describe, it, expect, vi } from 'vitest';
import { BatchApiService } from '@/services/BatchApiService';
import type { ApiClient } from '@/utils/ApiClient';

function makeClient(results: unknown[]) {
  return {
    call: vi.fn().mockResolvedValue({ results }),
    get: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  } as unknown as ApiClient & { call: ReturnType<typeof vi.fn>; get: ReturnType<typeof vi.fn> };
}

describe('BatchApiService (server batch)', () => {
  it('sends every GET in one call to /batch-jobs/load and never calls apiClient.get', async () => {
    const client = makeClient([
      { endpoint: '/api/a', method: 'GET', status: 200, body: { ok: 1 }, error: null, timing: 0 },
      { endpoint: '/api/b', method: 'GET', status: 403, body: { detail: 'nope' }, error: 'nope', timing: 0 },
    ]);
    const out = await new BatchApiService(client).batchRequests([
      { endpoint: '/api/a', method: 'GET' },
      { endpoint: '/api/b', method: 'GET' },
    ]);
    expect(client.call).toHaveBeenCalledTimes(1);
    expect(client.call.mock.calls[0].slice(0, 2)).toEqual(['post', '/api/batch-jobs/load']);
    expect(client.get).not.toHaveBeenCalled();
    expect(out[0]).toMatchObject({ success: true, data: { ok: 1 } });
    expect(out[1]).toMatchObject({ success: false, error: 'nope' });
  });

  it('keeps result order when a mutating request is mixed in, and sends it directly', async () => {
    const client = makeClient([{ endpoint: '/api/a', method: 'GET', status: 200, body: 1, error: null, timing: 0 }]);
    (client as unknown as { put: ReturnType<typeof vi.fn> }).put.mockResolvedValue('done');
    const out = await new BatchApiService(client).batchRequests([
      { endpoint: '/api/p', method: 'PUT', data: {} },
      { endpoint: '/api/a', method: 'GET' },
    ]);
    expect(out.map(r => r.endpoint)).toEqual(['/api/p', '/api/a']);
    expect(out.map(r => r.success)).toEqual([true, true]);
  });

  it('sends server paths when the client base is a proxy prefix, and keeps the caller endpoint in results', async () => {
    vi.stubEnv('VITE_API_BASE_PATH', '/autobot/api');
    try {
      const client = makeClient([{ endpoint: '/api/a', method: 'GET', status: 200, body: 1, error: null, timing: 0 }]);
      const out = await new BatchApiService(client).batchRequests([{ endpoint: '/autobot/api/a', method: 'GET' }]);
      // The typed call names the contract path; the client prepends the configured base (kit-tested).
      expect(client.call.mock.calls[0].slice(0, 2)).toEqual(['post', '/api/batch-jobs/load']);
      expect(client.call.mock.calls[0][2]).toEqual({ body: { requests: [{ endpoint: '/api/a', method: 'GET' }] } });
      expect(out[0]).toMatchObject({ endpoint: '/autobot/api/a', success: true });
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it('contrast: with the default base the endpoint is sent unchanged', async () => {
    const client = makeClient([{ endpoint: '/api/a', method: 'GET', status: 200, body: 1, error: null, timing: 0 }]);
    await new BatchApiService(client).batchRequests([{ endpoint: '/api/a', method: 'GET' }]);
    expect(client.call.mock.calls[0][2]).toEqual({ body: { requests: [{ endpoint: '/api/a', method: 'GET' }] } });
  });

  it('fetches a GET the loader refused (not allow-listed) directly, keeping order', async () => {
    const client = makeClient([
      { endpoint: '/api/a', method: 'GET', status: 200, body: 1, error: null, timing: 0, refused: false },
      { endpoint: '/api/other', method: 'GET', status: 403, body: null, error: 'endpoint is not batchable', timing: 0, refused: true },
    ]);
    client.get.mockResolvedValue({ direct: true });
    const out = await new BatchApiService(client).batchRequests([
      { endpoint: '/api/a', method: 'GET' },
      { endpoint: '/api/other', method: 'GET' },
    ]);
    expect(client.get).toHaveBeenCalledWith('/api/other');
    expect(out.map(r => r.success)).toEqual([true, true]);
    expect(out[1]).toMatchObject({ data: { direct: true } });
  });

  it('contrast: a dispatched route\'s own 403 stays a failure and is not retried', async () => {
    const client = makeClient([
      { endpoint: '/api/b', method: 'GET', status: 403, body: { detail: 'nope' }, error: 'nope', timing: 0, refused: false },
    ]);
    const out = await new BatchApiService(client).batchRequests([{ endpoint: '/api/b', method: 'GET' }]);
    expect(client.get).not.toHaveBeenCalled();
    expect(out[0]).toMatchObject({ success: false, error: 'nope' });
  });

  it('marks every GET failed when the batch call itself fails', async () => {
    const client = makeClient([]);
    client.call.mockRejectedValue(new Error('boom'));
    const out = await new BatchApiService(client).batchRequests([{ endpoint: '/api/a', method: 'GET' }]);
    expect(out[0].success).toBe(false);
  });
});
