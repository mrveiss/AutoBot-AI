# Frontend Cache Clearing Guide

## Overview

After deploying a new version of the AutoBot frontend, users may continue to see the old version due to browser caching. This guide explains why this happens and how to resolve it.

## Why Browser Caching Occurs

Modern browsers aggressively cache static assets (JavaScript, CSS, images) to improve performance. Even though our nginx configuration is designed to prevent caching of HTML files and force revalidation, browsers may:

1. **Ignore or misinterpret cache headers** in certain scenarios
2. **Cache service worker registrations** that continue serving old assets
3. **Use disk cache** even when memory cache is cleared
4. **Persist cached assets** across browser restarts

## Quick Fix: Clear Browser Cache

### Google Chrome / Chromium / Edge

**Method 1: Hard Refresh (Fastest)**
1. Press `Ctrl + Shift + R` (Windows/Linux) or `Cmd + Shift + R` (macOS)
2. This forces Chrome to bypass cache for the current page

**Method 2: Clear All Cached Data (Most Thorough)**
1. Press `Ctrl + Shift + Delete` (Windows/Linux) or `Cmd + Shift + Delete` (macOS)
2. Select **"All time"** from the time range dropdown
3. Check only **"Cached images and files"**
4. Click **"Clear data"**
5. Reload the page (`F5` or `Ctrl + R`)

**Method 3: DevTools Cache Clear**
1. Open DevTools (`F12`)
2. Go to the **Network** tab
3. Right-click on any network request
4. Select **"Clear browser cache"**
5. Reload the page

### Mozilla Firefox

**Method 1: Hard Refresh**
1. Press `Ctrl + Shift + R` (Windows/Linux) or `Cmd + Shift + R` (macOS)

**Method 2: Clear Cache**
1. Press `Ctrl + Shift + Delete` (Windows/Linux) or `Cmd + Shift + Delete` (macOS)
2. Select **"Everything"** from the time range
3. Check only **"Cache"**
4. Click **"Clear Now"**
5. Reload the page (`F5`)

### Safari (macOS)

**Method 1: Hard Refresh**
1. Press `Cmd + Option + R`

**Method 2: Clear Cache**
1. Go to **Safari → Settings → Privacy**
2. Click **"Manage Website Data..."**
3. Search for your AutoBot domain
4. Click **"Remove"** then **"Done"**
5. Reload the page

### All Browsers: Incognito/Private Mode (Testing)

For quick testing without clearing cache:

1. **Chrome/Edge**: `Ctrl + Shift + N` (Windows/Linux) or `Cmd + Shift + N` (macOS)
2. **Firefox**: `Ctrl + Shift + P` (Windows/Linux) or `Cmd + Shift + P` (macOS)
3. **Safari**: `Cmd + Shift + N`

Navigate to the AutoBot URL in the private window. If the new version loads correctly, the issue is cache-related.

## Verify New Version is Loading

After clearing cache, verify you're seeing the new deployment:

### Method 1: Check Asset Hashes in Network Tab

1. Open DevTools (`F12`)
2. Go to the **Network** tab
3. Reload the page
4. Look for JavaScript files like `index-[HASH].js`
5. The hash should match the latest deployment (compare with `dist/index.html` on the server)

Example:
```
OLD: /assets/index-BcXl2NoH.js
NEW: /assets/index-DfGh3KpL.js  ← Hash changed = new build
```

### Method 2: Check Console for Version Log

If the frontend logs its version on startup, check the browser console:

1. Open DevTools (`F12`)
2. Go to the **Console** tab
3. Look for version/build information in the startup logs

### Method 3: Check Last-Modified Header

1. Open DevTools (`F12`)
2. Go to the **Network** tab
3. Reload the page
4. Click on `index.html`
5. Check the **Response Headers** for `Last-Modified` or `ETag`
6. Compare with the server's deployment timestamp

## Technical Details: How Cache Headers Work

Our nginx configuration applies different cache strategies based on file type:

### HTML Files (`*.html`)
```nginx
Cache-Control: no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0
```
- `no-store`: Don't store this response in any cache
- `no-cache`: Revalidate with server before using cached copy
- `must-revalidate`: Can't serve stale cache, must check server
- `max-age=0`: Expires immediately

