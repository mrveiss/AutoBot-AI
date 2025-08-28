#!/usr/bin/env node

/**
 * MVC Implementation Test Script
 * Tests the key components of the MVC architecture
 */

const fs = require('fs');
const path = require('path');

console.log('🧪 Testing MVC Implementation...\n');

const projectRoot = '/home/kali/Desktop/AutoBot/autobot-vue';

// Test 1: Verify all View components exist
console.log('📋 Test 1: Checking View Components');
const viewComponents = [
  'DashboardView.vue',
  'ChatView.vue',
  'KnowledgeView.vue',
  'ToolsView.vue',
  'MonitoringView.vue',
  'SecretsView.vue',
  'SettingsView.vue',
  'NotFoundView.vue'
];

const viewsPath = path.join(projectRoot, 'src/views');
let viewsExist = 0;

viewComponents.forEach(component => {
  const componentPath = path.join(viewsPath, component);
  if (fs.existsSync(componentPath)) {
    console.log(`  ✅ ${component}`);
    viewsExist++;
  } else {
    console.log(`  ❌ ${component} - Missing`);
  }
});

console.log(`   ${viewsExist}/${viewComponents.length} View components found\n`);

// Test 2: Verify Controller layer exists
console.log('📋 Test 2: Checking Controller Layer');
const controllers = [
  'ChatController.ts'
];

const controllersPath = path.join(projectRoot, 'src/models/controllers');
let controllersExist = 0;

controllers.forEach(controller => {
  const controllerPath = path.join(controllersPath, controller);
  if (fs.existsSync(controllerPath)) {
    console.log(`  ✅ ${controller}`);
    controllersExist++;
  } else {
    console.log(`  ❌ ${controller} - Missing`);
  }
});

console.log(`   ${controllersExist}/${controllers.length} Controllers found\n`);

// Test 3: Verify Pinia stores exist
console.log('📋 Test 3: Checking Model Layer (Pinia Stores)');
const stores = [
  'useAppStore.ts',
  'useChatStore.ts',
  'useKnowledgeStore.ts',
  'useUserStore.ts'
];

const storesPath = path.join(projectRoot, 'src/stores');
let storesExist = 0;

stores.forEach(store => {
  const storePath = path.join(storesPath, store);
  if (fs.existsSync(storePath)) {
    console.log(`  ✅ ${store}`);
    storesExist++;
  } else {
    console.log(`  ❌ ${store} - Missing`);
  }
});

console.log(`   ${storesExist}/${stores.length} Stores found\n`);

// Test 4: Verify Repository pattern
console.log('📋 Test 4: Checking Repository Layer');
const repositories = [
  'index.ts',
  'ApiRepository.ts',
  'ChatRepository.ts',
  'KnowledgeRepository.ts',
  'SystemRepository.ts'
];

const repositoriesPath = path.join(projectRoot, 'src/models/repositories');
let repositoriesExist = 0;

repositories.forEach(repo => {
  const repoPath = path.join(repositoriesPath, repo);
  if (fs.existsSync(repoPath)) {
    console.log(`  ✅ ${repo}`);
    repositoriesExist++;
  } else {
    console.log(`  ❌ ${repo} - Missing`);
  }
});

console.log(`   ${repositoriesExist}/${repositories.length} Repositories found\n`);

// Test 5: Verify refactored components
console.log('📋 Test 5: Checking Refactored Components');
const refactoredComponents = {
  'Chat Components': [
    'src/components/chat/ChatInterface.vue',
    'src/components/chat/ChatSidebar.vue',
    'src/components/chat/ChatMessages.vue',
    'src/components/chat/ChatInput.vue'
  ],
  'Knowledge Components': [
    'src/components/knowledge/KnowledgeManager.vue',
    'src/components/knowledge/KnowledgeSearch.vue',
    'src/components/knowledge/KnowledgeCategories.vue',
    'src/components/knowledge/KnowledgeUpload.vue',
    'src/components/knowledge/KnowledgeEntries.vue',
    'src/components/knowledge/KnowledgeStats.vue'
  ]
};

Object.entries(refactoredComponents).forEach(([category, components]) => {
  console.log(`  📁 ${category}:`);
  let categoryCount = 0;

  components.forEach(componentPath => {
    const fullPath = path.join(projectRoot, componentPath);
    const componentName = path.basename(componentPath);

    if (fs.existsSync(fullPath)) {
      const stats = fs.statSync(fullPath);
      const content = fs.readFileSync(fullPath, 'utf8');
      const lineCount = content.split('\n').length;

      console.log(`    ✅ ${componentName} (${lineCount} lines)`);
      categoryCount++;
    } else {
      console.log(`    ❌ ${componentName} - Missing`);
    }
  });

  console.log(`    ${categoryCount}/${components.length} components found\n`);
});

// Test 6: Verify router configuration
console.log('📋 Test 6: Checking Router Configuration');
const routerPath = path.join(projectRoot, 'src/router/index.ts');

if (fs.existsSync(routerPath)) {
  const routerContent = fs.readFileSync(routerPath, 'utf8');

  const routes = [
    '/dashboard',
    '/chat',
    '/knowledge',
    '/tools',
    '/monitoring',
    '/secrets',
    '/settings'
  ];

  let routesFound = 0;
  routes.forEach(route => {
    if (routerContent.includes(`path: '${route}'`)) {
      console.log(`  ✅ ${route} route configured`);
      routesFound++;
    } else {
      console.log(`  ❌ ${route} route - Missing`);
    }
  });

  console.log(`   ${routesFound}/${routes.length} routes configured`);

  // Check for nested routes
  if (routerContent.includes('children:')) {
    console.log('  ✅ Nested routes configured');
  } else {
    console.log('  ❌ Nested routes - Missing');
  }

} else {
  console.log('  ❌ Router configuration file missing');
}

console.log('\n🎯 MVC Implementation Summary:');
console.log('=====================================');
console.log(`📈 Views: ${viewsExist}/${viewComponents.length} implemented`);
console.log(`🎮 Controllers: ${controllersExist}/${controllers.length} implemented`);
console.log(`💾 Models (Stores): ${storesExist}/${stores.length} implemented`);
console.log(`🔄 Repositories: ${repositoriesExist}/${repositories.length} implemented`);

const totalScore = viewsExist + controllersExist + storesExist + repositoriesExist;
const maxScore = viewComponents.length + controllers.length + stores.length + repositories.length;
const completionPercent = Math.round((totalScore / maxScore) * 100);

console.log(`\n🏆 Overall Completion: ${completionPercent}% (${totalScore}/${maxScore})`);

if (completionPercent >= 90) {
  console.log('🎉 MVC Implementation: EXCELLENT!');
} else if (completionPercent >= 75) {
  console.log('👍 MVC Implementation: GOOD');
} else if (completionPercent >= 50) {
  console.log('⚠️  MVC Implementation: NEEDS IMPROVEMENT');
} else {
  console.log('❌ MVC Implementation: INCOMPLETE');
}

console.log('\n✨ Next Steps:');
if (completionPercent < 100) {
  console.log('- Address any missing components identified above');
}
console.log('- Run integration tests');
console.log('- Test navigation between routes');
console.log('- Verify state management across components');
console.log('- Test API integration through repositories');
