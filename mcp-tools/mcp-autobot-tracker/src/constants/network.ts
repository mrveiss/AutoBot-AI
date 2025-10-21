/**
 * Network Constants for MCP AutoBot Tracker
 * =========================================
 * 
 * Centralized network configuration to eliminate hardcoded IPs and URLs.
 * Mirrors the Python network_constants.py structure for consistency.
 * 
 * Usage:
 *   import { NetworkConstants, ServiceURLs } from './constants/network';
 *   const redisUrl = `redis://${NetworkConstants.REDIS_VM_IP}:${NetworkConstants.REDIS_PORT}`;
 */

/**
 * Core network configuration constants
 */
export const NetworkConstants = {
  // Main machine (WSL)
  MAIN_MACHINE_IP: process.env.MAIN_MACHINE_IP || '172.16.168.20',

  // VM Infrastructure IPs
  FRONTEND_VM_IP: process.env.FRONTEND_VM_IP || '172.16.168.21',
  NPU_WORKER_VM_IP: process.env.NPU_WORKER_VM_IP || '172.16.168.22',
  REDIS_VM_IP: process.env.REDIS_VM_IP || '172.16.168.23',
  AI_STACK_VM_IP: process.env.AI_STACK_VM_IP || '172.16.168.24',
  BROWSER_VM_IP: process.env.BROWSER_VM_IP || '172.16.168.25',

  // Local/Localhost addresses
  LOCALHOST_IP: '127.0.0.1',
  LOCALHOST_NAME: 'localhost',

  // Standard ports
  BACKEND_PORT: parseInt(process.env.BACKEND_PORT || '8001'),
  FRONTEND_PORT: parseInt(process.env.FRONTEND_PORT || '5173'),
  REDIS_PORT: parseInt(process.env.REDIS_PORT || '6379'),
  OLLAMA_PORT: parseInt(process.env.OLLAMA_PORT || '11434'),
  VNC_PORT: parseInt(process.env.VNC_PORT || '6080'),
  BROWSER_SERVICE_PORT: parseInt(process.env.BROWSER_SERVICE_PORT || '3000'),
  AI_STACK_PORT: parseInt(process.env.AI_STACK_PORT || '8080'),
  NPU_WORKER_PORT: parseInt(process.env.NPU_WORKER_PORT || '8081'), // Linux NPU worker (VM2)
  NPU_WORKER_WINDOWS_PORT: parseInt(process.env.NPU_WORKER_WINDOWS_PORT || '8082'), // Windows NPU worker (primary)
} as const;

/**
 * Pre-built service URLs for common AutoBot services
 */
export const ServiceURLs = {
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

  // NPU Worker services
  NPU_WORKER_SERVICE: `http://${NetworkConstants.NPU_WORKER_VM_IP}:${NetworkConstants.NPU_WORKER_PORT}`,
  NPU_WORKER_WINDOWS_SERVICE: `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.NPU_WORKER_WINDOWS_PORT}`,
} as const;

/**
 * Service health check endpoints
 */
export const HealthCheckEndpoints = {
  FRONTEND: `${ServiceURLs.FRONTEND_VM}/health`,
  NPU_WORKER: `${ServiceURLs.NPU_WORKER_SERVICE}/health`,
  NPU_WORKER_WINDOWS: `${ServiceURLs.NPU_WORKER_WINDOWS_SERVICE}/health`,
  REDIS: ServiceURLs.REDIS_VM,
  AI_STACK: `${ServiceURLs.AI_STACK_SERVICE}/health`,
  BROWSER: `${ServiceURLs.BROWSER_SERVICE}/health`,
  BACKEND: `${ServiceURLs.BACKEND_API}/api/system/health`,
} as const;
