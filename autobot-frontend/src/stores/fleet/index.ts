// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Fleet Store (#19834, ported from the SLM app's `stores/fleet.ts`)
 *
 * Global fleet state: node CRUD, enrollment, certificates, events, updates and NPU management,
 * over the `slmApi` adapter (`/slm/api`, the main-app session). The store is a short setup that
 * composes slices; each slice is a set of module-level actions over one `FleetCtx`.
 */
import { defineStore } from 'pinia'
import { bindSlice } from '../bindSlice'
import * as cache from './cache'
import { createFleetContext } from './context'
import { createFleetGetters } from './getters'
import * as lifecycle from './lifecycle'
import * as nodes from './nodes'
import * as npu from './npu'

export const useFleetStore = defineStore('fleet', () => {
  const ctx = createFleetContext()
  return {
    ...ctx.state,
    ...createFleetGetters(ctx.state),
    ...bindSlice(ctx, nodes),
    ...bindSlice(ctx, lifecycle),
    ...bindSlice(ctx, npu),
    ...bindSlice(ctx, cache),
  }
})
