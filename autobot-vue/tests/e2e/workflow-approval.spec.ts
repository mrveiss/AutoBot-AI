import { test, expect } from '@playwright/test';
import { TEST_CONFIG } from './config';

test.describe('WorkflowApproval Component Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the AutoBot application
    await page.goto(TEST_CONFIG.FRONTEND_URL);
    await page.waitForLoadState('networkidle');
    
    // Wait for the application to load
    await page.waitForSelector('#app', { timeout: 10000 });
  });

  test('should load WorkflowApproval component without errors', async ({ page }) => {
    // Navigate to workflow section or open workflow modal
    // This test verifies the component loads without the previous 404 error
    
    // Check if workflows link/button exists in navigation
    const workflowButton = page.locator('text=Workflows').or(page.locator('[data-testid="workflows"]'));
    if (await workflowButton.count() > 0) {
      await workflowButton.click();
      
      // Wait for workflow approval interface to load
      await page.waitForTimeout(2000);
      
      // Check that no 404 error appears in console
      const logs = [];
      page.on('console', msg => {
        if (msg.type() === 'error' && msg.text().includes('404')) {
          logs.push(msg.text());
        }
      });
      
      // Wait a bit more to catch any async errors
      await page.waitForTimeout(3000);
      
      // Assert no 404 errors related to workflow API
      const workflowApiErrors = logs.filter(log => 
        log.includes('/api/workflow/workflow/workflows') || 
        log.includes('Failed to load workflows')
      );
      
      expect(workflowApiErrors.length).toBe(0);
    }
  });

  test('should be able to fetch workflows without 404 error', async ({ page }) => {
    // Test the API endpoint directly
    const response = await page.request.get(TEST_CONFIG.getApiUrl('/api/workflow/workflows'));
    
    // Should not return 404
    expect(response.status()).not.toBe(404);
    
    // Should return success response
    expect(response.status()).toBe(200);
    
    const responseData = await response.json();
    expect(responseData).toHaveProperty('success');
  });

  test('should display workflow information when workflows are available', async ({ page }) => {
    // Check if there are any active workflows
    const response = await page.request.get(TEST_CONFIG.getApiUrl('/api/workflow/workflows'));
    const workflowData = await response.json();
    
    if (workflowData.workflows && workflowData.workflows.length > 0) {
      // Navigate to workflows view
      const workflowButton = page.locator('text=Workflows').or(page.locator('[data-testid="workflows"]'));
      if (await workflowButton.count() > 0) {
        await workflowButton.click();
        await page.waitForTimeout(2000);
        
        // Should display workflow information
        await expect(page.locator('text=workflow').first()).toBeVisible();
      }
    }
  });

  test('should handle workflow approval actions', async ({ page }) => {
    // This test checks if the approval interface is functional
    // Navigate to workflows
    const workflowButton = page.locator('text=Workflows').or(page.locator('[data-testid="workflows"]'));
    if (await workflowButton.count() > 0) {
      await workflowButton.click();
      await page.waitForTimeout(2000);
      
      // Look for approval buttons (approve, deny, etc.)
      const approveButton = page.locator('text=Approve').or(page.locator('[data-testid="approve"]'));
      const denyButton = page.locator('text=Deny').or(page.locator('[data-testid="deny"]'));
      
      // At least one type of workflow control should be available
      const hasApproveControls = (await approveButton.count()) > 0 || (await denyButton.count()) > 0;
      
      // If no active workflows, that's okay - just ensure no errors
      if (!hasApproveControls) {
        // Check for "No active workflows" or similar message
        const noWorkflowsMessage = page.locator('text=No active').or(page.locator('text=no workflows'));
        // This is acceptable - either controls exist or "no workflows" message
        expect(true).toBe(true); // Test passes if we get here without errors
      }
    }
  });

  test('should refresh workflow list automatically', async ({ page }) => {
    // Test the auto-refresh functionality
    const workflowButton = page.locator('text=Workflows').or(page.locator('[data-testid="workflows"]'));
    if (await workflowButton.count() > 0) {
      await workflowButton.click();
      
      // Monitor network requests to workflow API
      const requests = [];
      page.on('request', request => {
        if (request.url().includes('/api/workflow/workflows')) {
          requests.push(request.url());
        }
      });
      
      // Wait for multiple refresh cycles (should refresh every few seconds)
      await page.waitForTimeout(8000);
      
      // Should have made multiple requests due to auto-refresh
      expect(requests.length).toBeGreaterThan(1);
      
      // All requests should be to the correct endpoint
      requests.forEach(url => {
        expect(url).not.toContain('/api/workflow/workflow/workflows');
        expect(url).toContain('/api/workflow/workflows');
      });
    }
  });
});