**Result**: Browser fetches fresh HTML on every request.

### JavaScript/CSS Files (`*.js`, `*.css`)
```nginx
Cache-Control: public, immutable, max-age=31536000
```
- `public`: Can be cached by any cache (browser, CDN, proxy)
- `immutable`: Content will NEVER change (safe to cache forever)
- `max-age=31536000`: Cache for 1 year (31536000 seconds)

**Result**: Once cached, these files are served instantly from cache. Since filenames include content hashes (e.g., `index-BcXl2NoH.js`), new deployments generate new filenames, automatically bypassing cache.

### Why This Usually Works

1. User requests `https://autobot.example.com/`
2. Browser fetches `index.html` (no-cache → always fresh)
3. `index.html` references `<script src="/assets/index-DfGh3KpL.js">`
4. If hash is **new**, browser fetches new JS (cache miss)
5. If hash is **same**, browser uses cached JS (cache hit)

**The problem**: If the browser somehow cached the old `index.html`, it will reference old asset hashes, serving the old version entirely.

## Nginx Configuration Details

The current configuration (deployed via Ansible) includes:

```jinja2
# Enable ETag support for cache validation
etag on;

# HTML files - NEVER cache
location ~* \.html$ {
    add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0";
    add_header Pragma "no-cache";
    add_header Expires "0";
    if_modified_since off;
}

# JS/CSS with hash - cache forever
location ~* \.(js|css)$ {
    expires 1y;
    add_header Cache-Control "public, immutable, max-age=31536000";
}
```

## Deployment Best Practices

To minimize cache-related issues after deployments:

### 1. Always Deploy via Ansible
```bash
cd autobot-slm-backend/ansible
ansible-playbook -i inventory/inventory.yml playbooks/deploy-frontend.yml --tags frontend,nginx
```

This ensures:
- Old files are removed from `dist/` before new ones are copied
- Nginx is reloaded with updated configuration
- Proper file permissions are set

### 2. Verify Deployment on Server
```bash
ssh autobot@172.16.168.21
ls -lh /opt/autobot/autobot-user-frontend/dist/
cat /opt/autobot/autobot-user-frontend/dist/index.html
```

Check that:
- Deployment timestamp matches your build
- Asset hashes in `index.html` are new

### 3. Test in Incognito Mode First
Before announcing deployment, test in incognito mode to verify cache doesn't interfere.

### 4. Document Version in Release Notes
Include the asset hash or build timestamp in release notes so users can verify they're running the latest version.

## Troubleshooting

### Issue: Clearing cache doesn't work

**Possible causes**:
1. **Service Worker caching**: Unregister service workers in DevTools → Application → Service Workers
2. **Proxy/CDN caching**: If there's a proxy between users and nginx, it may cache responses
3. **Browser extensions**: Ad blockers or privacy extensions may interfere with cache headers
4. **Old browser version**: Update browser to latest version

### Issue: Only some users see the old version

**Possible causes**:
1. **DNS caching**: Old IP may be cached in DNS if infrastructure changed
2. **Load balancer caching**: If using a load balancer, it may cache responses
3. **Mixed deployments**: Verify all frontend servers are updated (if using multiple)

### Issue: Hard refresh works but normal reload doesn't

**This is expected behavior**: Hard refresh bypasses cache, normal reload respects cache headers. If normal reload serves old content, the cache headers may not be correctly applied.

**Debug steps**:
1. Check network tab: Is `index.html` showing `200` (from cache) or `304` (revalidated)?
2. Verify nginx config is applied: `sudo nginx -t` on the frontend server
3. Check nginx access logs: `sudo tail -f /var/log/nginx/autobot-frontend-access.log`

## Additional Resources

- [MDN: HTTP Caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching)
- [MDN: Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control)
- [Nginx Caching Guide](https://nginx.org/en/docs/http/ngx_http_headers_module.html)

## Support

If cache clearing doesn't resolve the issue:

1. **Verify deployment**: Check that new files are actually on the server
2. **Check nginx logs**: Look for errors in `/var/log/nginx/autobot-frontend-error.log`
3. **Test with curl**: `curl -I https://autobot.example.com/` to see raw headers
4. **Create GitHub issue**: Include browser version, console errors, and network tab screenshots
