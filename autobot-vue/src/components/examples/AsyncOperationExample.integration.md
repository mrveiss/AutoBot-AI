# Integration Guide - useAsyncOperation Example

Quick guide for integrating the AsyncOperationExample component into the AutoBot frontend for testing and demonstration.

## Files Created

```
autobot-vue/src/components/examples/
├── AsyncOperationExample.vue          (1,202 lines) - Main example component
├── README.md                          (368 lines)   - Comprehensive documentation
├── QUICK_REFERENCE.md                 (387 lines)   - Developer quick reference
├── BEFORE_AFTER_COMPARISON.md         (576 lines)   - Side-by-side comparison
└── INTEGRATION_GUIDE.md               (this file)   - Integration instructions
```

**Total**: 2,533 lines of examples and documentation

## Quick Start (Recommended)

### Option 1: Add to Router (Best for Testing)

**1. Open router configuration:**
```bash
# File: autobot-vue/src/router/index.ts
```

**2. Add route:**
```typescript
{
  path: '/examples/async-operations',
  name: 'async-operations-example',
  component: () => import('@/components/examples/AsyncOperationExample.vue'),
  meta: {
    title: 'Async Operations Examples',
    requiresAuth: false // or true depending on your needs
  }
}
```

**3. Access in browser:**
```
http://172.16.168.21:5173/#/examples/async-operations
```

### Option 2: Add to Settings View (Production Demo)

**1. Open Settings view:**
```bash
# File: autobot-vue/src/views/SettingsView.vue
```

**2. Import component:**
```vue
<script setup lang="ts">
import SettingsPanel from '@/components/SettingsPanel.vue'
import AsyncOperationExample from '@/components/examples/AsyncOperationExample.vue'
</script>
```

**3. Add to template (optional tab):**
```vue
<template>
  <div class="settings-view">
    <div class="container mx-auto px-4 py-6">
      <!-- Existing settings -->
      <SettingsPanel />

      <!-- Example component (for demo) -->
      <div class="mt-8">
        <details>
          <summary class="text-lg font-semibold cursor-pointer">
            View Async Operation Examples
          </summary>
          <AsyncOperationExample />
        </details>
      </div>
    </div>
  </div>
</template>
```

### Option 3: Standalone Testing View

**1. Create temporary test view:**
```bash
# File: autobot-vue/src/views/AsyncOperationTestView.vue
```

```vue
<template>
  <AsyncOperationExample />
</template>

<script setup lang="ts">
import AsyncOperationExample from '@/components/examples/AsyncOperationExample.vue'
</script>
```

**2. Add to router:**
```typescript
{
  path: '/test/async-operations',
  name: 'test-async-operations',
  component: () => import('@/views/AsyncOperationTestView.vue')
}
```

## Navigation Integration

### Add to Navigation Menu (Optional)

**File**: `autobot-vue/src/components/Navigation.vue` or your navigation component

```vue
<!-- Development/Examples section -->
<div v-if="isDevelopment" class="nav-section">
  <h3>Examples</h3>
  <router-link to="/examples/async-operations">
    Async Operations
  </router-link>
</div>
```

## Testing Without Backend

If you want to test the examples without the backend running, you can modify the component to use mock data:

**1. Create mock API file:**
```typescript
// autobot-vue/src/utils/mockApi.ts
export const mockHealthCheck = async () => {
  await new Promise(resolve => setTimeout(resolve, 1000))
  return {
    status: 'healthy',
    timestamp: Date.now(),
    services: {
      backend: 'running',
      redis: 'running',
      npu: 'running'
    }
  }
}

export const mockSaveSettings = async (value: string) => {
  await new Promise(resolve => setTimeout(resolve, 800))
  if (Math.random() > 0.8) {
    throw new Error('Random error for testing')
  }
  return { success: true, value }
}

export const mockValidateConfig = async () => {
  await new Promise(resolve => setTimeout(resolve, 1200))
  if (Math.random() > 0.7) {
    throw new Error('Configuration validation failed')
  }
  return { valid: true }
}

export const mockUsers = async () => {
  await new Promise(resolve => setTimeout(resolve, 900))
  return [
    { id: 1, name: 'Alice', email: 'alice@example.com' },
    { id: 2, name: 'Bob', email: 'bob@example.com' }
  ]
}

export const mockSystemInfo = async () => {
  await new Promise(resolve => setTimeout(resolve, 1100))
  return {
    cpu: '45%',
    memory: '8.2 GB / 16 GB',
    uptime: '3 days',
    version: '2.1.0'
  }
}

export const mockAnalytics = async () => {
  await new Promise(resolve => setTimeout(resolve, 1500))
  return {
    requests: { total: 1250 },
    metrics: { avg_response_time: 342.56 },
    errors: 23
  }
}
```

