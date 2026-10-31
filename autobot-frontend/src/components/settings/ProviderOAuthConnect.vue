<template>
  <div class="provider-oauth-connect">
    <div v-if="$slots.apikey" class="auth-mode-toggle">
      <button
        :class="['auth-tab', { active: authMode === 'apikey' }]"
        @click="authMode = 'apikey'"
      >
        {{ t('settings.providerAuth.apiKeyTab') }}
      </button>
      <button
        :class="['auth-tab', { active: authMode === 'oauth' }]"
        @click="authMode = 'oauth'"
      >
        {{ t('settings.providerAuth.signInWith', { provider: providerLabel }) }}
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
          {{ t('settings.providerAuth.connected') }}
          <span v-if="status.expires_at" class="expiry-note">
            {{ t('settings.providerAuth.expiresAt', { date: formatExpiry(status.expires_at) }) }}
          </span>
        </span>
        <span v-else-if="status.needs_reauth" class="text-sm text-autobot-warning" data-testid="needs-reauth">
          {{ t('settings.providerAuth.needsReauth', { provider: providerLabel }) }}
        </span>
        <span v-else class="status-text">{{ t('settings.providerAuth.notConnected') }}</span>
        <template v-if="status.shared && (status.connected || status.needs_reauth)">
          <!-- #19241: an org-less admin's system connection IS the token every org shares. -->
          <BaseButton variant="error" size="xs"
            v-if="canRevokeShared"
            data-testid="shared-revoke-inline"
            :disabled="shared.busy.value"
            @click="revokeSharedHere"
          >
            {{ t('settings.providerAuth.shared.revokeButton', { provider: providerLabel }) }}
          </BaseButton>
          <span v-else class="status-text" data-testid="shared-superadmin-only">
            {{ t('settings.providerAuth.shared.superadminOnly', { provider: providerLabel }) }}
          </span>
        </template>
        <BaseButton variant="error" size="xs" v-else-if="status.connected || status.needs_reauth" @click="revoke">{{ t('settings.providerAuth.disconnect') }}</BaseButton>
      </div>
      <p v-if="revokeWarning" class="error-msg" data-testid="revoke-warning">{{ revokeWarning }}</p>
      <p v-if="shared.message.value" class="status-text" role="status">{{ shared.message.value }}</p>

      <!-- ToS / capability notice -->
      <p v-if="tosText" class="tos-notice">{{ tosText }}</p>

      <!-- Operator has not configured this provider: guidance only -->
      <div v-if="!configured" class="text-sm text-autobot-text-secondary" data-testid="provider-not-configured">
        <p>{{ t('settings.providerAuth.notConfigured', { provider: providerLabel }) }}</p>
        <ul v-if="missingSettings.length" class="ml-4 mt-1 text-xs">
          <li v-for="name in missingSettings" :key="name"><code>{{ name }}</code></li>
        </ul>
      </div>

      <template v-else>

      <!-- Device-code flow (headless / CLI) -->
      <div v-if="useDevice && !status?.connected" class="device-flow">
        <BaseButton variant="secondary" size="sm" :disabled="busy" @click="startDeviceFlow">
          <span v-if="busy && deviceStep === 'initiating'">{{ t('settings.providerAuth.connecting') }}</span>
          <span v-else>{{ t('settings.providerAuth.connectDeviceCode') }}</span>
        </BaseButton>
        <div v-if="deviceInstruction" class="device-instruction">
          <i18n-t keypath="settings.providerAuth.deviceInstruction" tag="p">
            <template #url>
              <a :href="deviceInstruction.verification_uri" target="_blank" rel="noopener noreferrer">
                {{ deviceInstruction.verification_uri }}
              </a>
            </template>
          </i18n-t>
          <code class="device-code">{{ deviceInstruction.user_code }}</code>
          <BaseButton size="sm" :disabled="busy" @click="pollDeviceFlow">
            {{ busy ? t('settings.providerAuth.checking') : t('settings.providerAuth.approvedButton') }}
          </BaseButton>
        </div>
      </div>

      <!-- Standard OAuth redirect (non-headless) -->
      <div v-else-if="!useDevice && !status?.connected" class="oauth-flow">
        <p class="oauth-description">
          {{ t('settings.providerAuth.oauthDescription', { provider: providerLabel }) }}
          {{ t('settings.providerAuth.noApiKeyRequired') }}
        </p>
        <BaseButton size="sm" data-testid="provider-signin" :disabled="busy" @click="initiateOAuth">
          {{ busy ? t('settings.providerAuth.redirecting') : t('settings.providerAuth.signInWith', { provider: providerLabel }) }}
        </BaseButton>
      </div>
      </template>

      <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { BaseButton } from '@autobot/ui'
