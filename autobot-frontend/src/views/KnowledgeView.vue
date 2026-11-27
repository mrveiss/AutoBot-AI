<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeView — the Knowledge section shell (#18244, Refined UI): the kit SectionShell
  (SectionNav sub-sidebar and mobile drawer, #22019): the mockup order, advanced entries hidden in Minimal mode, the
  "advanced area" notice on advanced pages, and the routed screen beside it.
-->
<template>
  <SectionShell
    v-model:open="showMobileSidebar"
    class="knowledge-view"
    :nav-label="$t('knowledge.views.navAriaLabel')"
    :title="$t('knowledge.views.title')"
    :sections="sections"
    :link-as="RouterLink"
    :open-label="$t('knowledge.views.openSidebar')"
    :close-label="$t('knowledge.views.closeSidebar')"
  >
    <template #toggle-icon="{ open }"><Icon :name="open ? 'times' : 'bars'" aria-hidden="true" /></template>
    <template #icon="{ item }"><Icon :name="iconOf(item.id)" aria-hidden="true" /></template>
    <AdvancedAreaNotice v-if="onAdvancedArea" />
    <router-view />
  </SectionShell>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { SectionShell } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import type { IconName } from '@/components/ui/Icon.vue'
import AdvancedAreaNotice from '@/components/layout/AdvancedAreaNotice.vue'
import { useUserStore } from '@/stores/useUserStore'
import { useKnowledgeSectionNav, KNOWLEDGE_NAV_ICONS } from '@/composables/knowledge/useKnowledgeSectionNav'

const STORAGE_KEY = 'knowledge-sidebar-mobile-open'

// #16666: the vector-store explorer is admin-only on the backend, so only admins see its link
const userStore = useUserStore()
const { sections, onAdvancedArea } = useKnowledgeSectionNav(computed(() => userStore.isAdmin))

// The kit SectionShell owns the drawer; the app only remembers whether it was left open.
const showMobileSidebar = ref(localStorage.getItem(STORAGE_KEY) === 'true')
watch(showMobileSidebar, (open) => localStorage.setItem(STORAGE_KEY, String(open)))
const iconOf = (id: string): IconName => KNOWLEDGE_NAV_ICONS[id] ?? 'folder'
</script>
