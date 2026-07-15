<template>
  <div class="provider-oauth-connect">
    <div class="auth-mode-toggle">
      <button
        :class="['auth-tab', { active: authMode === 'apikey' }]"
        @click="authMode = 'apikey'"
      >
        API Key
      </button>
      <button
        :class="['auth-tab', { active: authMode === 'oauth' }]"
        @click="authMode = 'oauth'"
      >
        Sign in with {{ providerLabel }}
      </button>
    </div>

    <!-- API key panel -->
    <div v-if="authMode === 'apikey'" class="auth-panel">
      <slot name="apikey" />
    </div>

    <!-- OAuth / device-code panel -->
    <div v-else class="auth-panel oauth-panel">
      <!-- Connection status -->
      <div v-if="status !== null" class="connection-status">
        <span :class="['status-dot', status.connected ? 'connected' : 'disconnected']" />
        <span v-if="status.connected" class="status-text connected-text">
          Connected
          <span v-if="status.expires_at" class="expiry-note">
            &mdash; expires {{ formatExpiry(status.expires_at) }}
          </span>
        </span>
        <span v-else class="status-text">Not connected</span>
        <button v-if="status.connected" class="btn-danger-sm" @click="revoke">Disconnect</button>
      </div>

      <!-- ToS / capability notice -->
      <p v-if="tosNote" class="tos-notice">{{ tosNote }}</p>

      <!-- Device-code flow (headless / CLI) -->
      <div v-if="deviceAuth && !status?.connected" class="device-flow">
        <button class="btn-secondary" :disabled="busy" @click="startDeviceFlow">
          <span v-if="busy && deviceStep === 'initiating'">Connecting...</span>
          <span v-else>Connect via device code</span>
        </button>
        <div v-if="deviceInstruction" class="device-instruction">
          <p>
            Visit <a :href="deviceInstruction.verification_uri" target="_blank" rel="noopener noreferrer">
              {{ deviceInstruction.verification_uri }}
            </a> and enter code:
          </p>
          <code class="device-code">{{ deviceInstruction.user_code }}</code>
          <button class="btn-primary btn-sm" :disabled="busy" @click="pollDeviceFlow">
            {{ busy ? 'Checking...' : 'I approved it' }}
          </button>
        </div>
      </div>

      <!-- Standard OAuth redirect (non-headless) -->
      <div v-else-if="!deviceAuth && !status?.connected" class="oauth-flow">
        <p class="oauth-description">
          Authenticate with your existing {{ providerLabel }} subscription.
          No API key required.
        </p>
        <button class="btn-primary" :disabled="busy" @click="initiateOAuth">
          {{ busy ? 'Redirecting...' : `Sign in with ${providerLabel}` }}
        </button>
      </div>

      <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import ApiClient from '@/utils/ApiClient'

interface DeviceInstruction {
  device_code: string
  user_code: string
  verification_uri: string
  expires_in: number
  interval: number
}

interface AuthStatus {
  provider_name: string
  connected: boolean
  expires_at?: number | null
  auth_kind?: string | null
}

const props = withDefaults(defineProps<{
  providerName: string
  providerLabel: string
  tosNote?: string
  /** Use device-code flow instead of browser redirect */
  deviceAuth?: boolean
  deviceAuthorizationUrl?: string
  tokenUrl?: string
  clientId?: string
  scope?: string
}>(), {
  tosNote: '',
  deviceAuth: false,
  deviceAuthorizationUrl: '',
  tokenUrl: '',
  clientId: '',
  scope: 'openid',
})

const authMode = ref<'apikey' | 'oauth'>('apikey')
const status = ref<AuthStatus | null>(null)
const busy = ref(false)
const errorMsg = ref('')
const deviceInstruction = ref<DeviceInstruction | null>(null)
const deviceStep = ref<'idle' | 'initiating' | 'polling'>('idle')

onMounted(loadStatus)

async function loadStatus(): Promise<void> {
  try {
    status.value = await ApiClient.get(`/api/llm-auth/status/${props.providerName}`)
    if (status.value?.connected) authMode.value = 'oauth'
  } catch {
    status.value = null
  }
}

async function revoke(): Promise<void> {
  busy.value = true
  errorMsg.value = ''
  try {
    await ApiClient.delete(`/api/llm-auth/${props.providerName}`)
    await loadStatus()
    authMode.value = 'apikey'
  } catch (err: unknown) {
    errorMsg.value = (err as Error).message ?? 'Disconnect failed'
  } finally {
    busy.value = false
  }
}

