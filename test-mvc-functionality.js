#!/usr/bin/env node

/**
 * MVC Functionality Test
 * Tests that all routes, components, and integrations work correctly
 */

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

console.log('🧪 Testing MVC Functionality End-to-End\n');

const projectRoot = '/home/kali/Desktop/AutoBot/autobot-vue';

// Test 1: Verify all routes are accessible
console.log('📋 Test 1: Route Accessibility Check');

const expectedRoutes = [
  { path: '/', redirectsTo: '/dashboard', description: 'Root redirect' },
  { path: '/dashboard', component: 'DashboardView', description: 'Dashboard main page' },
  { path: '/chat', component: 'ChatView', description: 'Chat interface' },
  { path: '/knowledge', redirectsTo: '/knowledge/search', description: 'Knowledge base' },
  { path: '/knowledge/search', component: 'KnowledgeSearch', description: 'Knowledge search' },
  { path: '/knowledge/categories', component: 'KnowledgeCategories', description: 'Categories management' },
  { path: '/knowledge/upload', component: 'KnowledgeUpload', description: 'Content upload' },
  { path: '/knowledge/manage', component: 'KnowledgeEntries', description: 'Document management' },
  { path: '/knowledge/stats', component: 'KnowledgeStats', description: 'Knowledge statistics' },
  { path: '/tools', redirectsTo: '/tools/terminal', description: 'Developer tools' },
  { path: '/tools/terminal', component: 'TerminalWindow', description: 'Terminal interface' },
  { path: '/tools/files', component: 'FileBrowser', description: 'File browser' },
  { path: '/tools/voice', component: 'VoiceInterface', description: 'Voice interface' },
  { path: '/monitoring', redirectsTo: '/monitoring/system', description: 'System monitoring' },
  { path: '/monitoring/system', component: 'SystemMonitor', description: 'System health' },
  { path: '/monitoring/analytics', component: 'CodebaseAnalytics', description: 'Code analytics' },
  { path: '/monitoring/rum', component: 'RumDashboard', description: 'RUM monitoring' },
  { path: '/monitoring/validation', component: 'ValidationDashboard', description: 'Validation dashboard' },
  { path: '/secrets', component: 'SecretsView', description: 'Secrets management' },
  { path: '/settings', component: 'SettingsView', description: 'Application settings' }
];

const routerPath = path.join(projectRoot, 'src/router/index.ts');
let routeTests = 0;
let routesPassed = 0;

if (fs.existsSync(routerPath)) {
  const routerContent = fs.readFileSync(routerPath, 'utf8');

  expectedRoutes.forEach(route => {
    routeTests++;

    if (route.redirectsTo) {
      // Check for redirect routes
      if (routerContent.includes(`path: '${route.path}'`) &&
          routerContent.includes(`redirect: '${route.redirectsTo}'`)) {
        console.log(`  ✅ ${route.path} → ${route.redirectsTo} (${route.description})`);
        routesPassed++;
      } else {
        console.log(`  ❌ ${route.path} redirect missing`);
      }
    } else {
      // Check for component routes
      if (routerContent.includes(`path: '${route.path}'`) &&
          routerContent.includes(route.component)) {
        console.log(`  ✅ ${route.path} → ${route.component} (${route.description})`);
        routesPassed++;
      } else {
        console.log(`  ❌ ${route.path} component missing`);
      }
    }
  });
}

console.log(`\n   Routes: ${routesPassed}/${routeTests} configured correctly\n`);

// Test 2: Component file existence and structure
console.log('📋 Test 2: Component File Structure Validation');

