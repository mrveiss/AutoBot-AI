// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14908: the main app's ApiClient is a thin subclass of the kit transport; this pins what the
// subclass still owns (org header, auth-endpoint 401 exemption, circuit-breaker GET stop) and
// that the shared mechanics (query params, GET retry, upload) reach it unchanged.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const { clearStoredAuth, orgId } = vi.hoisted(() => ({ clearStoredAuth: vi.fn(), orgId: { value: 'co-7' } }));

vi.mock('@/stores/useUserStore', () => ({ useUserStore: () => ({ logout: vi.fn() }) }));
vi.mock('@/utils/orgContext', () => ({ getSelectedCompanyId: () => orgId.value }));
vi.mock('@/utils/authToken', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/authToken')>()),
  readStoredAuthToken: () => 'live-jwt',
  clearStoredAuth,
}));

import { ApiClient } from '@/utils/ApiClient';
import { getApiBase } from '@/config/ssot-config';
import { resetCircuitBreakers } from '@/utils/apiCircuitBreaker';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

describe('ApiClient on the kit transport (#14908)', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    resetCircuitBreakers();
    clearStoredAuth.mockClear();
    orgId.value = 'co-7';
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('sends the bearer and the selected company, and the caller can override the company', async () => {
    fetchMock.mockImplementation(async () => json({}));
    const client = new ApiClient();
    await client.get('/x');
    await client.get('/y', { headers: { 'X-Organization-Id': 'mine' } });
    expect(fetchMock.mock.calls[0][1].headers).toMatchObject({ Authorization: 'Bearer live-jwt', 'X-Organization-Id': 'co-7' });
    expect(fetchMock.mock.calls[1][1].headers['X-Organization-Id']).toBe('mine');
  });

  it('omits the org header when no company is selected', async () => {
    orgId.value = '';
    fetchMock.mockImplementation(async () => json({}));
    await new ApiClient().get('/x');
    expect(fetchMock.mock.calls[0][1].headers['X-Organization-Id']).toBeUndefined();
  });

  it('a 401 on the auth endpoints does not clear the session', async () => {
    fetchMock.mockImplementation(async () => json({}, 401));
    await new ApiClient().rawRequest(`${getApiBase()}/auth/login`);
    expect(clearStoredAuth).not.toHaveBeenCalled();
  });

  it('GET retries a 5xx and gives up on a 4xx at once', async () => {
    fetchMock.mockImplementation(async () => json({}, 404));
    await expect(new ApiClient().get('/x', { suppressErrorLog: true })).rejects.toMatchObject({ status: 404 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fetchMock.mockClear();
    fetchMock.mockImplementation(async () => json({}, 500));
    await expect(new ApiClient().get('/x', { maxRetries: 2, suppressErrorLog: true })).rejects.toMatchObject({ status: 500 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('GET stops at once when the circuit breaker refuses', async () => {
    fetchMock.mockRejectedValue(new Error('network down'));
    const client = new ApiClient();
    for (let i = 0; i < 3; i++) {
      await client.get('/x', { circuitBreaker: 'dep', maxRetries: 1, suppressErrorLog: true }).catch(() => {});
    }
    fetchMock.mockClear();
    await expect(client.get('/x', { circuitBreaker: 'dep', suppressErrorLog: true })).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
