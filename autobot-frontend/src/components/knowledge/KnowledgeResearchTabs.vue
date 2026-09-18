<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  #16900: one Research surface. Research, Web Tools and their Settings were three
  top-level Knowledge sidebar entries answering one question — how do I research
  something — so they are one surface with tabs here.

  This hosts the three existing panels; it does not merge them. They are not two
  iterations of one feature: KnowledgeResearchPanel runs an agentic research task
  over a WebSocket, WebResearchPanel is four web-fetching primitives with its own
  inner tabs. They share a subject, not an implementation, and collapsing them
  would lose the distinction that makes each usable. What collapses is the three
  doors.

  `?tab=` mirrors KnowledgeEntries: the retired routes redirect here with it, so
  an existing link or bookmark lands on the tab it used to be a page.
-->
<template>
  <div class="knowledge-research-tabs">
    <div class="research-tabs">
      <BaseButton
        variant="ghost"
        @click="researchTab = 'research'"
        :class="['research-tab-btn', { active: researchTab === 'research' }]"
      >
        <Icon name="search" class="mr-2" />{{ $t('knowledge.views.research') }}
      </BaseButton>
      <BaseButton
        variant="ghost"
        @click="researchTab = 'webTools'"
        :class="['research-tab-btn', { active: researchTab === 'webTools' }]"
      >
        <Icon name="globe" class="mr-2" />{{ $t('knowledge.webResearch.navLabel') }}
      </BaseButton>
      <BaseButton
        variant="ghost"
        @click="researchTab = 'settings'"
        :class="['research-tab-btn', { active: researchTab === 'settings' }]"
      >
        <Icon name="cog" class="mr-2" />{{ $t('knowledge.webResearch.settingsNavLabel') }}
      </BaseButton>
    </div>

    <KnowledgeResearchPanel v-if="researchTab === 'research'" />
    <WebResearchPanel v-else-if="researchTab === 'webTools'" />
    <WebResearchSettings v-else-if="researchTab === 'settings'" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import Icon from '@/components/ui/Icon.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import KnowledgeResearchPanel from './KnowledgeResearchPanel.vue'
import WebResearchPanel from './WebResearchPanel.vue'
import WebResearchSettings from './WebResearchSettings.vue'

const route = useRoute()

// Initialised from ?tab= so /knowledge/research?tab=webTools — the redirect
// target for the retired /knowledge/web-research route — opens directly on the
// right tab, rather than landing on Research and making the user click.
type ResearchTab = 'research' | 'webTools' | 'settings'
const validResearchTabs: ResearchTab[] = ['research', 'webTools', 'settings']
const initialTab = validResearchTabs.includes(route.query.tab as ResearchTab)
  ? (route.query.tab as ResearchTab)
  : 'research'
const researchTab = ref<ResearchTab>(initialTab)
</script>

<style scoped>
.research-tabs {
  display: flex;
  gap: var(--space-2, 0.5rem);
  border-bottom: 1px solid var(--color-border, #e5e7eb);
  margin-bottom: var(--space-4, 1rem);
}

.research-tab-btn.active {
  border-bottom: 2px solid var(--color-primary, #3b82f6);
  color: var(--color-primary, #3b82f6);
}
</style>
