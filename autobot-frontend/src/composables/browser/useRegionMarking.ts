// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { ref, type Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useRegionMarking')

export interface RegionRect {
  x: number
  y: number
  w: number
  h: number
}

export interface PageRegion {
  selector: string
  xpath: string
  rect: RegionRect
  textPreview: string
  role: string
}

export interface SelectedRegion {
  selector: string
  xpath: string
  label: string
}

export interface UseRegionMarkingOptions {
  regions: Ref<PageRegion[]>
  imgRef: Ref<HTMLImageElement | null>
  viewportWidth: Ref<number>
  viewportHeight: Ref<number>
  onRegionsSelected?: (regions: SelectedRegion[]) => void
}

/**
 * Region-marking state for InteractiveScreenshot (#5136).
 *
 * Encapsulates hover, popup, label-input, and selection state plus
 * positioning helpers for region overlays drawn over a screenshot.
 */
export function useRegionMarking(options: UseRegionMarkingOptions) {
  const { regions, imgRef, viewportWidth, viewportHeight, onRegionsSelected } = options

  const hoveredRegion = ref<number | null>(null)
  const selectedRegions = ref<SelectedRegion[]>([])
  const popupRegionIndex = ref<number | null>(null)
  const popupLabel = ref('')

  function regionStyle(rect: RegionRect): Record<string, string> {
    const img = imgRef.value
    if (!img) return {}
    const imgRect = img.getBoundingClientRect()
    const scaleX = imgRect.width / viewportWidth.value
    const scaleY = imgRect.height / viewportHeight.value
    return {
      position: 'absolute',
      left: `${rect.x * scaleX}px`,
      top: `${rect.y * scaleY}px`,
      width: `${rect.w * scaleX}px`,
      height: `${rect.h * scaleY}px`,
      pointerEvents: 'all',
      cursor: 'pointer',
    }
  }

  function popupStyle(rect: RegionRect): Record<string, string> {
    const img = imgRef.value
    if (!img) return {}
    const imgRect = img.getBoundingClientRect()
    const scaleX = imgRect.width / viewportWidth.value
    const scaleY = imgRect.height / viewportHeight.value
    return {
      position: 'absolute',
      left: `${rect.x * scaleX}px`,
      top: `${(rect.y + rect.h) * scaleY + 4}px`,
      zIndex: '50',
    }
  }

  function openPopup(index: number): void {
    popupRegionIndex.value = index
    popupLabel.value = ''
  }

  function saveRegion(index: number | null): void {
    if (index === null || !regions.value) return
    const region = regions.value[index]
    selectedRegions.value.push({
      selector: region.selector,
      xpath: region.xpath,
      label: popupLabel.value || region.textPreview.slice(0, 20),
    })
    logger.debug('Region saved', { selector: region.selector, label: popupLabel.value })
    onRegionsSelected?.([...selectedRegions.value])
    popupRegionIndex.value = null
  }

  return {
    hoveredRegion,
    selectedRegions,
    popupRegionIndex,
    popupLabel,
    regionStyle,
    popupStyle,
    openPopup,
    saveRegion,
  }
}
