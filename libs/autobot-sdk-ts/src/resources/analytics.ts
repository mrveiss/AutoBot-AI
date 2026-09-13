// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Analytics resource operations.
 *
 * `/analytics/usage` and `/analytics/performance` are not routes: the
 * analytics router serves `usage/statistics` and `performance/metrics`
 * under its `/analytics` mount (#15528, mirroring the Python SDK's
 * already-fixed shape).
 *
 * Neither route wraps its body in a `DataResponse` envelope, and neither
 * declares a `period` query parameter -- both methods used to send one on
 * every call; FastAPI ignored it, so the window a caller asked for was
 * never the window they got. The argument is gone rather than renamed:
 * there is no parameter on either route to map it to.
 */
import type { AutoBotHttpClient } from "../client.js";
import type { AnalyticsPerformance, AnalyticsUsage } from "../types.js";

export class AnalyticsResource {
  constructor(private readonly client: AutoBotHttpClient) {}

  /** Usage statistics over the collector's own window. The route takes no
   * arguments, so neither does this. */
  usage(): Promise<AnalyticsUsage> {
    return this.client.get("/analytics/usage/statistics");
  }

  /** Performance metrics over the collector's own window. */
  performance(): Promise<AnalyticsPerformance> {
    return this.client.get("/analytics/performance/metrics");
  }
}
