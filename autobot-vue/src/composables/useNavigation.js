/**
 * Navigation Management Composable
 * Extracted from App.vue for better maintainability
 */

import { ref, onMounted, onUnmounted } from 'vue'

export function useNavigation() {
  const showMobileNav = ref(false)

  // Methods
  const toggleMobileNav = () => {
    showMobileNav.value = !showMobileNav.value
  }

  const closeMobileNav = () => {
    showMobileNav.value = false
  }

  const closeNavbarOnClickOutside = (event) => {
    // Close mobile nav when clicking outside
    if (showMobileNav.value && !event.target.closest('#mobile-nav') && !event.target.closest('[aria-controls="mobile-nav"]')) {
      showMobileNav.value = false
    }
  }

  // Lifecycle management
  onMounted(() => {
    // Add global click listener for mobile nav
    document.addEventListener('click', closeNavbarOnClickOutside)
  })

  onUnmounted(() => {
    // Clean up listeners
    document.removeEventListener('click', closeNavbarOnClickOutside)
  })

  return {
    // State
    showMobileNav,

    // Methods
    toggleMobileNav,
    closeMobileNav
  }
}