<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  AdminLayout (#19833, epic #19829): the shell of the one permission-gated /admin
  section (ADR-011). It owns the section header and renders the active admin page
  through a nested <router-view>; access is decided by the router guard, never here.
-->
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { PageHeader } from '@autobot/ui'

const { t } = useI18n()
</script>

<template>
  <section class="admin-layout h-full overflow-auto" :aria-label="t('admin.layout.ariaLabel')">
    <PageHeader
      class="admin-layout__header"
      :title="t('admin.layout.title')"
      :subtitle="t('admin.layout.subtitle')"
    />
    <router-view />
  </section>
</template>
