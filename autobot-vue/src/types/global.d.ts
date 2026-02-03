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

  // Issue #156 Fix: Window.rum is declared in src/utils/RumAgent.ts
  // Removed duplicate declaration to avoid type conflicts

  // Extend IteratorResult for cache keys
  interface IteratorResult<T> {
    value: T | undefined;
    done: boolean;
  }
}

export {};