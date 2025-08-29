const { chromium } = require('playwright');
const express = require('express');
const app = express();

// Simple console logger to replace winston initially
const logger = {
  info: (msg, meta = {}) => console.log('[INFO]', msg, meta ? JSON.stringify(meta) : ''),
  warn: (msg, meta = {}) => console.warn('[WARN]', msg, meta ? JSON.stringify(meta) : ''),
  error: (msg, meta = {}) => console.error('[ERROR]', msg, meta ? JSON.stringify(meta) : ''),
  debug: (msg, meta = {}) => console.log('[DEBUG]', msg, meta ? JSON.stringify(meta) : '')
};

app.use(express.json({ limit: '50mb' }));

let browser = null;

async function initBrowser() {
  try {
    if (!browser || !browser.isConnected()) {
      logger.info('Launching Chromium browser', { action: 'browser_launch' });

      // Check if we should run in headless or headed mode
      const headlessMode = process.env.HEADLESS !== 'false';
      logger.info('Browser mode configured', { 
        mode: headlessMode ? 'headless' : 'headed', 
        headless: headlessMode 
      });

      const launchOptions = {
        headless: headlessMode,
        args: [
          '--no-sandbox',
          '--disable-dev-shm-usage',
          '--disable-web-security',
          '--disable-features=VizDisplayCompositor',
          '--disable-background-timer-throttling',
          '--disable-backgrounding-occluded-windows',
          '--disable-renderer-backgrounding',
        ]
      };

      // Add headed mode specific options
      if (!headlessMode) {
        launchOptions.args.push(
          '--start-maximized',
          '--disable-infobars',
          '--disable-extensions'
        );
        // Set slower execution for visibility
        launchOptions.slowMo = 500; // 500ms delay between actions
      }

      browser = await chromium.launch(launchOptions);
      logger.info('Browser launched successfully', { 
        action: 'browser_launch_success',
        options: launchOptions 
      });
    }
    return browser;
  } catch (error) {
    logger.error('Failed to launch browser', { 
      action: 'browser_launch_error',
      error: error.message,
      stack: error.stack 
    });
    throw error;
  }
}

app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    browser_connected: browser ? browser.isConnected() : false
  });
});

