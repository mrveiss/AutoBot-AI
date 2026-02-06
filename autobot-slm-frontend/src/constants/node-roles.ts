// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Node Role Constants
 *
 * Fallback role definitions when API is unavailable.
 * Source of truth: slm-server/api/deployments.py:AVAILABLE_ROLES
 *
 * Issue #737 Phase 3: Unified data models
 */

import type { NodeRole, RoleCategory } from '@/types/slm'

/**
 * Role metadata for UI display and fallback data.
 */
export interface RoleMetadata {
  name: NodeRole
  displayName: string
  description: string
  category: RoleCategory
  tools: string[]
}

/**
 * Complete role metadata mapping.
 * Keep in sync with backend AVAILABLE_ROLES in slm-server/api/deployments.py
 */
export const NODE_ROLE_METADATA: Record<NodeRole, RoleMetadata> = {
  'slm-agent': {
    name: 'slm-agent',
    displayName: 'SLM Agent',
    description: 'SLM monitoring agent for node health reporting',
    category: 'core',
    tools: ['systemd', 'journalctl', 'htop', 'netstat'],
  },
  'redis': {
    name: 'redis',
    displayName: 'Redis',
    description: 'Redis Stack server for data persistence',
    category: 'data',
    tools: ['redis-server', 'redis-cli', 'redis-sentinel'],
  },
  'backend': {
    name: 'backend',
    displayName: 'Backend',
    description: 'AutoBot backend API server',
    category: 'application',
    tools: ['uvicorn', 'gunicorn', 'python3', 'pip'],
  },
  'frontend': {
    name: 'frontend',
    displayName: 'Frontend',
    description: 'AutoBot Vue.js frontend server',
    category: 'application',
    tools: ['nginx', 'node', 'npm', 'vite'],
  },
  'llm': {
    name: 'llm',
    displayName: 'LLM Provider',
    description: 'LLM inference provider (Ollama/vLLM)',
    category: 'ai',
    tools: ['ollama', 'vllm', 'llama-cpp'],
  },
  'ai-stack': {
    name: 'ai-stack',
    displayName: 'AI Stack',
    description: 'AI tools and processing stack',
    category: 'ai',
    tools: ['chromadb', 'langchain', 'transformers', 'torch', 'onnxruntime'],
  },
  'npu-worker': {
    name: 'npu-worker',
    displayName: 'NPU Worker',
    description: 'Intel NPU acceleration worker',
    category: 'ai',
    tools: ['openvino', 'intel-npu-driver', 'benchmark_app'],
  },
  'browser-automation': {
    name: 'browser-automation',
    displayName: 'Browser Automation',
    description: 'Playwright browser automation service',
    category: 'automation',
    tools: ['playwright', 'chromium', 'firefox', 'webkit'],
  },
  'monitoring': {
    name: 'monitoring',
    displayName: 'Monitoring',
    description: 'Prometheus and Grafana monitoring stack',
    category: 'observability',
    tools: ['prometheus', 'grafana', 'node_exporter', 'alertmanager'],
  },
  'vnc': {
    name: 'vnc',
    displayName: 'VNC Server',
    description: 'VNC remote desktop server with noVNC web interface',
    category: 'remote-access',
    tools: ['tigervnc-standalone-server', 'websockify', 'novnc', 'x11vnc'],
  },
}

/**
 * Default list of all available roles.
 * Used as fallback when API is unavailable.
 */
export const DEFAULT_ROLES: NodeRole[] = Object.keys(NODE_ROLE_METADATA) as NodeRole[]

/**
 * Get role metadata by role name.
 * Returns undefined if role not found.
 */
export function getRoleMetadata(role: NodeRole): RoleMetadata | undefined {
  return NODE_ROLE_METADATA[role]
}

/**
 * Get display name for a role.
 * Returns the role name if metadata not found.
 */
export function getRoleDisplayName(role: NodeRole): string {
  return NODE_ROLE_METADATA[role]?.displayName ?? role
}

/**
 * Get description for a role.
 * Returns 'Unknown role' if metadata not found.
 */
export function getRoleDescription(role: NodeRole): string {
  return NODE_ROLE_METADATA[role]?.description ?? 'Unknown role'
}

/**
 * Get tools for a role.
 * Returns empty array if metadata not found.
 */
export function getRoleTools(role: NodeRole): string[] {
  return NODE_ROLE_METADATA[role]?.tools ?? []
}

/**
 * Get category for a role.
 * Returns 'core' as default if metadata not found.
 */
export function getRoleCategory(role: NodeRole): RoleCategory {
  return NODE_ROLE_METADATA[role]?.category ?? 'core'
}
