// System Status Types
export type SystemSeverity = 'low' | 'medium' | 'high' | 'critical';

export interface SystemStatusDetails {
  status: string;
  lastCheck: number;
  consecutiveFailures?: number;
  error?: string;
  timestamp: number;
}

export interface SystemAlert {
  id: string;
  severity: SystemSeverity;
  title: string;
  message: string;
  visible: boolean;
  statusDetails?: SystemStatusDetails;
  timestamp: number;
}

export interface ServiceHealth {
  name: string;
  status: 'online' | 'warning' | 'error' | 'offline';
  statusText: string;
  version?: string;
  responseTime?: number;
  lastCheck?: number;
  consecutiveFailures?: number;
  error?: string;
  timestamp?: number;
  details?: Record<string, any>;
}