app.post('/navigate', async (req, res) => {
  logger.info('Received navigation request', { 
    endpoint: '/navigate',
    url: req.body.url,
    wait_for: req.body.wait_for 
  });
  
  try {
    const { url, wait_for = 'domcontentloaded' } = req.body;

    if (!url) {
      return res.status(400).json({
        success: false,
        error: 'URL parameter is required'
      });
    }

    const browser = await initBrowser();
    
    // Get or create a page (reuse existing page for VNC visibility)
    let pages = await browser.pages();
    let page = pages.length > 0 ? pages[0] : await browser.newPage();

    // Set user agent for better compatibility
    await page.setExtraHTTPHeaders({
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    });

    logger.info('Navigating to URL', { 
      action: 'navigation',
      url: url,
      wait_for: wait_for 
    });

    // Navigate to the URL
    const response = await page.goto(url, {
      waitUntil: wait_for,
      timeout: 30000
    });

    // Get final URL after redirects
    const finalUrl = page.url();
    const title = await page.title();

    logger.info('Navigation completed', { 
      action: 'navigation_complete',
      final_url: finalUrl,
      title: title,
      status: response?.status()
    });

    res.json({
      success: true,
      url: url,
      final_url: finalUrl,
      title: title,
      status: response?.status(),
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    logger.error('Navigation error', { 
      endpoint: '/navigate',
      error: error.message,
      stack: error.stack 
    });
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

app.post('/back', async (req, res) => {
  logger.info('Received back navigation request', { endpoint: '/back' });
  
  try {
    const browser = await initBrowser();
    let pages = await browser.pages();
    let page = pages.length > 0 ? pages[0] : await browser.newPage();

    await page.goBack({ waitUntil: 'domcontentloaded' });
    const finalUrl = page.url();
    const title = await page.title();

    logger.info('Back navigation completed', { final_url: finalUrl, title: title });

    res.json({
      success: true,
      final_url: finalUrl,
      title: title,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    logger.error('Back navigation error', { error: error.message });
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

app.post('/forward', async (req, res) => {
  logger.info('Received forward navigation request', { endpoint: '/forward' });
  
  try {
    const browser = await initBrowser();
    let pages = await browser.pages();
    let page = pages.length > 0 ? pages[0] : await browser.newPage();

    await page.goForward({ waitUntil: 'domcontentloaded' });
    const finalUrl = page.url();
    const title = await page.title();

    logger.info('Forward navigation completed', { final_url: finalUrl, title: title });

    res.json({
      success: true,
      final_url: finalUrl,
      title: title,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    logger.error('Forward navigation error', { error: error.message });
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

app.post('/reload', async (req, res) => {
  logger.info('Received reload request', { endpoint: '/reload' });
  
  try {
    const browser = await initBrowser();
    let pages = await browser.pages();
    let page = pages.length > 0 ? pages[0] : await browser.newPage();

    await page.reload({ waitUntil: 'domcontentloaded' });
    const finalUrl = page.url();
    const title = await page.title();

    logger.info('Reload completed', { final_url: finalUrl, title: title });

    res.json({
      success: true,
      final_url: finalUrl,
      title: title,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    logger.error('Reload error', { error: error.message });
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

app.get('/current', async (req, res) => {
  logger.info('Received current page info request', { endpoint: '/current' });
  
  try {
    const browser = await initBrowser();
    let pages = await browser.pages();
    let page = pages.length > 0 ? pages[0] : await browser.newPage();

    const url = page.url();
    const title = await page.title();
    
    // Check navigation history
    let canGoBack = false;
    let canGoForward = false;
    try {
      // These will throw if navigation is not possible
      await page.evaluate(() => window.history.length > 1);
      canGoBack = true;
    } catch (e) {}

    res.json({
      success: true,
      url: url,
      title: title,
      can_go_back: canGoBack,
      can_go_forward: canGoForward,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    logger.error('Current page info error', { error: error.message });
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

app.post('/search', async (req, res) => {
  logger.info('Received search request', { 
    endpoint: '/search',
    query: req.body.query,
    search_engine: req.body.search_engine 
  });
  try {
    const { query, search_engine = 'duckduckgo' } = req.body;

    if (!query) {
      return res.status(400).json({
        success: false,
        error: 'Query parameter is required'
      });
    }

    const browser = await initBrowser();
    const page = await browser.newPage();

    await page.setExtraHTTPHeaders({
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    });

    const searchUrls = {
      duckduckgo: 'https://duckduckgo.com/?q=' + encodeURIComponent(query)
    };

    const searchUrl = searchUrls[search_engine] || searchUrls.duckduckgo;
    logger.info('Navigating to search URL', { 
      action: 'navigation',
      url: searchUrl,
      search_engine 
    });

    await page.goto(searchUrl, {
      waitUntil: 'domcontentloaded',
      timeout: 15000
    });

    await page.waitForTimeout(3000);

    let results = [];

    try {
      const resultSelectors = [
        '[data-testid="result"]',
        '.result'
      ];

      let elements = [];
      for (const selector of resultSelectors) {
        try {
          await page.waitForSelector(selector, { timeout: 5000 });
          elements = await page.$$(selector);
          if (elements.length > 0) {
            logger.info('Search results found', { 
              action: 'results_found',
              selector,
              count: elements.length 
            });
            break;
          }
        } catch (e) {
          continue;
        }
      }

      for (const element of elements.slice(0, 5)) {
        try {
          const titleElement = await element.$('h2 a, h3 a, .result__title a');
          if (titleElement) {
            const title = await titleElement.textContent();
            const url = await titleElement.getAttribute('href');
            const snippet = '';

            if (url && title && title.trim()) {
              results.push({
                title: title.trim(),
                url: url.startsWith('http') ? url : 'https://duckduckgo.com' + url,
                snippet: snippet.trim(),
                source: 'DuckDuckGo'
              });
            }
          }
        } catch (e) {
          logger.warn('Error extracting search result', { 
            action: 'result_extraction_error',
            error: e.message 
          });
        }
      }
    } catch (e) {
      logger.warn('Error during search operation', { 
        action: 'search_operation_error',
        error: e.message 
      });
    }

    await page.close();

    res.json({
      success: true,
      query: query,
      search_engine: search_engine,
      results: results.slice(0, 5)
    });

  } catch (error) {
    logger.error('Search endpoint error', { 
      endpoint: '/search',
      error: error.message,
      stack: error.stack 
    });
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// Add comprehensive message testing endpoint
app.post('/send-test-message', async (req, res) => {
  logger.info('Received message test request', { 
    endpoint: '/send-test-message',
    frontend_url: req.body.frontend_url,
    message: req.body.message 
  });
  try {
    const { frontend_url = 'http://localhost:5173', message = 'what network scanning tools do we have available?' } = req.body;

    const browser = await initBrowser();
    const page = await browser.newPage();

    logger.info('Navigating to frontend', { 
      action: 'frontend_navigation',
      url: frontend_url 
    });
    await page.goto(frontend_url, { waitUntil: 'networkidle', timeout: 30000 });

    // Wait for Vue.js app to fully load
    await page.waitForTimeout(3000);

    const results = {
      success: true,
      frontend_url,
      message_sent: message,
      timestamp: new Date().toISOString(),
      steps: []
    };

    // Step 1: Navigate to AI Assistant
    logger.info('Navigating to AI Assistant', { 
      action: 'ai_assistant_navigation' 
    });
    try {
      const aiAssistantButton = page.getByText('AI ASSISTANT');
      await aiAssistantButton.click();
      await page.waitForTimeout(2000);

      results.steps.push({
        step: 'Navigate to AI Assistant',
        status: 'SUCCESS',
        details: 'AI Assistant section opened'
      });
    } catch (error) {
      results.steps.push({
        step: 'Navigate to AI Assistant',
        status: 'FAILED',
        details: error.message
      });
    }

    // Step 2: Find message input
    logger.info('Looking for message input field', { 
      action: 'find_message_input' 
    });
    try {
      const messageInput = page.locator('textarea[placeholder*="message"], textarea[placeholder*="Type"], textarea').first();

      if (await messageInput.count() > 0) {
        logger.info('Message input found', { 
          action: 'message_input_found' 
        });

        // Step 3: Type the test message
        logger.info('Typing message', { 
          action: 'type_message',
          message 
        });
        await messageInput.fill(message);
        await page.waitForTimeout(1000);

        results.steps.push({
          step: 'Type message',
          status: 'SUCCESS',
          details: `Message typed: "${message}"`
        });

        // Step 4: Send the message
        logger.info('Looking for send button', { 
          action: 'find_send_button' 
        });
        const sendSelectors = [
          'text=Send',
          'button[type="submit"]',
          '.send-button',
          '.btn:has-text("Send")',
          'button:has-text("Send")'
        ];

        let messageSent = false;
        for (const selector of sendSelectors) {
          try {
            const sendBtn = page.locator(selector);
            if (await sendBtn.count() > 0) {
              logger.info('Clicking send button', { 
                action: 'click_send_button',
                selector 
              });
              await sendBtn.click();
              messageSent = true;
              break;
            }
          } catch (e) {
            continue;
          }
        }

        if (messageSent) {
          await page.waitForTimeout(3000); // Wait for response

          results.steps.push({
            step: 'Send message',
            status: 'SUCCESS',
            details: 'Message sent successfully'
          });

          // Step 5: Check for workflow response
          logger.info('Waiting for workflow response', { 
            action: 'wait_workflow_response' 
          });
          await page.waitForTimeout(5000);

          // Look for workflow indicators
          const workflowIndicators = [
            '.workflow-progress',
            '.workflow-step',
            '[data-testid="workflow"]',
            'text=workflow',
            'text=step',
            'text=approval'
          ];

          let workflowDetected = false;
          const workflowDetails = [];

          for (const indicator of workflowIndicators) {
            try {
              const elements = await page.locator(indicator).count();
              if (elements > 0) {
                workflowDetected = true;
                workflowDetails.push(`Found ${elements} elements matching "${indicator}"`);
              }
            } catch (e) {
              continue;
            }
          }

          results.steps.push({
            step: 'Check workflow response',
            status: workflowDetected ? 'SUCCESS' : 'PENDING',
            details: workflowDetected ? workflowDetails.join(', ') : 'Workflow may still be processing'
          });

        } else {
          results.steps.push({
            step: 'Send message',
            status: 'FAILED',
            details: 'Send button not found'
          });
        }

      } else {
        results.steps.push({
          step: 'Find message input',
          status: 'FAILED',
          details: 'Message input field not found'
        });
      }

    } catch (error) {
      results.steps.push({
        step: 'Find message input',
        status: 'FAILED',
        details: error.message
      });
    }

    // Take screenshot for debugging
    try {
      const screenshot = await page.screenshot({ fullPage: true, type: 'png' });
      results.screenshot_size = screenshot.length;
      results.has_screenshot = true;
      logger.info('Screenshot captured', { 
        action: 'screenshot_captured',
        size_bytes: screenshot.length 
      });
    } catch (error) {
      results.screenshot_error = error.message;
    }

    await page.close();

    logger.info('Message test completed', { 
      endpoint: '/send-test-message',
      action: 'test_completed',
      success: true 
    });
    res.json(results);

  } catch (error) {
    logger.error('Message test error', { 
      endpoint: '/send-test-message',
      error: error.message,
      stack: error.stack 
    });
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Add frontend testing endpoint
app.post('/test-frontend', async (req, res) => {
  logger.info('Received frontend test request', { 
    endpoint: '/test-frontend',
    frontend_url: req.body.frontend_url 
  });
  try {
    const { frontend_url = 'http://localhost:5173' } = req.body;

    const browser = await initBrowser();
    const page = await browser.newPage();

    logger.info('Navigating to frontend for testing', { 
      action: 'frontend_test_navigation',
      url: frontend_url 
    });
    await page.goto(frontend_url, { waitUntil: 'networkidle', timeout: 30000 });

    // Wait for Vue.js app to fully load
    await page.waitForTimeout(5000);

    // Wait for Vue app to be mounted
    try {
      await page.waitForSelector('#app', { timeout: 10000 });
      logger.info('Vue app container found', { 
        action: 'vue_app_found' 
      });
    } catch (e) {
      logger.warn('Vue app container not found', { 
        action: 'vue_app_not_found',
        error: e.message 
      });
    }

    const results = {
      success: true,
      frontend_url,
      timestamp: new Date().toISOString(),
      tests: []
    };

    // Test 1: Check if page loaded
    const title = await page.title();
    results.tests.push({
      name: 'Page Load',
      status: title ? 'PASS' : 'FAIL',
      details: `Title: ${title}`
    });

    // Test 2: Check for main navigation
    const navItems = ['DASHBOARD', 'AI ASSISTANT', 'VOICE INTERFACE', 'KNOWLEDGE BASE', 'TERMINAL', 'FILE MANAGER', 'SYSTEM MONITOR', 'SETTINGS'];
    for (const navItem of navItems) {
      try {
        const element = await page.getByText(navItem).first();
        const isVisible = await element.isVisible();
        results.tests.push({
          name: `Navigation: ${navItem}`,
          status: isVisible ? 'PASS' : 'FAIL',
          details: isVisible ? 'Navigation item found' : 'Navigation item not visible'
        });

        if (isVisible) {
          await element.click();
          await page.waitForTimeout(1000);
          logger.info('Navigation item clicked', { 
            action: 'nav_item_clicked',
            item: navItem 
          });
        }
      } catch (error) {
        results.tests.push({
          name: `Navigation: ${navItem}`,
          status: 'FAIL',
          details: error.message
        });
      }
    }

    // Test 3: Check AI Assistant functionality
    try {
      logger.info('Testing AI Assistant functionality', { 
        action: 'ai_assistant_test' 
      });
      const aiAssistantButton = page.getByText('AI ASSISTANT');
      await aiAssistantButton.click();
      await page.waitForTimeout(5000);

      logger.info('AI Assistant navigation completed', { 
        action: 'ai_assistant_nav_complete',
        current_url: page.url() 
      });

      // Wait for ChatInterface component to load
      logger.info('Waiting for chat interface to load', { 
        action: 'wait_chat_interface' 
      });
      await page.waitForTimeout(3000);

      // Debug: Check what's actually in the DOM
      const chatSection = page.locator('[key="chat"], .chat-interface, [data-testid="chat"]');
      const chatSectionCount = await chatSection.count();
      logger.info('Chat sections analysis', { 
        action: 'chat_sections_found',
        count: chatSectionCount 
      });

      if (chatSectionCount > 0) {
        const chatSectionHTML = await chatSection.first().innerHTML();
        logger.debug('Chat section HTML preview', { 
          action: 'chat_section_html',
          html_preview: chatSectionHTML.substring(0, 200) + '...' 
        });
      }

      // Look for chat interface elements with multiple selectors
      const messageSelectors = [
        'textarea[placeholder*="message"]',
        'input[placeholder*="message"]',
        'textarea[placeholder*="Type"]',
        'input[placeholder*="Type"]',
        '.chat-input textarea',
        '.message-input textarea',
        'textarea',
        'input[type="text"]'
      ];

      let hasMessageInput = false;
      let messageInputDetails = 'No message input found';

      for (const selector of messageSelectors) {
        try {
          const inputs = await page.locator(selector).count();
          if (inputs > 0) {
            hasMessageInput = true;
            messageInputDetails = `Message input found with selector: ${selector}`;
            break;
          }
        } catch (e) {
          continue;
        }
      }

      results.tests.push({
        name: 'Chat Interface',
        status: hasMessageInput ? 'PASS' : 'FAIL',
        details: messageInputDetails
      });

      // Test Reload System button with multiple selectors
      const reloadSelectors = [
        'text=Reload System',
        'text=Reload',
        '[data-testid="reload-button"]',
        'button:has-text("Reload")',
        '.reload-button',
        '.btn:has-text("Reload")'
      ];

      let hasReloadButton = false;
      let reloadButtonDetails = 'No reload button found';

      for (const selector of reloadSelectors) {
        try {
          const buttons = await page.locator(selector).count();
          if (buttons > 0) {
            hasReloadButton = true;
            reloadButtonDetails = `Reload button found with selector: ${selector}`;
            break;
          }
        } catch (e) {
          continue;
        }
      }

      results.tests.push({
        name: 'Reload System Button',
        status: hasReloadButton ? 'PASS' : 'FAIL',
        details: reloadButtonDetails
      });

      // Test sending a message if input is found
      if (hasMessageInput) {
        try {
          const textarea = page.locator('textarea').first();
          await textarea.fill('Test message from Playwright');
          await page.waitForTimeout(1000);

          // Look for send button
          const sendSelectors = ['text=Send', 'button[type="submit"]', '.send-button', '.btn:has-text("Send")'];
          let messageSent = false;

          for (const selector of sendSelectors) {
            try {
              const sendBtn = page.locator(selector);
              if (await sendBtn.count() > 0) {
                await sendBtn.click();
                messageSent = true;
                break;
              }
            } catch (e) {
              continue;
            }
          }

          results.tests.push({
            name: 'Message Sending',
            status: messageSent ? 'PASS' : 'FAIL',
            details: messageSent ? 'Test message sent successfully' : 'Send button not found'
          });
        } catch (error) {
          results.tests.push({
            name: 'Message Sending',
            status: 'FAIL',
            details: error.message
          });
        }
      }

    } catch (error) {
      results.tests.push({
        name: 'AI Assistant Navigation',
        status: 'FAIL',
        details: error.message
      });
    }

    // Capture page HTML for debugging
    try {
      // Wait a bit more to ensure all elements are loaded
      await page.waitForTimeout(2000);

      // Extract key elements for debugging
      const allButtons = await page.locator('button').all();
      const buttonTexts = [];
      for (const button of allButtons) {
        try {
          const text = await button.textContent();
          if (text && text.trim()) {
            buttonTexts.push(text.trim());
          }
        } catch (e) {
          continue;
        }
      }

      // Look for all form elements
      const textareas = await page.locator('textarea').count();
      const inputs = await page.locator('input').count();
      const forms = await page.locator('form').count();

      // Get current page structure
      const navItems = await page.locator('nav a, .nav a, [role="navigation"] a, .sidebar a').all();
      const navTexts = [];
      for (const nav of navItems) {
        try {
          const text = await nav.textContent();
          if (text && text.trim()) {
            navTexts.push(text.trim());
          }
        } catch (e) {
          continue;
        }
      }

      results.debug_info = {
        page_title: await page.title(),
        url: page.url(),
        textareas: textareas,
        inputs: inputs,
        forms: forms,
        button_texts: buttonTexts.slice(0, 15),
        navigation_texts: navTexts.slice(0, 10),
        body_classes: await page.locator('body').getAttribute('class') || '',
        app_element: await page.locator('#app').count(),
        vue_components: await page.locator('[data-v-]').count()
      };
    } catch (error) {
      results.debug_error = error.message;
    }

    // Take screenshot for debugging
    try {
      const screenshot = await page.screenshot({ fullPage: true, type: 'png' });
      // Save screenshot to results but truncated for response size
      results.screenshot_size = screenshot.length;
      results.has_screenshot = true;
    } catch (error) {
      results.screenshot_error = error.message;
    }

    await page.close();

    const passCount = results.tests.filter(t => t.status === 'PASS').length;
    const totalTests = results.tests.length;

    results.summary = {
      total_tests: totalTests,
      passed: passCount,
      failed: totalTests - passCount,
      success_rate: `${Math.round((passCount / totalTests) * 100)}%`
    };

    logger.info('Frontend testing completed', { 
      endpoint: '/test-frontend',
      action: 'test_completed',
      summary: results.summary 
    });
    res.json(results);

  } catch (error) {
    logger.error('Frontend test error', { 
      endpoint: '/test-frontend',
      error: error.message,
      stack: error.stack 
    });
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

const port = 3000;
app.listen(port, '0.0.0.0', async () => {
  logger.info('Playwright service started', { 
    action: 'service_start',
    port,
    host: '0.0.0.0' 
  });

  try {
    await initBrowser();
    logger.info('Browser pre-initialized and ready', { 
      action: 'browser_preinitialized' 
    });
  } catch (error) {
    logger.error('Failed to pre-initialize browser', { 
      action: 'browser_preinit_error',
      error: error.message,
      stack: error.stack 
    });
  }
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  logger.info('Shutting down gracefully', { 
    action: 'graceful_shutdown',
    signal: 'SIGTERM' 
  });
  if (browser) {
    await browser.close();
    logger.info('Browser closed successfully', { 
      action: 'browser_closed' 
    });
  }
  process.exit(0);
});

process.on('SIGINT', async () => {
  logger.info('Received interrupt signal, shutting down', { 
    action: 'interrupt_shutdown',
    signal: 'SIGINT' 
  });
  if (browser) {
    await browser.close();
    logger.info('Browser closed successfully', { 
      action: 'browser_closed' 
    });
  }
  process.exit(0);
});
