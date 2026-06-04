// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2026 mrveiss
// Author: mrveiss
/**
 * useWebResearch — API calls for the 4-tab Web Research panel (MVA-344).
 *
 * Endpoints:
 *   POST /knowledge/scrape   → ScrapeResponse
 *   POST /knowledge/crawl    → CrawlResponse   (long-running, pair with usePollingJob)
 *   POST /knowledge/site-map → SiteMapResponse (long-running, pair with usePollingJob)
 *   POST /knowledge/extract  → ExtractResponse
 */

import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'

// ── Scrape ─────────────────────────────────────────────────────────────────

export interface ScrapeRequest {
  url: string
  render?: 'auto' | 'fast' | 'playwright'
  ingest?: boolean
  format?: 'markdown' | 'html' | 'json'
}

export interface ScrapeMetadata {
  title: string
  fetched_at: string
}

export interface ScrapeResponse {
  url: string
  markdown?: string
  html?: string
  metadata: ScrapeMetadata
  indexed: boolean
}

// ── Crawl ──────────────────────────────────────────────────────────────────

export interface CrawlRequest {
  seeds: string[]
  max_depth?: number
  max_pages?: number
  respect_robots?: boolean
  ingest?: boolean
  same_origin?: boolean
  render?: 'auto' | 'fast' | 'playwright'
}

export interface CrawlPageEntry {
  url: string
  markdown: string
  depth: number
  success: boolean
}

export interface CrawlResponse {
  pages: CrawlPageEntry[]
  count: number
  indexed: boolean
}

// ── Site Map ───────────────────────────────────────────────────────────────

export interface SiteMapRequest {
  domain: string
  max_urls?: number
  respect_robots?: boolean
}

export interface SiteMapUrlEntry {
  url: string
  title: string | null
  depth: number
}

export interface SiteMapResponse {
  domain: string
  source: string
  urls: SiteMapUrlEntry[]
  count: number
}

// ── Extract ────────────────────────────────────────────────────────────────

export interface ExtractRequest {
  url: string
  schema: Record<string, unknown>
  render?: 'auto' | 'fast' | 'playwright'
  ingest?: boolean
}

export interface ExtractResponse {
  url: string
  data: Record<string, unknown>
  schema_valid: boolean
}

// ── Composable ─────────────────────────────────────────────────────────────

export function useWebResearch() {
  const base = getApiBase()

  function scrapePage(req: ScrapeRequest): Promise<ScrapeResponse> {
    return apiClient.post<ScrapeResponse>(`${base}/knowledge/scrape`, req)
  }

  function crawlSite(req: CrawlRequest): Promise<CrawlResponse> {
    return apiClient.post<CrawlResponse>(`${base}/knowledge/crawl`, req)
  }

  function findPages(req: SiteMapRequest): Promise<SiteMapResponse> {
    return apiClient.post<SiteMapResponse>(`${base}/knowledge/site-map`, req)
  }

  function extractData(req: ExtractRequest): Promise<ExtractResponse> {
    return apiClient.post<ExtractResponse>(`${base}/knowledge/extract`, req)
  }

  return { scrapePage, crawlSite, findPages, extractData }
}
