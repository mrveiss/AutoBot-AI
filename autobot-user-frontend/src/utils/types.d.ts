// Type declarations for JavaScript modules

declare module '@/utils/ChatIdGenerator.js' {
  export function generateChatId(): string
  export function generateMessageId(): string
}

// System status indicator type enhancement
interface SystemStatusIndicator {
  status: string;
  text: string;
  pulse: boolean;
  statusDetails?: {
    lastCheck: number;
    consecutiveFailures?: number;
    error?: string;
  };
}

// Service info types for proper compatibility
interface ServiceInfo {
  name: string;
  status: string;
  statusText: string;
  version?: string;
  responseTime?: number;
}
