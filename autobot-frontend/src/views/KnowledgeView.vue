<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeView — the Knowledge section shell (#18244, Refined UI): the kit SectionNav
  sub-sidebar in the mockup's order with advanced entries hidden in Minimal mode, the
  "advanced area" notice on advanced pages, and the routed screen beside it.
-->
<template>
  <div class="knowledge-view">
    <div v-if="showMobileSidebar" class="mobile-overlay" aria-hidden="true" @click="closeSidebar" />

    <aside class="knowledge-sidebar" :class="{ 'mobile-open': showMobileSidebar }">
      <BaseButton
        variant="ghost"
        size="sm"
        class="mobile-toggle"
        :aria-label="showMobileSidebar ? $t('knowledge.views.closeSidebar') : $t('knowledge.views.openSidebar')"
        :aria-expanded="showMobileSidebar"
        @click="toggleMobileSidebar"
      >
        <Icon :name="showMobileSidebar ? 'times' : 'bars'" aria-hidden="true" />
      </BaseButton>
      <SectionNav
        class="knowledge-nav"
        :label="$t('knowledge.views.navAriaLabel')"
        :title="$t('knowledge.views.title')"
        :sections="sections"
        :link-as="RouterLink"
        @click="onNavClick"
      >
        <template #icon="{ item }"><Icon :name="iconOf(item.id)" aria-hidden="true" /></template>
      </SectionNav>
    </aside>

    <main class="knowledge-content">
      <AdvancedAreaNotice v-if="onAdvancedArea" />
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { BaseButton, SectionNav } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import type { IconName } from '@/components/ui/Icon.vue'
import AdvancedAreaNotice from '@/components/layout/AdvancedAreaNotice.vue'
import { useUserStore } from '@/stores/useUserStore'
import { useKnowledgeSectionNav, KNOWLEDGE_NAV_ICONS } from '@/composables/knowledge/useKnowledgeSectionNav'

const STORAGE_KEY = 'knowledge-sidebar-mobile-open'
const MOBILE_MAX_WIDTH = 768

// #16666: the vector-store explorer is admin-only on the backend, so only admins see its link
const userStore = useUserStore()
const { sections, onAdvancedArea } = useKnowledgeSectionNav(computed(() => userStore.isAdmin))

const showMobileSidebar = ref(false)
const iconOf = (id: string): IconName => KNOWLEDGE_NAV_ICONS[id] ?? 'folder'

onMounted(() => {
  showMobileSidebar.value = localStorage.getItem(STORAGE_KEY) === 'true'
})

function setSidebar(open: boolean) {
  showMobileSidebar.value = open
  localStorage.setItem(STORAGE_KEY, String(open))
}

const toggleMobileSidebar = () => setSidebar(!showMobileSidebar.value)
const closeSidebar = () => setSidebar(false)

function onNavClick(e: Event) {
  if (window.innerWidth <= MOBILE_MAX_WIDTH && showMobileSidebar.value && (e.target as HTMLElement).closest('a')) {
    closeSidebar()
  }
}
</script>

<style scoped>
.knowledge-view {
  contain: layout style paint;
  display: flex;
  min-block-size: 0;
  background: var(--bg);
}

.knowledge-sidebar {
  inline-size: var(--subnav-w);
  min-inline-size: var(--subnav-w);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: var(--surface);
  border-inline-end: var(--bw) solid var(--border);
}

.knowledge-nav {
  flex: 1;
  border-inline-end: 0;
}

.knowledge-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-inline-size: 0;
  overflow-x: hidden;
  overflow-y: auto;
  background: var(--bg);
}

.mobile-toggle,
.mobile-overlay {
  display: none;
}

@media (max-width: 768px) {
  .knowledge-view {
    flex-direction: column;
    position: relative;
  }

  .knowledge-sidebar {
    inline-size: 100%;
    min-inline-size: 100%;
    border-inline-end: 0;
    border-block-end: var(--bw) solid var(--border);
    position: relative;
    z-index: var(--z-sticky);
  }

  .mobile-toggle {
    display: inline-flex;
    align-self: flex-start;
    margin: var(--spacing-2);
  }

  .knowledge-sidebar:not(.mobile-open) .knowledge-nav {
    display: none;
  }

  .knowledge-sidebar.mobile-open {
    position: fixed;
    inset-block: 0;
    inset-inline-start: 0;
    inline-size: 80vw;
    max-inline-size: 320px;
    min-inline-size: 0;
    z-index: var(--z-fixed);
  }

  .mobile-overlay {
    display: block;
    position: fixed;
    inset: 0;
    background: var(--bg-overlay);
    z-index: var(--z-drawer-backdrop);
  }
}
</style>
