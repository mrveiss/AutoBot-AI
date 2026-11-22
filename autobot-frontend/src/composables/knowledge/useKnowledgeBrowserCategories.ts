// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Main-category state for the Knowledge Browser (#18244): the three category cards,
 * the connectivity flags behind them, Populate, and the Edit modal.
 *
 * Moved out of KnowledgeBrowser.vue with its behaviour unchanged.
 */
import { ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { fetchMainCategories, type MainCategory } from '@/composables/knowledge/useKnowledgeBrowser'
import { useMachineKnowledge } from '@/composables/knowledge/useMachineKnowledge'
import { useManPages } from '@/composables/knowledge/useManPages'
import type { Category } from '@/components/knowledge/modals/CategoryEditModal.vue'

const logger = createLogger('KnowledgeBrowserCategories')

// The backend gives no live progress, so Populate shows a stepped bar and then a result.
const POPULATE_PROGRESS_STEP = 10
const POPULATE_PROGRESS_CAP = 90
const POPULATE_TICK_MS = 500
const POPULATE_SETTLE_MS = 3000
const POPULATE_DONE_MS = 1000

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/** Shown when the categories endpoint fails, so the cards still render. */
const FALLBACK_CATEGORIES: MainCategory[] = [
  {
    id: 'autobot-documentation',
    name: 'AutoBot Documentation',
    description: "AutoBot's initial knowledge - documentation and guides",
    icon: 'book',
    color: 'var(--i1)',
    count: 0,
  },
  {
    id: 'system-knowledge',
    name: 'System Knowledge',
    description: "AutoBot's initial knowledge - system info, man pages, OS knowledge",
    icon: 'server',
    color: 'var(--i2)',
    count: 0,
  },
  {
    id: 'user-knowledge',
    name: 'User Knowledge',
    description: 'What AutoBot is used for - user-provided domain knowledge',
    icon: 'user-circle',
    color: 'var(--i3)',
    count: 0,
  },
]

type PopulationState = { isPopulating: boolean; progress: number }
const IDLE: PopulationState = { isPopulating: false, progress: 0 }

export function useKnowledgeBrowserCategories(reloadTree: () => Promise<unknown>) {
  const { refreshSystemKnowledge } = useMachineKnowledge()
  const { populateAutoBotDocs } = useManPages()

  const mainCategories = ref<MainCategory[]>([])
  const selectedMainCategory = ref<string | null>(null)
  const selectedCategory = ref<string | null>(null)
  // #5201: "empty KB" (kb_connected=true, counts 0) vs "broken KB" (kb_connected=false);
  // true until the first fetch so the error banner does not flash.
  const kbConnected = ref(true)
  // #5590: a fetch-layer error (5xx, network) is not "Redis is down".
  const kbFetchError = ref(false)
  const populationStates = ref<Record<string, PopulationState>>({
    'autobot-documentation': { ...IDLE },
    'system-knowledge': { ...IDLE },
  })
  const showCategoryEditModal = ref(false)
  const categoryToEdit = ref<Category | null>(null)

  const loadMainCategories = async () => {
    kbFetchError.value = false
    try {
      const data = await fetchMainCategories()
      if (data && data.categories) {
        mainCategories.value = data.categories
        kbConnected.value = data.kb_connected !== false
      }
    } catch (err) {
      logger.error('Failed to load main categories:', err)
      kbFetchError.value = true
      mainCategories.value = FALLBACK_CATEGORIES.map((c) => ({ ...c }))
    }
  }

  const selectCategory = (category: string | null) => {
    selectedCategory.value = category
  }

  const selectMainCategory = (id: string) => {
    selectedMainCategory.value = id
  }

  const handleEditCategory = (cat: MainCategory) => {
    categoryToEdit.value = cat as Category
    showCategoryEditModal.value = true
  }

  const closeEditModal = () => {
    showCategoryEditModal.value = false
    categoryToEdit.value = null
  }

  const handleCategoryUpdated = (updated: Category) => {
    const idx = mainCategories.value.findIndex((c) => c.id === updated.id)
    if (idx !== -1) mainCategories.value[idx] = { ...mainCategories.value[idx], ...updated }
    closeEditModal()
  }

  const handleCategoryDeleted = (categoryId: string) => {
    mainCategories.value = mainCategories.value.filter((c) => c.id !== categoryId)
    closeEditModal()
  }

  const runPopulate = (categoryId: string) =>
    categoryId === 'autobot-documentation'
      ? populateAutoBotDocs()
      : categoryId === 'system-knowledge'
        ? refreshSystemKnowledge()
        : Promise.resolve(undefined)

  const handlePopulate = async (categoryId: string) => {
    if (populationStates.value[categoryId]?.isPopulating) return
    populationStates.value[categoryId] = { isPopulating: true, progress: 0 }
    try {
      const result = await runPopulate(categoryId)
      const ticker = setInterval(() => {
        const state = populationStates.value[categoryId]
        if (state.progress < POPULATE_PROGRESS_CAP) state.progress += POPULATE_PROGRESS_STEP
      }, POPULATE_TICK_MS)
      await sleep(POPULATE_SETTLE_MS)
      clearInterval(ticker)
      populationStates.value[categoryId].progress = 100
      await sleep(POPULATE_DONE_MS)
      populationStates.value[categoryId] = { ...IDLE }
      await reloadTree()
      logger.info(`${categoryId} population completed:`, result)
    } catch (err) {
      logger.error(`Failed to populate ${categoryId}:`, err)
      populationStates.value[categoryId] = { ...IDLE }
    }
  }

  return {
    mainCategories, selectedMainCategory, selectedCategory, kbConnected, kbFetchError, populationStates,
    showCategoryEditModal, categoryToEdit, loadMainCategories, selectCategory, selectMainCategory,
    handleEditCategory, handleCategoryUpdated, handleCategoryDeleted, handlePopulate,
  }
}
