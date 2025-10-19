/**
 * Type definitions for System Status Management Composable
 */

import { Ref } from 'vue';

export interface SystemService {
  name: string;
  status: 'healthy' | 'warning' | 'error';
  statusText: string;
}

export interface SystemStatus {
  isHealthy: boolean;
  hasIssues: boolean;
  lastChecked: Date;
  apiErrors?: boolean;
  criticalError?: boolean;
}

export interface UseSystemStatusReturn {
  // State
  systemStatus: Ref<SystemStatus>;
  systemServices: Ref<SystemService[]>;
  showSystemStatus: Ref<boolean>;

  // API utilities
  clearStatusCache: () => void;

  // Computed
  getSystemStatusTooltip: () => string;
  getSystemStatusText: () => string;
  getSystemStatusDescription: () => string;

  // Methods
  toggleSystemStatus: () => void;
  refreshSystemStatus: () => Promise<void>;
  updateSystemStatus: () => void;
}

export function useSystemStatus(): UseSystemStatusReturn;
