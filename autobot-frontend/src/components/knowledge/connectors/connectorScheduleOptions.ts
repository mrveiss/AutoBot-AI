// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** The schedule choices of the connector dialog, split out of a frozen file (#19714). */
export function connectorScheduleOptions(t: (key: string) => string) {
  return [
    { value: 'manual', label: t('knowledge.connectors.config.scheduleManual'), cron: null },
    { value: '15min', label: t('knowledge.connectors.config.schedule15min'), cron: '*/15 * * * *' },
    { value: 'hourly', label: t('knowledge.connectors.config.scheduleHourly'), cron: '0 * * * *' },
    { value: 'daily', label: t('knowledge.connectors.config.scheduleDaily'), cron: '0 0 * * *' },
    { value: 'weekly', label: t('knowledge.connectors.config.scheduleWeekly'), cron: '0 0 * * 0' }
  ]
}
