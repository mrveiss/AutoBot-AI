// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import type { AutoBotHttpClient } from "../client.js";
import type { AgentConfig, AgentHealth, DataResponse } from "../types.js";

export class AgentsResource {
  constructor(private readonly client: AutoBotHttpClient) {}

  health(): Promise<AgentHealth> {
    return this.client.get("/health/enhanced");
  }

  getConfig(): Promise<DataResponse<AgentConfig>> {
    return this.client.get("/agent/config");
  }

  updateConfig(fields: Partial<AgentConfig>): Promise<DataResponse<AgentConfig>> {
    return this.client.put("/agent/config", fields);
  }

  sendCommand(command: string, sessionId?: string): Promise<Record<string, unknown>> {
    return this.client.post("/agent/execute_command", { command, session_id: sessionId });
  }
}
