// TypeScript declarations for useServiceMonitor.js
import { Ref, ComputedRef } from 'vue'

export interface ServiceInfo {
  name: string
  status: string
  statusText?: string
  message?: string
  icon?: string
  category: string
  response_time?: number
  responseTime?: number
  version?: string
}

export interface SystemResources {
  [key: string]: any
}

export interface ServiceSummary {
  total: number
  online: number
  warning: number
  error: number
  offline: number
}

export interface UseServiceMonitorReturn {
  // State
  services: Ref<ServiceInfo[]>
  systemResources: Ref<SystemResources>
  overallStatus: Ref<string>
  serviceSummary: Ref<ServiceSummary>
  lastCheck: Ref<Date | null>
  isLoading: Ref<boolean>
  error: Ref<string | null>
  
  // Computed
  healthyServices: ComputedRef<number>
  healthPercentage: ComputedRef<number>
  statusColor: ComputedRef<string>
  statusIcon: ComputedRef<string>
  statusMessage: ComputedRef<string>
  servicesByCategory: ComputedRef<{ [category: string]: ServiceInfo[] }>
  coreServices: ComputedRef<ServiceInfo[]>
  
  // Methods
  fetchServiceStatus: () => Promise<void>
  fetchHealthCheck: () => Promise<void>
  startMonitoring: () => void
  stopMonitoring: () => void
  refresh: () => void
  getService: (name: string) => ServiceInfo | undefined
  getServicesByStatus: (status: string) => ServiceInfo[]
  formatResponseTime: (ms?: number) => string
  formatLastCheck: () => string
}

export declare function useServiceMonitor(): UseServiceMonitorReturn