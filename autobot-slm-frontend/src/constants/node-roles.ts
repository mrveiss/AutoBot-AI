// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Node Role Constants
 *
 * Fallback role definitions when API is unavailable.
 * Source of truth: autobot-slm-backend/services/role_registry.py:DEFAULT_ROLES
 *
 * Issue #737 Phase 3: Unified data models
 * Issue #1247: Consistent roles across all views
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
 * Keep in sync with role_registry.py DEFAULT_ROLES.
 */
export const NODE_ROLE_METADATA: Record<NodeRole, RoleMetadata> = {
  'slm-backend': {
    name: 'slm-backend',
    displayName: 'SLM Backend',
    description: 'SLM backend API server',
    category: 'core',
    tools: ['uvicorn', 'python3', 'pip', 'alembic'],
  },
  'slm-frontend': {
    name: 'slm-frontend',
    displayName: 'SLM Frontend',
    description: 'SLM Vue.js frontend',
    category: 'core',
    tools: ['nginx', 'node', 'npm'],
  },
  'slm-database': {
    name: 'slm-database',
    displayName: 'SLM Database',
    description: 'PostgreSQL 16 database server',
    category: 'core',
    tools: ['postgresql', 'psql', 'pg_dump', 'pg_restore'],
  },
  'slm-monitoring': {
    name: 'slm-monitoring',
    displayName: 'SLM Monitoring',
    description: 'Prometheus and Grafana monitoring stack',
    category: 'observability',
    tools: ['prometheus', 'grafana', 'node_exporter', 'alertmanager'],
  },
  'backend': {
    name: 'backend',
    displayName: 'Backend',
    description: 'AutoBot backend API server',
    category: 'application',
    tools: ['uvicorn', 'gunicorn', 'python3', 'pip'],
  },
  'celery': {
    name: 'celery',
    displayName: 'Celery Worker',
    description: 'Celery background task worker',
    category: 'application',
    tools: ['celery', 'python3'],
  },
  'frontend': {
    name: 'frontend',
    displayName: 'Frontend',
    description: 'AutoBot Vue.js frontend server',
    category: 'application',
    tools: ['nginx', 'node', 'npm', 'vite'],
  },
  'redis': {
    name: 'redis',
    displayName: 'Redis',
    description: 'Redis Stack server for data persistence',
    category: 'data',
    tools: ['redis-server', 'redis-cli', 'redis-sentinel'],
  },
  'ai-stack': {
    name: 'ai-stack',
    displayName: 'AI Stack',
    description: 'AI tools and processing stack',
    category: 'ai',
    tools: ['chromadb', 'langchain', 'transformers', 'torch', 'onnxruntime'],
  },
  'chromadb': {
    name: 'chromadb',
    displayName: 'ChromaDB',
    description: 'ChromaDB vector database',
    category: 'ai',
    tools: ['chromadb'],
  },
  'npu-worker': {
    name: 'npu-worker',
    displayName: 'NPU Worker',
    description: 'Intel NPU acceleration worker',
    category: 'ai',
    tools: ['openvino', 'intel-npu-driver', 'benchmark_app'],
  },
  'tts-worker': {
    name: 'tts-worker',
    displayName: 'TTS Worker',
    description: 'Text-to-speech synthesis worker',
    category: 'ai',
    tools: ['python3', 'pip'],
  },
  'browser-service': {
    name: 'browser-service',
    displayName: 'Browser Automation',
    description: 'Playwright browser automation service',
    category: 'automation',
    tools: ['playwright', 'chromium', 'firefox', 'webkit'],
  },
  'autobot-llm-cpu': {
    name: 'autobot-llm-cpu',
    displayName: 'LLM CPU Node',
    description: 'LLM inference on CPU (Ollama)',
    category: 'ai',
    tools: ['ollama'],
  },
  'autobot-llm-gpu': {
    name: 'autobot-llm-gpu',
    displayName: 'LLM GPU Node',
    description: 'LLM inference on GPU (Ollama)',
    category: 'ai',
    tools: ['ollama'],
  },
  'autobot-shared': {
    name: 'autobot-shared',
    displayName: 'Shared Library',
    description: 'Shared Python library (deployed to all nodes)',
    category: 'infrastructure',
    tools: ['pip', 'python3'],
  },
  'slm-agent': {
    name: 'slm-agent',
    displayName: 'SLM Agent',
    description: 'SLM monitoring agent for node health reporting',
    category: 'infrastructure',
    tools: ['systemd', 'journalctl', 'htop', 'netstat'],
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
