declare module '*.vue' {
  import { DefineComponent } from 'vue';
  const component: DefineComponent<{}, {}, any>;
  export default component;
}

// Vue Router type declarations
declare module '@vue/runtime-core' {
  import type { RouteLocationNormalizedLoaded, Router } from 'vue-router';

  interface ComponentCustomProperties {
    $route: RouteLocationNormalizedLoaded;
    $router: Router;
  }
}

export {};
