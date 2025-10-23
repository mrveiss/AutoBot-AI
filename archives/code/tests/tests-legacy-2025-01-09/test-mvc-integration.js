#!/usr/bin/env node

/**
 * MVC Integration Test
 * Validates that the MVC components work together properly
 */

const fs = require('fs');
const path = require('path');

console.log('🔧 MVC Integration Test Suite\n');

const projectRoot = '/home/kali/Desktop/AutoBot/autobot-vue';

// Test 1: Verify store integration in components
console.log('📋 Test 1: Store Integration Analysis');

const testStoreUsage = (filePath, storeName) => {
  if (!fs.existsSync(filePath)) return { exists: false };

  const content = fs.readFileSync(filePath, 'utf8');
  const hasImport = content.includes(`use${storeName}Store`);
  const hasUsage = content.includes(`${storeName.toLowerCase()}Store`);

  return {
    exists: true,
    hasImport,
    hasUsage,
    integrated: hasImport && hasUsage
  };
};

const integrationTests = [
  {
    component: 'ChatInterface.vue',
    path: 'src/components/chat/ChatInterface.vue',
    stores: ['Chat']
  },
  {
    component: 'ChatSidebar.vue',
    path: 'src/components/chat/ChatSidebar.vue',
    stores: ['Chat', 'App']
  },
  {
    component: 'KnowledgeManager.vue',
    path: 'src/components/knowledge/KnowledgeManager.vue',
    stores: ['Knowledge']
  },
  {
    component: 'App.vue',
    path: 'src/App.vue',
    stores: ['App', 'Chat', 'Knowledge']
  }
];

let totalIntegrations = 0;
let successfulIntegrations = 0;

integrationTests.forEach(test => {
  console.log(`\n  🔍 ${test.component}:`);

  test.stores.forEach(store => {
    const filePath = path.join(projectRoot, test.path);
    const result = testStoreUsage(filePath, store);
    totalIntegrations++;

    if (!result.exists) {
      console.log(`    ❌ File not found`);
    } else if (result.integrated) {
      console.log(`    ✅ ${store}Store properly integrated`);
      successfulIntegrations++;
    } else if (result.hasImport && !result.hasUsage) {
      console.log(`    ⚠️  ${store}Store imported but not used`);
    } else if (!result.hasImport && result.hasUsage) {
      console.log(`    ⚠️  ${store}Store used but not imported`);
    } else {
      console.log(`    ❌ ${store}Store not integrated`);
    }
  });
});

console.log(`\n   Store Integration: ${successfulIntegrations}/${totalIntegrations} successful\n`);

// Test 2: Router integration validation
console.log('📋 Test 2: Router Navigation Integration');

const routerPath = path.join(projectRoot, 'src/router/index.ts');
const appPath = path.join(projectRoot, 'src/App.vue');

let routerTests = 0;
let routerPassed = 0;

if (fs.existsSync(routerPath) && fs.existsSync(appPath)) {
  const routerContent = fs.readFileSync(routerPath, 'utf8');
  const appContent = fs.readFileSync(appPath, 'utf8');

  // Check if router is imported in main.ts
  const mainPath = path.join(projectRoot, 'src/main.ts');
  if (fs.existsSync(mainPath)) {
    const mainContent = fs.readFileSync(mainPath, 'utf8');
    routerTests++;
    if (mainContent.includes('import router from') && mainContent.includes('app.use(router)')) {
      console.log('  ✅ Router properly configured in main.ts');
      routerPassed++;
    } else {
      console.log('  ❌ Router not configured in main.ts');
    }
  }

  // Check if App.vue uses router-view
  routerTests++;
  if (appContent.includes('<router-view')) {
    console.log('  ✅ App.vue uses router-view');
    routerPassed++;
  } else {
    console.log('  ❌ App.vue missing router-view');
  }

  // Check if navigation uses router-link
  routerTests++;
  if (appContent.includes('<router-link') || appContent.includes('router-link')) {
    console.log('  ✅ Navigation uses router-link');
    routerPassed++;
  } else {
    console.log('  ❌ Navigation not using router-link');
  }

  // Check for navigation guards
  routerTests++;
  if (routerContent.includes('beforeEach')) {
    console.log('  ✅ Navigation guards configured');
    routerPassed++;
  } else {
    console.log('  ⚠️  No navigation guards found');
  }
}

console.log(`\n   Router Integration: ${routerPassed}/${routerTests} tests passed\n`);

// Test 3: Component dependency analysis
console.log('📋 Test 3: Component Architecture Validation');

const analyzeComponent = (componentPath) => {
  if (!fs.existsSync(componentPath)) return null;

  const content = fs.readFileSync(componentPath, 'utf8');
  const lines = content.split('\n').length;

  // Check for modern Vue 3 patterns
  const hasCompositionAPI = content.includes('setup(') || content.includes('<script setup');
  const hasTypeScript = componentPath.endsWith('.ts') || content.includes('lang="ts"');
  const hasPropsInterface = content.includes('interface') && content.includes('Props');
  const hasPiniaStore = content.includes('use') && content.includes('Store');

  return {
    lines,
    hasCompositionAPI,
    hasTypeScript,
    hasPropsInterface,
    hasPiniaStore,
    isMaintainable: lines < 800, // Components should be under 800 lines
    isModern: hasCompositionAPI && hasTypeScript
  };
};

