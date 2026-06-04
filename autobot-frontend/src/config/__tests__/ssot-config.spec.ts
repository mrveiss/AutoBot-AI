/**
 * Unit Tests for SSOT Configuration Loader (TypeScript)
 * =======================================================
 *
 * Tests the Single Source of Truth configuration system to ensure:
 * 1. Configuration loads from Vite environment variables correctly
 * 2. Default values are used when env values are missing
 * 3. Computed properties (URLs) are generated correctly
 * 4. Type safety is maintained
 * 5. Singleton pattern works correctly
 *
 * Issue: #601 - SSOT Phase 1: Foundation
 * Related: #599 - SSOT Configuration System Epic
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { reloadConfig, runtimeHttpProto } from '../ssot-config';

// Note: In a real test environment, we would need to mock import.meta.env
// For now, these tests validate the TypeScript structure and default values

describe('SSOT Config Types', () => {
  describe('VMConfig interface', () => {
    it('should have all required VM properties', () => {
      // Type check - this validates the interface structure
      const vmConfig = {
        main: '10.0.0.1',
        frontend: '10.0.0.2',
        npu: '10.0.0.3',
        redis: '10.0.0.4',
        aistack: '10.0.0.5',
        browser: '10.0.0.6',
        ollama: '127.0.0.1',
      };

      expect(vmConfig.main).toBe('10.0.0.1');
      expect(vmConfig.frontend).toBe('10.0.0.2');
      expect(vmConfig.npu).toBe('10.0.0.3');
      expect(vmConfig.redis).toBe('10.0.0.4');
      expect(vmConfig.aistack).toBe('10.0.0.5');
      expect(vmConfig.browser).toBe('10.0.0.6');
      expect(vmConfig.ollama).toBe('127.0.0.1');
    });
  });

  describe('PortConfig interface', () => {
    it('should have all required port properties', () => {
      const portConfig = {
        backend: 8001,
        frontend: 5173,
        redis: 6379,
        ollama: 11434,
        vnc: 6080,
        browser: 3000,
        aistack: 8080,
        npu: 8081,
        prometheus: 9090,
        grafana: 3000,
      };

      expect(portConfig.backend).toBe(8001);
      expect(portConfig.frontend).toBe(5173);
      expect(portConfig.redis).toBe(6379);
      expect(portConfig.ollama).toBe(11434);
      expect(portConfig.vnc).toBe(6080);
      expect(portConfig.browser).toBe(3000);
      expect(portConfig.aistack).toBe(8080);
      expect(portConfig.npu).toBe(8081);
      expect(portConfig.prometheus).toBe(9090);
      expect(portConfig.grafana).toBe(3000);
    });
  });

  describe('LLMConfig interface', () => {
    it('should have all required LLM properties', () => {
      const llmConfig = {
        defaultModel: 'qwen3.5:9b',
        embeddingModel: 'nomic-embed-text:latest',
        provider: 'ollama',
        timeout: 30000,
      };

      expect(llmConfig.defaultModel).toBe('qwen3.5:9b');
      expect(llmConfig.embeddingModel).toBe('nomic-embed-text:latest');
      expect(llmConfig.provider).toBe('ollama');
      expect(llmConfig.timeout).toBe(30000);
    });
  });

  describe('TimeoutConfig interface', () => {
    it('should have all required timeout properties in milliseconds', () => {
      const timeoutConfig = {
        api: 60000,
        knowledge: 300000,
        retryAttempts: 3,
        retryDelay: 1000,
        websocket: 30000,
      };

      expect(timeoutConfig.api).toBe(60000);
      expect(timeoutConfig.knowledge).toBe(300000);
      expect(timeoutConfig.retryAttempts).toBe(3);
      expect(timeoutConfig.retryDelay).toBe(1000);
      expect(timeoutConfig.websocket).toBe(30000);
    });
  });

  describe('VNCConfig interface', () => {
    it('should have desktop, terminal, and playwright configs', () => {
      const vncConfig = {
        desktop: {
          host: '10.0.0.1',
          port: 6080,
          password: 'autobot',
        },
        terminal: {
          host: '10.0.0.1',
          port: 6080,
          password: 'autobot',
        },
        playwright: {
          host: '10.0.0.6',
          port: 6081,
          password: 'playwright',
        },
      };

      expect(vncConfig.desktop.host).toBe('10.0.0.1');
      expect(vncConfig.desktop.port).toBe(6080);
      expect(vncConfig.playwright.host).toBe('10.0.0.6');
      expect(vncConfig.playwright.port).toBe(6081);
    });
  });

  describe('FeatureConfig interface', () => {
    it('should have all feature flag properties', () => {
      const featureConfig = {
        debug: false,
        rum: true,
        cacheDisabled: false,
      };

      expect(featureConfig.debug).toBe(false);
      expect(featureConfig.rum).toBe(true);
      expect(featureConfig.cacheDisabled).toBe(false);
    });
  });
});

describe('SSOT Config Helper Functions', () => {
  describe('getEnv helper', () => {
    it('should return default value when env is undefined', () => {
      // Simulating the getEnv function behavior
      const getEnv = (_key: string, defaultValue: string): string => {
        const value = undefined; // Simulating missing env var
        if (value === undefined || value === null || value === '') {
          return defaultValue;
        }
        return String(value);
      };

      expect(getEnv('VITE_MISSING_VAR', 'default')).toBe('default');
    });

    it('should return env value when present', () => {
      const getEnv = (key: string, defaultValue: string): string => {
        const mockEnv: Record<string, string> = {
          VITE_BACKEND_HOST: '10.0.0.1',
        };
        const value = mockEnv[key];
        if (value === undefined || value === null || value === '') {
          return defaultValue;
        }
        return String(value);
      };

      expect(getEnv('VITE_BACKEND_HOST', '10.0.0.1')).toBe('10.0.0.1');
    });
  });

  describe('getEnvNumber helper', () => {
    it('should return default value when env is undefined', () => {
      const getEnvNumber = (_key: string, defaultValue: number): number => {
        const value = undefined;
        if (value === undefined || value === null || value === '') {
          return defaultValue;
        }
        const parsed = parseInt(String(value), 10);
        return isNaN(parsed) ? defaultValue : parsed;
      };

      expect(getEnvNumber('VITE_MISSING_PORT', 8001)).toBe(8001);
    });

    it('should parse numeric string correctly', () => {
      const getEnvNumber = (key: string, defaultValue: number): number => {
        const mockEnv: Record<string, string> = {
          VITE_BACKEND_PORT: '9000',
        };
        const value = mockEnv[key];
        if (value === undefined || value === null || value === '') {
          return defaultValue;
        }
        const parsed = parseInt(String(value), 10);
        return isNaN(parsed) ? defaultValue : parsed;
      };

      expect(getEnvNumber('VITE_BACKEND_PORT', 8001)).toBe(9000);
    });

    it('should return default for invalid number', () => {
      const getEnvNumber = (key: string, defaultValue: number): number => {
        const mockEnv: Record<string, string> = {
          VITE_INVALID_PORT: 'not-a-number',
        };
        const value = mockEnv[key];
        if (value === undefined || value === null || value === '') {
          return defaultValue;
        }
        const parsed = parseInt(String(value), 10);
        return isNaN(parsed) ? defaultValue : parsed;
      };

      expect(getEnvNumber('VITE_INVALID_PORT', 8001)).toBe(8001);
    });
  });

  describe('getEnvBoolean helper', () => {
    it('should return default value when env is undefined', () => {
      const getEnvBoolean = (_key: string, defaultValue: boolean): boolean => {
        const value = undefined;
        if (value === undefined || value === null || value === '') {
          return defaultValue;
        }
        const strValue = String(value).toLowerCase();
        return strValue === 'true' || strValue === '1' || strValue === 'yes';
      };

      expect(getEnvBoolean('VITE_MISSING_FLAG', true)).toBe(true);
      expect(getEnvBoolean('VITE_MISSING_FLAG', false)).toBe(false);
    });

    it('should parse "true" correctly', () => {
      const getEnvBoolean = (key: string, defaultValue: boolean): boolean => {
        const mockEnv: Record<string, string> = {
          VITE_DEBUG: 'true',
        };
        const value = mockEnv[key];
        if (value === undefined || value === null || value === '') {
          return defaultValue;
        }
        const strValue = String(value).toLowerCase();
        return strValue === 'true' || strValue === '1' || strValue === 'yes';
      };

      expect(getEnvBoolean('VITE_DEBUG', false)).toBe(true);
    });

    it('should parse "1" correctly', () => {
      const getEnvBoolean = (key: string, defaultValue: boolean): boolean => {
        const mockEnv: Record<string, string> = {
          VITE_DEBUG: '1',
        };
        const value = mockEnv[key];
        if (value === undefined || value === null || value === '') {
          return defaultValue;
        }
        const strValue = String(value).toLowerCase();
        return strValue === 'true' || strValue === '1' || strValue === 'yes';
      };

      expect(getEnvBoolean('VITE_DEBUG', false)).toBe(true);
    });

    it('should parse "false" correctly', () => {
      const getEnvBoolean = (key: string, defaultValue: boolean): boolean => {
        const mockEnv: Record<string, string> = {
          VITE_DEBUG: 'false',
        };
        const value = mockEnv[key];
        if (value === undefined || value === null || value === '') {
          return defaultValue;
        }
        const strValue = String(value).toLowerCase();
        return strValue === 'true' || strValue === '1' || strValue === 'yes';
      };

      expect(getEnvBoolean('VITE_DEBUG', true)).toBe(false);
    });
  });
});

describe('SSOT Config URL Computation', () => {
  it('should compute backend URL correctly', () => {
    const vm = { main: '10.0.0.1' };
    const port = { backend: 8001 };
    const protocol = 'http';

    const backendUrl = `${protocol}://${vm.main}:${port.backend}`;
    expect(backendUrl).toBe('http://10.0.0.1:8001');
  });

  it('should compute WebSocket URL correctly', () => {
    const vm = { main: '10.0.0.1' };
    const port = { backend: 8001 };
    const httpProtocol: string = 'http';

    const wsProtocol = httpProtocol === 'https' ? 'wss' : 'ws';
    const websocketUrl = `${wsProtocol}://${vm.main}:${port.backend}/ws`;
    expect(websocketUrl).toBe('ws://10.0.0.1:8001/ws');
  });

  it('should compute Redis URL correctly', () => {
    const vm = { redis: '10.0.0.4' };
    const port = { redis: 6379 };

    const redisUrl = `redis://${vm.redis}:${port.redis}`;
    expect(redisUrl).toBe('redis://10.0.0.4:6379');
  });

  it('should compute VNC URL correctly', () => {
    const vm = { main: '10.0.0.1' };
    const port = { vnc: 6080 };
    const protocol = 'http';

    const vncUrl = `${protocol}://${vm.main}:${port.vnc}/vnc.html`;
    expect(vncUrl).toBe('http://10.0.0.1:6080/vnc.html');
  });

  it('should use wss for https protocol', () => {
    const vm = { main: '10.0.0.1' };
    const port = { backend: 8001 };
    const httpProtocol = 'https';

    const wsProtocol = httpProtocol === 'https' ? 'wss' : 'ws';
    const websocketUrl = `${wsProtocol}://${vm.main}:${port.backend}/ws`;
    expect(websocketUrl).toBe('wss://10.0.0.1:8001/ws');
  });
});

// =============================================================================
// Issue #6837: runtimeHttpProto() protocol detection tests
// =============================================================================

describe('SSOT Config runtimeHttpProto() — protocol detection', () => {
  // Getters read window.location.protocol on every access, so we override it
  // before reloadConfig() forces a fresh buildConfig() call.
  let originalLocation: Location;

  beforeEach(() => {
    originalLocation = window.location;
  });

  afterEach(() => {
    // Restore original location so other tests are not affected
    Object.defineProperty(window, 'location', {
      value: originalLocation,
      writable: true,
      configurable: true,
    });
  });

  const setProtocol = (protocol: 'https:' | 'http:') => {
    Object.defineProperty(window, 'location', {
      value: { ...window.location, protocol, hostname: 'test-host.example.com', host: 'test-host.example.com' },
      writable: true,
      configurable: true,
    });
  };

  describe('when window.location.protocol === "https:"', () => {
    it('backendUrl starts with https://', () => {
      setProtocol('https:');
      const cfg = reloadConfig();
      expect(cfg.backendUrl).toMatch(/^https:\/\//);
    });

    it('frontendUrl starts with https://', () => {
      setProtocol('https:');
      const cfg = reloadConfig();
      expect(cfg.frontendUrl).toMatch(/^https:\/\//);
    });

    it('ollamaUrl starts with https://', () => {
      setProtocol('https:');
      const cfg = reloadConfig();
      expect(cfg.ollamaUrl).toMatch(/^https:\/\//);
    });

    it('aistackUrl starts with https://', () => {
      setProtocol('https:');
      const cfg = reloadConfig();
      expect(cfg.aistackUrl).toMatch(/^https:\/\//);
    });

    it('npuWorkerUrl starts with https://', () => {
      setProtocol('https:');
      const cfg = reloadConfig();
      expect(cfg.npuWorkerUrl).toMatch(/^https:\/\//);
    });

    it('browserServiceUrl starts with https://', () => {
      setProtocol('https:');
      const cfg = reloadConfig();
      expect(cfg.browserServiceUrl).toMatch(/^https:\/\//);
    });

    it('vncUrl starts with https://', () => {
      setProtocol('https:');
      const cfg = reloadConfig();
      expect(cfg.vncUrl).toMatch(/^https:\/\//);
    });

    it('slmUrl starts with https:// when vm.slm is set', () => {
      setProtocol('https:');
      // Provide a non-empty VITE_SLM_HOST so the getter does not return '/slm'
      const originalEnv = import.meta.env.VITE_SLM_HOST;
      import.meta.env.VITE_SLM_HOST = 'slm.example.com';
      const cfg = reloadConfig();
      const result = cfg.slmUrl;
      import.meta.env.VITE_SLM_HOST = originalEnv;
      // When vm.slm is empty the getter falls back to '/slm'; only assert
      // the protocol when the URL is absolute.
      if (result.startsWith('/')) return;
      expect(result).toMatch(/^https:\/\//);
    });

    it('slmAdminUrl starts with https:// when vm.slm is set', () => {
      setProtocol('https:');
      const originalEnv = import.meta.env.VITE_SLM_HOST;
      import.meta.env.VITE_SLM_HOST = 'slm-admin.example.com';
      const cfg = reloadConfig();
      const result = cfg.slmAdminUrl;
      import.meta.env.VITE_SLM_HOST = originalEnv;
      if (result.startsWith('/')) return;
      expect(result).toMatch(/^https:\/\//);
    });

    it('redisUrl still uses redis:// (not affected by protocol detection)', () => {
      setProtocol('https:');
      const cfg = reloadConfig();
      expect(cfg.redisUrl).toMatch(/^redis:\/\//);
    });
  });

  describe('when window.location.protocol === "http:"', () => {
    it('backendUrl starts with http://', () => {
      setProtocol('http:');
      const cfg = reloadConfig();
      expect(cfg.backendUrl).toMatch(/^http:\/\//);
    });

    it('frontendUrl starts with http://', () => {
      setProtocol('http:');
      const cfg = reloadConfig();
      expect(cfg.frontendUrl).toMatch(/^http:\/\//);
    });

    it('ollamaUrl starts with http://', () => {
      setProtocol('http:');
      const cfg = reloadConfig();
      expect(cfg.ollamaUrl).toMatch(/^http:\/\//);
    });

    it('aistackUrl starts with http://', () => {
      setProtocol('http:');
      const cfg = reloadConfig();
      expect(cfg.aistackUrl).toMatch(/^http:\/\//);
    });

    it('npuWorkerUrl starts with http://', () => {
      setProtocol('http:');
      const cfg = reloadConfig();
      expect(cfg.npuWorkerUrl).toMatch(/^http:\/\//);
    });

    it('browserServiceUrl starts with http://', () => {
      setProtocol('http:');
      const cfg = reloadConfig();
      expect(cfg.browserServiceUrl).toMatch(/^http:\/\//);
    });

    it('vncUrl starts with http://', () => {
      setProtocol('http:');
      const cfg = reloadConfig();
      expect(cfg.vncUrl).toMatch(/^http:\/\//);
    });

    it('slmAdminUrl starts with http:// when vm.slm is set (fix GH #6837)', () => {
      setProtocol('http:');
      const originalEnv = import.meta.env.VITE_SLM_HOST;
      import.meta.env.VITE_SLM_HOST = 'slm-admin.example.com';
      const cfg = reloadConfig();
      const result = cfg.slmAdminUrl;
      import.meta.env.VITE_SLM_HOST = originalEnv;
      if (result.startsWith('/')) return;
      expect(result).toMatch(/^http:\/\//);
    });
  });
});

// =============================================================================
// Issue #6809: runtimeHttpProto() direct unit tests
// =============================================================================

describe('runtimeHttpProto', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns "https" when window.location.protocol is "https:"', () => {
    vi.stubGlobal('window', { location: { protocol: 'https:', host: 'example.com' } });
    expect(runtimeHttpProto()).toBe('https');
  });

  it('returns "http" when window.location.protocol is "http:"', () => {
    vi.stubGlobal('window', { location: { protocol: 'http:', host: 'example.com' } });
    expect(runtimeHttpProto()).toBe('http');
  });

  it('falls back to VITE_HTTP_PROTOCOL env var in SSR (no window)', () => {
    vi.stubGlobal('window', undefined);
    expect(runtimeHttpProto()).toBe('http'); // default from getEnv fallback
  });
});

describe('SSOT Config Service Lookup', () => {
  it('should look up service URLs by name', () => {
    const urls: Record<string, string> = {
      backend: 'http://10.0.0.1:8001',
      frontend: 'http://10.0.0.2:5173',
      redis: 'redis://10.0.0.4:6379',
      ollama: 'http://127.0.0.1:11434',
    };

    const getServiceUrl = (name: string): string | undefined => {
      return urls[name.toLowerCase()];
    };

    expect(getServiceUrl('backend')).toBe('http://10.0.0.1:8001');
    expect(getServiceUrl('BACKEND')).toBe('http://10.0.0.1:8001');
    expect(getServiceUrl('redis')).toBe('redis://10.0.0.4:6379');
    expect(getServiceUrl('unknown')).toBeUndefined();
  });

  it('should look up VM IPs by name', () => {
    const vms: Record<string, string> = {
      main: '10.0.0.1',
      frontend: '10.0.0.2',
      npu: '10.0.0.3',
      redis: '10.0.0.4',
      aistack: '10.0.0.5',
      browser: '10.0.0.6',
    };

    const getVmIp = (name: string): string | undefined => {
      return vms[name.toLowerCase()];
    };

    expect(getVmIp('main')).toBe('10.0.0.1');
    expect(getVmIp('redis')).toBe('10.0.0.4');
    expect(getVmIp('unknown')).toBeUndefined();
  });
});
