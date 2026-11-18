// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #18892 AC4: only a 401 on an authenticated request ends the session; a 503
// ("could not decide", e.g. revocation store unavailable) keeps it.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const { clearStoredAuth, logout } = vi.hoisted(() => ({ clearStoredAuth: vi.fn(), logout: vi.fn() }));

// The 401 path imports the user store lazily; mocked so the import resolves inside the test
// (an unmocked one loads after teardown, #18833) and so the store logout can be asserted.
vi.mock('@/stores/useUserStore', () => ({ useUserStore: () => ({ logout }) }));

vi.mock('@/utils/authToken', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/authToken')>()),
  readStoredAuthToken: () => 'live-jwt',
  clearStoredAuth,
}));

import { ApiClient } from '@/utils/ApiClient';
import { resetCircuitBreakers } from '@/utils/apiCircuitBreaker';

describe('ApiClient session handling on 401 vs 503 (#18892)', () => {
  let originalLocation: Location;

  beforeEach(() => {
    resetCircuitBreakers();
    clearStoredAuth.mockClear();
    logout.mockClear();
    originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { pathname: '/fleet', href: '', port: '' } as unknown as Location,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: originalLocation,
    });
  });

  it('503 neither clears auth nor redirects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 503 })));
    const res = await new ApiClient().rawRequest('/nodes');

    expect(res.status).toBe(503);
    expect(clearStoredAuth).not.toHaveBeenCalled();
    expect(logout).not.toHaveBeenCalled();
    expect(window.location.href).toBe('');
  });

  it('401 on an authenticated request still clears auth and redirects to login', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 401 })));
    await new ApiClient().rawRequest('/nodes');

    expect(clearStoredAuth).toHaveBeenCalledTimes(1);
    expect(window.location.href).toBe('/login?redirect=%2Ffleet');
    await vi.waitFor(() => expect(logout).toHaveBeenCalledTimes(1));
  });
});
