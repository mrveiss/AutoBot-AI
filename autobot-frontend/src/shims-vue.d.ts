declare module '*.vue' {
  import { DefineComponent } from 'vue';
  const component: DefineComponent<{}, {}, any>;
  export default component;
}

// Vue Router + vue-i18n type declarations
declare module '@vue/runtime-core' {
  import type { RouteLocationNormalizedLoaded, Router } from 'vue-router';

  interface ComponentCustomProperties {
    $route: RouteLocationNormalizedLoaded;
    $router: Router;
    $t: (key: string, ...args: unknown[]) => string;
  }
}

export {};