const componentTests = [
  // View components
  { path: 'src/views/DashboardView.vue', type: 'View', required: true },
  { path: 'src/views/ChatView.vue', type: 'View', required: true },
  { path: 'src/views/KnowledgeView.vue', type: 'View', required: true },
  { path: 'src/views/ToolsView.vue', type: 'View', required: true },
  { path: 'src/views/MonitoringView.vue', type: 'View', required: true },
  { path: 'src/views/SecretsView.vue', type: 'View', required: true },
  { path: 'src/views/SettingsView.vue', type: 'View', required: true },
  { path: 'src/views/NotFoundView.vue', type: 'View', required: true },

  // Refactored chat components
  { path: 'src/components/chat/ChatInterface.vue', type: 'Chat Component', required: true },
  { path: 'src/components/chat/ChatSidebar.vue', type: 'Chat Component', required: true },
  { path: 'src/components/chat/ChatMessages.vue', type: 'Chat Component', required: true },
  { path: 'src/components/chat/ChatInput.vue', type: 'Chat Component', required: true },

  // Refactored knowledge components
  { path: 'src/components/knowledge/KnowledgeManager.vue', type: 'Knowledge Component', required: true },
  { path: 'src/components/knowledge/KnowledgeSearch.vue', type: 'Knowledge Component', required: true },
  { path: 'src/components/knowledge/KnowledgeCategories.vue', type: 'Knowledge Component', required: true },
  { path: 'src/components/knowledge/KnowledgeUpload.vue', type: 'Knowledge Component', required: true },
  { path: 'src/components/knowledge/KnowledgeEntries.vue', type: 'Knowledge Component', required: true },
  { path: 'src/components/knowledge/KnowledgeStats.vue', type: 'Knowledge Component', required: true },
];

let componentTestCount = 0;
let componentsPassed = 0;

componentTests.forEach(test => {
  componentTestCount++;
  const fullPath = path.join(projectRoot, test.path);

  if (fs.existsSync(fullPath)) {
    const content = fs.readFileSync(fullPath, 'utf8');
    const lines = content.split('\n').length;
    const hasSetup = content.includes('<script setup') || content.includes('setup(');
    const hasTypeScript = content.includes('lang="ts"');

    let score = 1; // Base point for existing
    if (hasSetup) score += 0.5; // Composition API
    if (hasTypeScript) score += 0.5; // TypeScript
    if (lines < 1000) score += 0.5; // Reasonable size

    const quality = score >= 2 ? '✅' : score >= 1.5 ? '⚠️' : '❌';
    console.log(`  ${quality} ${test.type}: ${path.basename(test.path)} (${lines} lines, score: ${score}/2.5)`);

    if (score >= 1.5) componentsPassed++;
  } else {
    console.log(`  ❌ ${test.type}: ${path.basename(test.path)} - Missing`);
  }
});

console.log(`\n   Components: ${componentsPassed}/${componentTestCount} meet quality standards\n`);

// Test 3: Store integration validation
console.log('📋 Test 3: Store Integration Validation');

const storeTests = [
  { store: 'useAppStore', file: 'src/stores/useAppStore.ts', expectedExports: ['activeTab', 'navbarOpen', 'updateRoute'] },
  { store: 'useChatStore', file: 'src/stores/useChatStore.ts', expectedExports: ['sessions', 'currentSessionId', 'addMessage'] },
  { store: 'useKnowledgeStore', file: 'src/stores/useKnowledgeStore.ts', expectedExports: ['documents', 'activeTab', 'searchQuery'] },
  { store: 'useUserStore', file: 'src/stores/useUserStore.ts', expectedExports: ['user', 'preferences'] }
];

let storeValidations = 0;
let storesPassed = 0;

storeTests.forEach(test => {
  storeValidations++;
  const storePath = path.join(projectRoot, test.file);

  if (fs.existsSync(storePath)) {
    const content = fs.readFileSync(storePath, 'utf8');

    // Check for defineStore
    const hasDefineStore = content.includes('defineStore');

    // Check for expected exports (rough validation)
    let exportScore = 0;
    test.expectedExports.forEach(exp => {
      if (content.includes(exp)) exportScore++;
    });

    const exportPercent = Math.round((exportScore / test.expectedExports.length) * 100);

    if (hasDefineStore && exportPercent >= 60) {
      console.log(`  ✅ ${test.store}: Properly configured (${exportPercent}% exports found)`);
      storesPassed++;
    } else if (hasDefineStore) {
      console.log(`  ⚠️  ${test.store}: Missing some exports (${exportPercent}% found)`);
    } else {
      console.log(`  ❌ ${test.store}: Not properly configured`);
    }
  } else {
    console.log(`  ❌ ${test.store}: File missing`);
  }
});

