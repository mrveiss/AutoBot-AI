/**
 * useHostSelection - Composable for managing host selection for agent SSH actions
 *
 * Provides:
 * - Host selection dialog state management
 * - Default host configuration
 * - Session-level host persistence
 * - API for agents to request host selection
 */

import { ref, computed, readonly } from 'vue';
import { secretsApiClient } from '@/utils/SecretsApiClient';
import { getBackendUrl } from '@/config/ssot-config';
import { createLogger } from '@/utils/debugUtils';

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
  metadata?: Record<string, any>;
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

// Singleton state (shared across all component instances)
const showDialog = ref(false);
const pendingRequest = ref<HostSelectionRequest | null>(null);
const selectedHost = ref<InfrastructureHost | null>(null);
const defaultHostId = ref<string | null>(null);
const sessionHostId = ref<string | null>(null);
const hosts = ref<InfrastructureHost[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

// Promise resolvers for async request handling
let resolveHostSelection: ((result: HostSelectionResult | null) => void) | null = null;

/**
 * Load infrastructure hosts from the secrets API
 */
const loadHosts = async (): Promise<InfrastructureHost[]> => {
  loading.value = true;
  error.value = null;

  try {
    const backendUrl = getBackendUrl();

    // Fetch both secrets (infrastructure_host type) and legacy hosts
    const [secretsResponse, legacyHostsResponse] = await Promise.all([
      secretsApiClient.getSecrets({}),
      fetch(`${backendUrl}/api/infrastructure/hosts`)
        .then(r => r.ok ? r.json() : { hosts: [] })
        .catch(() => ({ hosts: [] }))
    ]);

    // Filter to infrastructure_host type secrets
    const infraSecrets = (secretsResponse.secrets || [])
      .filter((s: any) => s.type === 'infrastructure_host')
      .map((s: any) => ({
        id: s.id,
        name: s.name,
        host: s.metadata?.host || '',
        ssh_port: s.metadata?.ssh_port || 22,
        username: s.metadata?.username || 'root',
        auth_type: s.metadata?.auth_type || 'password',
        capabilities: s.metadata?.capabilities || ['ssh'],
        purpose: s.metadata?.purpose || s.description,
        os: s.metadata?.os,
        metadata: s.metadata,
        _isLegacyHost: false
      }));

    // Convert legacy hosts
    const legacyHosts = (legacyHostsResponse.hosts || []).map((h: any) => ({
      id: h.id,
      name: h.name,
      host: h.host,
      ssh_port: h.ssh_port || 22,
      username: h.username || 'root',
      auth_type: h.auth_type || 'password',
      capabilities: h.capabilities || ['ssh'],
      purpose: h.purpose || h.description,
      os: h.os,
      metadata: h,
      _isLegacyHost: true
    }));

    // Combine and deduplicate by host+port
    const hostMap = new Map<string, InfrastructureHost>();
    [...infraSecrets, ...legacyHosts].forEach(h => {
      const key = `${h.host}:${h.ssh_port}`;
      if (!hostMap.has(key)) {
        hostMap.set(key, h);
      }
    });

    hosts.value = Array.from(hostMap.values());
    logger.info('Loaded infrastructure hosts:', { count: hosts.value.length });

    return hosts.value;
  } catch (err) {
    logger.error('Failed to load hosts:', err);
    error.value = 'Failed to load infrastructure hosts';
    return [];
  } finally {
    loading.value = false;
  }
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

    // For direct state access in dialog component
    _showDialog: showDialog,
    _pendingRequest: pendingRequest
  };
}

// Default export for convenience
export default useHostSelection;
