<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

SettingsView.vue - User Settings and Preferences Page
Issue #753: User preference management interface
-->

<template>
  <div class="settings-view view-container">
    <div class="settings-content">
      <!-- Page Header -->
      <div class="page-header">
        <div class="header-content">
          <h1 class="page-title">
            <Icon name="cog" />
            Settings
          </h1>
          <p class="page-description">
            Customize your AutoBot experience with personalized preferences
          </p>
        </div>
      </div>

      <!-- Tab Bar -->
      <div class="settings-tabs">
        <button
          @click="activeTab = 'appearance'"
          :class="['settings-tab', { active: activeTab === 'appearance' }]"
        >
          <Icon name="paint-brush" />
          Appearance
        </button>
        <button
          @click="activeTab = 'language'"
          :class="['settings-tab', { active: activeTab === 'language' }]"
        >
          <Icon name="globe" />
          {{ $t('settings.language') }}
        </button>
        <button
          @click="activeTab = 'voice'"
          :class="['settings-tab', { active: activeTab === 'voice' }]"
        >
          <Icon name="microphone" />
          Voice
        </button>
        <button
          @click="activeTab = 'webresearch'"
          :class="['settings-tab', { active: activeTab === 'webresearch' }]"
        >
          <Icon name="search" />
          {{ $t('settings.webResearch.title') }}
        </button>
        <button
          @click="activeTab = 'apikeys'"
          :class="['settings-tab', { active: activeTab === 'apikeys' }]"
        >
          <Icon name="key" />
          {{ $t('settings.apiKeys.stepKeys') }}
        </button>
        <button
          @click="activeTab = 'connection'"
          :class="['settings-tab', { active: activeTab === 'connection' }]"
        >
          <Icon name="plug" />
          {{ $t('settings.connection.title') }}
        </button>
        <button
          @click="activeTab = 'featureflags'"
          :class="['settings-tab', { active: activeTab === 'featureflags' }]"
        >
          <Icon name="shield-alt" />
          Feature Flags
        </button>
        <button
          @click="activeTab = 'presets'"
          :class="['settings-tab', { active: activeTab === 'presets' }]"
        >
          <Icon name="bookmark" />
          {{ $t('settings.presets.title') }}
        </button>
        <button
          @click="activeTab = 'telegram'"
          :class="['settings-tab', { active: activeTab === 'telegram' }]"
        >
          <Icon name="paper-plane" />
          Telegram
        </button>
        <button
          @click="activeTab = 'notifications'"
          :class="['settings-tab', { active: activeTab === 'notifications' }]"
        >
          <Icon name="bell" />
          Notifications
        </button>
        <button
          @click="activeTab = 'devices'"
          :class="['settings-tab', { active: activeTab === 'devices' }]"
        >
          <Icon name="mobile" />
          Mobile Devices
        </button>
        <button
          @click="activeTab = 'privacy'"
          :class="['settings-tab', { active: activeTab === 'privacy' }]"
        >
          <Icon name="shield-alt" />
          Privacy
        </button>
      </div>

      <!-- Tab Content -->
      <div class="settings-tab-content">
        <section v-if="activeTab === 'appearance'" class="settings-section">
          <div class="section-header">
            <h2 class="section-title">
              <Icon name="paint-brush" />
              Appearance
            </h2>
            <p class="section-description">{{ $t('settings.appearanceDesc') }}</p>
          </div>
          <div class="section-content">
            <ThemePresetPicker />
            <div style="margin-top: var(--spacing-xl);">
              <PreferencesPanel />
            </div>
          </div>
        </section>

        <section v-if="activeTab === 'language'" class="settings-section">
          <div class="section-header">
            <h2 class="section-title">
              <Icon name="globe" />
              {{ $t('settings.language') }}
            </h2>
            <p class="section-description">{{ $t('settings.languageDesc') }}</p>
          </div>
          <div class="section-content">
            <LanguageSettingsPanel />
          </div>
        </section>

        <section v-if="activeTab === 'voice'" class="settings-section">
          <div class="section-header">
            <h2 class="section-title">
              <Icon name="microphone" />
              Voice
            </h2>
            <p class="section-description">{{ $t('settings.voiceDesc') }}</p>
          </div>
          <div class="section-content">
            <VoiceSettingsPanel />
          </div>
        </section>

        <section v-if="activeTab === 'webresearch'" class="settings-section">
          <div class="section-header">
            <h2 class="section-title">
              <Icon name="search" />
              {{ $t('settings.webResearch.title') }}
            </h2>
            <p class="section-description">{{ $t('settings.webResearch.desc') }}</p>
          </div>
          <div class="section-content">
            <WebResearchSettingsPanel />
          </div>
        </section>

        <section v-if="activeTab === 'apikeys'" class="settings-section">
          <div class="section-header">
            <h2 class="section-title">
              <Icon name="key" />
              {{ $t('settings.apiKeys.stepKeys') }}
            </h2>
            <p class="section-description">{{ $t('settings.apiKeys.configureKeysDescription') }}</p>
          </div>
          <div class="section-content">
            <button class="open-wizard-btn" @click="showApiKeyWizard = true">
              <Icon name="magic" />
              {{ $t('settings.apiKeys.wizardTitle') }}
            </button>
          </div>
        </section>

        <section v-if="activeTab === 'connection'" class="settings-section">
          <div class="section-header">
            <h2 class="section-title">
              <Icon name="plug" />
              {{ $t('settings.connection.title') }}
            </h2>
            <p class="section-description">{{ $t('settings.connection.desc') }}</p>
          </div>
          <div class="section-content">
            <!-- Backend reachability check (#6964 wire-in for apiClient.validateConnection, resolves #6845) -->
            <div class="backend-check-panel">
              <div class="backend-check-header">
                <h3 class="backend-check-title">
                  {{ $t('settings.connection.backendCheck.title') }}
                </h3>
                <p class="backend-check-description">
                  {{ $t('settings.connection.backendCheck.description') }}
                </p>
              </div>
              <div class="backend-check-actions">
                <button
                  type="button"
                  class="backend-check-button"
                  :disabled="isChecking"
                  @click="testBackendConnection"
                  data-testid="test-backend-connection"
                >
                  <Icon :name="isChecking ? 'sync-alt' : 'plug'" :spin="isChecking" />
                  <span>
                    {{
                      isChecking
                        ? $t('settings.connection.backendCheck.checking')
                        : $t('settings.connection.backendCheck.button')
                    }}
                  </span>
                </button>
                <div
                  v-if="lastResult !== null"
                  :class="['backend-check-status', lastResult ? 'status-ok' : 'status-fail']"
                  role="status"
                  aria-live="polite"
                >
                  <Icon :name="lastResult ? 'check-circle' : 'times-circle'" />
                  <span class="status-label">
                    {{
                      lastResult
                        ? $t('settings.connection.backendCheck.reachable')
                        : $t('settings.connection.backendCheck.unreachable')
                    }}
                  </span>
                  <span v-if="lastLatencyMs !== null" class="status-latency">
                    · {{ $t('settings.connection.backendCheck.latency') }}: {{ lastLatencyMs }}ms
                  </span>
                </div>
                <p v-if="lastTestedAt" class="backend-check-meta">
                  {{ $t('settings.connection.backendCheck.lastTested') }}: {{ lastTestedAt }}
                </p>
              </div>
            </div>
            <ConnectionSettingsPanel />
          </div>
        </section>

        <section v-if="activeTab === 'featureflags'" class="settings-section">
          <div class="section-header">
            <h2 class="section-title">
              <Icon name="shield-alt" />
              Feature Flags
            </h2>
            <p class="section-description">Manage feature flags, enforcement modes, and access control</p>
          </div>
          <div class="section-content">
            <FeatureFlagsSettingsPanel />
          </div>
        </section>

        <!-- GH#4449: Slash command preset management in settings -->
        <section v-if="activeTab === 'presets'" class="settings-section">
          <div class="section-header">
            <h2 class="section-title">
              <Icon name="bookmark" />
              {{ $t('settings.presets.title') }}
            </h2>
            <p class="section-description">{{ $t('settings.presets.description') }}</p>
          </div>
          <div class="section-content">
            <PresetsSettingsPanel />
          </div>
        </section>

        <!-- MVA-2074: Telegram bot configuration -->
        <section v-if="activeTab === 'telegram'" class="settings-section">
          <div class="section-header">
            <h2 class="section-title">
              <Icon name="paper-plane" />
              Telegram Bot
            </h2>
            <p class="section-description">Configure the AutoBot Telegram bot to receive and respond to messages.</p>
          </div>
          <div class="section-content">
            <TelegramSettingsPanel />
          </div>
        </section>

        <!-- GH#4459: Web push notification toggle -->
        <section v-if="activeTab === 'notifications'" class="settings-section">
          <div class="section-header">
            <h2 class="section-title">
              <Icon name="bell" />
              Notifications
            </h2>
            <p class="section-description">Manage browser push notifications for this device.</p>
          </div>
          <div class="section-content">
            <PushNotificationSettingsPanel />
          </div>
        </section>

        <!-- MVA-3024: Mobile device management -->
        <section v-if="activeTab === 'devices'" class="settings-section">
          <div class="section-header">
            <h2 class="section-title">
              <Icon name="mobile" />
              Mobile Devices
            </h2>
            <p class="section-description">Manage your paired mobile devices for push notifications and offline sync.</p>
          </div>
          <div class="section-content">
            <DeviceManagementPanel />
          </div>
        </section>

        <!-- Issue #9035: Telemetry and analytics opt-out -->
        <section v-if="activeTab === 'privacy'" class="settings-section">
          <div class="section-header">
            <h2 class="section-title">
              <Icon name="shield-alt" />
              Privacy & Telemetry
            </h2>
            <p class="section-description">Control which usage metrics AutoBot records locally on your infrastructure. Nothing is ever transmitted.</p>
          </div>
          <div class="section-content">
            <TelemetrySettingsPanel />
          </div>
        </section>
      </div>

    <ApiKeySetupWizard v-model="showApiKeyWizard" @saved="onApiKeysSaved" />
    </div>
  </div>
</template>

<script setup lang="ts">
import PreferencesPanel from '@/components/ui/PreferencesPanel.vue'
import ThemePresetPicker from '@/components/settings/ThemePresetPicker.vue'
import LanguageSettingsPanel from '@/components/settings/LanguageSettingsPanel.vue'
import VoiceSettingsPanel from '@/components/settings/VoiceSettingsPanel.vue'
import WebResearchSettingsPanel from '@/components/settings/WebResearchSettingsPanel.vue'
import TelegramSettingsPanel from '@/components/settings/TelegramSettingsPanel.vue'
import ApiKeySetupWizard from '@/components/settings/ApiKeySetupWizard.vue'
import ConnectionSettingsPanel from '@/components/desktop/ConnectionSettingsPanel.vue'
import FeatureFlagsSettingsPanel from '@/components/settings/FeatureFlagsSettingsPanel.vue'
import PresetsSettingsPanel from '@/components/settings/PresetsSettingsPanel.vue'
import PushNotificationSettingsPanel from '@/components/settings/PushNotificationSettingsPanel.vue'
import DeviceManagementPanel from '@/components/profile/DeviceManagementPanel.vue'
import TelemetrySettingsPanel from '@/components/settings/TelemetrySettingsPanel.vue'
import Icon from '@/components/ui/Icon.vue'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import { useNotificationBus } from '@/composables/useNotificationBus'
import apiClient from '@/utils/ApiClient'

const logger = createLogger('SettingsView')
const { t } = useI18n()
const { showToast } = useNotificationBus()

logger.debug('Settings view initialized')

type PreferenceTab = 'appearance' | 'language' | 'voice' | 'webresearch' | 'apikeys' | 'connection' | 'featureflags' | 'presets' | 'telegram' | 'notifications' | 'devices' | 'privacy'
const activeTab = ref<PreferenceTab>('appearance')
const showApiKeyWizard = ref(false)

// Backend reachability check (#6964 wire-in for apiClient.validateConnection, resolves #6845)
const isChecking = ref(false)
const lastResult = ref<boolean | null>(null)
const lastLatencyMs = ref<number | null>(null)
const lastTestedAt = ref<string | null>(null)

async function testBackendConnection(): Promise<void> {
  if (isChecking.value) return
  isChecking.value = true
  const t0 = performance.now()
  try {
    const reachable = await apiClient.validateConnection()
    lastLatencyMs.value = Math.round(performance.now() - t0)
    lastResult.value = reachable
    lastTestedAt.value = new Date().toLocaleTimeString()
    showToast(
      reachable
        ? `${t('settings.connection.backendCheck.reachable')} (${lastLatencyMs.value}ms)`
        : t('settings.connection.backendCheck.unreachable'),
      reachable ? 'success' : 'error'
    )
    logger.info('Backend reachability test', { reachable, latencyMs: lastLatencyMs.value })
  } catch (error) {
    lastLatencyMs.value = Math.round(performance.now() - t0)
    lastResult.value = false
    lastTestedAt.value = new Date().toLocaleTimeString()
    showToast(t('settings.connection.backendCheck.unreachable'), 'error')
    logger.error('Backend reachability test failed', error)
  } finally {
    isChecking.value = false
  }
}

function onApiKeysSaved(): void {
  logger.info('API keys saved successfully')
}
</script>

<style scoped>
/* ============================================
 * SETTINGS VIEW - Using Design Tokens
 * ============================================ */

.settings-content {
  width: 100%;
  max-width: var(--content-max-width);
  margin: 0 auto;
  padding: var(--spacing-6) var(--spacing-5);
}

/* ============================================
 * PAGE HEADER
 * ============================================ */

.page-header {
  margin-bottom: var(--spacing-2xl);
  padding-bottom: var(--spacing-xl);
  border-bottom: 2px solid var(--border-default);
}

.header-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.page-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  font-size: var(--text-3xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.page-title svg {
  width: var(--text-2xl);
  height: var(--text-2xl);
  color: var(--color-primary);
}

.page-description {
  font-size: var(--text-base);
  color: var(--text-secondary);
  margin: var(--spacing-0);
  line-height: var(--leading-relaxed);
}

/* ============================================
 * SETTINGS SECTIONS
 * ============================================ */

.settings-section {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
  overflow: hidden;
}

/* ============================================
 * SECTION HEADER
 * ============================================ */

.section-header {
  padding: var(--spacing-lg) var(--spacing-xl);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.section-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-xs) 0;
}

.section-title svg {
  width: var(--text-lg);
  height: var(--text-lg);
  color: var(--color-primary);
}

.section-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-0);
  line-height: var(--leading-normal);
}

