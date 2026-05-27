// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
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
