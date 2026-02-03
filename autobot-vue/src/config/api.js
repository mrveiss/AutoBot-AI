/**
 * API Configuration
 */

import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for api config
const logger = createLogger('api.config')

// Determine API base URL based on environment
const getApiBaseUrl = () => {
  // Check for environment variable first
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }

  // In development, use backend host/port from env or fallback
  if (import.meta.env.DEV) {
    const protocol = import.meta.env.VITE_HTTP_PROTOCOL || 'http';
    const host = import.meta.env.VITE_BACKEND_HOST || '127.0.0.3';
    const port = import.meta.env.VITE_BACKEND_PORT || '8001';
    return `${protocol}://${host}:${port}`;
  }

  // In production, use relative paths (assuming backend serves the frontend)
  return '';
};

export const API_BASE_URL = getApiBaseUrl();

/**
 * Create full API URL
 * @param {string} endpoint - API endpoint (e.g., '/api/phases/status')
 * @returns {string} - Full URL
 */
export const apiUrl = (endpoint) => {
  return `${API_BASE_URL}${endpoint}`;
};

/**
 * Make API request with error handling
 * @param {string} endpoint - API endpoint
 * @param {object} options - Fetch options
 * @returns {Promise<any>} - Response data
 */
export const apiRequest = async (endpoint, options = {}) => {
  try {
    const response = await fetch(apiUrl(endpoint), {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      throw new Error(`API request failed: ${response.status} ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    // Only log API errors in development mode
    if (import.meta.env.DEV) {
      logger.debug(`API request to ${endpoint} failed:`, error.message);
    }
    throw error;
  }
};
