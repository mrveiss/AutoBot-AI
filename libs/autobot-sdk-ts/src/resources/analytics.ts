// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import type { AutoBotHttpClient } from "../client.js";
import type { AnalyticsPerformance, AnalyticsUsage, DataResponse } from "../types.js";

export class AnalyticsResource {
  constructor(private readonly client: AutoBotHttpClient) {}

  usage(period = "day"): Promise<DataResponse<AnalyticsUsage>> {
    return this.client.get("/analytics/usage", { period });
  }

  performance(period = "day"): Promise<DataResponse<AnalyticsPerformance>> {
    return this.client.get("/analytics/performance", { period });
  }
}
