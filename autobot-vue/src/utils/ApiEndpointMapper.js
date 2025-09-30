/**
 * API Endpoint Mapper - Centralized endpoint mapping with graceful fallbacks
 * 
 * Maps legacy/incorrect endpoints to correct backend endpoints
 * Provides fallback mechanisms for missing endpoints
 * Prevents Vue app mounting failures due to API errors
 */

import appConfig from '@/config/AppConfig.js';

export class ApiEndpointMapper {
  constructor() {
    this.endpointMap = {
      // Legacy -> Correct endpoint mappings
      '/api/vms/status': '/api/enterprise/infrastructure',
      '/api/services/health': '/api/monitoring/services/health',
      '/api/services': '/api/monitoring/services/health', // Fallback mapping
      '/api/system/health': '/api/health', // Standardize health checks
      
      // Additional mappings for commonly misused endpoints
      '/api/vm/status': '/api/enterprise/infrastructure',
      '/api/infrastructure': '/api/enterprise/infrastructure',
      '/api/monitoring/status': '/api/monitoring/services/health'
    };

    this.fallbackData = {
      '/api/enterprise/infrastructure': {
        vms: [
          { name: 'Backend API', status: 'warning', message: 'Status Unknown' },
          { name: 'Frontend', status: 'healthy', message: 'Connected' },
          { name: 'NPU Worker', status: 'warning', message: 'Status Unknown' },
          { name: 'Redis', status: 'warning', message: 'Status Unknown' },
          { name: 'Browser Service', status: 'warning', message: 'Status Unknown' }
        ]
      },
      '/api/monitoring/services/health': {
        services: {
          backend: { status: 'warning', health: 'Status Unknown' },
          redis: { status: 'warning', health: 'Status Unknown' },
          ollama: { status: 'warning', health: 'Status Unknown' },
          npu_worker: { status: 'warning', health: 'Status Unknown' },
          browser: { status: 'warning', health: 'Status Unknown' }
        }
      },
      '/api/health': {
        status: 'healthy',
        timestamp: new Date().toISOString(),
        services: ['frontend']
      }
    };

    this.requestCache = new Map();
    this.cacheTimeout = 30000; // 30 seconds
  }

  /**
   * Map legacy endpoint to correct endpoint
   */
  mapEndpoint(originalEndpoint) {
    const mapped = this.endpointMap[originalEndpoint];
    if (mapped) {
      console.log(`[ApiMapper] Mapping ${originalEndpoint} → ${mapped}`);
      return mapped;
    }
    return originalEndpoint;
  }

  /**
   * Enhanced fetch with endpoint mapping and graceful fallbacks
   */
  async fetchWithFallback(endpoint, options = {}) {
    const mappedEndpoint = this.mapEndpoint(endpoint);
    const cacheKey = `${mappedEndpoint}_${JSON.stringify(options)}`;

    // Check cache first
    if (this.requestCache.has(cacheKey)) {
      const cached = this.requestCache.get(cacheKey);
      if (Date.now() - cached.timestamp < this.cacheTimeout) {
        console.log(`[ApiMapper] Returning cached response for ${mappedEndpoint}`);
        return {
          ok: true,
          status: 200,
          json: () => Promise.resolve(cached.data),
          cached: true
        };
      }
    }

    // Set up timeout with graceful handling
    const timeout = options.timeout || 5000;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      console.log(`[ApiMapper] Attempting request to ${mappedEndpoint}`);
      
      // Use AppConfig for enhanced fetch with proper error handling
      const response = await appConfig.fetchApi(mappedEndpoint, {
        ...options,
        signal: controller.signal,
        timeout
      });

      clearTimeout(timeoutId);

      if (response.ok) {
        // Cache successful response
        const data = await response.json();
        this.requestCache.set(cacheKey, {
          data,
          timestamp: Date.now()
        });

        console.log(`[ApiMapper] Successful response from ${mappedEndpoint}`);
        return {
          ok: true,
          status: response.status,
          json: () => Promise.resolve(data)
        };
      } else {
        console.warn(`[ApiMapper] HTTP ${response.status} from ${mappedEndpoint}, using fallback`);
        return this.getFallbackResponse(mappedEndpoint, response.status);
      }

    } catch (error) {
      clearTimeout(timeoutId);
      
      if (error.name === 'AbortError') {
        console.warn(`[ApiMapper] Request timeout for ${mappedEndpoint}, using fallback`);
      } else if (error.message.includes('Failed to fetch') || error.message.includes('Network')) {
        console.warn(`[ApiMapper] Network error for ${mappedEndpoint}, using fallback`);
      } else {
        console.warn(`[ApiMapper] Request failed for ${mappedEndpoint}:`, error.message);
      }

      return this.getFallbackResponse(mappedEndpoint, 0, error);
    }
  }

  /**
   * Get fallback response when API is unavailable
   */
  getFallbackResponse(endpoint, status = 503, error = null) {
    const fallbackData = this.fallbackData[endpoint];
    
    if (fallbackData) {
      console.log(`[ApiMapper] Using fallback data for ${endpoint}`);
      return {
        ok: false,
        status,
        fallback: true,
        json: () => Promise.resolve(fallbackData),
        error: error?.message
      };
    }

    // Generic fallback for unmapped endpoints
    console.log(`[ApiMapper] Using generic fallback for ${endpoint}`);
    return {
      ok: false,
      status,
      fallback: true,
      json: () => Promise.resolve({
        error: 'Service temporarily unavailable',
        fallback: true,
        message: 'Using cached or default data'
      }),
      error: error?.message
    };
  }

  /**
   * Clear cache (useful for forced refresh)
   */
  clearCache() {
    console.log('[ApiMapper] Clearing request cache');
    this.requestCache.clear();
  }

  /**
   * Get cache statistics
   */
  getCacheStats() {
    return {
      size: this.requestCache.size,
      entries: Array.from(this.requestCache.keys())
    };
  }

  /**
   * Validate endpoint availability (for health checks)
   */
  async validateEndpoint(endpoint) {
    try {
      const response = await this.fetchWithFallback(endpoint, { timeout: 3000 });
      return {
        endpoint,
        available: response.ok,
        status: response.status,
        fallback: response.fallback || false
      };
    } catch (error) {
      return {
        endpoint,
        available: false,
        status: 0,
        fallback: true,
        error: error.message
      };
    }
  }
}

// Singleton instance
const apiEndpointMapper = new ApiEndpointMapper();
export default apiEndpointMapper;