import { ref, computed, onMounted, useSlots } from 'vue'
import { useI18n } from 'vue-i18n'
import ApiClient from '@/utils/ApiClient'
import type { components } from '@/types/generated/api'
import { useSharedTokenRevoke } from '@/composables/useSharedTokenRevoke'
import {
  buildProviderRedirectUri,
  type ProviderAuthFlow,
  type ProviderAuthScope,
} from '@/utils/providerOAuth'

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
  scope?: ProviderAuthScope
  needs_reauth?: boolean
  shared?: boolean
}

type RevokeResult = components['schemas']['ProviderRevokeResult']

// #19241: provider endpoints, client ids and flow availability are server-side;
// the SPA only receives which flows work and which operator settings are missing.
const props = withDefaults(defineProps<{
  providerName: string
  providerLabel: string
  scope: ProviderAuthScope
  flows?: ProviderAuthFlow[]
  configured?: boolean
  missingSettings?: string[]
  /** Superadmin: may revoke the shared token from an org-less System row (#19241). */
  canRevokeShared?: boolean
}>(), {
  flows: () => [],
  configured: true,
  missingSettings: () => [],
  canRevokeShared: false,
})

const slots = useSlots()
// Sections without an API-key slot (per-user accounts) show only sign-in.
const authMode = ref<'apikey' | 'oauth'>(slots.apikey ? 'apikey' : 'oauth')
const status = ref<AuthStatus | null>(null)
const busy = ref(false)
const errorMsg = ref('')
const revokeWarning = ref('')
const shared = useSharedTokenRevoke()

async function revokeSharedHere(): Promise<void> {
  if (await shared.revokeShared({ name: props.providerName, label: props.providerLabel })) await loadStatus()
}
const deviceInstruction = ref<DeviceInstruction | null>(null)
const deviceStep = ref<'idle' | 'initiating' | 'polling'>('idle')

// #15031: every user-facing string, the error messages included, goes through
// i18n; `locale` also formats the token expiry in the reader's language.
const { t, te, locale } = useI18n()

// Redirect is preferred; device code is used only when it is the sole flow.
const useDevice = computed(() => !props.flows.includes('redirect') && props.flows.includes('device'))
const tosKey = computed(() => `settings.providerAuth.tos.${props.providerName}`)
const tosText = computed(() => (te(tosKey.value) ? t(tosKey.value) : ''))

onMounted(loadStatus)

function errText(err: unknown, fallbackKey: string): string {
  return (err as Error)?.message || t(fallbackKey)
}

async function loadStatus(): Promise<void> {
  try {
    status.value = await ApiClient.get(
      `/api/llm-auth/status/${props.providerName}?scope=${props.scope}`,
    )
    if (status.value?.connected) authMode.value = 'oauth'
  } catch {
    status.value = null
  }
}

