/**
 * Type definitions for OptimizedHealthMonitor
 */

export interface MonitorHealthStatus {
  overall: 'healthy' | 'degraded' | 'critical' | 'unknown';
  backend: 'healthy' | 'degraded' | 'critical' | 'unknown';
  frontend: 'healthy' | 'degraded' | 'critical' | 'unknown';
  websocket: 'healthy' | 'degraded' | 'critical' | 'unknown';
  router: 'healthy' | 'degraded' | 'critical' | 'unknown';
}

export interface PerformanceBudget {
  maxOverheadPerMinute: number;
  currentOverhead: number;
  lastReset: number;
}

export interface PerformanceThresholds {
  maxCheckDuration: number;
  degradeThreshold: number;
  criticalThreshold: number;
}

export interface IntervalConfig {
  healthy: number;
  degraded: number;
  critical: number;
  userActive: number;
}

export interface MonitorConfig {
  intervals: IntervalConfig;
  performanceThresholds: PerformanceThresholds;
}

export interface PerformanceMetrics {
  checksPerformed: number;
  totalCheckTime: number;
  averageCheckTime: number;
  lastSlowCheck: { duration: number; timestamp: number } | null;
}

export interface ConsecutiveFailures {
  backend: number;
  websocket: number;
}

export interface HealthData {
  status: MonitorHealthStatus;
  metrics: PerformanceMetrics;
  timestamp: number;
  monitoring: {
    isActive: boolean;
    performanceBudget: PerformanceBudget;
    lastCheck: number;
  };
}

export interface HealthCheckResult {
  status: 'fulfilled' | 'rejected';
  value?: any;
  reason?: any;
}

declare class OptimizedHealthMonitor {
  isMonitoring: boolean;
  performanceBudget: PerformanceBudget;
  healthStatus: MonitorHealthStatus;
  config: MonitorConfig;
  eventListeners: Map<string, EventListener>;
  consecutiveFailures: ConsecutiveFailures;
  healthCheckTimer: number | null;
  listeners: Array<(data: HealthData) => void>;
  isUserViewing: boolean;
  lastHealthCheck: number;
  performanceMetrics: PerformanceMetrics;

  initialize(): void;
  setupEventListeners(): void;
  addEventListenerWithTracking(event: string, handler: EventListener): void;
  setupPerformanceBudget(): void;
  scheduleNextCheck(healthState?: 'healthy' | 'degraded' | 'critical' | null): void;
  determineHealthState(): 'healthy' | 'degraded' | 'critical';
  isPerformanceBudgetExceeded(): boolean;
  performHealthCheck(): Promise<void>;
  performEssentialHealthChecks(): Promise<HealthCheckResult[]>;
  timeoutPromise(timeoutMs: number): Promise<never>;
  checkBackendHealth(): Promise<{ status: string; responseTime?: number; error?: string; consecutiveFailures?: number }>;
  processHealthResults(results: HealthCheckResult[]): void;
  updateOverallHealth(): void;
  handleHealthCheckFailure(): void;
  trackPerformance(duration: number): void;
  onErrorDetected(event: Event | PromiseRejectionEvent): void;
  onNetworkStatusChange(status: 'online' | 'offline'): void;
  onRouterNavigation(): void;
  setUserViewing(isViewing: boolean): void;
  pauseMonitoring(): void;
  resumeMonitoring(): void;
  performManualHealthCheck(): Promise<void>;
  onHealthChange(callback: (data: HealthData) => void): void;
  notifyHealthChange(): void;
  getHealthStatus(): MonitorHealthStatus & {
    isMonitoring: boolean;
    performanceMetrics: PerformanceMetrics;
    consecutiveFailures: ConsecutiveFailures;
    lastHealthCheck: number;
  };
  destroy(): void;
}

export const optimizedHealthMonitor: OptimizedHealthMonitor;
export default OptimizedHealthMonitor;
