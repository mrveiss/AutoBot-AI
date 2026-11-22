// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Circuit breaker for the canonical ApiClient (#11682).
 *
 * Folded in from the former ApiCircuitBreaker.js (zero importers): after
 * `failureThreshold` consecutive-ish failures the circuit OPENs and requests
 * fail fast with a CircuitBreakerError until `recoveryTimeMs` has elapsed,
 * then one HALF_OPEN probe decides whether to close it again. Opt-in per
 * request via `RequestOptions.circuitBreaker` (a key naming the dependency),
 * so default ApiClient behaviour is unchanged. Thresholds come from the SSOT
 * config (`timeout.circuitFailureThreshold`, `timeout.circuitRecoveryMs`).
 */
import { createLogger } from '@/utils/debugUtils';
import { getConfig } from '@/config/ssot-config';

const logger = createLogger('CircuitBreaker');

export type CircuitState = 'CLOSED' | 'OPEN' | 'HALF_OPEN';

export interface CircuitBreakerOptions {
  failureThreshold?: number;
  recoveryTimeMs?: number;
}


/** Response statuses that mean the dependency itself is unavailable. */
const UNAVAILABLE_STATUSES = new Set([502, 503, 504]);

export class CircuitBreakerError extends Error {
  readonly circuitState: CircuitState;
  constructor(key: string, state: CircuitState) {
    super(`Circuit breaker is OPEN for ${key} - service temporarily unavailable`);
    this.name = 'CircuitBreakerError';
    this.circuitState = state;
  }
}

export class ApiCircuitBreaker {
  state: CircuitState = 'CLOSED';
  failureCount = 0;
  private lastFailureTime = 0;
  private readonly failureThreshold: number;
  private readonly recoveryTimeMs: number;

  constructor(options: CircuitBreakerOptions = {}) {
    this.failureThreshold = options.failureThreshold ?? getConfig().timeout.circuitFailureThreshold;
    this.recoveryTimeMs = options.recoveryTimeMs ?? getConfig().timeout.circuitRecoveryMs;
  }

  canExecute(): boolean {
    if (this.state !== 'OPEN') return true;
    if (Date.now() - this.lastFailureTime < this.recoveryTimeMs) return false;
    this.state = 'HALF_OPEN';
    return true;
  }

  recordSuccess(): void {
    if (this.state === 'HALF_OPEN') {
      this.state = 'CLOSED';
      this.failureCount = 0;
    } else if (this.failureCount > 0) {
      this.failureCount -= 1;
    }
  }

  recordFailure(): void {
    this.lastFailureTime = Date.now();
    this.failureCount += 1;
    if (this.state === 'HALF_OPEN' || this.failureCount >= this.failureThreshold) {
      this.state = 'OPEN';
    }
  }

  reset(): void {
    this.state = 'CLOSED';
    this.failureCount = 0;
    this.lastFailureTime = 0;
  }
}

const breakers = new Map<string, ApiCircuitBreaker>();

export function getCircuitBreaker(key: string, options?: CircuitBreakerOptions): ApiCircuitBreaker {
  let breaker = breakers.get(key);
  if (!breaker) {
    breaker = new ApiCircuitBreaker(options);
    breakers.set(key, breaker);
  }
  return breaker;
}

export function resetCircuitBreakers(): void {
  breakers.clear();
}

/**
 * Run `send` under the breaker named `key`. Thrown errors and 502/503/504
 * responses count as failures; every other response (including 4xx) is a
 * success, because the dependency answered.
 */
export async function runWithCircuitBreaker(
  key: string,
  send: () => Promise<Response>
): Promise<Response> {
  const breaker = getCircuitBreaker(key);
  if (!breaker.canExecute()) throw new CircuitBreakerError(key, breaker.state);
  try {
    const response = await send();
    if (UNAVAILABLE_STATUSES.has(response.status)) breaker.recordFailure();
    else breaker.recordSuccess();
    return response;
  } catch (error) {
    breaker.recordFailure();
    logger.debug(`${key} failed (${breaker.state}, ${breaker.failureCount})`);
    throw error;
  }
}