async function revoke(): Promise<void> {
  busy.value = true
  errorMsg.value = ''
  revokeWarning.value = ''
  try {
    const result: RevokeResult = await ApiClient.delete(`/api/llm-auth/${props.providerName}?scope=${props.scope}`)
    // #19241: the local delete always happens; a provider-side revoke failure is surfaced, not hidden.
    revokeWarning.value = result?.provider_revoked === false
      ? t('settings.providerAuth.providerRevokeFailed', { reason: result.provider_error ?? '' })
      : ''
    await loadStatus()
    if (slots.apikey) authMode.value = 'apikey'
  } catch (err: unknown) {
    errorMsg.value = errText(err, 'settings.providerAuth.disconnectFailed')
  } finally {
    busy.value = false
  }
}

async function initiateOAuth(): Promise<void> {
  busy.value = true
  errorMsg.value = ''
  try {
    const resp: components['schemas']['OAuthAuthorizeResponse'] = await ApiClient.post(
      '/api/llm-auth/oauth/initiate',
      {
        provider_name: props.providerName,
        redirect_uri: buildProviderRedirectUri(),
        scope: props.scope,
      },
    )
    window.location.assign(resp.authorize_url)
  } catch (err: unknown) {
    errorMsg.value = errText(err, 'settings.providerAuth.initiateFailed')
    busy.value = false
  }
}

async function startDeviceFlow(): Promise<void> {
  busy.value = true
  deviceStep.value = 'initiating'
  errorMsg.value = ''
  try {
    const resp = await ApiClient.post('/api/llm-auth/device/initiate', {
      provider_name: props.providerName,
      scope: props.scope,
    })
    deviceInstruction.value = resp as DeviceInstruction
  } catch (err: unknown) {
    errorMsg.value = errText(err, 'settings.providerAuth.deviceInitFailed')
  } finally {
    busy.value = false
    deviceStep.value = 'idle'
  }
}

async function pollDeviceFlow(): Promise<void> {
  if (!deviceInstruction.value) return
  busy.value = true
  deviceStep.value = 'polling'
  errorMsg.value = ''
  try {
    const resp = await ApiClient.post('/api/llm-auth/device/poll', {
      provider_name: props.providerName,
      device_code: deviceInstruction.value.device_code,
    })
    if ((resp as { stored: boolean }).stored) {
      deviceInstruction.value = null
      await loadStatus()
    } else {
      errorMsg.value = t('settings.providerAuth.stillWaiting')
    }
  } catch (err: unknown) {
    errorMsg.value = errText(err, 'settings.providerAuth.pollFailed')
  } finally {
    busy.value = false
    deviceStep.value = 'idle'
  }
}

function formatExpiry(ts: number): string {
  return new Date(ts * 1000).toLocaleString(locale.value)
}
</script>

<style scoped>
.provider-oauth-connect { display: flex; flex-direction: column; gap: 0.75rem; }

.auth-mode-toggle { display: flex; gap: 0.25rem; border-bottom: 1px solid var(--border-default); }
.auth-tab {
  padding: 0.4rem 0.85rem;
  font-size: 0.8rem;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
}
.auth-tab.active { color: var(--color-primary); border-bottom-color: var(--color-primary); }

.auth-panel { padding: 0.75rem 0; }

.connection-status { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot.connected { background: var(--color-success); }
.status-dot.disconnected { background: var(--color-error); }
.status-text { font-size: 0.85rem; color: var(--text-secondary); }
.connected-text { color: var(--color-success); }
.expiry-note { font-size: 0.75rem; color: var(--text-muted); }

.tos-notice { font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.5rem; }

.oauth-description { font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.5rem; }

.device-flow, .oauth-flow { display: flex; flex-direction: column; gap: 0.5rem; }
.device-instruction { padding: 0.75rem; background: var(--bg-surface); border-radius: 6px; display: flex; flex-direction: column; gap: 0.5rem; font-size: 0.85rem; }
.device-code { font-size: 1.4rem; font-weight: 700; letter-spacing: 0.15em; text-align: center; padding: 0.25rem; }

.error-msg { color: var(--color-error); font-size: 0.8rem; }
</style>
