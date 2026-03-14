# Interactive Browser Control Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable click, scroll, type, and hover interactions on browser screenshot views in both VisualBrowserPanel and KnowledgeResearchPanel.

**Architecture:** Three layers — (1) new navPage interaction endpoints in `playwright-server.js` on Browser VM (.25), (2) a unified `/interact` proxy in the backend, (3) a shared `InteractiveScreenshot.vue` component replacing raw `<img>` tags in both panels.

**Tech Stack:** Node.js/Express (playwright-server.js), Python/FastAPI (backend), Vue 3 + TypeScript (frontend)

**Issue:** #1416
**Design:** `docs/plans/2026-03-06-interactive-browser-control-design.md`

---

## Task 1: Add jitter helper and viewport helper to playwright-server.js

**Files:**

- Modify: `autobot-browser-worker/playwright-server.js:79-96` (after `captureNavScreenshot`)

**Step 1: Add the jitter and response helpers**

Insert after the `captureNavScreenshot()` function (after line 96 in playwright-server.js):

```javascript
// Anti-detection: random offset +/-2-5px, biased slightly upper-left (#1416)
function applyJitter(x, y) {
  const jitter = () => {
    const sign = Math.random() < 0.6 ? -1 : 1;
    return sign * (2 + Math.random() * 3);
  };
  return { x: x + jitter(), y: y + jitter() };
}

// Standard response for all interaction endpoints (#1416)
async function navInteractionResponse(page) {
  const screenshot = await captureNavScreenshot();
  const vp = page.viewportSize() || { width: 1280, height: 720 };
  return {
    success: true,
    screenshot,
    url: page.url(),
    title: await page.title(),
    viewportWidth: vp.width,
    viewportHeight: vp.height,
  };
}
```

**Step 2: Verify file is valid**

Run: `ssh autobot@172.16.168.25 "node -c /opt/autobot/autobot-browser-worker/playwright-server.js"`

Expected: No syntax errors

**Step 3: Commit**

```bash
git add autobot-browser-worker/playwright-server.js
git commit -m "feat(browser): add jitter and viewport helpers (#1416)"
```

---

## Task 2: Add /click endpoint to playwright-server.js

**Files:**

- Modify: `autobot-browser-worker/playwright-server.js` (insert after `/reload` endpoint, before the `/search` endpoint block at line ~173)

**Step 1: Add the /click endpoint**

Insert after the `// --- End persistent navigation page endpoints ---` comment:

```javascript
// --- Interactive browser control endpoints (#1416) ---

app.post('/click', async (req, res) => {
  const { x, y } = req.body;
  if (typeof x !== 'number' || typeof y !== 'number') {
    return res.status(400).json({ success: false, error: 'x and y coordinates required' });
  }
  try {
    const page = await ensureNavPage();
    const jittered = applyJitter(x, y);
    logger.info('Click at:', { original: { x, y }, jittered });
    await page.mouse.click(jittered.x, jittered.y);
    await page.waitForTimeout(300);
    res.json(await navInteractionResponse(page));
  } catch (e) {
    logger.error('click error:', e.message);
    res.status(500).json({ success: false, error: e.message });
  }
});
```

**Step 2: Test manually**

Run: `ssh autobot@172.16.168.25 "curl -s -X POST http://localhost:3000/click -H 'Content-Type: application/json' -d '{\"x\":100,\"y\":100}'" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['success'], d.get('viewportWidth'))"`

Expected: `True 1280` (or similar viewport width)

**Step 3: Commit**

```bash
git add autobot-browser-worker/playwright-server.js
git commit -m "feat(browser): add /click endpoint with jitter (#1416)"
```

---

## Task 3: Add /scroll endpoint to playwright-server.js

**Files:**

- Modify: `autobot-browser-worker/playwright-server.js` (insert after `/click` endpoint)

**Step 1: Add the /scroll endpoint**

```javascript
app.post('/scroll', async (req, res) => {
  const { deltaX = 0, deltaY = 0 } = req.body;
  if (typeof deltaX !== 'number' || typeof deltaY !== 'number') {
    return res.status(400).json({ success: false, error: 'deltaX and deltaY must be numbers' });
  }
  try {
    const page = await ensureNavPage();
    logger.info('Scroll:', { deltaX, deltaY });
    await page.mouse.wheel(deltaX, deltaY);
    await page.waitForTimeout(200);
    res.json(await navInteractionResponse(page));
  } catch (e) {
    logger.error('scroll error:', e.message);
    res.status(500).json({ success: false, error: e.message });
  }
});
```

**Step 2: Test manually**

