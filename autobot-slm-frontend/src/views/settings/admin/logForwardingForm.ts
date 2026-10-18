// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Form state and request bodies for the Log Forwarding page (#18734).
 * The list returns api_key/password MASKED, so credentials are never prefilled
 * and an update carries one only when the user typed a new value.
 */
import type {
  LogForwardingDestination,
  LogForwardingDestinationCreate,
  LogForwardingDestinationUpdate,
} from '@/composables/autobotAdminModels'
import config from '@/config/ssot-config'

export function defaultForm() {
  return {
    name: '',
    type: 'syslog' as LogForwardingDestination['type'],
    enabled: true,
    url: '',
    syslog_protocol: 'udp',
    file_path: '',
    api_key: '',
    username: '',
    password: '',
    clear_api_key: false,
    clear_password: false,
    index: 'autobot-logs',
    min_level: 'Information',
    batch_size: 10,
    batch_timeout: 5,
  }
}

export type LogForwardingForm = ReturnType<typeof defaultForm>

/** Fields shared by create and update. Credentials are added by the callers. */
function buildCommonFields(form: LogForwardingForm) {
  return {
    enabled: form.enabled,
    url: form.url || null,
    username: form.username || null,
    index: form.index || null,
    file_path: form.file_path || null,
    syslog_protocol: form.syslog_protocol,
    min_level: form.min_level,
    batch_size: form.batch_size,
    batch_timeout: form.batch_timeout,
  }
}

export function buildCreateBody(form: LogForwardingForm): LogForwardingDestinationCreate {
  return {
    ...buildCommonFields(form),
    name: form.name,
    type: form.type,
    api_key: form.api_key || null,
    password: form.password || null,
    retry_count: 3,
    retry_delay: 1,
    scope: 'global',
  }
}

/** A credential is sent only when newly typed; a masked value must never round-trip. */
export function buildUpdateBody(form: LogForwardingForm): LogForwardingDestinationUpdate {
  const body: LogForwardingDestinationUpdate = buildCommonFields(form)
  // Typed value wins; "remove" sends an explicit null (the handler clears it); else omit.
  if (form.api_key) body.api_key = form.api_key
  else if (form.clear_api_key) body.api_key = null
  if (form.password) body.password = form.password
  else if (form.clear_password) body.password = null
  return body
}

export const destinationTypes = [
  { value: 'syslog', label: 'Syslog' },
  { value: 'webhook', label: 'Webhook' },
  { value: 'file', label: 'File' },
  { value: 'elasticsearch', label: 'Elasticsearch' },
  { value: 'loki', label: 'Loki' },
  { value: 'seq', label: 'Seq' },
]

/** Edit-form state for a served destination; credentials stay blank (they come back masked). */
export function formFromDestination(dest: LogForwardingDestination): LogForwardingForm {
  return {
    ...defaultForm(),
    name: dest.name,
    type: dest.type,
    enabled: dest.enabled,
    url: dest.url ?? '',
    syslog_protocol: dest.syslog_protocol,
    file_path: dest.file_path ?? '',
    username: dest.username ?? '',
    index: dest.index ?? '',
    min_level: dest.min_level,
    batch_size: dest.batch_size,
    batch_timeout: dest.batch_timeout,
  }
}

/** The URL field's example as an i18n key: RFC 2606 example hosts, never a real address. */
function urlPlaceholderKey(type: string): { key: string; params?: Record<string, unknown> } | null {
  const base = 'settings.admin.logForwardingSettings'
  switch (type) {
    case 'syslog':
      return { key: `${base}.urlPlaceholderSyslog` }
    case 'webhook':
      return { key: `${base}.urlPlaceholderWebhook` }
    case 'elasticsearch':
      return { key: `${base}.urlPlaceholderElasticsearch`, params: { port: config.port.elasticsearch } }
    default:
      return null
  }
}

/** The URL field's translated example for a destination type ('' when it has none). */
export function getUrlPlaceholder(type: string, translate: (key: string, params: Record<string, unknown>) => string): string {
  const example = urlPlaceholderKey(type)
  return example ? translate(example.key, example.params ?? {}) : ''
}
