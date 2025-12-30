/**
 * ServiceDiscovery - Dynamic Service URL Resolution
 *
 * Handles environment-aware service discovery using SSOT configuration.
 * Supports Docker, native VM, and development environments.
 *
 * Issue: #603 - SSOT Phase 3: Frontend Migration
 * Related: #599 - SSOT Configuration System Epic
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { getConfig, getServiceUrl as ssotGetServiceUrl } from './ssot-config';
import { buildDefaultServiceUrl, buildDefaultVncUrl } from './defaults.js';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('ServiceDiscovery');

export default class ServiceDiscovery {
  constructor() {
    this.cache = new Map();
    this.cacheTimeout = 60000; // 1 minute cache
    this.config = getConfig();
    this.debugMode = import.meta.env.DEV || this.config.feature.debug;

    this.log('ServiceDiscovery initialized with SSOT config');
  }

  /**
   * Get service URL with intelligent environment detection
   */
  async getServiceUrl(serviceName, options = {}) {
    const cacheKey = `${serviceName}_${JSON.stringify(options)}`;

    // Check cache first
    if (!options.skipCache && this.cache.has(cacheKey)) {
      const cached = this.cache.get(cacheKey);
      if (Date.now() - cached.timestamp < this.cacheTimeout) {
        this.log(`Cache hit for ${serviceName}:`, cached.url);
        return cached.url;
      }
    }

    let url;
    try {
      url = await this._resolveServiceUrl(serviceName, options);

      // Cache the result
      this.cache.set(cacheKey, {
        url,
        timestamp: Date.now()
      });

      this.log(`Resolved ${serviceName}:`, url);
      return url;
    } catch (error) {
      this.log(`Failed to resolve ${serviceName}:`, error.message);

      // For critical services, provide fallback URLs instead of throwing
      const fallbackUrl = this._getFallbackUrl(serviceName);
      if (fallbackUrl) {
        this.log(`Using fallback URL for ${serviceName}:`, fallbackUrl);

        // Cache the fallback result to avoid repeated failures
        this.cache.set(cacheKey, {
          url: fallbackUrl,
          timestamp: Date.now()
        });

        return fallbackUrl;
      }

      // If no fallback available, still throw but with enhanced error message
      throw new Error(`Failed to resolve service '${serviceName}': ${error.message}. No fallback URL configured.`);
    }
  }

  /**
   * Internal URL resolution logic using SSOT config
   */
  async _resolveServiceUrl(serviceName, options = {}) {
    // First try SSOT helper function for known services
    const ssotUrl = ssotGetServiceUrl(serviceName);
    if (ssotUrl) {
      this.log(`Using SSOT URL for ${serviceName}:`, ssotUrl);
      return ssotUrl;
    }

    // Get environment mappings for additional services
    const envMappings = this._getEnvironmentMappings();
    const serviceConfig = envMappings[serviceName];

    if (!serviceConfig) {
      throw new Error(`Unknown service: ${serviceName}`);
    }

    // Check for explicit environment variable override
    const envUrl = import.meta.env[serviceConfig.envVar];
    if (envUrl) {
      this.log(`Using environment variable ${serviceConfig.envVar}:`, envUrl);
      return envUrl;
    }

    // CRITICAL FIX: For backend service, check if we should use proxy mode
    if (serviceName === 'backend') {
      const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;

      // If VITE_API_BASE_URL is empty, use proxy mode (Vite dev server will proxy /api requests)
      if (!apiBaseUrl) {
        this.log('Backend service using proxy mode (empty URL) - requests will go through Vite proxy');
        return '';
      }
    }

    // Build URL from SSOT config values
    const host = await this._resolveHost(serviceName, serviceConfig);
    const port = options.port || serviceConfig.port;
    const protocol = options.protocol || this.config.httpProtocol;

    if (!host) {
      throw new Error(`Could not resolve host for service: ${serviceName}`);
    }

    return `${protocol}://${host}:${port}`;
  }

  /**
   * Get environment variable mappings for all services
   * Values now come from SSOT config
   */
  _getEnvironmentMappings() {
    const cfg = this.config;

    return {
      backend: {
        envVar: 'VITE_API_BASE_URL',
        hostVar: 'VITE_BACKEND_HOST',
        portVar: 'VITE_BACKEND_PORT',
        port: String(cfg.port.backend),
        protocol: cfg.httpProtocol,
        fallbackHosts: [cfg.vm.main, 'localhost', '127.0.0.1']
      },
      redis: {
        envVar: 'VITE_REDIS_URL',
        hostVar: 'VITE_REDIS_HOST',
        portVar: 'VITE_REDIS_PORT',
        port: String(cfg.port.redis),
        protocol: 'redis',
        fallbackHosts: [cfg.vm.redis, 'localhost', '127.0.0.1']
      },
      vnc_desktop: {
        envVar: 'VITE_DESKTOP_VNC_URL',
        hostVar: 'VITE_DESKTOP_VNC_HOST',
        portVar: 'VITE_DESKTOP_VNC_PORT',
        port: String(cfg.vnc.desktop.port),
        protocol: cfg.httpProtocol,
        fallbackHosts: [cfg.vnc.desktop.host, 'localhost', '127.0.0.1']
      },
      vnc_terminal: {
        envVar: 'VITE_TERMINAL_VNC_URL',
        hostVar: 'VITE_TERMINAL_VNC_HOST',
        portVar: 'VITE_TERMINAL_VNC_PORT',
        port: String(cfg.vnc.terminal.port),
        protocol: cfg.httpProtocol,
        fallbackHosts: [cfg.vnc.terminal.host, 'localhost', '127.0.0.1']
      },
      vnc_playwright: {
        envVar: 'VITE_PLAYWRIGHT_VNC_URL',
        hostVar: 'VITE_PLAYWRIGHT_VNC_HOST',
        portVar: 'VITE_PLAYWRIGHT_VNC_PORT',
        port: String(cfg.vnc.playwright.port),
        protocol: cfg.httpProtocol,
        fallbackHosts: [cfg.vnc.playwright.host, 'localhost', '127.0.0.1']
      },
      npu_worker: {
        envVar: 'VITE_NPU_WORKER_URL',
        hostVar: 'VITE_NPU_WORKER_HOST',
        portVar: 'VITE_NPU_WORKER_PORT',
        port: String(cfg.port.npu),
        protocol: cfg.httpProtocol,
        fallbackHosts: [cfg.vm.npu, 'localhost', '127.0.0.1']
      },
      ollama: {
        envVar: 'VITE_OLLAMA_URL',
        hostVar: 'VITE_OLLAMA_HOST',
        portVar: 'VITE_OLLAMA_PORT',
        port: String(cfg.port.ollama),
        protocol: cfg.httpProtocol,
        fallbackHosts: [cfg.vm.ollama, 'localhost', '127.0.0.1']
      },
      playwright: {
        envVar: 'VITE_PLAYWRIGHT_API_URL',
        hostVar: 'VITE_PLAYWRIGHT_HOST',
        portVar: 'VITE_PLAYWRIGHT_PORT',
        port: String(cfg.port.browser),
        protocol: cfg.httpProtocol,
        fallbackHosts: [cfg.vm.browser, 'localhost', '127.0.0.1']
      }
    };
  }

  /**
   * Resolve host with intelligent fallback
   */
  async _resolveHost(serviceName, serviceConfig) {
    // Check explicit host environment variable
    const envHost = import.meta.env[serviceConfig.hostVar];
    if (envHost) {
      this.log(`Using explicit host for ${serviceName}:`, envHost);
      return envHost;
    }

    // Determine environment context
    const environment = this._detectEnvironment();
    this.log(`Detected environment: ${environment}`);

    switch (environment) {
      case 'development':
        return this._getDevHost(serviceConfig);
      case 'production':
        return this._getProdHost(serviceConfig);
      case 'docker':
        return this._getDockerHost(serviceConfig);
      case 'vm':
        return this._getVmHost(serviceConfig);
      default:
        return this._getFallbackHost(serviceConfig);
    }
  }

  /**
   * Detect current deployment environment
   */
  _detectEnvironment() {
    const hostname = window.location.hostname;
    const port = window.location.port;

    // Development server (Vite)
    if (port === '5173' || port === '3000' || import.meta.env.DEV) {
      return 'development';
    }

    // VM environment (specific IP ranges)
    if (hostname.startsWith('172.16.168.') || hostname.startsWith('192.168.')) {
      return 'vm';
    }

    // Docker environment
    if (hostname === 'localhost' && port !== '5173') {
      return 'docker';
    }

    // Production environment
    if (import.meta.env.PROD) {
      return 'production';
    }

    return 'unknown';
  }

  /**
   * Get host for development environment
   */
  _getDevHost(_serviceConfig) {
    return 'localhost';
  }

  /**
   * Get host for production environment
   */
  _getProdHost(serviceConfig) {
    const currentHost = window.location.hostname;

    if (currentHost === 'localhost' || currentHost === '127.0.0.1') {
      return serviceConfig.fallbackHosts?.[0] || currentHost;
    }

    return currentHost;
  }

  /**
   * Get host for Docker environment
   */
  _getDockerHost(serviceConfig) {
    return serviceConfig.fallbackHosts?.[0] || 'localhost';
  }

  /**
   * Get host for VM environment
   */
  _getVmHost(serviceConfig) {
    return serviceConfig.fallbackHosts?.[0] || window.location.hostname;
  }

  /**
   * Get fallback host
   */
  _getFallbackHost(serviceConfig) {
    return serviceConfig.fallbackHosts?.[0] || 'localhost';
  }

  /**
   * Get fallback URL for critical services when normal resolution fails
   */
  _getFallbackUrl(serviceName) {
    try {
      // For backend service, return empty string to trigger proxy mode
      if (serviceName === 'backend') {
        this.log('Backend service fallback: using proxy mode (empty URL)');
        return '';
      }

      // Handle VNC services
      if (serviceName.startsWith('vnc_')) {
        const vncType = serviceName.replace('vnc_', '');
        return buildDefaultVncUrl(vncType);
      }

      // Handle regular services using defaults (which now uses SSOT)
      const serviceMap = {
        'npu_worker': 'npu_worker',
        'redis': 'redis',
        'browser': 'browser',
        'ai_stack': 'ai_stack'
      };

      const defaultServiceName = serviceMap[serviceName];
      if (defaultServiceName) {
        return buildDefaultServiceUrl(defaultServiceName);
      }

      // Legacy services that need special handling
      const legacyFallbacks = {
        'ollama': buildDefaultServiceUrl('backend').replace(`:${this.config.port.backend}`, `:${this.config.port.ollama}`),
        'playwright': buildDefaultServiceUrl('browser')
      };

      return legacyFallbacks[serviceName] || null;
    } catch (error) {
      logger.warn(`Failed to build fallback URL for ${serviceName}:`, error.message);
      return null;
    }
  }

  /**
   * Get WebSocket URL
   */
  async getWebSocketUrl(endpoint = '') {
    const backendUrl = await this.getServiceUrl('backend');

    // If backend URL is empty (proxy mode), use relative WebSocket path
    if (!backendUrl) {
      const wsUrl = `/ws${endpoint}`;
      this.log('WebSocket URL (proxy mode):', wsUrl);
      return wsUrl;
    }

    const wsProtocol = backendUrl.startsWith('https') ? 'wss:' : 'ws:';
    const backendHost = new URL(backendUrl).host;

    const wsUrl = `${wsProtocol}//${backendHost}/ws${endpoint}`;
    this.log('WebSocket URL:', wsUrl);
    return wsUrl;
  }

  /**
   * Test service connectivity
   */
  async testConnectivity(serviceName, timeout = 5000) {
    try {
      const url = await this.getServiceUrl(serviceName);

      // Handle proxy mode for backend service
      if (serviceName === 'backend' && !url) {
        const testUrl = '/api/health';
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        const response = await fetch(testUrl, {
          method: 'HEAD',
          signal: controller.signal,
          mode: 'cors'
        });

        clearTimeout(timeoutId);

        return {
          serviceName,
          url: 'proxy mode',
          accessible: response.ok,
          status: response.status,
          statusText: response.statusText,
          note: 'Using Vite proxy'
        };
      }

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeout);

      // Use different endpoints based on service type
      let testEndpoint = '/api/system/health';
      if (serviceName.startsWith('vnc_')) {
        testEndpoint = '/vnc.html';
      } else if (serviceName === 'redis') {
        clearTimeout(timeoutId);
        return {
          serviceName,
          url,
          accessible: true,
          status: 200,
          statusText: 'Redis URL resolved',
          note: 'Redis connectivity requires specialized client'
        };
      }

      const response = await fetch(`${url}${testEndpoint}`, {
        method: 'HEAD',
        signal: controller.signal,
        mode: 'cors'
      });

      clearTimeout(timeoutId);

      const result = {
        serviceName,
        url,
        accessible: response.ok,
        status: response.status,
        statusText: response.statusText
      };

      this.log(`Connectivity test for ${serviceName}:`, result);
      return result;
    } catch (error) {
      let serviceUrl = 'unknown';
      try {
        serviceUrl = await this.getServiceUrl(serviceName);
      } catch (_urlError) {
        // URL resolution also failed
      }

      const result = {
        serviceName,
        url: serviceUrl,
        accessible: false,
        error: error.name === 'AbortError' ? 'Connection timeout' : error.message,
        errorType: error.name || 'Unknown'
      };

      this.log(`Connectivity test failed for ${serviceName}:`, result);
      return result;
    }
  }

  /**
   * Test all services connectivity
   */
  async testAllServices() {
    const services = Object.keys(this._getEnvironmentMappings());
    const results = await Promise.all(
      services.map(service => this.testConnectivity(service))
    );

    return results.reduce((acc, result) => {
      acc[result.serviceName] = result;
      return acc;
    }, {});
  }

  /**
   * Clear service URL cache
   */
  clearCache() {
    this.cache.clear();
    this.log('Service URL cache cleared');
  }

  /**
   * Get cache statistics
   */
  getCacheStats() {
    return {
      size: this.cache.size,
      entries: Array.from(this.cache.keys())
    };
  }

  /**
   * Debug logging
   */
  log(...args) {
    if (this.debugMode) {
      logger.debug('[ServiceDiscovery]', ...args);
    }
  }
}
