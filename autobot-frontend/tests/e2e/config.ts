/**
 * E2E Test Configuration
 *
 * Centralized configuration for E2E tests with environment variable support.
 * Prevents hardcoded URLs and allows tests to run against different environments.
 *
 * Environment Variables:
 * - VITE_BASE_URL: Frontend URL (default: http://localhost:5173)
 * - VITE_API_BASE_URL: Backend API URL (default: http://localhost:8001)
 */

export const TEST_CONFIG = {
  /**
   * Frontend application URL
   */
  FRONTEND_URL: process.env.VITE_BASE_URL || 'http://localhost:5173',

  /**
   * Backend API URL
   */
  BACKEND_URL: process.env.VITE_API_BASE_URL || 'http://localhost:8001',

  /**
   * Get full API endpoint URL
   */
  getApiUrl: (endpoint: string): string => {
    const baseUrl = process.env.VITE_API_BASE_URL || 'http://localhost:8001';
    // Ensure endpoint starts with /
    const normalizedEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    return `${baseUrl}${normalizedEndpoint}`;
  },

  /**
   * Get WebSocket URL from backend URL
   */
  getWsUrl: (): string => {
    const baseUrl = process.env.VITE_API_BASE_URL || 'http://localhost:8001';
    // Convert http://... to ws://...
    return baseUrl.replace('http://', 'ws://').replace('https://', 'wss://');
  },

  /**
   * Extract hostname from URL for assertions
   */
  getFrontendHostname: (): string => {
    const url = process.env.VITE_BASE_URL || 'http://localhost:5173';
    return url.replace(/^https?:\/\//, '').replace(/:\d+$/, '');
  },

  /**
   * Extract full frontend host:port for assertions
   */
  getFrontendHost: (): string => {
    const url = process.env.VITE_BASE_URL || 'http://localhost:5173';
    return url.replace(/^https?:\/\//, '');
  },

  /**
   * Extract full backend host:port for assertions
   */
  getBackendHost: (): string => {
    const url = process.env.VITE_API_BASE_URL || 'http://localhost:8001';
    return url.replace(/^https?:\/\//, '');
  },
};
