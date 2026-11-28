// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest';
import { reloadConfig } from '../ssot-config';

// #20058: on a nginx host the OAuth callback must carry the served port, under its own name.
describe('frontendUrl port', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    reloadConfig();
  });

  it('uses the served port when one is set, leaving the dev port alone', () => {
    vi.stubEnv('VITE_FRONTEND_PORT', '5173');
    vi.stubEnv('VITE_FRONTEND_SERVED_PORT', '443');
    const cfg = reloadConfig();
    expect(cfg.frontendUrl).toMatch(/:443$/);
    expect(cfg.port.frontend).toBe(5173);
  });

  it('falls back to the dev port on a host that sets no served port', () => {
    vi.stubEnv('VITE_FRONTEND_PORT', '15173');
    vi.stubEnv('VITE_FRONTEND_SERVED_PORT', '');
    expect(reloadConfig().frontendUrl).toMatch(/:15173$/);
  });
});