Run: `ssh autobot@172.16.168.25 "curl -s -X POST http://localhost:3000/scroll -H 'Content-Type: application/json' -d '{\"deltaY\":300}'" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['success'])"`

Expected: `True`

**Step 3: Commit**

```bash
git add autobot-browser-worker/playwright-server.js
git commit -m "feat(browser): add /scroll endpoint (#1416)"
```

---

## Task 4: Add /type and /hover endpoints to playwright-server.js

**Files:**

- Modify: `autobot-browser-worker/playwright-server.js` (insert after `/scroll` endpoint)

**Step 1: Add /type endpoint**

```javascript
app.post('/type', async (req, res) => {
  const { text } = req.body;
  if (!text || typeof text !== 'string') {
    return res.status(400).json({ success: false, error: 'text string required' });
  }
  try {
    const page = await ensureNavPage();
    logger.info('Type:', text.substring(0, 50));
    await page.keyboard.type(text, { delay: 30 + Math.random() * 40 });
    await page.waitForTimeout(200);
    res.json(await navInteractionResponse(page));
  } catch (e) {
    logger.error('type error:', e.message);
    res.status(500).json({ success: false, error: e.message });
  }
});
```

**Step 2: Add /hover endpoint**

```javascript
app.post('/hover', async (req, res) => {
  const { x, y } = req.body;
  if (typeof x !== 'number' || typeof y !== 'number') {
    return res.status(400).json({ success: false, error: 'x and y coordinates required' });
  }
  try {
    const page = await ensureNavPage();
    const jittered = applyJitter(x, y);
    logger.info('Hover at:', { original: { x, y }, jittered });
    await page.mouse.move(jittered.x, jittered.y);
    await page.waitForTimeout(200);
    res.json(await navInteractionResponse(page));
  } catch (e) {
    logger.error('hover error:', e.message);
    res.status(500).json({ success: false, error: e.message });
  }
});

// --- End interactive browser control endpoints (#1416) ---
```

**Step 3: Test both**

Run: `ssh autobot@172.16.168.25 "curl -s -X POST http://localhost:3000/type -H 'Content-Type: application/json' -d '{\"text\":\"hello\"}'" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['success'])"`

Expected: `True`

Run: `ssh autobot@172.16.168.25 "curl -s -X POST http://localhost:3000/hover -H 'Content-Type: application/json' -d '{\"x\":200,\"y\":200}'" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['success'])"`

Expected: `True`

**Step 4: Commit**

```bash
git add autobot-browser-worker/playwright-server.js
git commit -m "feat(browser): add /type and /hover endpoints (#1416)"
```

---

## Task 5: Update existing navPage endpoints to include viewport dimensions

**Files:**

- Modify: `autobot-browser-worker/playwright-server.js` — update `/navigate`, `/screenshot`, `/back`, `/forward`, `/reload` responses

**Step 1: Replace response patterns to use navInteractionResponse**

Update each of the 5 existing navPage endpoints to use the new helper. For example, `/navigate`:

Before:

```javascript
    res.json({ success: true, url: page.url(), title: await page.title(), screenshot });
```

After:

```javascript
    res.json(await navInteractionResponse(page));
```

Apply the same pattern to: `/screenshot`, `/back`, `/forward`, `/reload`.

**Step 2: Test that navigate still works with new response shape**

Run: `ssh autobot@172.16.168.25 "curl -s -X POST http://localhost:3000/navigate -H 'Content-Type: application/json' -d '{\"url\":\"https://example.com\"}'" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['success'], d.get('viewportWidth'), d.get('url'))"`

Expected: `True 1280 https://example.com/` (or similar)

**Step 3: Commit**

```bash
git add autobot-browser-worker/playwright-server.js
git commit -m "feat(browser): add viewport dimensions to all navPage responses (#1416)"
```

---

## Task 6: Deploy updated playwright-server.js to Browser VM (.25)

**Files:**

- Deploy: `autobot-browser-worker/playwright-server.js` to `.25:/opt/autobot/autobot-browser-worker/`

**Step 1: Sync file to .25**

```bash
rsync -avz autobot-browser-worker/playwright-server.js autobot@172.16.168.25:/opt/autobot/autobot-browser-worker/playwright-server.js
```

**Step 2: Restart service on .25**

```bash
ssh autobot@172.16.168.25 "sudo systemctl restart autobot-playwright"
```

**Step 3: Verify service is running and endpoints work**

```bash
ssh autobot@172.16.168.25 "systemctl is-active autobot-playwright && curl -s http://localhost:3000/health | python3 -c 'import sys,json; print(json.load(sys.stdin))'"
```

