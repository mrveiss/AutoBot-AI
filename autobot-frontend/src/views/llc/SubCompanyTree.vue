<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, onMounted } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { useRouter } from 'vue-router'
import CompanyTreeNode from './CompanyTreeNode.vue'
import type { CompanyNode } from './CompanyTreeNode.vue'

const logger = createLogger('SubCompanyTree')
const api = useApiClient()
const router = useRouter()

const tree = ref<CompanyNode[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)

// Raw recursive shape returned by GET /api/llc/companies/{id}/tree.
interface RawCompanyTreeNode {
  id: string
  name: string
  slug?: string
  llc_status?: string
  children?: RawCompanyTreeNode[]
}

function statusOf(llcStatus?: string): CompanyNode['status'] {
  if (llcStatus === 'active') return 'active'
  if (llcStatus === 'paused') return 'paused'
  return 'inactive'
}

function mapNode(raw: RawCompanyTreeNode): CompanyNode {
  return {
    id: raw.id,
    name: raw.name,
    status: statusOf(raw.llc_status),
    // Budget is not exposed by the tree endpoint; shown as 0 until a
    // budget-aware tree endpoint exists (#9861).
    budget_spent: 0,
    budget_total: 0,
    children: (raw.children ?? []).map(mapNode),
    expanded: false,
  }
}

async function fetchTree() {
  isLoading.value = true
  error.value = null
  try {
    // No global tree route exists — build the forest from the root-company
    // list plus each root's recursive subtree (#9861).
    const roots = await api.get<{ id: string }[]>('/api/llc/companies/')
    const subtrees = await Promise.all(
      (roots ?? []).map((c) => api.get<RawCompanyTreeNode>(`/api/llc/companies/${c.id}/tree`)),
    )
    tree.value = subtrees.filter(Boolean).map(mapNode)
    markExpanded(tree.value, true)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Failed to fetch company tree:', msg)
    error.value = msg
  } finally {
    isLoading.value = false
  }
}

function markExpanded(nodes: CompanyNode[], expanded: boolean) {
  for (const node of nodes) {
    node.expanded = expanded
    if (node.children) markExpanded(node.children, false)
  }
}

function toggle(node: CompanyNode) {
  node.expanded = !node.expanded
}

function navigate(node: CompanyNode) {
  router.push({ path: '/llc/dashboard', query: { company: node.id } })
}

onMounted(fetchTree)
</script>

<template>
  <div class="p-4 max-w-5xl mx-auto">
    <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Company Hierarchy</h1>

    <div v-if="error" class="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm mb-4">
      {{ error }}
      <button class="ml-4 underline" @click="fetchTree">Retry</button>
    </div>

    <div v-if="isLoading" class="text-center py-12 text-gray-500">Loading…</div>

    <div v-else-if="tree.length === 0 && !error" class="text-center py-12 text-gray-400">No companies found.</div>

    <div v-else class="space-y-2">
      <CompanyTreeNode
        v-for="company in tree"
        :key="company.id"
        :node="company"
        :depth="0"
        @toggle="toggle"
        @navigate="navigate"
      />
    </div>
  </div>
</template>
