/**
 * Network Constants for AutoBot Frontend
 * =====================================
 *
 * Centralized network configuration constants to eliminate hardcoded URLs and IP addresses
 * throughout the frontend codebase. This mirrors the Python constants in src/constants/network_constants.py
 *
 * Usage:
 *     import { NetworkConstants, ServiceURLs } from '@/constants/network-constants.js'
 *
 *     // Use VM IP addresses
 *     const redisUrl = `redis://${NetworkConstants.REDIS_VM_IP}:6379`
 *
 *     // Use service URLs
 *     const backendUrl = ServiceURLs.BACKEND_API
 */

/**
 * Core network constants for AutoBot distributed infrastructure
 */
export const NetworkConstants = Object.freeze({
  // Main machine (WSL)
  MAIN_MACHINE_IP: "172.16.168.20",

  // VM Infrastructure IPs
  FRONTEND_VM_IP: "172.16.168.21",
  NPU_WORKER_VM_IP: "172.16.168.22",
  REDIS_VM_IP: "172.16.168.23",
  AI_STACK_VM_IP: "172.16.168.24",
  BROWSER_VM_IP: "172.16.168.25",

  // Local/Localhost addresses
  LOCALHOST_IP: "127.0.0.1",
  LOCALHOST_NAME: "localhost",

  // Standard ports
  BACKEND_PORT: 8001,
  FRONTEND_PORT: 5173,
  REDIS_PORT: 6379,
  OLLAMA_PORT: 11434,
  VNC_PORT: 6080,
  BROWSER_SERVICE_PORT: 3000,
  AI_STACK_PORT: 8080,
  NPU_WORKER_PORT: 8081,

  // Development ports
  DEV_FRONTEND_PORT: 5173,
  DEV_BACKEND_PORT: 8001
});

/**
 * Pre-built service URLs for common AutoBot services
 */
export const ServiceURLs = Object.freeze({
  // Backend API URLs
  BACKEND_API: `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`,
  BACKEND_LOCAL: `http://${NetworkConstants.LOCALHOST_NAME}:${NetworkConstants.BACKEND_PORT}`,

  // Frontend URLs
  FRONTEND_VM: `http://${NetworkConstants.FRONTEND_VM_IP}:${NetworkConstants.FRONTEND_PORT}`,
  FRONTEND_LOCAL: `http://${NetworkConstants.LOCALHOST_NAME}:${NetworkConstants.FRONTEND_PORT}`,

  // Redis URLs
  REDIS_VM: `redis://${NetworkConstants.REDIS_VM_IP}:${NetworkConstants.REDIS_PORT}`,
  REDIS_LOCAL: `redis://${NetworkConstants.LOCALHOST_IP}:${NetworkConstants.REDIS_PORT}`,

  // Ollama LLM URLs
  OLLAMA_LOCAL: `http://${NetworkConstants.LOCALHOST_NAME}:${NetworkConstants.OLLAMA_PORT}`,
  OLLAMA_MAIN: `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.OLLAMA_PORT}`,

  // VNC Desktop URLs
  VNC_DESKTOP: `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.VNC_PORT}/vnc.html`,
  VNC_LOCAL: `http://${NetworkConstants.LOCALHOST_NAME}:${NetworkConstants.VNC_PORT}/vnc.html`,

  // Browser automation service
  BROWSER_SERVICE: `http://${NetworkConstants.BROWSER_VM_IP}:${NetworkConstants.BROWSER_SERVICE_PORT}`,

  // AI Stack service
  AI_STACK_SERVICE: `http://${NetworkConstants.AI_STACK_VM_IP}:${NetworkConstants.AI_STACK_PORT}`,

  // NPU Worker service
  NPU_WORKER_SERVICE: `http://${NetworkConstants.NPU_WORKER_VM_IP}:${NetworkConstants.NPU_WORKER_PORT}`
});

/**
 * Dynamic network configuration based on environment
 */
export class NetworkConfig {
  constructor() {
    this._deploymentMode = import.meta.env.VITE_AUTOBOT_DEPLOYMENT_MODE || 'distributed';
    this._isDevelopment = import.meta.env.MODE === 'development';
  }

  get backendUrl() {
    if (this._deploymentMode === 'local') {
      return ServiceURLs.BACKEND_LOCAL;
    }
    return ServiceURLs.BACKEND_API;
  }

  get frontendUrl() {
    if (this._deploymentMode === 'local') {
      return ServiceURLs.FRONTEND_LOCAL;
    }
    return ServiceURLs.FRONTEND_VM;
  }

  get redisUrl() {
    if (this._deploymentMode === 'local') {
      return ServiceURLs.REDIS_LOCAL;
    }
    return ServiceURLs.REDIS_VM;
  }

  get ollamaUrl() {
    return ServiceURLs.OLLAMA_LOCAL; // Always local for now
  }

  getServiceUrl(serviceName) {
    const serviceMap = {
      'backend': this.backendUrl,
      'frontend': this.frontendUrl,
      'redis': this.redisUrl,
      'ollama': this.ollamaUrl,
      'browser': ServiceURLs.BROWSER_SERVICE,
      'ai_stack': ServiceURLs.AI_STACK_SERVICE,
      'npu_worker': ServiceURLs.NPU_WORKER_SERVICE,
      'vnc': ServiceURLs.VNC_DESKTOP
    };
    return serviceMap[serviceName] || null;
  }

  getVmIp(vmName) {
    const vmMap = {
      'main': NetworkConstants.MAIN_MACHINE_IP,
      'frontend': NetworkConstants.FRONTEND_VM_IP,
      'npu_worker': NetworkConstants.NPU_WORKER_VM_IP,
      'redis': NetworkConstants.REDIS_VM_IP,
      'ai_stack': NetworkConstants.AI_STACK_VM_IP,
      'browser': NetworkConstants.BROWSER_VM_IP
    };
    return vmMap[vmName] || null;
  }
}

// Global network configuration instance
export const networkConfig = new NetworkConfig();

/**
 * Redis database assignments to eliminate hardcoded database numbers
 */
export const DatabaseConstants = Object.freeze({
  // Core databases
  MAIN_DB: 0,
  KNOWLEDGE_DB: 1,
  CACHE_DB: 2,
  VECTORS_DB: 8,

  // Specialized databases
  SESSIONS_DB: 3,
  METRICS_DB: 4,
  LOGS_DB: 5,
  CONFIG_DB: 6,
  WORKFLOWS_DB: 7,
  TEMP_DB: 9,
  MONITORING_DB: 10,
  RATE_LIMITING_DB: 11
});

// Legacy compatibility exports
export const BACKEND_URL = ServiceURLs.BACKEND_API;
export const FRONTEND_URL = ServiceURLs.FRONTEND_VM;
export const REDIS_HOST = NetworkConstants.REDIS_VM_IP;
export const MAIN_MACHINE_IP = NetworkConstants.MAIN_MACHINE_IP;
export const LOCALHOST_IP = NetworkConstants.LOCALHOST_IP;