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

      <!-- Settings Sections -->
      <div class="settings-sections">
        <!-- Appearance Section -->
        <section class="settings-section">
          <div class="section-header">
            <h2 class="section-title">
              <i class="fas fa-paint-brush"></i>
              Appearance
            </h2>
            <p class="section-description">
              Customize the look and feel of your workspace
            </p>
          </div>

          <div class="section-content">
            <PreferencesPanel />
          </div>
        </section>

        <!-- Future sections can be added here -->
        <!-- Example: Notifications, Privacy, Account, etc. -->
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import PreferencesPanel from '@/components/ui/PreferencesPanel.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SettingsView')

logger.debug('Settings view initialized')
</script>

<style scoped>
/* ============================================
 * SETTINGS VIEW - Using Design Tokens
 * ============================================ */

.settings-content {
  width: 100%;
  max-width: var(--content-max-width);
  margin: 0 auto;
  padding: var(--content-padding-y) var(--content-padding-x);
}

/* ============================================
 * PAGE HEADER
 * ============================================ */

.page-header {
  margin-bottom: var(--spacing-2xl);
  padding-bottom: var(--spacing-xl);
  border-bottom: 2px solid var(--border-color);
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
  font-size: var(--font-size-3xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.page-title i {
  font-size: var(--font-size-2xl);
  color: var(--color-primary);
}

.page-description {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  margin: 0;
  line-height: var(--line-height-relaxed);
}

/* ============================================
 * SETTINGS SECTIONS
 * ============================================ */

.settings-sections {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2xl);
}

.settings-section {
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-color);
  overflow: hidden;
}

/* ============================================
 * SECTION HEADER
 * ============================================ */

.section-header {
  padding: var(--spacing-lg) var(--spacing-xl);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-color);
}

.section-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-xs) 0;
}

.section-title i {
  font-size: var(--font-size-lg);
  color: var(--color-primary);
}

.section-description {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0;
  line-height: var(--line-height-normal);
}

/* ============================================
 * SECTION CONTENT
 * ============================================ */

.section-content {
  padding: var(--spacing-xl);
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
    font-size: var(--font-size-2xl);
  }

  .page-title i {
    font-size: var(--font-size-xl);
  }

  .section-header {
    padding: var(--spacing-md);
  }

  .section-content {
    padding: var(--spacing-md);
  }
}
</style>
