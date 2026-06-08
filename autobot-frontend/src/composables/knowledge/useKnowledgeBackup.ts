// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useKnowledgeBackup Composable
 *
 * Encapsulates all HTTP calls for BackupManager:
 *   - loadBackups  — GET /knowledge-maintenance/backups
 *   - createBackup — POST /knowledge-maintenance/backup
 *   - restoreBackup — POST /knowledge-maintenance/restore (dry-run then actual)
 *   - deleteBackup — DELETE /knowledge-maintenance/backup (with JSON body)
 *
 * Extracted from BackupManager.vue (#6038).
 */

import { ref, readonly, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'

// ==================== Types ====================

export interface BackupOptions {
  includeEmbeddings: boolean
  compression: boolean
  description: string
}

export interface BackupInfo {
  name: string
  size: number
  created_at: string
  description?: string
  facts_count?: number
}

interface BackupListResponse {
  backups?: BackupInfo[]
  [key: string]: unknown
}

interface BackupActionResponse {
  status: string
  message?: string
  backup_name?: string
  total_facts_in_backup?: number
  restored?: number
  [key: string]: unknown
}

// ==================== Composable ====================

export interface UseKnowledgeBackupReturn {
  backups: Readonly<Ref<BackupInfo[]>>
  isLoadingBackups: Readonly<Ref<boolean>>
  isCreatingBackup: Readonly<Ref<boolean>>
  isRestoring: Readonly<Ref<boolean>>
  isDeletingBackup: Readonly<Ref<boolean>>
  loadBackups: () => Promise<void>
  createBackup: (options: BackupOptions) => Promise<BackupActionResponse>
  restoreBackupDryRun: (backupName: string) => Promise<BackupActionResponse>
  restoreBackupActual: (backupName: string) => Promise<BackupActionResponse>
  deleteBackup: (backupName: string) => Promise<BackupActionResponse>
}

export function useKnowledgeBackup(): UseKnowledgeBackupReturn {
  const backups = ref<BackupInfo[]>([])

  const loadingState = useLoadingState()
  const createState = useLoadingState()
  const restoreState = useLoadingState()
  const deleteState = useLoadingState()

  // Pattern A: GET read populating reactive data
  const loadBackups = async (): Promise<void> => {
    await loadingState.wrap(async () => {
      const data = await apiClient.get<BackupListResponse>(
        `${getApiBase()}/knowledge-maintenance/backups`,
      )
      if (data.backups) {
        backups.value = data.backups
      }
    })
  }

  // Pattern B: POST mutation
  const createBackup = (options: BackupOptions): Promise<BackupActionResponse> =>
    createState.wrap(() =>
      apiClient.post<BackupActionResponse>(`${getApiBase()}/knowledge-maintenance/backup`, {
        include_embeddings: options.includeEmbeddings,
        compression: options.compression,
        description: options.description || undefined,
      }),
    )

  // Pattern B: POST mutation — dry-run validation pass
  const restoreBackupDryRun = (backupName: string): Promise<BackupActionResponse> =>
    restoreState.wrap(() =>
      apiClient.post<BackupActionResponse>(`${getApiBase()}/knowledge-maintenance/restore`, {
        backup_file: backupName,
        dry_run: true,
      }),
    )

  // Pattern B: POST mutation — actual restore pass
  const restoreBackupActual = (backupName: string): Promise<BackupActionResponse> =>
    restoreState.wrap(() =>
      apiClient.post<BackupActionResponse>(`${getApiBase()}/knowledge-maintenance/restore`, {
        backup_file: backupName,
        dry_run: false,
        skip_duplicates: true,
      }),
    )

  // Pattern B: DELETE mutation — body passed via rawRequest because
  // ApiClient.delete() does not expose a body parameter in its public signature.
  const deleteBackup = (backupName: string): Promise<BackupActionResponse> =>
    deleteState.wrap(async () => {
      const response = await apiClient.rawRequest(
        `${getApiBase()}/knowledge-maintenance/backup`,
        { method: 'DELETE', body: { backup_file: backupName } },
      )
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      return (await response.json()) as BackupActionResponse
    })

  return {
    backups: readonly(backups) as Readonly<Ref<BackupInfo[]>>,
    isLoadingBackups: readonly(loadingState.isLoading),
    isCreatingBackup: readonly(createState.isLoading),
    isRestoring: readonly(restoreState.isLoading),
    isDeletingBackup: readonly(deleteState.isLoading),
    loadBackups,
    createBackup,
    restoreBackupDryRun,
    restoreBackupActual,
    deleteBackup,
  }
}

export default useKnowledgeBackup
