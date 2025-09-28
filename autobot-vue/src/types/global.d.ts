// Global type declarations for AutoBot frontend

interface Window {
  rum?: {
    trackApiCall(method: string, endpoint: string, startTime: number, endTime: number, status: number | string, error?: Error): void;
  };
}

// Extend IteratorResult for cache keys
declare global {
  interface IteratorResult<T> {
    value: T | undefined;
    done: boolean;
  }
}