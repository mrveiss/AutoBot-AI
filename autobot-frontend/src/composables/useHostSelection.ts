// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useHostSelection - Composable for managing host selection for agent SSH actions
 *
 * Provides:
 * - Host selection dialog state management
 * - Default host configuration
 * - Session-level host persistence
 * - API for agents to request host selection
 *
 * ⚠️ DISTINCT FROM useHostInventory (GH#9063 audit):
 * - useHostSelection: User-configured SSH targets from secrets.env
 *   → Data source: main backend /api/infrastructure/hosts (user secrets)
 *   → Used by: agent SSH actions, terminal selector, ui/HostSelector
 *
 * - useHostInventory: Ansible-managed fleet nodes
 *   → Data source: SLM backend /api/nodes (Ansible inventory, provisioning)
 *   → Used by: admin dashboard (HostsView.vue) for fleet management
 *
 * These serve DIFFERENT purposes and MUST remain separate composables.
 *
 * fetchWithAuth replaced with useFetchEndpoint (Pattern A) for both
 * loadHosts and loadTerminalHosts (Issue #6089).
 */

import { ref, computed, readonly } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint';
import type { HostConfig } from '@/composables/useTerminalStore';

const logger = createLogger('useHostSelection');

// Types
export interface InfrastructureHost {
  id: string;
  name: string;
  host: string;
  ssh_port?: number;
  username?: string;
  auth_type?: 'ssh_key' | 'password';
  capabilities?: string[];
  purpose?: string;
  os?: string;
  metadata?: Record<string, unknown>;
  _isLegacyHost?: boolean;
}

export interface HostSelectionRequest {
  requestId: string;
  command?: string;
  purpose?: string;
  agentSessionId?: string;
  preferredHostId?: string;
  allowAutoSelect?: boolean;
}

export interface HostSelectionResult {
  host: InfrastructureHost;
  rememberChoice: boolean;
  requestId: string;
}

interface HostsApiRaw {
  hosts?: Record<string, unknown>[];
}

// Singleton state (shared across all component instances)
const showDialog = ref(false);
const pendingRequest = ref<HostSelectionRequest | null>(null);
const selectedHost = ref<InfrastructureHost | null>(null);
const defaultHostId = ref<string | null>(null);
const sessionHostId = ref<string | null>(null);
const hosts = ref<InfrastructureHost[]>([]);
const error = ref<string | null>(null);

// useFetchEndpoint instance for the shared /api/infrastructure/hosts GET
// Issue #1310: Single source — only user-configured hosts from secrets.
// Fleet/system VMs no longer included (they belong in SLM).
const _hostsEndpoint = useFetchEndpoint<HostsApiRaw, InfrastructureHost[]>({
  path: '/api/infrastructure/hosts',
  label: 'Infrastructure hosts',
  pickData: (raw) =>
    (raw.hosts ?? []).map((h) => ({
      id: h.id as string,
      name: h.name as string,
      host: h.host as string,
      ssh_port: (h.ssh_port as number) || 22,
      username: (h.username as string) || 'root',
      auth_type: (h.auth_type as 'ssh_key' | 'password') || 'password',
      capabilities: (h.capabilities as string[]) || ['ssh'],
      purpose: (h.purpose as string) || (h.description as string),
      os: h.os as string | undefined,
      metadata: h,
      _isLegacyHost: false,
    })),
  onSuccess: (data) => {
    hosts.value = data;
    logger.info('Loaded infrastructure hosts:', { count: data.length });
  },
  onError: (msg) => {
    logger.error('Failed to load infrastructure hosts:', msg);
    error.value = 'Failed to load infrastructure hosts';
  },
  fallbackData: [],
});

const loading = _hostsEndpoint.loading;

// Terminal-specific host list (HostConfig[] shape for useTerminalStore)
const terminalHosts = ref<HostConfig[]>([]);

const _terminalHostsEndpoint = useFetchEndpoint<HostsApiRaw, HostConfig[]>({
  path: '/api/infrastructure/hosts',
  label: 'Terminal infrastructure hosts',
  pickData: (raw) =>
    (raw.hosts ?? []).map((h) => ({
      id: h.id as string,
      name: h.name as string,
      ip: h.host as string,
      port: (h.ssh_port as number) || 22,
      description:
        (h.description as string) ||
        `${(h.os as string) || 'Host'} - ${((h.capabilities as string[])?.join(', ')) || 'SSH'}`,
    })),
  onSuccess: (data) => {
    terminalHosts.value = data;
    logger.info(`Loaded ${data.length} terminal infrastructure hosts`);
  },
  onError: (msg) => {
    logger.error('Failed to load terminal infrastructure hosts:', msg);
  },
  fallbackData: [],
});

const terminalHostsLoading = _terminalHostsEndpoint.loading;

// AbortControllers for in-flight loadHosts / loadTerminalHosts requests.
// Abort-prior is already handled inside useFetchEndpoint/useApiResource, but
// these module-scope refs let external callers (e.g. onUnmounted hooks) cancel
// a pending fetch when no component is left waiting for the result (#6136).
let _loadController: AbortController | null = null;
let _terminalLoadController: AbortController | null = null;

// Promise resolvers for async request handling
let resolveHostSelection: ((result: HostSelectionResult | null) => void) | null = null;

/**
 * Load infrastructure hosts from the secrets API (Issue #1310, #6089)
 */
const loadHosts = async (): Promise<InfrastructureHost[]> => {
  _loadController?.abort();
  _loadController = new AbortController();
  const signal = _loadController.signal;
  error.value = null;
  try {
    await _hostsEndpoint.load();
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') return hosts.value;
    throw err;
  }
  if (signal.aborted) return hosts.value;
  return hosts.value;
};

/**
 * Load infrastructure hosts mapped to HostConfig[] format for the terminal
 * HostSelector component (Issue #6089).
 */
const loadTerminalHosts = async (): Promise<HostConfig[]> => {
  _terminalLoadController?.abort();
  _terminalLoadController = new AbortController();
  const signal = _terminalLoadController.signal;
  try {
    await _terminalHostsEndpoint.load();
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') return terminalHosts.value;
    throw err;
  }
  if (signal.aborted) return terminalHosts.value;
  return terminalHosts.value;
};

/**
 * Initialize host selection state from localStorage/sessionStorage
 */
const initialize = () => {
  // Load default host from localStorage
  const savedDefault = localStorage.getItem('autobot_default_ssh_host');
  if (savedDefault) {
    defaultHostId.value = savedDefault;
  }

  // Load session host from sessionStorage
  const savedSession = sessionStorage.getItem('autobot_session_ssh_host');
  if (savedSession) {
    sessionHostId.value = savedSession;
  }
};

/**
 * Set the default host for SSH actions
 */
const setDefaultHost = (hostId: string) => {
  defaultHostId.value = hostId;
  localStorage.setItem('autobot_default_ssh_host', hostId);
  logger.info('Set default host:', { hostId });
};

/**
 * Clear the default host
 */
const clearDefaultHost = () => {
  defaultHostId.value = null;
  localStorage.removeItem('autobot_default_ssh_host');
};

/**
 * Set the session host (temporary, cleared on session end)
 */
const setSessionHost = (hostId: string) => {
  sessionHostId.value = hostId;
  sessionStorage.setItem('autobot_session_ssh_host', hostId);
  logger.info('Set session host:', { hostId });
};

/**
 * Clear the session host
 */
const clearSessionHost = () => {
  sessionHostId.value = null;
  sessionStorage.removeItem('autobot_session_ssh_host');
};

/**
 * Get the currently selected host (session > default > first available)
 */
const getCurrentHost = async (): Promise<InfrastructureHost | null> => {
  // Ensure hosts are loaded
  if (hosts.value.length === 0) {
    await loadHosts();
  }

  // Priority: session host > default host > first available
  const preferredId = sessionHostId.value || defaultHostId.value;

  if (preferredId) {
    const host = hosts.value.find(h => h.id === preferredId);
    if (host) {
      return host;
    }
  }

  // Fall back to first available host
  return hosts.value.length > 0 ? hosts.value[0] : null;
};

/**
 * Request host selection from the user via dialog
 * Returns a promise that resolves when user makes a selection or cancels
 */
const requestHostSelection = async (request: HostSelectionRequest): Promise<HostSelectionResult | null> => {
  logger.info('Host selection requested:', request);

  // Check if auto-select is allowed and we have a preferred host
  if (request.allowAutoSelect) {
    const currentHost = await getCurrentHost();
    if (currentHost) {
      logger.info('Auto-selecting host:', { hostId: currentHost.id, hostName: currentHost.name });
      return {
        host: currentHost,
        rememberChoice: false,
        requestId: request.requestId
      };
    }
  }

  // Show dialog and wait for user selection
  return new Promise((resolve) => {
    pendingRequest.value = request;
    resolveHostSelection = resolve;
    showDialog.value = true;
  });
};

/**
 * Handle host selection from dialog
 */
const handleHostSelected = (result: { host: InfrastructureHost; rememberChoice: boolean }) => {
  if (!pendingRequest.value) return;

  const selectionResult: HostSelectionResult = {
    host: result.host,
    rememberChoice: result.rememberChoice,
    requestId: pendingRequest.value.requestId
  };

  // Save session preference if requested
  if (result.rememberChoice) {
    setSessionHost(result.host.id);
  }

  // Update selected host
  selectedHost.value = result.host;

  // Resolve the pending promise
  if (resolveHostSelection) {
    resolveHostSelection(selectionResult);
    resolveHostSelection = null;
  }

  // Clear pending request
  pendingRequest.value = null;
  showDialog.value = false;

  logger.info('Host selected:', { hostId: result.host.id, hostName: result.host.name });
};

/**
 * Handle dialog cancellation
 */
const handleDialogCancelled = () => {
  // Resolve with null to indicate cancellation
  if (resolveHostSelection) {
    resolveHostSelection(null);
    resolveHostSelection = null;
  }

  pendingRequest.value = null;
  showDialog.value = false;

  logger.info('Host selection cancelled');
};

/**
 * Handle dialog close
 */
const handleDialogClose = () => {
  showDialog.value = false;
};

/**
 * Check if a specific host is available
 */
const isHostAvailable = async (hostId: string): Promise<boolean> => {
  if (hosts.value.length === 0) {
    await loadHosts();
  }
  return hosts.value.some(h => h.id === hostId);
};

/**
 * Get host by ID
 */
const getHostById = async (hostId: string): Promise<InfrastructureHost | null> => {
  if (hosts.value.length === 0) {
    await loadHosts();
  }
  return hosts.value.find(h => h.id === hostId) || null;
};

// Initialize on module load
initialize();

/**
 * Composable for host selection
 */
export function useHostSelection() {
  return {
    // State (readonly to prevent external mutations)
    showDialog: readonly(showDialog),
    pendingRequest: readonly(pendingRequest),
    selectedHost: readonly(selectedHost),
    defaultHostId: readonly(defaultHostId),
    sessionHostId: readonly(sessionHostId),
    hosts: readonly(hosts),
    loading: readonly(loading),
    error: readonly(error),

    // Computed
    hasDefaultHost: computed(() => !!defaultHostId.value),
    hasSessionHost: computed(() => !!sessionHostId.value),
    hostCount: computed(() => hosts.value.length),

    // Terminal variant
    terminalHosts: readonly(terminalHosts),
    terminalHostsLoading: readonly(terminalHostsLoading),
    loadTerminalHosts,

    // Methods
    loadHosts,
    setDefaultHost,
    clearDefaultHost,
    setSessionHost,
    clearSessionHost,
    getCurrentHost,
    requestHostSelection,
    handleHostSelected,
    handleDialogCancelled,
    handleDialogClose,
    isHostAvailable,
    getHostById,
    /** Cancel any in-flight loadHosts request (call from onUnmounted if needed). */
    abortLoadHosts: () => { _loadController?.abort(); _loadController = null; },
    /** Cancel any in-flight loadTerminalHosts request (call from onUnmounted if needed). */
    abortLoadTerminalHosts: () => { _terminalLoadController?.abort(); _terminalLoadController = null; },

    // For direct state access in dialog component
    _showDialog: showDialog,
    _pendingRequest: pendingRequest
  };
}

// Default export for convenience
export default useHostSelection;
