// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * planRequest (#19938): a Workflow Planner call whose path, method and response all come from the
 * generated contract (`paths`). A path or method the backend does not declare does not compile,
 * and the response type is read from the declared 200/201 body instead of asserted at the call.
 */
import type { paths } from '@/types/generated/api'
import type { useApiClient } from '@/plugins/api'

type Client = ReturnType<typeof useApiClient>
type Verb = 'get' | 'post' | 'put' | 'patch' | 'delete'

export type PlanPath = Extract<keyof paths, `/api/llc/company-os/workflow-plans${string}`>

type JsonBody<O> = O extends { content: { 'application/json': infer J } } ? J : void
type OkBody<R> = R extends { 200: infer O } ? JsonBody<O> : R extends { 201: infer O } ? JsonBody<O> : void

/** The declared success body of `METHOD path` in the generated contract. */
export type PlanResponse<P extends PlanPath, V extends Verb> = paths[P][V] extends { responses: infer R }
  ? OkBody<R>
  : never

/** Fills `{name}` placeholders of a declared path; every value is URL-encoded. */
export function fillPath(template: string, params: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, name: string) => encodeURIComponent(params[name] ?? ''))
}

export async function planRequest<P extends PlanPath, V extends Verb & keyof paths[P]>(
  client: Client,
  verb: V & Verb,
  path: P,
  params: Record<string, string> = {},
  body?: unknown,
): Promise<PlanResponse<P, V & Verb>> {
  const url = fillPath(path, params)
  const data: unknown = await (body === undefined ? client[verb](url) : client[verb as 'post'](url, body))
  return data as PlanResponse<P, V & Verb>
}