Expected: `active` and `{'status': 'healthy', ...}`

**Step 4: Smoke test all new endpoints**

```bash
ssh autobot@172.16.168.25 "curl -s -X POST http://localhost:3000/navigate -H 'Content-Type: application/json' -d '{\"url\":\"https://example.com\"}' | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"navigate:\", d[\"success\"], d.get(\"viewportWidth\"))'"
ssh autobot@172.16.168.25 "curl -s -X POST http://localhost:3000/click -H 'Content-Type: application/json' -d '{\"x\":100,\"y\":100}' | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"click:\", d[\"success\"])'"
ssh autobot@172.16.168.25 "curl -s -X POST http://localhost:3000/scroll -H 'Content-Type: application/json' -d '{\"deltaY\":300}' | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"scroll:\", d[\"success\"])'"
ssh autobot@172.16.168.25 "curl -s -X POST http://localhost:3000/type -H 'Content-Type: application/json' -d '{\"text\":\"test\"}' | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"type:\", d[\"success\"])'"
ssh autobot@172.16.168.25 "curl -s -X POST http://localhost:3000/hover -H 'Content-Type: application/json' -d '{\"x\":200,\"y\":200}' | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"hover:\", d[\"success\"])'"
```

Expected: All print `True`

---

## Task 7: Add /interact proxy endpoint to backend

**Files:**

- Modify: `autobot-backend/api/playwright.py` — add `InteractRequest` model and `/interact` endpoint

**Step 1: Add the Pydantic model**

Insert after the `ReloadRequest` class (around line 63):

```python
class InteractRequest(BaseModel):
    action: str  # "click" | "scroll" | "type" | "hover"
    params: dict  # { x, y } | { deltaX, deltaY } | { text }
```

**Step 2: Add the /interact endpoint**

Insert after the existing `BROWSER_VM_URL` definition (around line 69), add the valid actions set and endpoint:

```python
VALID_INTERACT_ACTIONS = {"click", "scroll", "type", "hover"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="interact",
    error_code_prefix="PLAYWRIGHT",
)
@router.post("/interact")
async def interact_with_browser(request: InteractRequest):
    """
    Interactive browser control - click, scroll, type, hover (#1416)

    Proxies interaction commands to Browser VM navPage endpoints.
    """
    if request.action not in VALID_INTERACT_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action: {request.action}. "
            f"Valid: {', '.join(sorted(VALID_INTERACT_ACTIONS))}",
        )
    try:
        http_client = get_http_client()
        async with await http_client.post(
            f"{BROWSER_VM_URL}/{request.action}",
            json=request.params,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            result = await response.json()
            if response.status == 200:
                return result
            else:
                raise HTTPException(
                    status_code=response.status,
                    detail=result.get("error", f"{request.action} failed"),
                )
    except aiohttp.ClientError as e:
        logger.error("Browser VM connection error: %s", e)
        raise HTTPException(
            status_code=503,
            detail=f"Browser VM unavailable: {str(e)}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Interact error (%s): %s", request.action, e)
        raise HTTPException(
            status_code=500,
            detail=f"{request.action} failed: {str(e)}",
        )
```

**Step 3: Verify no syntax errors**

Run: `cd /home/kali/Desktop/AutoBot && python3 -c "import ast; ast.parse(open('autobot-backend/api/playwright.py').read()); print('OK')"`

Expected: `OK`

**Step 4: Commit**

```bash
git add autobot-backend/api/playwright.py
git commit -m "feat(browser): add /interact proxy endpoint (#1416)"
```

---

## Task 8: Create InteractiveScreenshot.vue component

**Files:**

- Create: `autobot-frontend/src/components/browser/InteractiveScreenshot.vue`

**Step 1: Create the component**

Create the file with the full component code (see design doc for props/events spec). The component handles:

- Click on image with coordinate scaling (`clickX / imgWidth * viewportWidth`)
- Mousewheel scroll with 100ms debounce and delta accumulation
- Scroll buttons toolbar (up/down/page-up/page-down) on the right edge
- Type overlay that appears on keypress, submits on Enter/blur
- Loading state with opacity dim
- Empty state slot for customization

Key implementation details:

- `tabindex="0"` on container div to receive keyboard events
- `event.preventDefault()` on wheel to stop page scrolling
- `draggable="false"` on img to prevent drag-and-drop interference
- Jitter is server-side only — frontend sends exact scaled coordinates

**Step 2: Verify it compiles**

Run: `cd /home/kali/Desktop/AutoBot/autobot-frontend && npx vue-tsc --noEmit 2>&1 | grep -i "InteractiveScreenshot" | head -5`

