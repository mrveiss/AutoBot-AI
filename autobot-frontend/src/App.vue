<template>
  <div id="app" class="h-screen bg-autobot-bg-primary flex flex-col overflow-hidden">
    <!-- Skip Navigation Links -->
    <div v-if="showAuthChrome" class="skip-links">
      <a href="#main-content" class="skip-link sr-only-focusable">{{ $t('nav.skipToContent') }}</a>
      <a href="#navigation" class="skip-link sr-only-focusable">{{ $t('nav.skipToNavigation') }}</a>
    </div>

    <!-- Header - Issue #901: Professional solid color (no gradients) -->
    <!-- Hide navigation bar on login page -->
    <header v-if="showAuthChrome" class="bg-autobot-bg-secondary border-b border-autobot-border relative z-30" style="min-height: 56px; height: auto;">
      <div class="max-w-full mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex items-center justify-between" style="min-height: 56px; height: auto;">
          <!-- Logo/Brand with System Status -->
          <div class="shrink-0 flex items-center">
            <button
              @click="toggleSystemStatus"
              class="flex items-center gap-3 hover:bg-autobot-bg-tertiary rounded-md px-2 py-1 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-autobot-primary"
              :title="getSystemStatusTooltip()"
              :aria-label="getSystemStatusAriaLabel()"
            >
              <div class="relative w-8 h-8 bg-white rounded flex items-center justify-center">
                <span class="text-slate-800 font-bold text-sm font-mono">AB</span>
                <!-- System status indicator dot -->
                <div
                  :class="{
                    'bg-green-400': systemStatus.isHealthy && !systemStatus.hasIssues,
                    'bg-yellow-400': !systemStatus.isHealthy && !systemStatus.hasIssues,
                    'bg-red-400': systemStatus.hasIssues,
                    'animate-pulse': systemStatus.hasIssues
                  }"
                  class="absolute -top-1 -right-1 w-3 h-3 rounded-full border-2 border-white"
                  aria-hidden="true"
                ></div>
              </div>
              <span class="text-autobot-text-primary font-bold text-lg hidden sm:block">AutoBot</span>
            </button>
          </div>

          <!-- Desktop Navigation -->
          <nav id="navigation" class="hidden lg:block" role="navigation" :aria-label="$t('nav.mainNavigation')">
            <div class="hidden lg:flex items-center gap-8">
              <div ref="navContainerRef" class="flex items-center gap-4">
                <template v-for="item in visibleNavItems" :key="item.to">
                <router-link
                  :to="item.to"
                  data-nav-item
                  :class="{
                    'bg-autobot-primary text-white': $route.path.startsWith(item.to),
                    'text-autobot-text-primary hover:bg-autobot-bg-tertiary': !$route.path.startsWith(item.to)
                  }"
                  class="px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 shrink-0"
                >
                  <div class="flex items-center gap-1">
                    <svg class="w-4 h-4" :fill="item.iconStroke ? 'none' : 'currentColor'" :stroke="item.iconStroke ? 'currentColor' : undefined" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                      <template v-if="item.iconPaths">
                        <path v-for="(p, pi) in item.iconPaths" :key="pi" :d="p" :fill-rule="item.iconRule" :clip-rule="item.iconRule"></path>
                      </template>
                      <path v-else :d="item.icon" :fill-rule="item.iconRule" :clip-rule="item.iconRule" :stroke-linecap="item.iconStroke ? 'round' : undefined" :stroke-linejoin="item.iconStroke ? 'round' : undefined" :stroke-width="item.iconStroke ? '2' : undefined"></path>
                    </svg>
                    <span>{{ $t(item.labelKey) }}</span>
                  </div>
                </router-link>
                </template>

                <NavOverflowMenu
                  v-if="overflowNavItems.length > 0"
                  :items="overflowNavItems"
                />

                <!-- SLM Admin: external link (Issue #729, #8753) -->
                <div class="flex items-center shrink-0">
                  <div class="w-px h-5 bg-autobot-border mx-1" aria-hidden="true"></div>
                  <a
                    :href="slmAdminUrl"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="px-3 py-2 rounded text-sm font-medium transition-colors duration-150 text-autobot-text-secondary hover:text-autobot-text-primary hover:bg-autobot-bg-tertiary border border-transparent hover:border-autobot-border"
                    :title="$t('nav.slmAdminTitle')"
                    :aria-label="$t('nav.slmAdminTitle')"
                  >
                    <div class="flex items-center gap-1">
                      <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                        <path fill-rule="evenodd" d="M2 5a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm3.293 1.293a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 01-1.414-1.414L7.586 10 5.293 7.707a1 1 0 010-1.414zM11 12a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd"></path>
                      </svg>
                      <span>{{ $t('nav.slmAdmin') }}</span>
                      <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                        <path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z"></path>
                        <path d="M5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-3a1 1 0 10-2 0v3H5V7h3a1 1 0 000-2H5z"></path>
                      </svg>
                    </div>
                  </a>
                </div>
              </div>
            </div>
          </nav>

          <!-- Right side - Status and controls -->
          <div class="flex items-center gap-4">
            <!-- User Profile Dropdown (GH#8748: surfaces settings/admin items moved from primary nav) -->
            <div v-if="userStore.isAuthenticated" class="relative hidden sm:block" ref="profileDropdownRef">
              <button
                @click="showProfileDropdown = !showProfileDropdown"
                class="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium text-autobot-text-primary hover:bg-autobot-bg-tertiary transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-autobot-primary"
                :title="$t('nav.profileSettings')"
                :aria-label="$t('nav.profileSettings')"
                :aria-expanded="showProfileDropdown"
                aria-haspopup="menu"
              >
                <div class="w-6 h-6 rounded-full bg-autobot-primary flex items-center justify-center text-white text-xs font-bold shrink-0">
                  {{ displayUsername?.charAt(0)?.toUpperCase() || 'U' }}
                </div>
                <span class="max-w-[120px] truncate">{{ displayUsername || $t('nav.profile') }}</span>
                <svg class="w-3 h-3" :class="showProfileDropdown ? 'rotate-180' : ''" fill="none" stroke="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8l5 5 5-5" />
                </svg>
              </button>

              <Teleport to="body">
                <div
                  v-if="showProfileDropdown"
                  ref="profileDropdownMenuRef"
                  :style="profileDropdownStyle"
                  class="fixed z-50 bg-autobot-bg-secondary border border-autobot-border rounded-md shadow-lg py-1 min-w-48"
                  role="menu"
                >
                  <!-- Open full profile modal -->
                  <button
                    role="menuitem"
                    class="flex items-center gap-2 w-full text-start px-3 py-2 text-sm transition-colors duration-150 hover:bg-autobot-bg-tertiary text-autobot-text-primary"
                    @click="showProfileModal = true; showProfileDropdown = false"
                  >
                    <div class="w-4 h-4 rounded-full bg-autobot-primary flex items-center justify-center text-white text-[10px] font-bold shrink-0">
                      {{ displayUsername?.charAt(0)?.toUpperCase() || 'U' }}
                    </div>
                    <span>{{ $t('nav.profileSettings') }}</span>
                  </button>

                  <hr class="my-1 border-autobot-border" />

                  <!-- Settings & Tools section -->
                  <p class="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-autobot-text-secondary">{{ $t('nav.settingsAndTools') }}</p>
                  <router-link
                    v-for="item in profileMenuItems"
                    :key="item.to"
                    :to="item.to"
                    role="menuitem"
                    class="flex items-center gap-2 px-3 py-2 text-sm transition-colors duration-150 hover:bg-autobot-bg-tertiary text-autobot-text-primary"
                    @click="showProfileDropdown = false"
                  >
                    <svg class="w-4 h-4 shrink-0" :fill="item.iconStroke ? 'none' : 'currentColor'" :stroke="item.iconStroke ? 'currentColor' : undefined" viewBox="0 0 20 20" aria-hidden="true">
                      <path :d="item.icon" :fill-rule="item.iconRule" :clip-rule="item.iconRule" :stroke-linecap="item.iconStroke ? 'round' : undefined" :stroke-linejoin="item.iconStroke ? 'round' : undefined" :stroke-width="item.iconStroke ? '2' : undefined" />
                    </svg>
                    <span>{{ $t(item.labelKey) }}</span>
                  </router-link>

                  <!-- Admin section (admin-only) -->
                  <template v-if="userStore.isAdmin">
                    <hr class="my-1 border-autobot-border" />
                    <p class="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-autobot-text-secondary">{{ $t('nav.adminPanel') }}</p>
                    <router-link
                      v-for="item in adminMenuItems"
                      :key="item.to"
                      :to="item.to"
                      role="menuitem"
                      class="flex items-center gap-2 px-3 py-2 text-sm transition-colors duration-150 hover:bg-autobot-bg-tertiary text-autobot-text-primary"
                      @click="showProfileDropdown = false"
                    >
                      <svg class="w-4 h-4 shrink-0" :fill="item.iconStroke ? 'none' : 'currentColor'" :stroke="item.iconStroke ? 'currentColor' : undefined" viewBox="0 0 20 20" aria-hidden="true">
                        <path :d="item.icon" :fill-rule="item.iconRule" :clip-rule="item.iconRule" :stroke-linecap="item.iconStroke ? 'round' : undefined" :stroke-linejoin="item.iconStroke ? 'round' : undefined" :stroke-width="item.iconStroke ? '2' : undefined" />
                      </svg>
                      <span>{{ $t(item.labelKey) }}</span>
                    </router-link>
                  </template>
                </div>
              </Teleport>
            </div>

            <!-- Dark Mode Toggle -->
            <DarkModeToggle />

            <!-- Language Switcher -->
            <LanguageSwitcher />

            <!-- Mobile menu button -->
            <button
              @click="toggleMobileNav"
              class="lg:hidden inline-flex items-center justify-center p-2 rounded text-autobot-text-primary hover:bg-autobot-bg-tertiary focus:outline-none focus:ring-2 focus:ring-autobot-primary"
              aria-controls="mobile-nav"
              :aria-expanded="showMobileNav"
            >
              <span class="sr-only">{{ $t('nav.openMainMenu') }}</span>
              <!-- Hamburger / X icon toggle (#1804) -->
              <svg v-if="!showMobileNav" class="block h-6 w-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
              <svg v-else class="block h-6 w-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- Mobile Navigation Panel -->
      <Transition
        enter-active-class="transition duration-300 ease-out"
        enter-from-class="transform -translate-y-full opacity-0"
        enter-to-class="transform translate-y-0 opacity-100"
        leave-active-class="transition duration-200 ease-in"
        leave-from-class="transform translate-y-0 opacity-100"
        leave-to-class="transform -translate-y-full opacity-0"
      >
        <div
          v-show="showMobileNav"
          id="mobile-nav"
          class="lg:hidden absolute top-full left-0 right-0 bg-autobot-bg-secondary border-b border-autobot-border shadow-lg z-20"
        >
          <div class="px-4 py-3 space-y-2">
            <template v-for="item in navItems" :key="item.to">
            <router-link
              v-if="!item.adminOnly || userStore.isAdmin"
              :to="item.to"
              @click="closeMobileNav"
              :class="{
                'bg-autobot-primary text-white': $route.path.startsWith(item.to),
                'text-autobot-text-primary hover:bg-autobot-bg-tertiary': !$route.path.startsWith(item.to)
              }"
              class="w-full text-start px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 block"
            >
              <div class="flex items-center gap-2">
                <svg class="w-4 h-4" :fill="item.iconStroke ? 'none' : 'currentColor'" :stroke="item.iconStroke ? 'currentColor' : undefined" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                  <template v-if="item.iconPaths">
                    <path v-for="(p, pi) in item.iconPaths" :key="pi" :d="p" :fill-rule="item.iconRule" :clip-rule="item.iconRule"></path>
                  </template>
                  <path v-else :d="item.icon" :fill-rule="item.iconRule" :clip-rule="item.iconRule" :stroke-linecap="item.iconStroke ? 'round' : undefined" :stroke-linejoin="item.iconStroke ? 'round' : undefined" :stroke-width="item.iconStroke ? '2' : undefined"></path>
                </svg>
                <span>{{ $t(item.labelKey) }}</span>
              </div>
            </router-link>
            </template>

            <!-- SLM Admin: external link (Issue #729, #8753) -->
            <div class="border-t border-autobot-border pt-2 mt-1">
              <a
                :href="slmAdminUrl"
                target="_blank"
                rel="noopener noreferrer"
                @click="closeMobileNav"
                class="w-full text-start px-3 py-2 rounded text-sm font-medium transition-colors duration-150 block text-autobot-text-secondary hover:text-autobot-text-primary hover:bg-autobot-bg-tertiary border border-transparent hover:border-autobot-border"
                :aria-label="$t('nav.slmAdminTitle')"
                :title="$t('nav.slmAdminTitle')"
              >
                <div class="flex items-center gap-2">
                  <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                    <path fill-rule="evenodd" d="M2 5a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm3.293 1.293a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 01-1.414-1.414L7.586 10 5.293 7.707a1 1 0 010-1.414zM11 12a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd"></path>
                  </svg>
                  <span>{{ $t('nav.slmAdmin') }}</span>
                  <svg class="w-4 h-4 ml-auto" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                    <path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z"></path>
                    <path d="M5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-3a1 1 0 10-2 0v3H5V7h3a1 1 0 000-2H5z"></path>
                  </svg>
                </div>
              </a>
            </div>

                        <!-- Language Switcher -->
            <LanguageSwitcher :mobile="true" />

            <!-- GH#8748: Settings & Tools (moved from primary nav) -->
            <div class="border-t border-autobot-border pt-2 mt-1">
              <p class="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-autobot-text-secondary">{{ $t('nav.settingsAndTools') }}</p>
              <router-link
                v-for="item in profileMenuItems"
                :key="item.to"
                :to="item.to"
                @click="closeMobileNav"
                :class="{
                  'bg-autobot-primary text-white': $route.path.startsWith(item.to),
                  'text-autobot-text-primary hover:bg-autobot-bg-tertiary': !$route.path.startsWith(item.to)
                }"
                class="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200"
              >
                <svg class="w-4 h-4 shrink-0" :fill="item.iconStroke ? 'none' : 'currentColor'" :stroke="item.iconStroke ? 'currentColor' : undefined" viewBox="0 0 20 20" aria-hidden="true">
                  <path :d="item.icon" :fill-rule="item.iconRule" :clip-rule="item.iconRule" :stroke-linecap="item.iconStroke ? 'round' : undefined" :stroke-linejoin="item.iconStroke ? 'round' : undefined" :stroke-width="item.iconStroke ? '2' : undefined" />
                </svg>
                <span>{{ $t(item.labelKey) }}</span>
              </router-link>
            </div>

            <!-- GH#8748: Admin tools (moved from primary nav, admin-only) -->
            <template v-if="userStore.isAdmin">
              <div class="border-t border-autobot-border pt-2 mt-1">
                <p class="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-autobot-text-secondary">{{ $t('nav.adminPanel') }}</p>
                <router-link
                  v-for="item in adminMenuItems"
                  :key="item.to"
                  :to="item.to"
                  @click="closeMobileNav"
                  :class="{
                    'bg-autobot-primary text-white': $route.path.startsWith(item.to),
                    'text-autobot-text-primary hover:bg-autobot-bg-tertiary': !$route.path.startsWith(item.to)
                  }"
                  class="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200"
                >
                  <svg class="w-4 h-4 shrink-0" :fill="item.iconStroke ? 'none' : 'currentColor'" :stroke="item.iconStroke ? 'currentColor' : undefined" viewBox="0 0 20 20" aria-hidden="true">
                    <path :d="item.icon" :fill-rule="item.iconRule" :clip-rule="item.iconRule" :stroke-linecap="item.iconStroke ? 'round' : undefined" :stroke-linejoin="item.iconStroke ? 'round' : undefined" :stroke-width="item.iconStroke ? '2' : undefined" />
                  </svg>
                  <span>{{ $t(item.labelKey) }}</span>
                </router-link>
              </div>
            </template>

            <!-- Profile Settings (Issue #950) -->
            <button
              v-if="userStore.isAuthenticated"
              @click="showProfileModal = true; closeMobileNav()"
              class="w-full text-start px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 text-autobot-text-primary hover:bg-autobot-bg-tertiary"
            >
              <div class="flex items-center gap-2">
                <div class="w-4 h-4 rounded-full bg-autobot-primary flex items-center justify-center text-white text-xs font-bold">
                  {{ displayUsername?.charAt(0)?.toUpperCase() || 'U' }}
                </div>
                <span>{{ $t('nav.profileSettings') }}</span>
              </div>
            </button>
          </div>
        </div>
      </Transition>

      <!-- Click overlay to close mobile nav -->
      <div
        v-if="showMobileNav"
        @click="showMobileNav = false"
        class="lg:hidden fixed inset-0 bg-black/25 z-10"
      ></div>
    </header>

    <!-- System Status Modal -->
    <Teleport to="body">
      <div
        v-if="showSystemStatus"
        class="fixed inset-0 z-50 overflow-y-auto"
        @click="showSystemStatus = false"
      >
        <div class="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
          <div class="fixed inset-0 bg-black/75 transition-opacity"></div>

          <div
            @click.stop
            class="relative transform overflow-hidden rounded-lg bg-autobot-bg-card px-4 pb-4 pt-5 text-start shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-lg sm:p-6"
          >
            <!-- Header -->
            <div class="flex items-center justify-between border-b border-autobot-border pb-3 mb-4">
              <h3 class="text-lg font-medium text-autobot-text-primary flex items-center">
                <div class="w-6 h-6 bg-autobot-primary rounded flex items-center justify-center me-2">
                  <span class="text-white text-xs font-bold">AB</span>
                </div>
                {{ $t('nav.systemStatus') }}
              </h3>
              <button
                @click="showSystemStatus = false"
                class="rounded-md text-autobot-text-muted hover:text-autobot-text-primary focus:outline-none focus:ring-2 focus:ring-autobot-primary"
                :aria-label="$t('common.close')"
              >
                <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <!-- System Overview -->
            <div class="mb-4">
              <div
                :class="{
                  'bg-green-900/20 border-green-700': systemStatus.isHealthy && !systemStatus.hasIssues,
                  'bg-yellow-900/20 border-yellow-700': !systemStatus.isHealthy && !systemStatus.hasIssues,
                  'bg-red-900/20 border-red-700': systemStatus.hasIssues
                }"
                class="rounded-lg border p-3 flex items-center"
              >
                <div
                  :class="{
                    'bg-green-400': systemStatus.isHealthy && !systemStatus.hasIssues,
                    'bg-yellow-400': !systemStatus.isHealthy && !systemStatus.hasIssues,
                    'bg-red-400': systemStatus.hasIssues,
                    'animate-pulse': systemStatus.hasIssues
                  }"
                  class="w-3 h-3 rounded-full me-3"
                ></div>
                <div>
                  <p class="font-medium text-autobot-text-primary">{{ getSystemStatusText() }}</p>
                  <p class="text-sm text-autobot-text-secondary">{{ getSystemStatusDescription() }}</p>
                </div>
              </div>
            </div>

            <!-- Services Status -->
            <div class="space-y-3">
              <h4 class="font-medium text-autobot-text-primary">{{ $t('nav.services') }}</h4>
              <div class="space-y-2">
                <div
                  v-for="service in systemServices"
                  :key="service.name"
                  class="flex items-center justify-between p-2 rounded border"
                >
                  <div class="flex items-center">
                    <div
                      :class="{
                        'bg-green-400': service.status === 'healthy',
                        'bg-yellow-400': service.status === 'warning',
                        'bg-red-400': service.status === 'error'
                      }"
                      class="w-2 h-2 rounded-full me-2"
                    ></div>
                    <span class="text-sm font-medium">{{ service.name }}</span>
                  </div>
                  <span
                    :class="{
                      'text-green-600': service.status === 'healthy',
                      'text-yellow-600': service.status === 'warning',
                      'text-red-600': service.status === 'error'
                    }"
                    class="text-xs"
                  >
                    {{ service.statusText }}
                  </span>
                </div>
              </div>
            </div>

            <!-- Action Buttons -->
            <div class="mt-6 flex justify-between">
              <button
                @click="refreshSystemStatus"
                class="inline-flex items-center px-3 py-2 border border-autobot-border shadow-sm text-sm leading-4 font-medium rounded-md text-autobot-text-primary bg-autobot-bg-secondary hover:bg-autobot-bg-tertiary focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-autobot-primary"
              >
                <svg class="w-4 h-4 me-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
                </svg>
                {{ $t('common.refresh') }}
              </button>
              <button
                @click="showSystemStatus = false"
                class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-autobot-primary hover:bg-autobot-primary-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-autobot-primary"
              >
                {{ $t('common.close') }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Profile Modal (Issue #950) -->
    <ProfileModal
      :is-open="showProfileModal"
      @close="showProfileModal = false"
    />

    <!-- System Status Notifications (limit to last 5 to prevent teleport accumulation) -->
    <SystemStatusNotification
      v-for="notif in (appStore?.systemNotifications || []).filter(n => n.visible).slice(-5)"
      :key="`notification-${notif.id}`"
      :visible="notif.visible"
      :severity="notif.severity"
      :title="notif.title"
      :message="notif.message"
      :status-details="notif.statusDetails"
      :allow-dismiss="true"
      :show-details="notif.statusDetails ? true : false"
      :auto-hide="0"
      @dismiss="() => appStore?.removeSystemNotification(notif.id)"
      @expired="() => appStore?.removeSystemNotification(notif.id)"
      @hide="() => appStore?.removeSystemNotification(notif.id)"
      @remove="() => appStore?.removeSystemNotification(notif.id)"
    />

    <!-- CAPTCHA Human-in-the-Loop Notification (Issue #206) -->
    <CaptchaNotification />

    <!-- Toast Notifications Container (Issue #502) -->
    <ToastContainer />

    <!-- Host Selection Dialog for Agent SSH Actions -->
    <HostSelectionDialog
      :show="hostSelectionState.showDialog"
      :command="hostSelectionState.pendingRequest?.command"
      :purpose="hostSelectionState.pendingRequest?.purpose"
      :request-id="hostSelectionState.pendingRequest?.requestId"
      @selected="onHostSelected"
      @cancelled="onHostSelectionCancelled"
      @close="onHostSelectionClose"
    />

    <!-- Offline mode banner — #3275 -->
    <OfflineBanner />

    <!-- Main Content Area with Router -->
    <main id="main-content" class="flex-1 min-h-0 overflow-hidden" role="main">
      <LoadingBoundary
        :loading="isLoading"
        :on-retry="clearAllCaches"
        :timeout-ms="15000"
        @loading-timeout="handleLoadingTimeout"
        class="h-full"
      >
        <!-- Use router-view for all content to enable proper sub-routing -->
        <ErrorBoundary>
          <router-view class="h-full" />
        </ErrorBoundary>
      </LoadingBoundary>
    </main>

    <!-- Footer: About link (hidden on public routes and routes with hideFooter meta) -->
    <footer v-if="showAuthChrome && !hideFooter" class="flex-shrink-0 flex justify-center py-1 border-t border-autobot-border/30">
      <router-link to="/about" class="text-xs text-autobot-text-muted hover:text-autobot-text-secondary transition-colors">
        {{ $t('nav.about') }}
      </router-link>
    </footer>
  </div>

  <!-- Issue #729: RUM Dashboard moved to slm-admin -->
  <!-- ElevationDialog removed: feature not yet implemented (#920) -->

  <!-- Global confirm dialog (#6092) -->
  <ConfirmDialog />
</template>

<script lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted, defineAsyncComponent } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useAppStore } from '@/stores/useAppStore'
import { useUserStore } from '@/stores/useUserStore'
import { useChatStore } from '@/stores/useChatStore'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useSystemStatus } from '@/composables/useSystemStatus'
import { useHostSelection } from '@/composables/useHostSelection';
import { useNavOverflow } from '@/composables/useNavOverflow'
import NavOverflowMenu from '@/components/layout/NavOverflowMenu.vue'
import { createLogger } from '@/utils/debugUtils'
import { cacheBuster } from '@/utils/CacheBuster.js';
import { optimizedHealthMonitor } from '@/utils/OptimizedHealthMonitor.js';
import { initializeNotificationBridge } from '@/utils/notificationBridge';
import { smartMonitoringController, getAdaptiveInterval } from '@/config/OptimizedPerformance.js';
import { clearAllSystemNotifications, resetHealthMonitor } from '@/utils/ClearNotifications.js';
import { getSLMAdminUrl } from '@/config/ssot-config';
import { navItems, profileMenuItems, adminMenuItems } from '@/config/navItems';
import SystemStatusNotification from '@/components/ui/SystemStatusNotification.vue';
import CaptchaNotification from '@/components/research/CaptchaNotification.vue';
import ToastContainer from '@/components/ui/ToastContainer.vue';
import HostSelectionDialog from '@/components/ui/HostSelectionDialog.vue';
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue';
import LoadingBoundary from '@/components/ui/LoadingBoundary.vue';
import ProfileModal from '@/components/profile/ProfileModal.vue';
import ErrorBoundary from '@/components/common/ErrorBoundary.vue'
import OfflineBanner from '@/components/ui/OfflineBanner.vue';

const logger = createLogger('App');

export default {
  name: 'App',

  components: {
    SystemStatusNotification,
    OfflineBanner,
    CaptchaNotification,
    ToastContainer,
    HostSelectionDialog,
    ConfirmDialog,
    LoadingBoundary,
    ProfileModal,
    ErrorBoundary,
    NavOverflowMenu,
    DarkModeToggle: defineAsyncComponent(() => import('@/components/ui/DarkModeToggle.vue')),
    LanguageSwitcher: defineAsyncComponent(() => import('@/components/layout/LanguageSwitcher.vue')),
  },

  setup() {
    const { t } = useI18n()

    // Store references
    const appStore = useAppStore();
    const userStore = useUserStore();
    const chatStore = useChatStore();
    const knowledgeStore = useKnowledgeStore();
    const router = useRouter();
    const route = useRoute();

    // Initialize user preferences system (Issue #753)
    import('@/composables/usePreferences').then(({ usePreferences }) => {
      const prefs = usePreferences();
      logger.debug('User preferences system initialized');

      // Cross-device language sync: load stored language from backend after login (#1675)
      watch(
        () => userStore.isAuthenticated,
        async (authenticated) => {
          if (authenticated) {
            await prefs.loadLanguageFromBackend();
          }
        },
        { immediate: true }
      );
    });

    // FIXED: Use useSystemStatus composable instead of duplicate logic
    const {
      systemStatus,
      systemServices,
      showSystemStatus,
      getSystemStatusTooltip,
      getSystemStatusAriaLabel,
      getSystemStatusText,
      getSystemStatusDescription,
      toggleSystemStatus,
      refreshSystemStatus,
      updateSystemStatus
    } = useSystemStatus()

    // Host selection composable for agent SSH actions
    const {
      showDialog: hostSelectionShowDialog,
      pendingRequest: hostSelectionPendingRequest,
      handleHostSelected,
      handleDialogCancelled,
      handleDialogClose
    } = useHostSelection()

    // Create reactive state object for host selection
    const hostSelectionState = computed(() => ({
      showDialog: hostSelectionShowDialog.value,
      pendingRequest: hostSelectionPendingRequest.value
    }))

    // Host selection event handlers
    const onHostSelected = (result: { host: any; rememberChoice: boolean }) => {
      handleHostSelected(result)
    }

    const onHostSelectionCancelled = () => {
      handleDialogCancelled()
    }

    const onHostSelectionClose = () => {
      handleDialogClose()
    }

    // Reactive data (non-status related)
    const showMobileNav = ref(false);
    const showProfileModal = ref(false);

    // GH#8748: profile dropdown (settings/admin items moved from primary nav)
    const showProfileDropdown = ref(false);
    const profileDropdownRef = ref<HTMLElement | null>(null);
    const profileDropdownMenuRef = ref<HTMLElement | null>(null);
    const profileDropdownStyle = ref<Record<string, string>>({});

    function positionProfileDropdown() {
      if (!profileDropdownRef.value) return;
      const rect = profileDropdownRef.value.getBoundingClientRect();
      const menuWidth = profileDropdownMenuRef.value?.getBoundingClientRect().width || 192;
      const spaceRight = window.innerWidth - rect.left;
      const left = spaceRight < menuWidth ? rect.right - menuWidth : rect.left;
      profileDropdownStyle.value = {
        top: `${rect.bottom + 4}px`,
        left: `${Math.max(0, left)}px`,
      };
    }

    function onProfileDropdownClickOutside(event: MouseEvent) {
      const target = event.target as Node;
      if (
        !profileDropdownRef.value?.contains(target) &&
        !profileDropdownMenuRef.value?.contains(target)
      ) {
        showProfileDropdown.value = false;
      }
    }

    watch(showProfileDropdown, async (open) => {
      if (open) {
        positionProfileDropdown();
        await nextTick();
        positionProfileDropdown();
        document.addEventListener('click', onProfileDropdownClickOutside, true);
      } else {
        document.removeEventListener('click', onProfileDropdownClickOutside, true);
      }
    });

    let notificationCleanup: number | null = null;

    // Computed properties
    const isLoading = computed(() => appStore?.isLoading || false);
    const hasErrors = computed(() => false); // No errors property in store
    const isPublicRoute = computed(() => !!route.meta.isPublic);
    const showAuthChrome = computed(() => userStore.isAuthenticated && !isPublicRoute.value);
    const hideFooter = computed(() => !!route.meta.hideFooter);

    // Methods
    const toggleMobileNav = () => {
      showMobileNav.value = !showMobileNav.value;
    };

    const closeMobileNav = () => {
      showMobileNav.value = false;
    };

    const closeNavbarOnClickOutside = (event: MouseEvent) => {
      // Close mobile nav when clicking outside
      const target = event.target as HTMLElement | null;
      if (showMobileNav.value && target && !target.closest('#mobile-nav') && !target.closest('[aria-controls="mobile-nav"]')) {
        showMobileNav.value = false;
      }
    };

    const closeNavbarOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && showMobileNav.value) {
        showMobileNav.value = false;
      }
    };

    const clearAllCaches = async () => {
      try {
        // Clear all stores
        if (appStore && typeof appStore.clearAllNotifications === 'function') {
          appStore.clearAllNotifications();
        }
        if (chatStore && typeof chatStore.clearAllSessions === 'function') {
          chatStore.clearAllSessions();
        }
        // Knowledge store doesn't have clearCache method
        // Clear by refreshing stats
        if (knowledgeStore && typeof knowledgeStore.refreshStats === 'function') {
          await knowledgeStore.refreshStats();
        }

        // Reload the page
        window.location.reload();
      } catch (error) {
        logger.error('Error clearing caches:', error);
      }
    };

    const handleGlobalError = (error: Error) => {
      logger.error('Global error:', error);
      if (appStore && typeof appStore.addSystemNotification === 'function') {
        appStore.addSystemNotification({
          severity: 'error',
          title: t('nav.applicationError'),
          message: error.message || t('nav.unexpectedError')
        });
      }
    };

    // Named handlers for global error listeners (#2849)
    const handleWindowError = (event: ErrorEvent) => {
      handleGlobalError(event.error || event);
    };
    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      handleGlobalError(event.reason);
    };

    // Unified loading event handlers
    const handleLoadingComplete = () => {
      logger.debug('Loading completed successfully');
      if (appStore && typeof appStore.setLoading === 'function') {
        appStore.setLoading(false);
      }
    };

    const handleLoadingError = (error: string | Error) => {
      logger.error('Loading error:', error);
      handleGlobalError(error instanceof Error ? error : new Error(String(error)));
    };

    const handleLoadingTimeout = () => {
      logger.warn('Loading timed out - continuing with available content');
      if (appStore && typeof appStore.addSystemNotification === 'function') {
        appStore.addSystemNotification({
          severity: 'warning',
          title: t('nav.loadingTimeout'),
          message: t('nav.loadingTimeoutMessage')
        });
      }
    };

    // OPTIMIZED: Intelligent system health monitoring
    const startOptimizedHealthCheck = () => {
      logger.debug('Starting optimized health monitoring system...');

      // Listen for health changes from optimized monitor
      optimizedHealthMonitor.onHealthChange((healthData) => {
        // Update app store with health status
        if (appStore && typeof appStore.setBackendStatus === 'function') {
          const backendStatus = healthData.status.backend;

          // Determine status text based on backend health
          let statusText = 'Disconnected';
          let statusClass: 'success' | 'warning' | 'error' = 'error';

          if (backendStatus === 'healthy') {
            statusText = 'Connected';
            statusClass = 'success';
          } else if (backendStatus === 'degraded') {
            statusText = 'Degraded';
            statusClass = 'warning';
          }

          appStore.setBackendStatus({
            text: statusText,
            class: statusClass
          });
        }

        // Update smart monitoring controller (filter out 'unknown' state)
        const healthState = healthData.status.overall;
        if (healthState !== 'unknown') {
          smartMonitoringController.setSystemHealth(healthState);
        }
      });

      logger.debug('Optimized health monitoring initialized');
    };

    // OPTIMIZED: Smart notification cleanup with adaptive intervals
    const startOptimizedNotificationCleanup = () => {
      if (notificationCleanup) {
        clearInterval(notificationCleanup);
      }

      // Use adaptive interval based on system state
      const cleanupInterval = getAdaptiveInterval('NOTIFICATION_CLEANUP', 'healthy', false);

      notificationCleanup = setInterval(() => {
        if (appStore && appStore.systemNotifications && appStore.systemNotifications.length > 5) {
          logger.debug('Cleaning up excessive notifications:', appStore.systemNotifications.length);
          // Keep only the last 5 notifications
          const recentNotifications = appStore.systemNotifications.slice(-5);
          appStore.systemNotifications.splice(0, appStore.systemNotifications.length, ...recentNotifications);
        }
      }, cleanupInterval);

      logger.debug(`Notification cleanup scheduled every ${Math.round(cleanupInterval/60000)} minutes`);
    };

    const stopOptimizedNotificationCleanup = () => {
      if (notificationCleanup) {
        clearInterval(notificationCleanup);
        notificationCleanup = null;
      }
    };

    // Router event monitoring - OPTIMIZED: Event-driven instead of polling
    const setupRouterMonitoring = () => {
      // Monitor router navigation events
      router.afterEach((to, from) => {
        logger.debug(`Navigation: ${from.path} → ${to.path}`);

        // Update user activity in smart monitoring controller
        smartMonitoringController.userActivity.lastActivity = Date.now();
        smartMonitoringController.userActivity.isActive = true;
      });

      // Monitor router errors
      router.onError((error) => {
        logger.error('Router error:', error);
        handleGlobalError(error);
      });
    };

    // Lifecycle hooks
    onMounted(async () => {
      logger.debug('Initializing optimized AutoBot application...');

      // Add global click and keyboard listeners for mobile nav
      document.addEventListener('click', closeNavbarOnClickOutside);
      document.addEventListener('keydown', closeNavbarOnEscape);

      // Set up global error handling (#2849: use named handlers for cleanup)
      window.addEventListener('error', handleWindowError);
      window.addEventListener('unhandledrejection', handleUnhandledRejection);

      // CRITICAL FIX: Clear any stuck system notifications on startup
      logger.debug('Clearing stuck system notifications on startup...');
      clearAllSystemNotifications();
      resetHealthMonitor();

      // Initialize notification bridge for ErrorHandler integration (Issue #502)
      initializeNotificationBridge();
      logger.debug('NotificationBridge initialized for ErrorHandler integration');

      // OPTIMIZED: Initialize new performance-aware systems
      try {
        // Initialize cache buster
        if (cacheBuster && typeof cacheBuster.initialize === 'function') {
          cacheBuster.initialize();
        }

        // OPTIMIZED: Start optimized health monitoring
        startOptimizedHealthCheck();

        // FIXED: Use useSystemStatus composable's refresh method
        logger.debug('Initializing system status with composable...');
        try {
          await refreshSystemStatus();
          updateSystemStatus();
        } catch (statusError) {
          logger.warn('System status initialization failed, but Vue app will continue:', statusError);
          // Don't throw - let Vue app mount successfully
        }

        // OPTIMIZED: Setup router monitoring (event-driven)
        setupRouterMonitoring();

        logger.debug('Optimized monitoring systems initialized successfully');

      } catch (error) {
        logger.error('Error initializing optimized systems:', error);
        // Don't let initialization errors prevent app mounting
      }

      // OPTIMIZED: Start adaptive notification cleanup
      startOptimizedNotificationCleanup();

      // Set loading to false once initialization is complete
      if (appStore && typeof appStore.setLoading === 'function') {
        appStore.setLoading(false);
      }

      logger.debug('Optimized AutoBot initialized - monitoring restored with <50ms performance budget');
    });

    onUnmounted(() => {
      logger.debug('Cleaning up optimized monitoring systems...');

      // Clean up listeners (#2849: remove all event listeners added in onMounted)
      document.removeEventListener('click', closeNavbarOnClickOutside);
      document.removeEventListener('keydown', closeNavbarOnEscape);
      window.removeEventListener('error', handleWindowError);
      window.removeEventListener('unhandledrejection', handleUnhandledRejection);
      stopOptimizedNotificationCleanup();

      // Destroy optimized health monitor
      if (optimizedHealthMonitor && typeof optimizedHealthMonitor.destroy === 'function') {
        optimizedHealthMonitor.destroy();
      }
    });

    // SLM Admin URL from SSOT config (Issue #729)
    const slmAdminUrl = computed(() => getSLMAdminUrl());

    // Data-driven navigation items: single source of truth for desktop + mobile nav.
    // Lives in `@/config/navItems.ts` (#6499) so it can be unit-tested for
    // coverage against the router. Adding a top-level `requiresAuth` route
    // without a navItems entry will fail `nav-items-coverage.test.ts`.

    // Nav overflow: ref for container, filtered/visible/overflow computed slices
    const navContainerRef = ref<HTMLElement | null>(null)

    const filteredNavItems = computed(() =>
      navItems.filter(item => !item.adminOnly || userStore.isAdmin)
    )

    const { visibleCount } = useNavOverflow(
      navContainerRef,
      computed(() => filteredNavItems.value.length)
    )

    const visibleNavItems = computed(() => filteredNavItems.value.slice(0, visibleCount.value))
    const overflowNavItems = computed(() => filteredNavItems.value.slice(visibleCount.value))

    // Issue #973: Guard against Promise objects being rendered as username
    const displayUsername = computed(() => {
      const username = userStore.currentUser?.username
      return typeof username === 'string' ? username : null
    });

    return {
      // Store references
      appStore,
      userStore,
      chatStore,
      knowledgeStore,

      // Reactive data
      showMobileNav,
      showProfileModal,
      showProfileDropdown,
      profileDropdownRef,
      profileDropdownMenuRef,
      profileDropdownStyle,

      // System status (from composable)
      showSystemStatus,
      systemStatus,
      systemServices,

      // Computed
      isLoading,
      hasErrors,
      isPublicRoute,
      showAuthChrome,
      hideFooter,
      navItems,
      profileMenuItems,
      adminMenuItems,
      slmAdminUrl,
      displayUsername,

      // Nav overflow
      navContainerRef,
      visibleNavItems,
      overflowNavItems,

      // Methods
      toggleMobileNav,
      closeMobileNav,
      clearAllCaches,
      handleGlobalError,

      // Unified loading handlers
      handleLoadingComplete,
      handleLoadingError,
      handleLoadingTimeout,

      // System status methods (from composable)
      toggleSystemStatus,
      getSystemStatusTooltip,
      getSystemStatusAriaLabel,
      getSystemStatusText,
      getSystemStatusDescription,
      refreshSystemStatus,
      updateSystemStatus,

      // Host selection (for agent SSH actions)
      hostSelectionState,
      onHostSelected,
      onHostSelectionCancelled,
      onHostSelectionClose,
    };
  }
};
</script>

<style scoped>
/* Skip Navigation Links */
.skip-links {
  position: relative;
  z-index: var(--z-toast);
}

.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  background: #000;
  color: #fff;
  padding: var(--spacing-2) var(--spacing-4);
  text-decoration: none;
  border-radius: 0 0 var(--radius-default) 0;
  font-size: var(--text-sm);
  font-weight: 500;
  transition: top var(--duration-200) var(--ease-in-out);
  z-index: var(--z-maximum);
}

.skip-link:focus {
  top: 0;
  outline: 2px solid #fff;
  outline-offset: 2px;
}

/* Navigation link focus indicators */
nav a:focus-visible {
  outline: 2px solid rgba(255, 255, 255, 0.8);
  outline-offset: 2px;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.3);
}

/* Add any component-specific styles here */
.fade-enter-active, .fade-leave-active {
  transition: opacity var(--duration-500);
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

/* Ensure proper z-index for mobile navigation */
#mobile-nav {
  z-index: 50;
}

/* Smooth transitions for navigation state changes */
.transition-transform {
  transition-property: transform;
  transition-timing-function: var(--ease-in-out);
  transition-duration: var(--duration-300);
}
</style>
