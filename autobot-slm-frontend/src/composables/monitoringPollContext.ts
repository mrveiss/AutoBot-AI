// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Poll ownership for the monitoring routes (#19851).
 *
 * A layout view (MonitoringView, PerformanceView) owns the poller for its
 * route and provides the composable's state under these keys; a child route
 * reads it instead of polling a second time. A child that renders without
 * the layout above it receives nothing and falls back to its own poller.
 */

import { inject, provide, type InjectionKey } from 'vue'
import type { useFleetMetrics } from '@/composables/useFleetMetrics'
import type { usePerformanceMonitoring } from '@/composables/usePerformanceMonitoring'

export type FleetMetricsState = ReturnType<typeof useFleetMetrics>
export type PerformanceMonitoringState = ReturnType<typeof usePerformanceMonitoring>

export const FLEET_METRICS_KEY: InjectionKey<FleetMetricsState> = Symbol('fleetMetrics')
export const PERFORMANCE_MONITORING_KEY: InjectionKey<PerformanceMonitoringState> =
  Symbol('performanceMonitoring')

export interface PollOwnership<T> {
  state: T
  /** True when no layout above provided the state, so this view polls itself */
  ownsPoll: boolean
}

/** Layout side: publish the state this route polls. */
export function provideFleetMetrics(state: FleetMetricsState): void {
  provide(FLEET_METRICS_KEY, state)
}

export function providePerformanceMonitoring(state: PerformanceMonitoringState): void {
  provide(PERFORMANCE_MONITORING_KEY, state)
}

/** Child side: the provided state, else one built by `create` (which polls). */
export function injectFleetMetrics(
  create: () => FleetMetricsState
): PollOwnership<FleetMetricsState> {
  const provided = inject(FLEET_METRICS_KEY, null)
  return provided ? { state: provided, ownsPoll: false } : { state: create(), ownsPoll: true }
}

export function injectPerformanceMonitoring(
  create: () => PerformanceMonitoringState
): PollOwnership<PerformanceMonitoringState> {
  const provided = inject(PERFORMANCE_MONITORING_KEY, null)
  return provided ? { state: provided, ownsPoll: false } : { state: create(), ownsPoll: true }
}
