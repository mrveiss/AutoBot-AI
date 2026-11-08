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

import { computed, inject, onBeforeUnmount, onMounted, provide, shallowReactive, type ComputedRef, type InjectionKey } from 'vue'
import type { UsePollingJobReturn } from '@autobot/ui'
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

/**
 * One paused notice per route (#19851). The outer layout owns the notice; a nested
 * layout registers its poller here instead of rendering a second one, so a full
 * outage shows one notice and Retry restarts every paused poller on the route.
 */
export type RoutePoller = UsePollingJobReturn<void>

export const NESTED_POLLERS_KEY: InjectionKey<RoutePoller[]> = Symbol('nestedPollers')

export interface PausedNotice {
  /** Shape PollingPausedAlert reads: true while any poller on the route is paused */
  alertSource: { pausedOnErrors: ComputedRef<boolean> }
  retry: () => void
}

/** Outer layout: collect the nested pollers and expose one notice for all of them. */
export function useRoutePausedNotice(own: RoutePoller): PausedNotice {
  const nested = shallowReactive<RoutePoller[]>([])
  provide(NESTED_POLLERS_KEY, nested)
  const all = () => [own, ...nested]
  return {
    alertSource: { pausedOnErrors: computed(() => all().some(p => p.pausedOnErrors.value)) },
    retry: () => all().filter(p => p.pausedOnErrors.value).forEach(p => p.start('')),
  }
}

/** Nested layout: hand the poller to the outer layout; true when one took it. */
export function registerWithOuterNotice(poller: RoutePoller): boolean {
  const outer = inject(NESTED_POLLERS_KEY, null)
  if (!outer) return false
  onMounted(() => outer.push(poller))
  onBeforeUnmount(() => {
    const i = outer.indexOf(poller)
    if (i >= 0) outer.splice(i, 1)
  })
  return true
}
