// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import type { AutoBotHttpClient } from "../client.js";
import type { AgentConfig, AgentHealth, DataResponse } from "../types.js";

export class AgentsResource {
  constructor(private readonly client: AutoBotHttpClient) {}

  health(): Promise<AgentHealth> {
    return this.client.get("/health/detailed");
  }

  getConfig(): Promise<DataResponse<AgentConfig>> {
    return this.client.get("/agent/config");
  }

  updateConfig(fields: Partial<AgentConfig>): Promise<DataResponse<AgentConfig>> {
    return this.client.put("/agent/config", fields);
  }

  // #15527: the route reads `command` only. `sessionId` named nothing it has,
  // and until that fix the operation was form-encoded, so no body reached it.
  sendCommand(command: string): Promise<Record<string, unknown>> {
    return this.client.post("/agent/execute_command", { command });
  }
}
