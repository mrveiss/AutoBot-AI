// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  ApiCircuitBreaker,
  CircuitBreakerError,
  getCircuitBreaker,
  resetCircuitBreakers,
  runWithCircuitBreaker,
} from '@/utils/apiCircuitBreaker';

const ok = (status = 200) => () => Promise.resolve(new Response('{}', { status }));
const boom = () => Promise.reject(new Error('network down'));

describe('ApiCircuitBreaker', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetCircuitBreakers();
  });
  afterEach(() => vi.useRealTimers());

  it('opens after the failure threshold and then fails fast without calling send', async () => {
    for (let i = 0; i < 3; i++) await expect(runWithCircuitBreaker('svc', boom)).rejects.toThrow('network down');
    const send = vi.fn(ok());
    await expect(runWithCircuitBreaker('svc', send)).rejects.toBeInstanceOf(CircuitBreakerError);
    expect(send).not.toHaveBeenCalled();
  });

  it('contrast: a closed circuit passes calls through untouched', async () => {
    const res = await runWithCircuitBreaker('svc', ok());
    expect(res.status).toBe(200);
    expect(getCircuitBreaker('svc').state).toBe('CLOSED');
  });

  it('half-opens after recovery and closes on a successful probe', async () => {
    for (let i = 0; i < 3; i++) await runWithCircuitBreaker('svc', boom).catch(() => {});
    vi.advanceTimersByTime(30_000);
    await runWithCircuitBreaker('svc', ok());
    expect(getCircuitBreaker('svc').state).toBe('CLOSED');
  });

  it('re-opens when the half-open probe fails', async () => {
    for (let i = 0; i < 3; i++) await runWithCircuitBreaker('svc', boom).catch(() => {});
    vi.advanceTimersByTime(30_000);
    await runWithCircuitBreaker('svc', boom).catch(() => {});
    expect(getCircuitBreaker('svc').state).toBe('OPEN');
  });

  it('counts 503 as unavailable but 404 as the dependency answering', async () => {
    for (let i = 0; i < 3; i++) await runWithCircuitBreaker('a', ok(503));
    expect(getCircuitBreaker('a').state).toBe('OPEN');
    for (let i = 0; i < 5; i++) await runWithCircuitBreaker('b', ok(404));
    expect(getCircuitBreaker('b').state).toBe('CLOSED');
  });

  it('keeps breakers independent per key', async () => {
    for (let i = 0; i < 3; i++) await runWithCircuitBreaker('x', boom).catch(() => {});
    expect((await runWithCircuitBreaker('y', ok())).status).toBe(200);
  });

  it('reset() closes the circuit', () => {
    const b = new ApiCircuitBreaker({ failureThreshold: 1 });
    b.recordFailure();
    expect(b.canExecute()).toBe(false);
    b.reset();
    expect(b.canExecute()).toBe(true);
  });
});
