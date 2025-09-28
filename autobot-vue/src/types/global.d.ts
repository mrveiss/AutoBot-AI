// Global type declarations for AutoBot frontend

// Replace NodeJS namespace with browser-compatible timer types
declare global {
  // Browser timer types to replace NodeJS.Timeout
  type TimerHandle = ReturnType<typeof setTimeout>;
  type IntervalHandle = ReturnType<typeof setInterval>;

  // For compatibility with existing code using NodeJS namespace
  namespace NodeJS {
    type Timeout = TimerHandle;
    type Timer = TimerHandle;
  }

  // Window interface extensions
  interface Window {
    rum?: {
      trackError: (type: string, data: Record<string, unknown>) => void;
      trackUserInteraction: (type: string, element: unknown, data: Record<string, unknown>) => void;
      trackApiCall: (method: string, endpoint: string, startTime: number, endTime: number, status: number | string, error?: any) => void;
      reportCriticalIssue: (type: string, data: Record<string, unknown>) => void;
    };
  }

  // Extend IteratorResult for cache keys
  interface IteratorResult<T> {
    value: T | undefined;
    done: boolean;
  }
}

export {};