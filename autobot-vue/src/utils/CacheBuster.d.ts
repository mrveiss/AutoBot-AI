/**
 * Type definitions for CacheBuster utility
 */

export interface CacheBustParams {
  _cb: number | string;
  _sid: string;
  _req: number;
  _ts: number;
}

export interface CacheBustHeaders {
  'Cache-Control': string;
  'Pragma': string;
  'Expires': string;
  'X-Cache-Bust': number | string;
  'X-Session-ID': string;
  'X-Request-ID': number;
  'X-Timestamp': number;
  'If-None-Match': string;
  'If-Modified-Since': string;
}

export interface CachePoisoningIndicators {
  staleManifest: boolean;
  missingAssets: boolean;
  versionMismatch: boolean;
}

declare class CacheBuster {
  buildId: number | string;
  sessionId: string;
  requestCounter: number;
  lastConnectionErrorLog: number;
  connectionErrorCount: number;
  connectionErrorCooldown: number;

  generateSessionId(): string;
  getCacheBustParams(): CacheBustParams;
  bustUrl(url: string): string;
  getBustHeaders(): CacheBustHeaders;
  forceCriticalResourceReload(): void;
  clearAllCaches(): Promise<void>;
  detectCachePoisoning(): boolean;
  checkManifestStaleness(): boolean;
  checkMissingAssets(): boolean;
  checkVersionMismatch(): boolean;
  handleCachePoisoning(): Promise<void>;
  setupCacheErrorMonitoring(): void;
  initialize(): void;
}

export const cacheBuster: CacheBuster;
export default CacheBuster;
