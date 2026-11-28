// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Batch Processing and Vision: user work, moved here from the SLM console (#20644).
 *
 * Any signed-in user may open both. Their backend routes need only authentication
 * (`get_current_user`), and batch jobs are scoped to their owner (#21650), so an ordinary
 * user sees only their own. The paths are not under `/tools`, because every `/tools/*` path
 * of this app leaves for the SLM (slmRedirectRoutes.ts). Split out of router/index.ts, which
 * is at its size ceiling. Both are reached from the profile menu (navItems `profileMenuItems`).
 */
import i18n from '@/i18n'
import type { RouteRecordRaw } from 'vue-router'

/** Meta for a signed-in user's screen: `titleKey` is resolved when read, so a locale change applies. */
const userMeta = (titleKey: string) => ({
  titleKey,
  get title(): string {
    return i18n.global.t(titleKey)
  },
  hideInNav: true,
  requiresAuth: true,
})

export const BATCH_JOBS_PATH = '/batch'
export const VISION_PATH = '/vision'

export const userToolRoutes: RouteRecordRaw[] = [
  {
    path: BATCH_JOBS_PATH,
    name: 'batch-jobs',
    component: () => import('@/views/BatchJobsView.vue'),
    meta: userMeta('batchJobs.title'),
  },
  {
    path: VISION_PATH,
    name: 'vision-capture',
    component: () => import('@/views/VisionCaptureView.vue'),
    meta: userMeta('visionCapture.title'),
  },
]