async function initiateOAuth(): Promise<void> {
  busy.value = true
  errorMsg.value = ''
  try {
    // The backend manages the PKCE verifier + state via the code-exchange endpoint.
    // For browser-redirect flows the SPA opens the authorize URL directly.
    // This stub redirects to a provider-specific authorize URL when configured.
    errorMsg.value = 'OAuth browser-redirect flow requires server-side callback configuration. Use device-code for headless environments.'
  } finally {
    busy.value = false
  }
}

async function startDeviceFlow(): Promise<void> {
  if (!props.deviceAuthorizationUrl || !props.clientId) {
    errorMsg.value = 'Device auth is not configured for this provider'
    return
  }
  busy.value = true
  deviceStep.value = 'initiating'
  errorMsg.value = ''
  try {
    const resp = await ApiClient.post('/api/llm-auth/device/initiate', {
      provider_name: props.providerName,
      device_authorization_url: props.deviceAuthorizationUrl,
      client_id: props.clientId,
      scope: props.scope,
    })
    deviceInstruction.value = resp as DeviceInstruction
  } catch (err: unknown) {
    errorMsg.value = (err as Error).message ?? 'Device flow initiation failed'
  } finally {
    busy.value = false
    deviceStep.value = 'idle'
  }
}

async function pollDeviceFlow(): Promise<void> {
  if (!deviceInstruction.value || !props.tokenUrl) return
  busy.value = true
  deviceStep.value = 'polling'
  errorMsg.value = ''
  try {
    const resp = await ApiClient.post('/api/llm-auth/device/poll', {
      provider_name: props.providerName,
      token_url: props.tokenUrl,
      client_id: props.clientId,
      device_code: deviceInstruction.value.device_code,
    })
    if ((resp as { stored: boolean }).stored) {
      deviceInstruction.value = null
      await loadStatus()
    } else {
      errorMsg.value = 'Still waiting for approval — try again in a moment.'
    }
  } catch (err: unknown) {
    errorMsg.value = (err as Error).message ?? 'Poll failed'
  } finally {
    busy.value = false
    deviceStep.value = 'idle'
  }
}

function formatExpiry(ts: number): string {
  return new Date(ts * 1000).toLocaleString()
}
</script>

<style scoped>
.provider-oauth-connect { display: flex; flex-direction: column; gap: 0.75rem; }

.auth-mode-toggle { display: flex; gap: 0.25rem; border-bottom: 1px solid var(--autobot-border); }
.auth-tab {
  padding: 0.4rem 0.85rem;
  font-size: 0.8rem;
  border: none;
  background: transparent;
  color: var(--autobot-text-muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
}
.auth-tab.active { color: var(--autobot-accent); border-bottom-color: var(--autobot-accent); }

.auth-panel { padding: 0.75rem 0; }

.connection-status { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot.connected { background: #22c55e; }
.status-dot.disconnected { background: #ef4444; }
.status-text { font-size: 0.85rem; color: var(--autobot-text-secondary); }
.connected-text { color: #22c55e; }
.expiry-note { font-size: 0.75rem; color: var(--autobot-text-muted); }

.tos-notice { font-size: 0.75rem; color: var(--autobot-text-muted); margin-bottom: 0.5rem; }

.oauth-description { font-size: 0.85rem; color: var(--autobot-text-secondary); margin-bottom: 0.5rem; }

.device-flow, .oauth-flow { display: flex; flex-direction: column; gap: 0.5rem; }
.device-instruction { padding: 0.75rem; background: var(--autobot-bg-surface); border-radius: 6px; display: flex; flex-direction: column; gap: 0.5rem; font-size: 0.85rem; }
.device-code { font-size: 1.4rem; font-weight: 700; letter-spacing: 0.15em; text-align: center; padding: 0.25rem; }

.btn-danger-sm { font-size: 0.75rem; padding: 0.2rem 0.5rem; border-radius: 4px; border: 1px solid #ef4444; color: #ef4444; background: transparent; cursor: pointer; }
.btn-danger-sm:hover { background: #fee2e2; }
.btn-sm { font-size: 0.8rem; padding: 0.3rem 0.75rem; }

.error-msg { color: #ef4444; font-size: 0.8rem; }
</style>
