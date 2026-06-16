<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  ProgramBrowserView (GH#9628) — middle tier of the LLC work hierarchy.
  Lists the programs under a portfolio as a card grid; clicking a card
  drills down into that program's projects.
-->
<template>
  <div class="llc-browser">
    <LlcBreadcrumb :items="breadcrumb" />

    <header class="browser-header">
      <h2 class="browser-title">Programs</h2>
      <span class="browser-count">{{ programs.length }} programs</span>
    </header>

    <div v-if="loading" class="browser-state">Loading programs…</div>
    <div v-else-if="!programs.length" class="browser-state">No programs yet.</div>

    <div v-else class="card-grid">
      <button
        v-for="p in programs"
        :key="p.id"
        type="button"
        class="entity-card"
        @click="openProgram(p)"
      >
        <div class="card-top">
          <h3 class="card-name">{{ p.name }}</h3>
          <span class="status-badge" :class="`status-${p.status}`">{{ p.status }}</span>
        </div>
        <p v-if="p.description" class="card-desc">{{ p.description }}</p>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import LlcBreadcrumb, { type BreadcrumbItem } from '@/components/llc/LlcBreadcrumb.vue'

interface ProgramResponse {
  id: string
  company_id: string
  portfolio_id: string
  name: string
  description: string | null
  status: string
  created_at: string
  updated_at: string
}

const logger = createLogger('ProgramBrowserView')
const api = useApiClient()
const route = useRoute()
const router = useRouter()

const companyId = computed(() => route.params.companyId as string)
const portfolioId = computed(() => route.params.portfolioId as string)
const programs = ref<ProgramResponse[]>([])
const loading = ref(false)

const breadcrumb = computed<BreadcrumbItem[]>(() => [
  {
    label: 'Portfolios',
    to: { name: 'llc-portfolios', params: { companyId: companyId.value } },
  },
  { label: 'Programs' },
])

async function loadPrograms(): Promise<void> {
  loading.value = true
  try {
    programs.value = await api.get<ProgramResponse[]>(
      `/api/llc/portfolios/${portfolioId.value}/programs`,
    )
  } catch (err) {
    logger.error('Failed to load programs', err)
    programs.value = []
  } finally {
    loading.value = false
  }
}

function openProgram(p: ProgramResponse): void {
  router.push({
    name: 'llc-projects',
    params: { companyId: companyId.value, programId: p.id },
  })
}

onMounted(loadPrograms)
</script>

<style scoped>
.llc-browser {
  padding: 1.5rem;
}

.browser-header {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.browser-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text-primary, #111827);
  margin: 0;
}

.browser-count {
  font-size: 0.875rem;
  color: var(--color-text-secondary, #9ca3af);
}

.browser-state {
  padding: 2rem 0;
  color: var(--color-text-secondary, #9ca3af);
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
  gap: 1rem;
}

.entity-card {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1rem;
  text-align: left;
  cursor: pointer;
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--border-default, #e5e7eb);
  background: var(--bg-surface, #ffffff);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.entity-card:hover {
  border-color: var(--color-accent, #c4651a);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

.card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
}

.card-name {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary, #111827);
  margin: 0;
}

.card-desc {
  font-size: 0.875rem;
  color: var(--color-text-secondary, #9ca3af);
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.status-badge {
  flex: none;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
  background: var(--bg-hover, #f3f4f6);
  color: var(--color-text-secondary, #6b7280);
}
</style>
