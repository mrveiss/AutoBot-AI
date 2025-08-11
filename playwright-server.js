const { chromium } = require('playwright');
const express = require('express');
const app = express();

app.use(express.json({ limit: '50mb' }));

let browser = null;

async function initBrowser() {
  try {
    if (!browser || !browser.isConnected()) {
      console.log('🚀 Launching Chromium browser...');

      // Check if we should run in headless or headed mode
      const headlessMode = process.env.HEADLESS !== 'false';
      console.log(`Browser mode: ${headlessMode ? 'headless' : 'headed (visible)'}`);

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
      console.log('✅ Browser launched successfully');
    }
    return browser;
  } catch (error) {
    console.error('❌ Failed to launch browser:', error);
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

app.post('/search', async (req, res) => {
  console.log('🔍 Received search request:', req.body);
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
    console.log('🌐 Navigating to:', searchUrl);

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
            console.log('✅ Found results with selector:', selector);
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
          console.error('❌ Error extracting result:', e.message);
        }
      }
    } catch (e) {
      console.error('❌ Error with search:', e.message);
    }

    await page.close();

    res.json({
      success: true,
      query: query,
      search_engine: search_engine,
      results: results.slice(0, 5)
    });

  } catch (error) {
    console.error('❌ Search error:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// Add comprehensive message testing endpoint
app.post('/send-test-message', async (req, res) => {
  console.log('💬 Received message test request:', req.body);
  try {
    const { frontend_url = 'http://localhost:5173', message = 'what network scanning tools do we have available?' } = req.body;

    const browser = await initBrowser();
    const page = await browser.newPage();

    console.log('🌐 Navigating to frontend:', frontend_url);
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
    console.log('🧭 Clicking AI ASSISTANT navigation...');
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
    console.log('🔍 Looking for message input field...');
    try {
      const messageInput = page.locator('textarea[placeholder*="message"], textarea[placeholder*="Type"], textarea').first();

      if (await messageInput.count() > 0) {
        console.log('✅ Message input found');

        // Step 3: Type the test message
        console.log(`💬 Typing message: "${message}"`);
        await messageInput.fill(message);
        await page.waitForTimeout(1000);

        results.steps.push({
          step: 'Type message',
          status: 'SUCCESS',
          details: `Message typed: "${message}"`
        });

        // Step 4: Send the message
        console.log('📤 Looking for send button...');
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
              console.log(`📤 Clicking send button: ${selector}`);
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
          console.log('⏳ Waiting for workflow response...');
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
      console.log(`📸 Screenshot captured: ${screenshot.length} bytes`);
    } catch (error) {
      results.screenshot_error = error.message;
    }

    await page.close();

    console.log('✅ Message test completed');
    res.json(results);

  } catch (error) {
    console.error('❌ Message test error:', error);
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Add frontend testing endpoint
app.post('/test-frontend', async (req, res) => {
  console.log('🎯 Received frontend test request:', req.body);
  try {
    const { frontend_url = 'http://localhost:5173' } = req.body;

    const browser = await initBrowser();
    const page = await browser.newPage();

    console.log('🌐 Navigating to frontend:', frontend_url);
    await page.goto(frontend_url, { waitUntil: 'networkidle', timeout: 30000 });

    // Wait for Vue.js app to fully load
    await page.waitForTimeout(5000);

    // Wait for Vue app to be mounted
    try {
      await page.waitForSelector('#app', { timeout: 10000 });
      console.log('✅ Vue app container found');
    } catch (e) {
      console.log('⚠️ Vue app container not found');
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
          console.log(`✅ Clicked ${navItem}`);
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
      console.log('🤖 Navigating to AI Assistant...');
      const aiAssistantButton = page.getByText('AI ASSISTANT');
      await aiAssistantButton.click();
      await page.waitForTimeout(5000);

      console.log('📍 Current URL after AI Assistant click:', page.url());

      // Wait for ChatInterface component to load
      console.log('⏳ Waiting for chat interface to load...');
      await page.waitForTimeout(3000);

      // Debug: Check what's actually in the DOM
      const chatSection = page.locator('[key="chat"], .chat-interface, [data-testid="chat"]');
      const chatSectionCount = await chatSection.count();
      console.log(`🔍 Chat sections found: ${chatSectionCount}`);

      if (chatSectionCount > 0) {
        const chatSectionHTML = await chatSection.first().innerHTML();
        console.log('📝 Chat section HTML preview:', chatSectionHTML.substring(0, 200) + '...');
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

    console.log('✅ Frontend testing completed:', results.summary);
    res.json(results);

  } catch (error) {
    console.error('❌ Frontend test error:', error);
    res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

const port = 3000;
app.listen(port, '0.0.0.0', async () => {
  console.log('🚀 Playwright service listening on port ' + port);

  try {
    await initBrowser();
    console.log('✅ Browser pre-initialized and ready');
  } catch (error) {
    console.error('⚠️ Failed to pre-initialize browser:', error);
  }
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  console.log('🛑 Shutting down gracefully...');
  if (browser) {
    await browser.close();
    console.log('✅ Browser closed');
  }
  process.exit(0);
});

process.on('SIGINT', async () => {
  console.log('🛑 Received SIGINT, shutting down...');
  if (browser) {
    await browser.close();
    console.log('✅ Browser closed');
  }
  process.exit(0);
});
