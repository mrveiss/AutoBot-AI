// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Agent resource operations.
 *
 * The agent surface spans two mounts (#15528, mirroring the Python SDK's
 * already-fixed shape): the agent router is registered under `/agent` and
 * per-agent configuration under `/agent_config`, so `health()` needed a
 * `/agent` segment it was missing, and `getConfig`/`setModel`/`setEnabled`
 * are all per-agent (`/agent_config/agents/{agentId}/...`), not the
 * bare `/agent/config` this used to call with no `agentId` at all.
 *
 * `updateConfig` is gone rather than fixed: there is no PUT route for
 * arbitrary agent config, on either mount. `setModel`/`setEnabled` are the
 * two ways an agent's config can actually be changed.
 */
import type { AutoBotHttpClient } from "../client.js";
import type { AgentConfig, AgentHealth } from "../types.js";

export class AgentsResource {
  constructor(private readonly client: AutoBotHttpClient) {}

  health(): Promise<AgentHealth> {
    return this.client.get("/agent/health/detailed");
  }

  /** Configuration of one agent. The response is a flat document, not a
   * `DataResponse` envelope. */
  getConfig(agentId: string): Promise<AgentConfig> {
    return this.client.get(`/agent_config/agents/${agentId}`);
  }

  setModel(agentId: string, model: string, provider?: string): Promise<Record<string, unknown>> {
    const body: Record<string, unknown> = { agent_id: agentId, model };
    if (provider) body["provider"] = provider;
    return this.client.post(`/agent_config/agents/${agentId}/model`, body);
  }

  setEnabled(agentId: string, enabled: boolean): Promise<Record<string, unknown>> {
    const action = enabled ? "enable" : "disable";
    return this.client.post(`/agent_config/agents/${agentId}/${action}`);
  }

  // #15527: the route reads `command` only. `sessionId` named nothing it has,
  // and until that fix the operation was form-encoded, so no body reached it.
  sendCommand(command: string): Promise<Record<string, unknown>> {
    return this.client.post("/agent/execute_command", { command });
  }
}