**2. Modify AsyncOperationExample.vue to use mocks:**
```typescript
// Add at top of script section
import * as mockApi from '@/utils/mockApi'

// Change fetch calls to mock calls
const checkHealth = () => health.execute(() => mockApi.mockHealthCheck())
const saveSettings = () => saveOp.execute(() => mockApi.mockSaveSettings(settingValue.value))
// ... etc
```

## Development Workflow

### 1. Local Development

```bash
# Make changes to example component locally
cd /home/kali/Desktop/AutoBot/autobot-vue/src/components/examples/

# Edit files
# AsyncOperationExample.vue
# README.md
# etc.
```

### 2. Test Locally (If Running Frontend Locally)

```bash
cd /home/kali/Desktop/AutoBot/autobot-vue
npm run dev
```

**⚠️ Remember**: AutoBot uses distributed architecture, frontend should run on VM (172.16.168.21)

### 3. Sync to Frontend VM

```bash
# From AutoBot root directory
cd /home/kali/Desktop/AutoBot

# Sync the entire examples directory
./scripts/utilities/sync-to-vm.sh frontend \
  autobot-vue/src/components/examples/ \
  /home/autobot/autobot-vue/src/components/examples/
```

### 4. Rebuild on Frontend VM

```bash
# SSH to frontend VM
ssh autobot@172.16.168.21

# Rebuild (if running production build)
cd /home/autobot/autobot-vue
npm run build

# Or restart dev server (if running dev mode)
# Vite will hot-reload automatically
```

## Verification Checklist

After integration, verify:

- [ ] Example component accessible via route
- [ ] All 5 examples render correctly
- [ ] Loading states display properly
- [ ] Error messages show when operations fail
- [ ] Success states display after successful operations
- [ ] Reset buttons clear state correctly
- [ ] Before/After code sections expand/collapse
- [ ] Summary card displays benefits correctly
- [ ] No console errors
- [ ] Responsive layout works on different screen sizes

## Browser Testing

Test in:
- [ ] Chrome/Chromium
- [ ] Firefox
- [ ] Safari (if available)

Test responsive breakpoints:
- [ ] Desktop (1920x1080)
- [ ] Laptop (1366x768)
- [ ] Tablet (768x1024)
- [ ] Mobile (375x667)

## Troubleshooting

### Example doesn't load
- Check router configuration
- Verify file paths in import statements
- Check browser console for errors
- Ensure composable is properly imported

### API calls fail
- Backend may not be running (`http://172.16.168.20:8001`)
- Use mock API for testing (see above)
- Check network tab in browser DevTools
- Verify CORS settings if needed

### Styling issues
- Tailwind CSS should be loaded
- Check if custom styles are conflicting
- Verify Tailwind config includes example files
- Clear browser cache

### TypeScript errors
- Run `npm run type-check` to verify types
- Check composable import path
- Verify TypeScript version compatibility

## Performance Considerations

The example component includes:
- 5 async operations
- Multiple loading states
- Error handling
- Success callbacks
- Data transformations

**Expected performance**:
- Initial load: ~50ms (component mount)
- Per operation: 100-1500ms (depends on API)
- Memory usage: Minimal (efficient Vue 3 reactivity)

## Cleanup (If Needed)

To remove the example from production:

```bash
# Remove the entire examples directory
rm -rf /home/kali/Desktop/AutoBot/autobot-vue/src/components/examples/

# Remove route from router
# Edit: autobot-vue/src/router/index.ts
# Delete the async-operations-example route

# Remove any navigation links
# Check: Navigation component, Settings, etc.

# Sync to frontend VM
./scripts/utilities/sync-to-vm.sh frontend autobot-vue/ /home/autobot/autobot-vue/
```

## Production Deployment Considerations

### Before deploying to production:

1. **Remove or protect example route**
   - Add authentication requirement
   - Or remove route entirely
   - Or add `VITE_ENABLE_EXAMPLES` env flag

2. **Use real API endpoints**
   - Replace mock API calls with real ones
   - Or remove examples entirely

3. **Security review**
   - Ensure no sensitive data exposed
   - Verify all API calls are authenticated
   - Check CORS settings

4. **Performance optimization**
   - Component is already optimized
   - Consider lazy loading if adding to main bundle

## Next Steps

After integrating and testing the example:

1. **Review with team** - Get feedback on the pattern
2. **Identify refactoring candidates** - BackendSettings, NPUWorkersSettings, etc.
3. **Create migration plan** - Prioritize high-traffic components
4. **Refactor incrementally** - One component at a time
5. **Update documentation** - As patterns evolve

## Questions?

- Check `README.md` for comprehensive documentation
- Review `QUICK_REFERENCE.md` for quick patterns
- See `BEFORE_AFTER_COMPARISON.md` for detailed comparisons
- Review composable source: `src/composables/useAsyncOperation.ts`

---

**Status**: ✅ Ready for integration
**Testing**: Local testing recommended before sync to VM
**Deployment**: Development/staging environments first

**Last Updated**: 2025-10-27
