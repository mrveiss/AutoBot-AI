// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import type { Ref } from 'vue'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('projectRoot')

export interface ProjectRootTarget {
  rootPath: Ref<string>
  progressStatus: Ref<string>
  t: (key: string, params?: Record<string, unknown>) => string
}

/**
 * Fill `rootPath` from the backend's project root unless the user saved one.
 *
 * Moved out of `useAnalyticsDataFetchers` unchanged (#21003: that file is at its size ceiling).
 */
export async function loadProjectRoot({ rootPath, progressStatus, t }: ProjectRootTarget): Promise<void> {
  const saved = localStorage.getItem('codebase-analytics-path')
  if (saved) {
    logger.debug('Using saved path from localStorage:', saved)
    return
  }
  try {
    const projectRoot = await appConfig.getProjectRoot()
    if (projectRoot) {
      rootPath.value = projectRoot
    } else {
      logger.warn('Project root not found in config, using default')
    }
  } catch (error: unknown) {
    logger.error('Failed to load project root:', error)
    progressStatus.value = t('analytics.codebase.status.enterProjectPath')
  }
}
