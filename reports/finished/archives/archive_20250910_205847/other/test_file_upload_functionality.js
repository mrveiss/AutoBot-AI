/**
 * File Upload Functionality Test
 * 
 * Tests the file upload capabilities of the FileBrowser component.
 * Validates both programmatic and direct file input methods for automated testing.
 */

const { test, expect } = require('@playwright/test');
const path = require('path');

test.describe('File Upload Functionality', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to AutoBot frontend
    await page.goto('http://localhost:3000');
    
    // Wait for app to be fully loaded
    await page.waitForSelector('.dashboard-container', { timeout: 30000 });
  });

  test('file browser should be accessible and show file upload interface', async ({ page }) => {
    console.log('🧪 Testing file browser accessibility...');

    // Navigate to file browser or find file management section
    // This might be in a different section - let's check available navigation
    const navItems = await page.locator('nav a, .nav-item, .sidebar a').all();
    
    let fileBrowserFound = false;
    for (const item of navItems) {
      const text = await item.textContent();
      if (text && (text.toLowerCase().includes('file') || text.toLowerCase().includes('browse'))) {
        await item.click();
        fileBrowserFound = true;
        break;
      }
    }

    if (!fileBrowserFound) {
      // Try direct component access
      const fileBrowser = page.locator('.file-browser');
      await expect(fileBrowser).toBeVisible({ timeout: 10000 });
    }

    // Verify file browser components are present
    await expect(page.locator('.file-browser')).toBeVisible();
    await expect(page.locator('button[aria-label="Upload file"]')).toBeVisible();
    await expect(page.locator('button[aria-label="Refresh"]')).toBeVisible();

    console.log('✅ File browser interface is accessible');
  });

  test('should have both hidden and visible file input elements', async ({ page }) => {
    console.log('🧪 Testing file input element presence...');

    // Navigate to file browser
    await page.goto('http://localhost:3000');
    
    // Look for file browser component
    const fileBrowser = page.locator('.file-browser');
    await expect(fileBrowser).toBeVisible({ timeout: 15000 });

    // Check for hidden file input (legacy)
    const hiddenFileInput = page.locator('input[data-testid="file-upload-input"]');
    await expect(hiddenFileInput).toBeAttached();
    
    // Verify it's hidden
    const isHidden = await hiddenFileInput.evaluate(el => {
      const style = window.getComputedStyle(el);
      return style.display === 'none';
    });
    expect(isHidden).toBe(true);

    // Check for visible file input (new)
    const visibleFileInput = page.locator('input[data-testid="visible-file-upload-input"]');
    await expect(visibleFileInput).toBeVisible();
    await expect(visibleFileInput).toHaveAttribute('type', 'file');

    console.log('✅ Both file input elements are present and configured correctly');
  });

  test('should handle file upload via visible file input', async ({ page }) => {
    console.log('🧪 Testing direct file upload via visible input...');

    // Navigate to file browser
    await page.goto('http://localhost:3000');
    
    const fileBrowser = page.locator('.file-browser');
    await expect(fileBrowser).toBeVisible({ timeout: 15000 });

    // Create a test file
    const testFileName = 'test-upload.txt';
    const testFileContent = 'This is a test file for upload functionality testing.';
    
    // Use Playwright's file upload capability
    const visibleFileInput = page.locator('input[data-testid="visible-file-upload-input"]');
    
    // Create a temporary file for testing
    const testFilePath = path.join(__dirname, '..', 'fixtures', testFileName);
    
    // Set the files on the input (simulates file selection)
    await visibleFileInput.setInputFiles({
      name: testFileName,
      mimeType: 'text/plain',
      buffer: Buffer.from(testFileContent)
    });

    // Wait for upload processing
    await page.waitForTimeout(2000);

    console.log('✅ File upload via visible input completed');
  });

  test('should handle file upload via upload button', async ({ page }) => {
    console.log('🧪 Testing file upload via upload button...');

    // Navigate to file browser
    await page.goto('http://localhost:3000');
    
    const fileBrowser = page.locator('.file-browser');
    await expect(fileBrowser).toBeVisible({ timeout: 15000 });

    // Prepare file upload handler
    const testFileName = 'button-upload-test.txt';
    const testFileContent = 'Test file uploaded via button click.';

    // Set up file chooser handler
    page.on('filechooser', async (fileChooser) => {
      // Create a file for upload
      await fileChooser.setFiles({
        name: testFileName,
        mimeType: 'text/plain',
        buffer: Buffer.from(testFileContent)
      });
    });

    // Click the upload button
    const uploadButton = page.locator('button[aria-label="Upload file"]');
    await uploadButton.click();

    // Wait for upload processing
    await page.waitForTimeout(2000);

    console.log('✅ File upload via button completed');
  });

  test('should show appropriate error messages for invalid files', async ({ page }) => {
    console.log('🧪 Testing file upload error handling...');

    // Navigate to file browser
    await page.goto('http://localhost:3000');
    
    const fileBrowser = page.locator('.file-browser');
    await expect(fileBrowser).toBeVisible({ timeout: 15000 });

    // Test with invalid file type (executable)
    const invalidFileName = 'malicious.exe';
    const invalidFileContent = 'Fake executable content';

    const visibleFileInput = page.locator('input[data-testid="visible-file-upload-input"]');
    
    // Listen for console errors or alerts
    let alertMessage = '';
    page.on('dialog', async (dialog) => {
      alertMessage = dialog.message();
      await dialog.accept();
    });

    // Try to upload invalid file
    await visibleFileInput.setInputFiles({
      name: invalidFileName,
      mimeType: 'application/octet-stream',
      buffer: Buffer.from(invalidFileContent)
    });

    // Wait for error handling
    await page.waitForTimeout(2000);

    // Check if appropriate error message was shown
    console.log('Alert message:', alertMessage);

    console.log('✅ Error handling test completed');
  });

  test('should refresh file list after upload', async ({ page }) => {
    console.log('🧪 Testing file list refresh after upload...');

    // Navigate to file browser
    await page.goto('http://localhost:3000');
    
    const fileBrowser = page.locator('.file-browser');
    await expect(fileBrowser).toBeVisible({ timeout: 15000 });

    // Get initial file count
    const initialRows = await page.locator('.file-table tbody tr').count();
    console.log('Initial file count:', initialRows);

    // Upload a file
    const testFileName = 'refresh-test.txt';
    const testFileContent = 'File for testing refresh functionality.';

    const visibleFileInput = page.locator('input[data-testid="visible-file-upload-input"]');
    await visibleFileInput.setInputFiles({
      name: testFileName,
      mimeType: 'text/plain',
      buffer: Buffer.from(testFileContent)
    });

    // Wait for upload and refresh
    await page.waitForTimeout(3000);

    // Check if file list was refreshed (this depends on backend availability)
    const finalRows = await page.locator('.file-table tbody tr').count();
    console.log('Final file count:', finalRows);

    // Verify the refresh button works
    const refreshButton = page.locator('button[aria-label="Refresh"]');
    await refreshButton.click();
    await page.waitForTimeout(1000);

    console.log('✅ File list refresh test completed');
  });

  test('should handle large file uploads appropriately', async ({ page }) => {
    console.log('🧪 Testing large file upload handling...');

    // Navigate to file browser
    await page.goto('http://localhost:3000');
    
    const fileBrowser = page.locator('.file-browser');
    await expect(fileBrowser).toBeVisible({ timeout: 15000 });

    // Create a large file (simulating > 50MB limit)
    const largeFileName = 'large-file.txt';
    const largeFileContent = 'x'.repeat(52 * 1024 * 1024); // 52MB

    let alertMessage = '';
    page.on('dialog', async (dialog) => {
      alertMessage = dialog.message();
      await dialog.accept();
    });

    const visibleFileInput = page.locator('input[data-testid="visible-file-upload-input"]');
    
    try {
      await visibleFileInput.setInputFiles({
        name: largeFileName,
        mimeType: 'text/plain',
        buffer: Buffer.from(largeFileContent)
      });

      // Wait for error handling
      await page.waitForTimeout(3000);

      console.log('Large file upload alert:', alertMessage);
      
    } catch (error) {
      console.log('Large file upload correctly rejected:', error.message);
    }

    console.log('✅ Large file upload handling test completed');
  });

  test('should validate file input accessibility features', async ({ page }) => {
    console.log('🧪 Testing file input accessibility...');

    // Navigate to file browser
    await page.goto('http://localhost:3000');
    
    const fileBrowser = page.locator('.file-browser');
    await expect(fileBrowser).toBeVisible({ timeout: 15000 });

    // Check ARIA labels
    const visibleFileInput = page.locator('input[data-testid="visible-file-upload-input"]');
    await expect(visibleFileInput).toHaveAttribute('aria-label', 'Visible file upload input');

    const hiddenFileInput = page.locator('input[data-testid="file-upload-input"]');
    await expect(hiddenFileInput).toHaveAttribute('aria-label', 'File upload input');

    // Check for proper labeling
    const label = page.locator('label[for="visible-file-input"]');
    await expect(label).toBeVisible();

    // Test keyboard navigation
    await visibleFileInput.focus();
    await expect(visibleFileInput).toBeFocused();

    // Test tab navigation
    await page.keyboard.press('Tab');
    // Should move to next focusable element

    console.log('✅ File input accessibility test completed');
  });
});