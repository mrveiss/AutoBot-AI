// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
// Fetch-based HTTP client for the AutoBot SDK.

const DEFAULT_BASE_URL = "http://localhost:8000";
const TOKEN_ENV = "AUTOBOT_API_TOKEN";

// Every core and optional router is mounted by the backend's application
// factory at `/api{registry_prefix}` -- a single loop, no exceptions (#15053,
// #16495 -- the same bug found once already in the Python SDK, and found here
// undiscovered because nothing in this package's default test run makes an
// HTTP call). The only mounts that are NOT under `/api` are the OpenAI/
// Anthropic compatibility routers at `/v1` and the JWKS document at
// `/.well-known`, and this SDK exposes neither. So the prefix is a property
// of the whole surface and belongs here, applied once, rather than repeated
// on every resource path.
const API_PREFIX = "/api";

/** Place a resource path under the backend's API root, once, idempotently.
 * `/chat/sessions` -> `/api/chat/sessions`. A path that already carries the
 * prefix is not double-prefixed. */
function apiPath(path: string): string {
  const normalised = "/" + path.replace(/^\/+/, "");
  return normalised === API_PREFIX || normalised.startsWith(`${API_PREFIX}/`) ? normalised : `${API_PREFIX}${normalised}`;
}

export interface ClientOptions {
  baseUrl?: string;
  token?: string;
  timeout?: number;
}

export class AutoBotHttpClient {
  protected readonly baseUrl: string;
  protected readonly token: string;
  protected readonly timeout: number;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? process.env["AUTOBOT_BASE_URL"] ?? DEFAULT_BASE_URL).replace(/\/$/, "");
    this.token = options.token ?? process.env[TOKEN_ENV] ?? "";
    this.timeout = options.timeout ?? 30_000;
  }

  private get defaultHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json",
    };
    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }
    return headers;
  }

  private buildUrl(path: string, params?: Record<string, string | number | undefined>): string {
    const url = new URL(`${this.baseUrl}${apiPath(path)}`);
    if (params) {
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== null) {
          url.searchParams.set(key, String(value));
        }
      }
    }
    return url.toString();
  }

  async get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
    const res = await fetch(this.buildUrl(path, params), {
      method: "GET",
      headers: this.defaultHeaders,
      signal: AbortSignal.timeout(this.timeout),
    });
    if (!res.ok) {
      throw new Error(`AutoBot API error: ${res.status} ${res.statusText} — ${path}`);
    }
    return res.json() as Promise<T>;
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(this.buildUrl(path), {
      method: "POST",
      headers: this.defaultHeaders,
      body: JSON.stringify(body ?? {}),
      signal: AbortSignal.timeout(this.timeout),
    });
    if (!res.ok) {
      throw new Error(`AutoBot API error: ${res.status} ${res.statusText} — ${path}`);
    }
    return res.json() as Promise<T>;
  }

  async put<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(this.buildUrl(path), {
      method: "PUT",
      headers: this.defaultHeaders,
      body: JSON.stringify(body ?? {}),
      signal: AbortSignal.timeout(this.timeout),
    });
    if (!res.ok) {
      throw new Error(`AutoBot API error: ${res.status} ${res.statusText} — ${path}`);
    }
    return res.json() as Promise<T>;
  }

  async delete<T>(path: string): Promise<T> {
    const res = await fetch(this.buildUrl(path), {
      method: "DELETE",
      headers: this.defaultHeaders,
      signal: AbortSignal.timeout(this.timeout),
    });
    if (!res.ok) {
      throw new Error(`AutoBot API error: ${res.status} ${res.statusText} — ${path}`);
    }
    return res.json() as Promise<T>;
  }
}
