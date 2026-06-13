// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Minimal type declarations for the `qrcode` package (#9724).
 *
 * NOTE: `qrcode` is imported by usePairingQR.ts and
 * DevicePairingSettingsPanel.vue (MVA-2993) but was never added to
 * package.json — the dependency must still be installed for the device
 * pairing feature to build/run. This shim only covers the API surface
 * AutoBot uses (toDataURL / toCanvas) so type-checking reflects real usage.
 */
declare module 'qrcode' {
  export interface QRCodeToDataURLOptions {
    width?: number
    margin?: number
    scale?: number
    errorCorrectionLevel?: 'low' | 'medium' | 'quartile' | 'high' | 'L' | 'M' | 'Q' | 'H'
    color?: {
      dark?: string
      light?: string
    }
  }

  export type QRCodeToCanvasOptions = QRCodeToDataURLOptions

  export function toDataURL(
    text: string,
    options?: QRCodeToDataURLOptions
  ): Promise<string>

  export function toCanvas(
    canvas: HTMLCanvasElement,
    text: string,
    options?: QRCodeToCanvasOptions
  ): Promise<HTMLCanvasElement>

  const QRCode: {
    toDataURL: typeof toDataURL
    toCanvas: typeof toCanvas
  }
  export default QRCode
}
