// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #18978: the projects a work item can go in, for the backlog's filter, form and sprint picker.
// A failed request is kept apart from an empty result, so a company is not told it has no project.
import { ref, watch, type Ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useAssignableProjects')

export interface ProjectOpt {
  id: string
  name: string
  lifecycle_state: string
}

export function useAssignableProjects(companyId: Readonly<Ref<string>>) {
  const api = useApiClient()
  const projects = ref<ProjectOpt[]>([])
  const isLoadingProjects = ref(false)
  const projectsFailed = ref(false)

  // Counts loads (the pattern useCompanyTeams uses): of overlapping loads only the newest may land.
  let loadSeq = 0

  async function loadProjects() {
    const req = ++loadSeq
    const current = () => req === loadSeq
    isLoadingProjects.value = true
    projectsFailed.value = false
    try {
      const result = await api.get<ProjectOpt[]>(`/api/llc/companies/${companyId.value}/projects`)
      if (!current()) return
      projects.value = (result ?? []).filter(
        p => p.lifecycle_state !== 'archived' && p.lifecycle_state !== 'disposed',
      )
    } catch (err) {
      if (!current()) return
      logger.error('Failed to load projects', err)
      projectsFailed.value = true
    } finally {
      if (current()) isLoadingProjects.value = false
    }
  }

  // A different company has different projects: drop the old list and any load still in flight, then load again.
  // Whoever holds a selection (`projects` is what it must be one of) re-validates it against the new list.
  watch(companyId, (next, previous) => {
    if (next === previous) return
    loadSeq++
    projects.value = []
    projectsFailed.value = false
    isLoadingProjects.value = false
    if (next) void loadProjects()
  })

  return { projects, isLoadingProjects, projectsFailed, loadProjects }
}
