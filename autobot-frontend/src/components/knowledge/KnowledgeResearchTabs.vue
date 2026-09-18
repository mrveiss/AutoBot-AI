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

  #16972: the tab row itself uses the shared tab-nav/tab-btn pattern from
  components.css (BrowserAutomationView.vue, VisionAutomationView.vue,
  BusinessIntelligenceView.vue already do) rather than a component-local
  variant -- KnowledgeEntries.vue's own manage-tabs/manage-tab-btn is a
  DIFFERENT, filled-pill treatment, not this one, so this intentionally does
  not reuse that file's classes even though "mirrors KnowledgeEntries" above
  is about the ?tab= behaviour, not the visual style.
-->
<template>
  <div class="knowledge-research-tabs">
    <nav class="tab-nav">
      <button @click="researchTab = 'research'" :class="['tab-btn', { active: researchTab === 'research' }]">
        <Icon name="search" />{{ $t('knowledge.views.research') }}
      </button>
      <button @click="researchTab = 'webTools'" :class="['tab-btn', { active: researchTab === 'webTools' }]">
        <Icon name="globe" />{{ $t('knowledge.webResearch.navLabel') }}
      </button>
      <button @click="researchTab = 'settings'" :class="['tab-btn', { active: researchTab === 'settings' }]">
        <Icon name="cog" />{{ $t('knowledge.webResearch.settingsNavLabel') }}
      </button>
    </nav>

    <KnowledgeResearchPanel v-if="researchTab === 'research'" />
    <WebResearchPanel v-else-if="researchTab === 'webTools'" />
    <WebResearchSettings v-else-if="researchTab === 'settings'" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import Icon from '@/components/ui/Icon.vue'
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
