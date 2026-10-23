// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { ErrorInfo } from '@/utils/ApiClient';

/** Pull status, message and parsed body out of a failed Response (moved from ApiClient, #11682). */
export async function extractErrorInfo(response: Response): Promise<ErrorInfo> {
  try {
    const errorData = await response.json();
    const raw = errorData.error || errorData.message || errorData.detail;
    let message: string;
    if (raw == null) message = JSON.stringify(errorData) || 'Unknown error';
    else message = typeof raw === 'string' ? raw : JSON.stringify(raw);
    return { status: response.status, message, details: errorData };
  } catch {
    return {
      status: response.status,
      message: response.statusText || 'Unknown error',
      details: null,
    };
  }
}
