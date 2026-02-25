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
            <i class="fas fa-cog"></i>
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
          <i class="fas fa-paint-brush"></i>
          Appearance
        </button>
        <button
          @click="activeTab = 'voice'"
          :class="['settings-tab', { active: activeTab === 'voice' }]"
        >
          <i class="fas fa-microphone"></i>
          Voice
        </button>
      </div>

      <!-- Tab Content -->
      <div class="settings-tab-content">
        <section v-if="activeTab === 'appearance'" class="settings-section">
          <div class="section-header">
            <h2 class="section-title">
              <i class="fas fa-paint-brush"></i>
              Appearance
            </h2>
            <p class="section-description">Customize the look and feel of your workspace</p>
          </div>
          <div class="section-content">
            <PreferencesPanel />
          </div>
        </section>

        <section v-if="activeTab === 'voice'" class="settings-section">
          <div class="section-header">
            <h2 class="section-title">
              <i class="fas fa-microphone"></i>
              Voice
            </h2>
            <p class="section-description">Configure text-to-speech voice and voice profiles</p>
          </div>
          <div class="section-content">
            <VoiceSettingsPanel />
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import PreferencesPanel from '@/components/ui/PreferencesPanel.vue'
import VoiceSettingsPanel from '@/components/settings/VoiceSettingsPanel.vue'
import { ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SettingsView')

logger.debug('Settings view initialized')

type PreferenceTab = 'appearance' | 'voice'
const activeTab = ref<PreferenceTab>('appearance')
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
  margin: 0;
}

.page-title i {
  font-size: var(--text-2xl);
  color: var(--color-primary);
}

.page-description {
  font-size: var(--text-base);
  color: var(--text-secondary);
  margin: 0;
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

.section-title i {
  font-size: var(--text-lg);
  color: var(--color-primary);
}

.section-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
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
  margin-bottom: -2px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
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

  .page-title i {
    font-size: var(--text-xl);
  }

  .section-header {
    padding: var(--spacing-md);
  }

  .section-content {
    padding: var(--spacing-md);
  }
}
</style>
