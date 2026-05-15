/**
 * Type definitions for OptimizedPerformance configuration
 */

export interface IntervalConfiguration {
  HEALTH_CHECK_HEALTHY: number;
  HEALTH_CHECK_DEGRADED: number;
  HEALTH_CHECK_CRITICAL: number;
  HEALTH_CHECK_USER_ACTIVE: number;
  RUM_DASHBOARD_DEFAULT: number;
  RUM_DASHBOARD_FAST: number;
  RUM_DASHBOARD_SLOW: number;
  SYSTEM_STATUS_UPDATE: number;
  CONNECTION_STATUS_CHECK: number;
  NOTIFICATION_CLEANUP: number;
  BACKEND_API_HEALTH: number;
  WEBSOCKET_HEALTH: number;
  ROUTER_HEALTH: number;
  DESKTOP_CONNECTION_CHECK: number;
  BROWSER_HEALTH_CHECK: number;
  TERMINAL_STATUS_CHECK: number;
  LOG_VIEWER_REFRESH: number;
  FILE_BROWSER_REFRESH: number;
}

export interface FeatureToggles {
  OPTIMIZED_HEALTH_MONITOR: boolean;
  SMART_RUM_DASHBOARD: boolean;
  PERFORMANCE_BUDGET_TRACKING: boolean;
  AGGRESSIVE_HEALTH_MONITOR: boolean;
  WEBSOCKET_POLLING: boolean;
  DOM_MUTATION_MONITORING: boolean;
  INTELLIGENT_AUTO_RECOVERY: boolean;
  RATE_LIMITED_RECOVERY: boolean;
  USER_CONTROLLED_RECOVERY: boolean;
  ADAPTIVE_INTERVALS: boolean;
  PERFORMANCE_SELF_REGULATION: boolean;
  TAB_VISIBILITY_OPTIMIZATION: boolean;
  USER_ACTIVITY_DETECTION: boolean;
  HOT_RELOAD_OPTIMIZATION: boolean;
  ERROR_BOUNDARY_MONITORING: boolean;
}

export interface PerformanceConfiguration {
  MAX_MONITORING_OVERHEAD_PER_MINUTE: number;
  MAX_SINGLE_CHECK_DURATION: number;
  PERFORMANCE_CHECK_THRESHOLD: number;
  MAX_CONCURRENT_HEALTH_CHECKS: number;
  MAX_WEBSOCKET_CONNECTIONS: number;
  MAX_API_REQUESTS_PER_MINUTE: number;
  MAX_NOTIFICATIONS_MEMORY: number;
  MAX_PERFORMANCE_HISTORY: number;
  MAX_ERROR_HISTORY: number;
  MAX_DASHBOARD_REFRESH_RATE: number;
  AUTO_PAUSE_INACTIVE_TABS: boolean;
  AUTO_REDUCE_ON_BATTERY: boolean;
}

export interface TimeoutConfiguration {
  HEALTH_CHECK_TIMEOUT: number;
  API_REQUEST_TIMEOUT: number;
  WEBSOCKET_CONNECTION_TIMEOUT: number;
  DASHBOARD_LOAD_TIMEOUT: number;
  MANUAL_REFRESH_TIMEOUT: number;
  AUTO_RECOVERY_TIMEOUT: number;
  LOG_FETCH_TIMEOUT: number;
  FILE_OPERATION_TIMEOUT: number;
}

export interface ThresholdConfiguration {
  CONSECUTIVE_FAILURES_FOR_DEGRADED: number;
  CONSECUTIVE_FAILURES_FOR_CRITICAL: number;
  RECOVERY_SUCCESS_THRESHOLD: number;
  HIGH_MEMORY_USAGE_THRESHOLD: number;
  CRITICAL_MEMORY_USAGE_THRESHOLD: number;
  SLOW_API_RESPONSE_THRESHOLD: number;
  VERY_SLOW_API_RESPONSE_THRESHOLD: number;
  USER_ACTIVE_THRESHOLD: number;
  USER_VIEWING_DASHBOARD_THRESHOLD: number;
  TAB_INACTIVE_THRESHOLD: number;
}

export interface DebugConfiguration {
  LOG_PERFORMANCE_METRICS: boolean;
  LOG_ADAPTIVE_CHANGES: boolean;
  LOG_USER_INTERACTIONS: boolean;
  SHOW_PERFORMANCE_WARNINGS: boolean;
  MEASURE_MONITORING_OVERHEAD: boolean;
  PERFORMANCE_CONSOLE_REPORTS: boolean;
}

export interface OptimizedPerformanceConfig {
  ENABLED: boolean;
  INTERVALS: IntervalConfiguration;
  FEATURES: FeatureToggles;
  PERFORMANCE: PerformanceConfiguration;
  TIMEOUTS: TimeoutConfiguration;
  THRESHOLDS: ThresholdConfiguration;
  DEBUG: DebugConfiguration;
}

export const OPTIMIZED_PERFORMANCE: OptimizedPerformanceConfig;

export function getAdaptiveInterval(
  intervalName: keyof IntervalConfiguration,
  currentHealthState?: 'healthy' | 'degraded' | 'critical',
  isUserActive?: boolean
): number;

export function isOptimizedFeatureEnabled(featureName: keyof FeatureToggles): boolean;

export function getPerformanceLimit(
  limitName: keyof PerformanceConfiguration,
  currentSystemLoad?: 'normal' | 'medium' | 'high'
): number;

export function getAdaptiveTimeout(
  timeoutName: keyof TimeoutConfiguration,
  urgency?: 'normal' | 'high' | 'low'
): number;

export interface PerformanceRecord {
  operation: string;
  duration: number;
  timestamp: number;
}

export interface BudgetStatus {
  currentOverhead: number;
  maxBudget: number;
  percentageUsed: number;
  isExceeded: boolean;
  recentOperations: PerformanceRecord[];
}

declare class PerformanceBudgetTracker {
  currentOverhead: number;
  lastReset: number;
  history: PerformanceRecord[];

  trackOperation(operationName: string, duration: number): void;
  onBudgetExceeded(operationName: string, duration: number): void;
  resetBudget(): void;
  getBudgetStatus(): BudgetStatus;
}

export const performanceBudgetTracker: PerformanceBudgetTracker;

export interface UserActivity {
  isActive: boolean;
  lastActivity: number;
  isDashboardVisible: boolean;
}

export interface SystemState {
  health: 'healthy' | 'degraded' | 'critical';
  load: 'normal' | 'medium' | 'high';
  batteryStatus: 'unknown' | 'charging' | 'discharging';
}

export declare class SmartMonitoringController {
  userActivity: UserActivity;
  systemState: SystemState;

  setupUserActivityDetection(): void;
  setupSystemStateDetection(): void;
  shouldReduceMonitoring(): boolean;
  getOptimalInterval(baseInterval: number): number;
  setUserDashboardViewing(isViewing: boolean): void;
  setSystemHealth(health: 'healthy' | 'degraded' | 'critical'): void;
  getSystemState(): { userActivity: UserActivity } & SystemState;
}

export const smartMonitoringController: SmartMonitoringController;

export function isPerformanceModeEnabled(): boolean;
export function logPerformanceMetric(component: string, metric: string, value: number | string): void;
export function shouldUseAdaptiveMonitoring(): boolean;

export default OPTIMIZED_PERFORMANCE;