Expected: No errors

**Step 3: Commit**

```bash
git add autobot-frontend/src/components/browser/InteractiveScreenshot.vue
git commit -m "feat(browser): create InteractiveScreenshot shared component (#1416)"
```

---

## Task 9: Add i18n strings for InteractiveScreenshot

**Files:**

- Modify: `autobot-frontend/src/i18n/locales/en.json`

**Step 1: Add browser.interactive namespace**

Find or create the `"browser"` section in `en.json`. Add the `"interactive"` subsection:

```json
"browser": {
  "interactive": {
    "screenshotAlt": "Live browser view",
    "noScreenshot": "No screenshot available",
    "scrollUp": "Scroll up",
    "scrollDown": "Scroll down",
    "pageUp": "Page up",
    "pageDown": "Page down",
    "typePlaceholder": "Type text and press Enter...",
    "typeLabel": "Keyboard input"
  }
}
```

If `"browser"` already exists, merge `"interactive"` into it.

**Step 2: Commit**

```bash
git add autobot-frontend/src/i18n/locales/en.json
git commit -m "feat(i18n): add interactive browser control strings (#1416)"
```

---

## Task 10: Integrate InteractiveScreenshot into VisualBrowserPanel

**Files:**

- Modify: `autobot-frontend/src/components/chat/VisualBrowserPanel.vue`

**Step 1: Add import**

After the existing imports (around line 18), add:

```typescript
import InteractiveScreenshot from '@/components/browser/InteractiveScreenshot.vue'
```

**Step 2: Add viewport state refs**

After existing refs (around line 33), add:

```typescript
const viewportWidth = ref(1280)
const viewportHeight = ref(720)
```

**Step 3: Add interact handler**

After the `handleKeydown` function (around line 161), add:

```typescript
async function handleInteract(payload: {
  action: string
  params: Record<string, unknown>
}): Promise<void> {
  if (!isConnected.value) return
  loading.value = true
  error.value = null
  try {
    const data = (await ApiClient.post(
      '/api/playwright/interact',
      payload
    )) as Record<string, unknown>
    if (data.screenshot) screenshot.value = data.screenshot as string
    if (data.url) {
      currentUrl.value = data.url as string
      url.value = data.url as string
    }
    if (data.title) pageTitle.value = data.title as string
    if (data.viewportWidth)
      viewportWidth.value = data.viewportWidth as number
    if (data.viewportHeight)
      viewportHeight.value = data.viewportHeight as number
  } catch (e) {
    logger.warn('Interact failed:', e)
  } finally {
    loading.value = false
  }
}
```

**Step 4: Update navigate/goBack/goForward/captureScreenshot to capture viewport**

In each function that receives a response with viewport data, add after existing field extraction:

```typescript
    if (nav.viewportWidth) viewportWidth.value = nav.viewportWidth as number
    if (nav.viewportHeight) viewportHeight.value = nav.viewportHeight as number
```

**Step 5: Replace the `<img>` tag in the template**

Replace lines 263-270:

```html
        <!-- Screenshot Display -->
        <img
          v-else-if="screenshot"
          :src="`data:image/png;base64,${screenshot}`"
          :alt="$t('chat.browser.screenshot')"
          class="screenshot-img"
          :class="{ 'screenshot-img--loading': loading }"
        />
```

With:

```html
        <!-- Interactive Screenshot Display (#1416) -->
        <InteractiveScreenshot
          v-else-if="screenshot"
          :screenshot="screenshot"
          :loading="loading"
          :interactive="isConnected"
          :viewport-width="viewportWidth"
          :viewport-height="viewportHeight"
          @interact="handleInteract"
        />
```

**Step 6: Commit**

```bash
git add autobot-frontend/src/components/chat/VisualBrowserPanel.vue
git commit -m "feat(browser): integrate InteractiveScreenshot into VisualBrowserPanel (#1416)"
```

---

## Task 11: Integrate InteractiveScreenshot into KnowledgeResearchPanel

**Files:**

- Modify: `autobot-frontend/src/components/knowledge/KnowledgeResearchPanel.vue`

**Step 1: Add import**

After the existing imports (around line 18-20), add:

```typescript
import InteractiveScreenshot from '@/components/browser/InteractiveScreenshot.vue'
```

**Step 2: Add viewport state refs**

After existing refs (around line 35), add:

```typescript
const viewportWidth = ref(1280)
const viewportHeight = ref(720)
```

**Step 3: Add interact handler**

After the `fetchScreenshot` function (around line 78), add:

```typescript
async function handleInteract(payload: {
  action: string
  params: Record<string, unknown>
}): Promise<void> {
  if (!browserConnected.value) return
  screenshotLoading.value = true
  try {
    const data = (await ApiClient.post(
      '/api/playwright/interact',
      payload
    )) as Record<string, unknown>
    if (data.screenshot) screenshot.value = data.screenshot as string
    if (data.viewportWidth)
      viewportWidth.value = data.viewportWidth as number
    if (data.viewportHeight)
      viewportHeight.value = data.viewportHeight as number
  } catch (e) {
    logger.warn('Interact failed:', e)
  } finally {
    screenshotLoading.value = false
  }
}
```

**Step 4: Update fetchScreenshot to capture viewport**

In `fetchScreenshot()`, after `screenshot.value = data.screenshot as string`, add:

```typescript
      if (data.viewportWidth) viewportWidth.value = data.viewportWidth as number
      if (data.viewportHeight) viewportHeight.value = data.viewportHeight as number
```

**Step 5: Replace the `<img>` tag**

Replace lines 441-448:

```html
          <!-- Screenshot -->
          <img
            v-if="screenshot"
            :src="`data:image/png;base64,${screenshot}`"
            :alt="$t('knowledge.research.liveBrowserView')"
            class="screenshot-img"
            :class="{ 'screenshot-img--loading': screenshotLoading }"
          />
```

With:

```html
          <!-- Interactive Screenshot (#1416) -->
          <InteractiveScreenshot
            v-if="screenshot"
            :screenshot="screenshot"
            :loading="screenshotLoading"
            :interactive="isResearching && browserConnected"
            :viewport-width="viewportWidth"
            :viewport-height="viewportHeight"
            @interact="handleInteract"
          />
```

**Step 6: Commit**

```bash
git add autobot-frontend/src/components/knowledge/KnowledgeResearchPanel.vue
git commit -m "feat(browser): integrate InteractiveScreenshot into KnowledgeResearchPanel (#1416)"
```

---

## Task 12: Fix KnowledgeResearchPanel initial status check

**Files:**

- Modify: `autobot-frontend/src/components/knowledge/KnowledgeResearchPanel.vue`

**Step 1: Add onMounted import and call checkBrowserStatus on mount**

Replace:

```typescript
import { ref, onUnmounted } from 'vue'
```

With:

```typescript
import { ref, onMounted, onUnmounted } from 'vue'
```

Add after the `onUnmounted` block (around line 261):

```typescript
onMounted(() => {
  checkBrowserStatus()
})
```

**Step 2: Commit**

```bash
git add autobot-frontend/src/components/knowledge/KnowledgeResearchPanel.vue
git commit -m "fix(browser): check browser status on research panel mount (#1416)"
```

---

## Task 13: Build frontend and verify

**Step 1: Build frontend**

Run: `cd /home/kali/Desktop/AutoBot/autobot-frontend && npm run build 2>&1 | tail -10`

Expected: Build succeeds with no errors

**Step 2: If build fails, fix TypeScript/import errors and re-commit**

**Step 3: Sync to frontend VM (.21)**

```bash
./autobot-infrastructure/shared/scripts/utilities/sync-to-vm.sh 172.16.168.21 /home/kali/Desktop/AutoBot/autobot-frontend /opt/autobot/autobot-frontend
ssh autobot@172.16.168.21 "cd /opt/autobot/autobot-frontend && npm run build"
```

**Step 4: Verify in browser**

Navigate to `https://172.16.168.21/knowledge/research` — status should show "Connected" on mount.

Navigate to the chat browser tab — click on a screenshot and verify the page responds.

---

## Task 14: End-to-end verification

**Step 1: Navigate to a page via the visual browser**

Enter `https://example.com` in the VisualBrowserPanel address bar, click Go.

**Step 2: Test click interaction**

Click on any link in the screenshot. Verify:

- Screenshot refreshes showing the navigated page
- URL updates in the address bar

**Step 3: Test scroll interaction**

Use mousewheel over the screenshot on a long page. Verify:

- Screenshot refreshes showing scrolled content
- Scroll buttons work (up/down arrows on right edge)

**Step 4: Test type interaction**

Navigate to a search engine, click the search box area, then type. Verify:

- Type overlay appears
- Text is sent and screenshot shows typed text

**Step 5: Close issue**

```bash
gh issue close 1416 --comment "Implemented interactive browser control. Click/scroll/type/hover on screenshot views in both VisualBrowserPanel and KnowledgeResearchPanel. Also fixed initial status check on research panel."
```