/* ============================================
 * SECTION CONTENT
 * ============================================ */

.section-content {
  padding: var(--spacing-xl);
}

/* ============================================
 * TAB NAVIGATION
 * ============================================ */

.settings-tabs {
  display: flex;
  gap: var(--spacing-2);
  border-bottom: 2px solid var(--border-default);
  margin-bottom: var(--spacing-xl);
}

.settings-tab {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: var(--spacing-neg-2px);
  cursor: pointer;
  transition: color var(--duration-150), border-color var(--duration-150);
}

.settings-tab:hover {
  color: var(--text-primary);
}

.settings-tab.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

.settings-tab-content {
  min-height: 300px;
}

/* ============================================
 * RESPONSIVE
 * ============================================ */

@media (max-width: 768px) {
  .settings-content {
    padding: var(--spacing-md);
  }

  .page-header {
    margin-bottom: var(--spacing-xl);
    padding-bottom: var(--spacing-lg);
  }

  .page-title {
    font-size: var(--text-2xl);
  }

  .page-title svg {
    width: var(--text-xl);
    height: var(--text-xl);
  }

  .section-header {
    padding: var(--spacing-md);
  }

  .section-content {
    padding: var(--spacing-md);
  }

  /* Prevent tab bar overflow on narrow screens */
  .settings-tabs {
    overflow-x: auto;
    flex-wrap: nowrap;
    -webkit-overflow-scrolling: touch;
    gap: var(--spacing-0);
  }

  .settings-tab {
    white-space: nowrap;
    flex-shrink: 0;
    /* Ensure min 44px touch target height */
    min-height: 44px;
    padding: var(--spacing-2) var(--spacing-3);
  }
}
.open-wizard-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md, 8px);
  font-weight: 500;
  cursor: pointer;
  transition: opacity var(--duration-200);
}

.open-wizard-btn:hover {
  opacity: 0.9;
}

/* ============================================
 * BACKEND REACHABILITY CHECK (#6964)
 * ============================================ */

.backend-check-panel {
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
  background: var(--surface-secondary, var(--bg-secondary));
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md, 8px);
}

.backend-check-header {
  margin-bottom: var(--spacing-md);
}

.backend-check-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-xs) 0;
}

.backend-check-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
}

.backend-check-actions {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.backend-check-button {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm);
  align-self: flex-start;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md, 8px);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: opacity var(--duration-150);
}

.backend-check-button:hover:not(:disabled) {
  opacity: 0.9;
}

.backend-check-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.backend-check-status {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm, 4px);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  align-self: flex-start;
}

.backend-check-status.status-ok {
  color: var(--color-success, #16a34a);
  background: var(--color-success-bg, rgba(22, 163, 74, 0.1));
}

.backend-check-status.status-fail {
  color: var(--color-error, #dc2626);
  background: var(--color-danger-bg, rgba(220, 38, 38, 0.1));
}

.status-latency {
  font-weight: var(--font-normal);
  opacity: 0.85;
}

.backend-check-meta {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin: 0;
}
</style>
