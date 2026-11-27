// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The Manage entry dialog state (#18244, #17530): which document is open and in which mode.
 * An edit can only be saved for a document whose full content was read from the server
 * (`contentComplete`); a preview saved back would overwrite the document with its first characters.
 */
import { computed, ref } from 'vue'
import type { KnowledgeDocument } from '@/stores/useKnowledgeStore'
import { useModal } from '@/composables/useModal'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useKnowledgeEntryDialog')

type DocumentUpdater = (id: string, updates: Partial<KnowledgeDocument>) => Promise<void>

export type EntryEdit = Pick<KnowledgeDocument, 'title' | 'category' | 'source' | 'content' | 'tags'>

export function useKnowledgeEntryDialog(update: DocumentUpdater) {
  const { isOpen: showDialog, open: openDialog, close: closeDialogModal } = useModal({ id: 'entry-dialog' })
  const dialogMode = ref<'view' | 'edit'>('view')
  const currentEntry = ref<KnowledgeDocument | null>(null)

  const canSaveEdit = computed(() => currentEntry.value?.contentComplete === true)

  const openEntry = (entry: KnowledgeDocument, mode: 'view' | 'edit') => {
    currentEntry.value = entry
    dialogMode.value = mode
    openDialog()
  }

  const closeDialog = () => {
    closeDialogModal()
    currentEntry.value = null
    dialogMode.value = 'view'
  }

  const saveEdit = async (edit: EntryEdit) => {
    if (!currentEntry.value || !canSaveEdit.value) return
    try {
      await update(currentEntry.value.id, edit)
      closeDialog()
    } catch (error) {
      logger.error('Failed to save changes:', error)
    }
  }

  return {
    showDialog, dialogMode, currentEntry, canSaveEdit, saveEdit, closeDialog,
    viewEntry: (entry: KnowledgeDocument) => openEntry(entry, 'view'),
    editEntry: (entry: KnowledgeDocument) => openEntry(entry, 'edit'),
    cancelEdit: () => { dialogMode.value = 'view' },
  }
}
