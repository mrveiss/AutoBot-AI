// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * `slmApi`: the SLM control plane's data layer in the main app (#19834, ADR 011 section 4).
 *
 * One adapter over the main-app `ApiClient`, base path `/slm/api`, main-app session token.
 * A store takes it as `SlmApi`, so a test can hand it a fake without touching the network.
 */
import * as nodes from './nodes'
import * as npu from './npu'
import * as provision from './provision'

export { SLM_API_PREFIX, slmClient, slmUrl, slmWsUrl } from './transport'

export const slmApi = { ...nodes, ...npu, ...provision }

export type SlmApi = typeof slmApi