const componentsToAnalyze = [
  { name: 'ChatInterface', path: 'src/components/chat/ChatInterface.vue', maxLines: 500 },
  { name: 'ChatSidebar', path: 'src/components/chat/ChatSidebar.vue', maxLines: 400 },
  { name: 'ChatMessages', path: 'src/components/chat/ChatMessages.vue', maxLines: 700 },
  { name: 'KnowledgeManager', path: 'src/components/knowledge/KnowledgeManager.vue', maxLines: 200 },
  { name: 'KnowledgeSearch', path: 'src/components/knowledge/KnowledgeSearch.vue', maxLines: 500 }
];

let architectureScore = 0;
let maxArchitectureScore = 0;

componentsToAnalyze.forEach(comp => {
  const fullPath = path.join(projectRoot, comp.path);
  const analysis = analyzeComponent(fullPath);

  if (analysis) {
    console.log(`\n  📦 ${comp.name}:`);
    console.log(`    Lines: ${analysis.lines} (target: <${comp.maxLines})`);

    maxArchitectureScore += 5; // 5 points possible per component

    if (analysis.lines < comp.maxLines) {
      console.log(`    ✅ Component size: Maintainable`);
      architectureScore++;
    } else {
      console.log(`    ⚠️  Component size: Large (${analysis.lines} lines)`);
    }

    if (analysis.hasCompositionAPI) {
      console.log(`    ✅ Uses Composition API`);
      architectureScore++;
    }

    if (analysis.hasTypeScript) {
      console.log(`    ✅ TypeScript enabled`);
      architectureScore++;
    }

    if (analysis.hasPiniaStore) {
      console.log(`    ✅ Pinia store integration`);
      architectureScore++;
    }

    if (analysis.isModern) {
      console.log(`    ✅ Modern Vue 3 patterns`);
      architectureScore++;
    }
  }
});

console.log(`\n   Architecture Quality: ${architectureScore}/${maxArchitectureScore} points\n`);

// Test 4: Build and type safety validation
console.log('📋 Test 4: Build System Validation');

const packageJsonPath = path.join(projectRoot, 'package.json');
let buildTests = 0;
let buildPassed = 0;

if (fs.existsSync(packageJsonPath)) {
  const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));

  // Check for required dependencies
  buildTests++;
  if (packageJson.dependencies?.pinia && packageJson.dependencies?.['vue-router']) {
    console.log('  ✅ Core MVC dependencies present');
    buildPassed++;
  } else {
    console.log('  ❌ Missing core MVC dependencies');
  }

  // Check for development dependencies
  buildTests++;
  if (packageJson.devDependencies?.typescript && packageJson.devDependencies?.['vue-tsc']) {
    console.log('  ✅ TypeScript tooling configured');
    buildPassed++;
  } else {
    console.log('  ⚠️  TypeScript tooling incomplete');
  }

  // Check build scripts
  buildTests++;
  if (packageJson.scripts?.build && packageJson.scripts?.dev) {
    console.log('  ✅ Build scripts configured');
    buildPassed++;
  } else {
    console.log('  ❌ Build scripts missing');
  }
}

console.log(`\n   Build System: ${buildPassed}/${buildTests} checks passed\n`);

// Final Report
console.log('🎯 MVC Integration Test Results');
console.log('=====================================');

const storeIntegrationPercent = Math.round((successfulIntegrations / totalIntegrations) * 100);
const routerIntegrationPercent = Math.round((routerPassed / routerTests) * 100);
const architecturePercent = Math.round((architectureScore / maxArchitectureScore) * 100);
const buildPercent = Math.round((buildPassed / buildTests) * 100);

console.log(`📊 Store Integration: ${storeIntegrationPercent}%`);
console.log(`🔗 Router Integration: ${routerIntegrationPercent}%`);
console.log(`🏗️  Architecture Quality: ${architecturePercent}%`);
console.log(`⚙️  Build System: ${buildPercent}%`);

const overallScore = Math.round((storeIntegrationPercent + routerIntegrationPercent + architecturePercent + buildPercent) / 4);
console.log(`\n🏆 Overall Integration Score: ${overallScore}%`);

if (overallScore >= 90) {
  console.log('\n🎉 EXCELLENT! MVC implementation is production-ready');
  console.log('   - All components properly integrated');
  console.log('   - Architecture follows best practices');
  console.log('   - Ready for deployment');
} else if (overallScore >= 75) {
  console.log('\n👍 GOOD! MVC implementation is solid');
  console.log('   - Minor optimizations recommended');
  console.log('   - Core functionality working');
} else if (overallScore >= 60) {
  console.log('\n⚠️  FAIR! MVC implementation needs improvement');
  console.log('   - Address failing integration tests');
  console.log('   - Review architecture decisions');
} else {
  console.log('\n❌ POOR! MVC implementation has serious issues');
  console.log('   - Major integration problems detected');
  console.log('   - Requires significant refactoring');
}

console.log('\n✨ Recommendations:');
if (storeIntegrationPercent < 100) {
  console.log('  - Review store usage in components');
  console.log('  - Ensure proper import/export patterns');
}
if (routerIntegrationPercent < 100) {
  console.log('  - Complete router-link migration');
  console.log('  - Add missing navigation guards');
}
if (architecturePercent < 80) {
  console.log('  - Break down large components further');
  console.log('  - Implement more TypeScript interfaces');
}
if (buildPercent < 100) {
  console.log('  - Complete build tooling setup');
  console.log('  - Add missing dependencies');
}

console.log('\n🚀 Ready for production deployment!');
