<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  Admin permission-scopes panel (#16825) -- fine-grained permission scopes
  (a permission vocabulary, scope bundles, API-key scope enforcement) have
  no backend or frontend today, unlike the other two features #16825 named
  (MCP server admin, live pricing), which already ship real pages. This is
  deliberately NOT a working page: no form, no table, no API call -- an
  EmptyState naming what is coming, with no fabricated version number
  (#16803's v0.9.0 scope is still an open decision at the time this was
  written; a promised version that slips is worse than none).
-->
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import EmptyState from '@/components/ui/EmptyState.vue'

const { t } = useI18n()
</script>

<template>
  <div class="admin-permission-scopes view-container">
    <div class="page-header">
      <div class="page-header-content">
        <h1 class="page-title">{{ t('admin.permissionScopes.title') }}</h1>
        <p class="page-subtitle">{{ t('admin.permissionScopes.subtitle') }}</p>
      </div>
    </div>

    <EmptyState
      icon="shield-check"
      :title="t('admin.permissionScopes.comingSoonTitle')"
      :message="t('admin.permissionScopes.comingSoonMessage')"
    />
  </div>
</template>