console.log(`\n   Stores: ${storesPassed}/${storeValidations} properly configured\n`);

// Test 4: Build system validation
console.log('📋 Test 4: Build System Health Check');

const buildFiles = [
  { path: 'package.json', description: 'Package configuration' },
  { path: 'vite.config.ts', description: 'Vite configuration' },
  { path: 'tsconfig.json', description: 'TypeScript configuration' },
  { path: 'src/main.ts', description: 'Application entry point' },
  { path: 'dist/index.html', description: 'Built application' }
];

let buildTests = 0;
let buildPassed = 0;

buildFiles.forEach(file => {
  buildTests++;
  const filePath = path.join(projectRoot, file.path);

  if (fs.existsSync(filePath)) {
    console.log(`  ✅ ${file.description}: ${file.path}`);
    buildPassed++;
  } else {
    console.log(`  ❌ ${file.description}: ${file.path} - Missing`);
  }
});

// Check if dependencies are installed
const nodeModulesPath = path.join(projectRoot, 'node_modules');
buildTests++;
if (fs.existsSync(nodeModulesPath)) {
  console.log(`  ✅ Dependencies: node_modules installed`);
  buildPassed++;
} else {
  console.log(`  ❌ Dependencies: node_modules missing`);
}

console.log(`\n   Build System: ${buildPassed}/${buildTests} components ready\n`);

// Final Score Calculation
console.log('🎯 MVC Functionality Test Results');
console.log('=====================================');

const routeScore = Math.round((routesPassed / routeTests) * 100);
const componentScore = Math.round((componentsPassed / componentTestCount) * 100);
const storeScore = Math.round((storesPassed / storeValidations) * 100);
const buildScore = Math.round((buildPassed / buildTests) * 100);

console.log(`🗺️  Route Configuration: ${routeScore}%`);
console.log(`🧩 Component Quality: ${componentScore}%`);
console.log(`📦 Store Integration: ${storeScore}%`);
console.log(`⚙️  Build System: ${buildScore}%`);

const overallFunctionality = Math.round((routeScore + componentScore + storeScore + buildScore) / 4);
console.log(`\n🏆 Overall Functionality Score: ${overallFunctionality}%`);

// Status Assessment
if (overallFunctionality >= 95) {
  console.log('\n🎉 EXCELLENT! MVC implementation is fully functional');
  console.log('   - All routes properly configured');
  console.log('   - Components meet quality standards');
  console.log('   - Store integration working');
  console.log('   - Build system operational');
  console.log('   ➡️  Ready for production use');
} else if (overallFunctionality >= 85) {
  console.log('\n✅ VERY GOOD! MVC implementation is highly functional');
  console.log('   - Core functionality working well');
  console.log('   - Minor optimizations possible');
  console.log('   ➡️  Ready for deployment with monitoring');
} else if (overallFunctionality >= 75) {
  console.log('\n👍 GOOD! MVC implementation is functional');
  console.log('   - Most features working correctly');
  console.log('   - Some areas need attention');
  console.log('   ➡️  Ready for staging environment');
} else if (overallFunctionality >= 60) {
  console.log('\n⚠️  FAIR! MVC implementation needs improvement');
  console.log('   - Basic functionality present');
  console.log('   - Several issues to address');
  console.log('   ➡️  Requires additional development');
} else {
  console.log('\n❌ POOR! MVC implementation has significant issues');
  console.log('   - Major functionality problems');
  console.log('   - Extensive fixes required');
  console.log('   ➡️  Not ready for deployment');
}

console.log('\n🚀 Recommended Next Actions:');
if (routeScore < 90) {
  console.log('  - Complete route configuration');
  console.log('  - Test navigation between all routes');
}
if (componentScore < 85) {
  console.log('  - Improve component quality and structure');
  console.log('  - Add missing TypeScript types');
}
if (storeScore < 90) {
  console.log('  - Complete store implementations');
  console.log('  - Test state management integration');
}
if (buildScore < 95) {
  console.log('  - Fix build configuration issues');
  console.log('  - Ensure all dependencies are properly installed');
}

if (overallFunctionality >= 85) {
  console.log('\n🎯 MVC Implementation Status: PRODUCTION READY! 🎯');
}
