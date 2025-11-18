// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Network Constants - TypeScript Mirror of Python NetworkConstants
 *
 * This file mirrors src/constants/network_constants.py to provide
 * consistent network configuration across frontend and backend.
 *
 * IMPORTANT: Keep in sync with Python NetworkConstants
 */

/**
 * Network configuration for AutoBot distributed architecture
 *
 * Service Distribution (6-VM Architecture):
 * - Main Machine (WSL): 172.16.168.20 - Backend API + VNC Desktop
 * - VM1 Frontend: 172.16.168.21:5173 - Web interface (SINGLE FRONTEND SERVER)
 * - VM2 NPU Worker: 172.16.168.22:8081 - Hardware AI acceleration
 * - VM3 Redis: 172.16.168.23:6379 - Data layer
 * - VM4 AI Stack: 172.16.168.24:8080 - AI processing
 * - VM5 Browser: 172.16.168.25:3000 - Web automation (Playwright)
 */
export const NetworkConstants = {
  // Main Machine (WSL)
  MAIN_MACHINE_IP: '172.16.168.20',
  BACKEND_PORT: 8001,
  VNC_PORT: 6080,
  OLLAMA_PORT: 11434,

  // VM1 - Frontend
  FRONTEND_VM_IP: '172.16.168.21',
  FRONTEND_PORT: 5173,

  // VM2 - NPU Worker
  NPU_WORKER_VM_IP: '172.16.168.22',
  NPU_WORKER_PORT: 8081,

  // VM3 - Redis
  REDIS_VM_IP: '172.16.168.23',
  REDIS_PORT: 6379,

  // VM4 - AI Stack
  AI_STACK_VM_IP: '172.16.168.24',
  AI_STACK_PORT: 8080,

  // VM5 - Browser Service (Playwright)
  BROWSER_VM_IP: '172.16.168.25',
  BROWSER_SERVICE_PORT: 3000,

  /**
   * Get backend API base URL
   * Uses environment variable if available, falls back to constant
   */
  getBackendUrl(): string {
    const host = import.meta.env.VITE_BACKEND_HOST || this.MAIN_MACHINE_IP
    const port = import.meta.env.VITE_BACKEND_PORT || this.BACKEND_PORT
    return `http://${host}:${port}`
  },

  /**
   * Get frontend base URL
   */
  getFrontendUrl(): string {
    const host = import.meta.env.VITE_FRONTEND_HOST || this.FRONTEND_VM_IP
    const port = import.meta.env.VITE_FRONTEND_PORT || this.FRONTEND_PORT
    return `http://${host}:${port}`
  },

  /**
   * Get browser service (Playwright) URL
   */
  getBrowserServiceUrl(): string {
    const host = import.meta.env.VITE_PLAYWRIGHT_HOST || this.BROWSER_VM_IP
    const port = import.meta.env.VITE_PLAYWRIGHT_VNC_PORT || this.BROWSER_SERVICE_PORT
    return `http://${host}:${port}`
  },

  /**
   * Get VNC (noVNC) URL
   */
  getVncUrl(): string {
    const host = import.meta.env.VITE_VNC_HOST || this.MAIN_MACHINE_IP
    const port = import.meta.env.VITE_VNC_PORT || this.VNC_PORT
    return `http://${host}:${port}`
  }
} as const

/**
 * Type-safe exports for individual constants
 */
export const {
  MAIN_MACHINE_IP,
  BACKEND_PORT,
  VNC_PORT,
  OLLAMA_PORT,
  FRONTEND_VM_IP,
  FRONTEND_PORT,
  NPU_WORKER_VM_IP,
  NPU_WORKER_PORT,
  REDIS_VM_IP,
  REDIS_PORT,
  AI_STACK_VM_IP,
  AI_STACK_PORT,
  BROWSER_VM_IP,
  BROWSER_SERVICE_PORT
} = NetworkConstants

export default NetworkConstants
