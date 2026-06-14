// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
declare module '*.vue' {
  import { DefineComponent } from 'vue';
  const component: DefineComponent<{}, {}, any>;
  export default component;
}

// Vue Router + vue-i18n type declarations
// Vue 3.5+ requires augmenting 'vue' instead of '@vue/runtime-core'
declare module 'vue' {
  interface ComponentCustomProperties {
    $route: import('vue-router').RouteLocationNormalizedLoaded;
    $router: import('vue-router').Router;
    $t: (key: string, ...args: unknown[]) => string;
  }
}

export {};

// Compile-time feature flag defines injected by Vite (#3009)
declare const __FEATURE_VOICE__: boolean
declare const __FEATURE_VNC__: boolean
declare const __FEATURE_BROWSER__: boolean
