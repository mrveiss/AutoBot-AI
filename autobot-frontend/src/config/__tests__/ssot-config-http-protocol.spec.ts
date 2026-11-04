// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #19821: config.httpProtocol follows the page, like every URL builder (#6795).
 * It was a build-time value defaulting to 'http', which served http on HTTPS deploys.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { getConfig, reloadConfig } from '../ssot-config';

const originalLocation = window.location;

const setProtocol = (protocol: 'https:' | 'http:') => {
  Object.defineProperty(window, 'location', {
    value: { ...originalLocation, protocol, hostname: 'test-host.example.com', host: 'test-host.example.com' },
    writable: true,
    configurable: true,
  });
};

describe('ssot-config httpProtocol', () => {
  afterEach(() => {
    Object.defineProperty(window, 'location', { value: originalLocation, writable: true, configurable: true });
  });

  it('is https on an https page', () => {
    setProtocol('https:');
    expect(reloadConfig().httpProtocol).toBe('https');
  });

  it('is http on an http page, read at access time rather than at build', () => {
    setProtocol('https:');
    const cfg = reloadConfig();
    setProtocol('http:');
    expect(cfg.httpProtocol).toBe('http');
    expect(getConfig().httpProtocol).toBe('http');
  });
});
