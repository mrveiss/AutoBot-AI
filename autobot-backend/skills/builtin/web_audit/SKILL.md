---
name: web-audit
description: Full security, SEO, and AI-friendliness audit for any website. Runs multi-pass checks covering HTTP headers, DNS/subdomain recon, port scan, TLS, CORS, email spoofing, exposed admin panels, plugin CVEs, open resolvers, FTP, per-page SEO, performance, and compromise indicators. Outputs a self-contained HTML report.
---

# /web-audit — Full Website Audit

Performs a comprehensive multi-pass audit of any website and writes a self-contained HTML report to the current working directory.

**Usage:** `/web-audit https://example.com`

---

## Phase 0 — Setup

Extract the target URL from the user's arguments. Derive BASE (e.g. `https://mbd.lv`) and DOMAIN (e.g. `mbd.lv`).

Create a temp working dir and page-audit helper script:

```bash
mkdir -p /tmp/webaudit
cat << 'EOF' > /tmp/audit_page.sh
#!/bin/bash
URL="$1"
echo "=== PAGE: $URL ==="
HTML=$(curl -sL --max-time 12 "$URL" 2>&1)
STATUS=$(curl -o /dev/null -sw "%{http_code}" -L --max-time 12 "$URL" 2>/dev/null)
echo "STATUS: $STATUS"
echo "TITLE: $(echo "$HTML" | grep -oP '(?<=<title>)[^<]+')"
echo "DESC_LEN: $(echo "$HTML" | grep -oP 'name="description" content="[^"]+"' | head -1 | grep -oP 'content="[^"]+"' | wc -c)"
echo "DESC: $(echo "$HTML" | grep -oP 'name="description" content="[^"]+"' | head -1)"
echo "CANONICAL: $(echo "$HTML" | grep -oP 'rel="canonical" href="[^"]+"' | head -1)"
echo "ROBOTS_META: $(echo "$HTML" | grep -oP 'name=['\''"]robots['\''"] content="[^"]+"' | head -1)"
echo "OG_TITLE: $(echo "$HTML" | grep -oP 'property="og:title" content="[^"]+"' | head -1)"
echo "OG_DESC: $(echo "$HTML" | grep -oP 'property="og:description" content="[^"]+"' | head -1)"
echo "OG_IMAGE: $(echo "$HTML" | grep -oP 'property="og:image" content="[^"]+"' | head -1)"
echo "TW_CARD: $(echo "$HTML" | grep -oP 'name="twitter:card" content="[^"]+"' | head -1)"
echo "HREFLANG: $(echo "$HTML" | grep -oP 'hreflang="[^"]+"' | tr '\n' ' ')"
echo "SCHEMA_TYPES: $(echo "$HTML" | grep -oP '"@type":"[^"]+"' | sort -u | tr '\n' ' ')"
echo "IMG_TOTAL: $(echo "$HTML" | grep -oP '<img[^>]*>' | wc -l)"
echo "IMG_NO_ALT: $(echo "$HTML" | grep -oP '<img[^>]*>' | grep -v 'alt=' | wc -l)"
echo "NOINDEX: $(echo "$HTML" | grep -i noindex | head -1)"
echo "WORD_COUNT: $(echo "$HTML" | sed 's/<[^>]*>//g' | wc -w)"
echo "RENDER_BLOCKING: $(echo "$HTML" | grep -oP '<script[^>]*src="[^"]+"[^>]*>' | grep -v 'async\|defer' | wc -l)"
echo "LAZY_IMGS: $(echo "$HTML" | grep -oP 'loading="lazy"' | wc -l)"
echo "=== END ==="
EOF
chmod +x /tmp/audit_page.sh
```

---

## Phase 1 — Global Reconnaissance (run all in parallel)

```bash
# 1a. HTTP response headers
curl -sI BASE/ 2>/dev/null

# 1b. robots.txt + sitemap
curl -s BASE/robots.txt
curl -s BASE/sitemap.xml || curl -s BASE/sitemap_index.xml

# 1c. DNS records — full enumeration
dig DOMAIN ANY +noall +answer
dig DOMAIN MX +short
dig DOMAIN TXT +short
dig DOMAIN NS +short
dig DOMAIN A +short
dig _dmarc.DOMAIN TXT +short

# 1d. DKIM selector enumeration
for sel in google default mail dkim smtp s1 s2 k1 selector1 selector2 mbd; do
  result=$(dig TXT ${sel}._domainkey.DOMAIN +short 2>/dev/null)
  [ -n "$result" ] && echo "DKIM $sel: FOUND"
done

# 1e. SSL certificate — SANs reveal related domains
echo | openssl s_client -connect DOMAIN:443 -servername DOMAIN 2>/dev/null \
  | openssl x509 -noout -text 2>/dev/null | grep -A5 "Subject Alternative Name"
echo | openssl s_client -connect DOMAIN:443 -servername DOMAIN 2>/dev/null \
  | openssl x509 -noout -dates 2>/dev/null

# 1f. TLS protocol version check (flag TLS 1.0/1.1 as high)
for proto in tls1 tls1_1 tls1_2 tls1_3; do
  result=$(echo | openssl s_client -connect DOMAIN:443 -$proto 2>&1 | grep -i 'handshake\|error' | head -1)
  echo "$proto: $result"
done

# 1g. HTTP to HTTPS redirect
curl -sIL http://DOMAIN/ 2>&1 | grep -i "location\|HTTP/"

# 1h. CORS — test on main page and REST/API endpoint
curl -sI -H "Origin: https://evil-test-cors.com" BASE/ 2>/dev/null | grep -i "access-control"
curl -sI -H "Origin: https://evil-test-cors.com" BASE/wp-json/ 2>/dev/null | grep -i "access-control"
curl -sI -H "Origin: null" BASE/wp-json/ 2>/dev/null | grep -i "access-control"
```

**Record:** security headers present/absent, HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, CORS origin reflection + credentials, SPF (~all vs -all), DMARC policy (none/quarantine/reject), DKIM present, cert SANs and expiry, TLS 1.0/1.1 enabled.

---

## Phase 1b — Subdomain & Infrastructure Discovery

Run in parallel with Phase 1.

```bash
# Certificate transparency — finds subdomains not in DNS
curl -s "https://crt.sh/?q=%.DOMAIN&output=json" 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
names = set()
for cert in data:
    for name in cert.get('name_value','').split('\n'):
        name = name.strip().lstrip('*.')
        if 'DOMAIN' in name:
            names.add(name)
for n in sorted(names): print(n)
"

# DNS subdomain bruteforce (common names)
for sub in www mail webmail ftp smtp api admin dev staging campaigns preview vpn crm erp shop blog; do
  result=$(dig +short A ${sub}.DOMAIN 2>/dev/null)
  [ -n "$result" ] && echo "${sub}.DOMAIN -> $result"
done

# Resolve each subdomain found and get IP info
# For each unique IP: curl -s https://ipinfo.io/IP/json

# Port scan main server IP
for port in 21 22 25 53 80 110 143 443 465 587 993 995 3306 5432 6379 8080 8443 27017; do
  (timeout 2 bash -c "echo >/dev/tcp/SERVER_IP/$port" 2>/dev/null && echo "OPEN: $port") || true
done

# Open DNS resolver check (flag as High if server resolves external domains)
dig @SERVER_IP google.com A +short 2>/dev/null | grep -q '[0-9]' && echo "OPEN RESOLVER: YES" || echo "OPEN RESOLVER: NO"

# FTP banner (if port 21 open)
timeout 5 bash -c "echo '' | nc -w3 SERVER_IP 21" 2>/dev/null | head -3
# Test anonymous FTP
(echo 'USER anonymous'; sleep 1; echo 'PASS test@test.com'; sleep 1) | timeout 5 nc -w5 SERVER_IP 21 2>/dev/null | grep -i '230\|530\|anonymous'
```

**For each subdomain found:** check HTTP status, identify platform (WordPress, Mautic, custom), run same sensitive-path scan from Phase 3. A subdomain on the same server inherits all server-level vulnerabilities (phpMyAdmin, shared MySQL, same filesystem).

---

## Phase 2 — WordPress / CMS Detection & Specific Checks

Run only if WordPress indicators found (wp-content, wp-json, generator meta).

```bash
# Version disclosure
curl -s BASE/ | grep -oP 'ver=[\d.]+' | sort -uV | tail -3

# WordPress core version vs latest
INSTALLED_VER=$(curl -s BASE/ | grep -oP 'ver=[\d.]+' | sort -uV | tail -1 | cut -d= -f2)
LATEST_VER=$(curl -s "https://api.wordpress.org/core/version-check/1.7/" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['offers'][0]['current'])" 2>/dev/null)
echo "Installed: $INSTALLED_VER | Latest: $LATEST_VER"

# Sensitive files
for f in readme.html license.txt wp-config.php.bak wp-config.php.old \
          wp-config.txt .env .git/HEAD .git/config phpinfo.php debug.log \
          wp-content/debug.log; do
  s=$(curl -o /dev/null -sw "%{http_code}" --max-time 5 BASE/$f)
  echo "$s  $f"
done

# WordPress attack surfaces
curl -sI BASE/wp-login.php
curl -sI -X POST BASE/xmlrpc.php
curl -s -X POST BASE/xmlrpc.php \
  -d '<?xml version="1.0"?><methodCall><methodName>system.listMethods</methodName></methodCall>' | head -3
curl -sI BASE/wp-json/ | head -10
curl -sI "BASE/wp-cron.php?doing_wp_cron"
curl -s -X POST BASE/wp-admin/admin-ajax.php \
  -d "action=heartbeat&screen_id=front" | head -3

# Username enumeration
curl -sIL "BASE/?author=1" | grep -i "location\|HTTP/"
curl -s "BASE/wp-json/wp/v2/users" | python3 -m json.tool 2>/dev/null | head -20

# Password reset oracle (different messages for valid vs invalid users)
r1=$(curl -s -X POST "BASE/wp-login.php?action=lostpassword" \
  -d "user_login=admin&redirect_to=&wp-submit=Get+New+Password" --connect-timeout 5 2>/dev/null \
  | grep -oi 'error\|invalid\|not found\|check your email\|email has been sent' | head -1)
r2=$(curl -s -X POST "BASE/wp-login.php?action=lostpassword" \
  -d "user_login=notarealuser99999xyz&redirect_to=&wp-submit=Get+New+Password" --connect-timeout 5 2>/dev/null \
  | grep -oi 'error\|invalid\|not found\|check your email\|email has been sent' | head -1)
echo "admin reset: $r1 | fakeuser reset: $r2"
# Different responses = username oracle

# Plugin version check via WordPress.org API
for plugin in contact-form-7 wordpress-seo cookie-law-info wordfence; do
  installed=$(curl -s BASE/wp-content/plugins/${plugin}/readme.txt 2>/dev/null | grep -i 'stable tag' | head -1)
  latest=$(curl -s "https://api.wordpress.org/plugins/info/1.0/${plugin}.json" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('Latest:', d.get('version'), '| Updated:', d.get('last_updated','')[:10])" 2>/dev/null)
  echo "$plugin | $installed | $latest"
done

# REST API endpoint enumeration
curl -s "BASE/wp-json/" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('Namespaces:', d.get('namespaces', []))
" 2>/dev/null

# Cookie flags
curl -sI BASE/wp-login.php | grep -i "set-cookie"

# HTTP methods
curl -sI -X OPTIONS BASE/ | grep -i "allow"
curl -sI -X TRACE BASE/ | head -3

# dev/staging environment check — look for dev subdomains
# If dev.DOMAIN exists: check if it has auth gate
curl -sI https://dev.DOMAIN 2>/dev/null | head -5
```

**Record:** WP version vs latest, outdated plugins with version gap, exposed files, xmlrpc active, user enumeration possible, password reset oracle (same/different message), cookie flags, open registration, REST namespace disclosure.

---

## Phase 3 — Exposed Admin Panels & Services

```bash
for path in phpmyadmin pma webmail mail roundcube admin plesk cpanel ispconfig \
            wp-admin/install.php adminer db adminer.php; do
  s=$(curl -o /dev/null -sw "%{http_code}" --max-time 5 BASE/$path/)
  [ "$s" != "404" ] && echo "$s  /$path/"
done
```

For any panel returning 200:
- Fetch page source and extract version, auth type, connected user identity from JS/HTML
- For phpMyAdmin: look for `user:"..."` in JavaScript `CommonParams.setAll` — this reveals the MySQL username before login
- For Roundcube: check CHANGELOG last-modified date to fingerprint version; compare against CVE timeline
- Check if same panel is accessible on all subdomains on the same server IP

**Roundcube version fingerprinting:**
```bash
curl -sI BASE/webmail/CHANGELOG 2>/dev/null | grep "last-modified"
# Cross-reference with https://github.com/roundcube/roundcubemail/releases
```

---

## Phase 4 — Per-Page Analysis

Enumerate all pages from sitemap. For each unique URL, run `/tmp/audit_page.sh URL` in parallel batches of 8. Collect:

- HTTP status
- Title tag (length, language, keyword relevance)
- Meta description (length: <120 = too short, >160 = too long, language match, typos)
- Canonical URL (present, self-referencing, cross-domain issues)
- robots meta (noindex/nofollow — expected or accidental)
- OG title, description, image (present, correct dimensions signal)
- Twitter card type
- hreflang declarations (correct language codes, reciprocal pairs)
- Schema types present (WebPage, Organization, FAQPage, etc.)
- Image counts: total, missing alt, empty alt
- Noindex (expected vs. unexpected)
- Word count (very low = thin content)
- Render-blocking script count
- Lazy-loaded image count

**Flag these per-page issues:**
- Status not 200 but in sitemap → broken sitemap entry
- Description in wrong language (detect with character set heuristics — Latvian: ā,č,ē,ģ,ī,ķ,ļ,ņ,š,ū,ž; Estonian: õ,ä,ö,ü — cross-check against page hreflang)
- Description < 120 chars
- Missing OG image
- img tags without alt
- Page in sitemap multiple times (duplicate lastmod)
- Noindex set without reason
- Trashed/deleted page accessible

---

## Phase 4b — AI Visibility

Run in parallel with Phase 4. These checks reveal how well the site will be understood and cited by AI-powered search (Perplexity, ChatGPT Search, Gemini) and AI assistants crawling the web.

```bash
# llms.txt — follow redirects; content matters, not just status
curl -sIL BASE/llms.txt 2>/dev/null | grep -i "HTTP\|location\|content-type"
curl -sL BASE/llms.txt 2>/dev/null | head -20

# AI bot crawler policy in robots.txt
curl -s BASE/robots.txt | grep -iA2 'GPTBot\|ClaudeBot\|anthropic-ai\|PerplexityBot\|CCBot\|Bytespider\|cohere\|YouBot\|Diffbot\|ai2Bot\|omgili'
# No match = all AI bots allowed by wildcard (usually good)

# Parse all JSON-LD schema blocks on homepage
curl -sL BASE/ 2>/dev/null | python3 -c "
import sys, re, json
html = sys.stdin.read()
blocks = re.findall(r'<script[^>]*type=[\"\']\s*application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL)
for i, b in enumerate(blocks):
    try:
        d = json.loads(b.strip())
        print(f'Block {i+1}:', json.dumps(d, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f'Block {i+1} parse error:', e)
"

# og:type on homepage (should be 'website', not 'article')
curl -sL BASE/ 2>/dev/null | grep -oP 'property="og:type" content="[^"]+"'

# og:site_name — check for truncation, trailing punctuation
curl -sL BASE/ 2>/dev/null | grep -oP 'property="og:site_name" content="[^"]+"'

# Schema types on key pages — homepage, services, about, contact
for url in BASE/ BASE/services/ BASE/pakalpojumi/ BASE/about/ BASE/par-mums/ BASE/contact/ BASE/kontakti/ BASE/faq/ BASE/buj/; do
  types=$(curl -sL "$url" 2>/dev/null | grep -oP '"@type"\s*:\s*"[^"]+"' | sort -u | tr '\n' ' ')
  [ -n "$types" ] && echo "$url → $types"
done

# Organization schema completeness check
curl -sL BASE/ 2>/dev/null | python3 -c "
import sys, re, json
html = sys.stdin.read()
blocks = re.findall(r'<script[^>]*type=[\"\']\s*application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL)
for b in blocks:
    try:
        d = json.loads(b.strip())
        graph = d.get('@graph', [d])
        for node in graph:
            if node.get('@type') == 'Organization':
                present = [k for k in ['name','url','description','logo','telephone','address','foundingDate','sameAs'] if k in node]
                missing = [k for k in ['name','url','description','logo','telephone','address','foundingDate','sameAs'] if k not in node]
                print('Organization present:', present)
                print('Organization missing:', missing)
                same = node.get('sameAs', [])
                print('sameAs entries:', same)
    except: pass
"

# WebSite SearchAction (sitelinks searchbox)
curl -sL BASE/ 2>/dev/null | grep -i 'SearchAction\|potentialAction\|query-input' | head -3

# Sitemap sub-structure — content type coverage
curl -s BASE/sitemap.xml 2>/dev/null | grep '<loc>' | head -5
curl -s BASE/sitemap_index.xml 2>/dev/null | grep '<loc>\|<sitemap>' | head -20

# Breadcrumb language check — flag if "Home" used on non-English site
curl -sL BASE/ 2>/dev/null | grep -i '"BreadcrumbList"\|"ListItem"\|"name"' | head -10

# Service/FAQ/JobPosting schema on sub-pages
for url in BASE/services/ BASE/pakalpojumi/ BASE/faq/ BASE/buj/ BASE/jobs/ BASE/vakances/; do
  types=$(curl -sL "$url" 2>/dev/null | grep -oP '"@type"\s*:\s*"[^"]+"' | sort -u | tr '\n' ' ')
  [ -n "$types" ] && echo "$url → $types"
done
```

**Record and flag these AI visibility issues:**

| Check | Flag if |
|---|---|
| llms.txt | Missing or redirects to homepage instead of returning structured content |
| AI bot rules | Any of GPTBot / ClaudeBot / PerplexityBot explicitly blocked (Disallow) |
| og:type on homepage | Value is `article` instead of `website` |
| og:site_name | Truncated, trailing punctuation, or inconsistent with Organization `name` |
| Organization schema | Missing `description`, `logo`, `foundingDate`, or `sameAs` |
| sameAs | Fewer than 2 social/profile links; missing LinkedIn for B2B businesses |
| Brand entity consistency | Organization `name`, `og:site_name`, and page title use different brand strings |
| WebSite schema | No `potentialAction` with SearchAction |
| Services page | Only WebPage schema — no `Service` or `ProfessionalService` type |
| FAQ/BUJ page | FAQ content present but no `FAQPage` or `QAPage` schema |
| Vacancy/jobs page | Job listings without `JobPosting` schema |
| Portfolio items | CreativeWork or VisualArtwork schema absent on large portfolios |
| Breadcrumb | Root item named "Home" on a non-English primary language site |
| robots.txt | llms.txt exists but AI crawlers are blocked by Disallow |

**Severity guide:**
- **Medium**: og:type wrong, brand entity inconsistency, Organization missing description/logo, no Service schema on services page, no FAQPage on FAQ page
- **Low**: og:site_name truncation, no SearchAction, no JobPosting schema, breadcrumb language mismatch, no CreativeWork schema, incomplete sameAs, no llms.txt

---

## Phase 5 — Compromise Indicators

```bash
curl -sL BASE/ > /tmp/audit_homepage.html

# Injected content
grep -i "iframe" /tmp/audit_homepage.html
grep -oP 'eval\s*\(' /tmp/audit_homepage.html | wc -l   # should be 0
grep -oP 'base64' /tmp/audit_homepage.html | wc -l       # should be 0 or minimal
grep -iP 'casino|poker|viagra|cialis|pharma|loan|bitcoin|crypto|gambling|payday' /tmp/audit_homepage.html | grep -v 'script\|style' | head -5
grep -i "display:none\|visibility:hidden" /tmp/audit_homepage.html \
  | grep -v "nav\|modal\|overlay\|cookie\|menu" | head -10

# Backdoor file probe
for p in wp-content/uploads/shell.php wp-content/uploads/wp-config.php \
          wp-content/mu-plugins/loader.php wp-content/mu-plugins/wp.php \
          wp-content/uploads/images.php wp-content/plugins/hello.php; do
  s=$(curl -o /dev/null -sw "%{http_code}" --max-time 5 BASE/$p)
  [ "$s" != "404" ] && echo "SUSPICIOUS: $s  $p"
done

# External malware check
curl -s "https://sitecheck.sucuri.net/api/v3/?scan=DOMAIN" \
  | python3 -m json.tool 2>/dev/null | grep -A2 '"malware"\|"blacklists"\|"clean"'
```

---

## Phase 6 — Performance Signals

```bash
# TTFB + transfer size
curl -so /dev/null -w "TTFB: %{time_starttransfer}s | Total: %{time_total}s | Size: %{size_download}B\n" BASE/

# WebP/AVIF usage
curl -s BASE/ | grep -oP '\.webp|\.avif' | wc -l
```

**Flag:** TTFB > 800ms, render-blocking scripts > 5, zero lazy-loaded images, zero WebP/AVIF.

---

## Phase 7 — Related Domain Audit

After initial audit, check for sister/related domains revealed by:
- schema.org `logo.url` pointing to a different domain
- SPF `include:` directives pointing to third-party mail infrastructure
- SSL certificate SANs
- MX record domain (e.g., `mbd-ee.mail.protection.outlook.com` → check `mbd.ee`)
- TXT records: `MS=`, `google-site-verification=`, `mscid=`

For each related domain found, run abbreviated checks:
```bash
# DNS and email auth
dig RELATED_DOMAIN A +short
dig RELATED_DOMAIN MX +short
dig RELATED_DOMAIN TXT +short
dig _dmarc.RELATED_DOMAIN TXT +short

# Server identification
curl -sI https://RELATED_DOMAIN 2>/dev/null | grep -i 'server\|x-powered-by\|content-type'

# Basic sensitive paths
for path in /phpmyadmin/ /webmail/ /wp-login.php /readme.html; do
  code=$(curl -so /dev/null -w "%{http_code}" --connect-timeout 5 https://RELATED_DOMAIN$path 2>/dev/null)
  echo "$code $path"
done
```

**Flag:** No DMARC on related domain, EOL PHP version, exposed admin panels, separate unaudited server.

---

## Phase 8 — Generate HTML Report

Write the report to `./audit_report.html` using the template below. The report is fully self-contained (no external CSS or JS dependencies).

### Report Structure

1. **Header** — site URL, date, pages crawled
2. **Score dashboard** — Critical / High / Medium / Low counts (update after each pass)
3. **Table of contents** — link to each section
4. **Section 1 — Global Security** — one `.global-issue` card per finding with severity badge, category badge, description, and `.fix` block containing exact code
5. **Section 2 — Global SEO & Structure** — same card format
6. **Section 3 — Global AI-Friendliness** — same card format
7. **Section 4 — Per-Page Analysis** — one `.page-card` per page with HTTP status badge; one `.finding` row per issue
8. **Section 5 — Additional Findings** — performance, cookies, SRI, plugin versions
9. **Section 6 — Attack Vector Analysis** — critical chains with step-by-step attack flow
10. **Section 7 — DNS & Infrastructure** — subdomain map, port scan results, related domains
11. **Section 8 — Priority Fix Matrix** — all issues sorted by severity with effort estimates

### HTML Template

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Audit Report — DOMAIN — DATE</title>
<style>
  :root {
    --red:#dc2626;--orange:#ea580c;--yellow:#ca8a04;--green:#16a34a;
    --blue:#2563eb;--bg:#f8fafc;--card:#ffffff;--border:#e2e8f0;
    --text:#1e293b;--muted:#64748b;--code-bg:#f1f5f9;
  }
  *{box-sizing:border-box;margin:0;padding:0;}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);line-height:1.6;}
  .wrapper{max-width:1200px;margin:0 auto;padding:40px 24px 80px;}
  header{background:#0f172a;color:#fff;padding:40px 24px;}
  header .inner{max-width:1200px;margin:0 auto;}
  header h1{font-size:1.8rem;font-weight:700;}
  header .meta{color:#94a3b8;margin-top:6px;font-size:.9rem;}
  header .site{font-size:1rem;color:#60a5fa;margin-top:8px;}
  .score-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin:32px 0;}
  .score-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;text-align:center;}
  .score-card .num{font-size:2.8rem;font-weight:800;line-height:1;}
  .score-card .label{font-size:.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-top:6px;}
  .score-card.red .num{color:var(--red);}
  .score-card.orange .num{color:var(--orange);}
  .score-card.yellow .num{color:var(--yellow);}
  .score-card.green .num{color:var(--green);}
  h2.section{font-size:1.3rem;font-weight:700;margin:48px 0 20px;border-left:4px solid var(--blue);padding-left:14px;}
  h3.group{font-size:.78rem;font-weight:700;margin:32px 0 12px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;}
  .toc{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px 24px;margin-bottom:32px;}
  .toc h3{font-size:.85rem;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:12px;}
  .toc ol{padding-left:18px;font-size:.88rem;}
  .toc li{margin-bottom:4px;}
  .toc a{color:var(--blue);text-decoration:none;}
  .global-issue{background:var(--card);border:1px solid var(--border);border-radius:12px;margin-bottom:16px;overflow:hidden;}
  .global-issue-header{padding:14px 20px;display:flex;align-items:center;gap:12px;}
  .global-issue-body{padding:0 20px 16px;}
  .global-issue-body p{font-size:.86rem;color:var(--muted);margin-bottom:10px;}
  .badge{display:inline-flex;align-items:center;gap:5px;font-size:.72rem;font-weight:700;border-radius:6px;padding:3px 10px;text-transform:uppercase;letter-spacing:.05em;flex-shrink:0;}
  .badge-critical,.badge-sec{background:#fee2e2;color:var(--red);}
  .badge-high{background:#ffedd5;color:var(--orange);}
  .badge-medium{background:#fef9c3;color:var(--yellow);}
  .badge-low{background:#dcfce7;color:var(--green);}
  .badge-seo{background:#ede9fe;color:#6d28d9;border:1px solid #ddd6fe;}
  .badge-ai{background:#e0f2fe;color:#0369a1;border:1px solid #bae6fd;}
  .global-issue-header h4{font-size:.95rem;font-weight:700;}
  .fix{margin-top:8px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:10px 14px;}
  .fix p,.fix pre{font-size:.84rem;color:#166534;}
  pre{background:#0f172a;color:#e2e8f0;border-radius:8px;padding:12px 16px;font-size:.78rem;overflow-x:auto;margin-top:6px;line-height:1.5;}
  .page-card{background:var(--card);border:1px solid var(--border);border-radius:12px;margin-bottom:24px;overflow:hidden;}
  .page-card-header{display:flex;align-items:flex-start;gap:12px;padding:16px 20px;background:#f8fafc;border-bottom:1px solid var(--border);}
  .page-card-header h4{font-size:1rem;font-weight:700;}
  .page-card-header .url{font-size:.8rem;color:var(--muted);font-family:monospace;}
  .page-card-header .status{font-size:.75rem;font-weight:700;border-radius:6px;padding:2px 8px;flex-shrink:0;}
  .status-200{background:#dcfce7;color:#15803d;}
  .status-404{background:#fee2e2;color:#b91c1c;}
  .status-301{background:#fef3c7;color:#92400e;}
  .finding{display:grid;grid-template-columns:28px 1fr;padding:12px 20px;border-top:1px solid var(--border);}
  .sev{width:10px;height:10px;border-radius:50%;margin-top:6px;flex-shrink:0;}
  .sev-critical{background:var(--red);}
  .sev-high{background:var(--orange);}
  .sev-medium{background:var(--yellow);}
  .sev-low{background:var(--green);}
  .finding-title{font-weight:600;font-size:.9rem;margin-bottom:2px;}
  .finding-desc{font-size:.85rem;color:var(--muted);}
  .bad{color:var(--red);font-family:monospace;font-size:.82rem;background:#fee2e2;padding:1px 4px;border-radius:4px;}
  .good{color:var(--green);font-family:monospace;font-size:.82rem;background:#dcfce7;padding:1px 4px;border-radius:4px;}
  .summary-table,.priority-table{width:100%;border-collapse:collapse;font-size:.85rem;background:var(--card);border-radius:12px;overflow:hidden;border:1px solid var(--border);margin-bottom:24px;}
  .summary-table th,.priority-table th{background:#1e293b;color:#f1f5f9;padding:10px 14px;text-align:left;font-weight:600;}
  .summary-table td,.priority-table td{padding:10px 14px;border-top:1px solid var(--border);vertical-align:top;}
</style>
</head>
<body>
<header>
  <div class="inner">
    <h1>Full Website Audit Report</h1>
    <div class="site">BASE_URL</div>
    <div class="meta">Security · SEO · AI-Friendliness · Performance | DATE | N pages crawled</div>
  </div>
</header>
<div class="wrapper">
  <!-- score grid, TOC, sections go here -->
</div>
</body>
</html>
```

---

## Severity Classification

| Severity | Condition |
|---|---|
| **Critical** | Exploitable without credentials, full data/server compromise possible, or active CVE in exploited versions |
| **High** | Requires one precondition (e.g., valid credentials, phishing click), high-impact data leakage, or actively exploited known CVE |
| **Medium** | Degrades security/SEO/AI posture but no immediate compromise path |
| **Low** | Information disclosure, minor best-practice gaps, outdated but low-risk versions |

---

## Issue Card Rules

Every issue card must contain:
1. Severity badge + category badge (Security / SEO / AI / Performance)
2. Plain-English title (what is wrong, not the CVE name)
3. Description: what was found (literal values, URLs, response codes), why it matters
4. **Fix block**: exact commands, code, or configuration — not "update the plugin" but the specific file and lines to change

Per-page findings must reference the exact URL and literal value that is wrong.

---

## Key Probes Reference

### Security & Infrastructure

| Probe | What to check | Flag if |
|---|---|---|
| CORS | `Origin: https://evil.com` + `Origin: null` → check `Access-Control-Allow-Origin` | Echoes origin back with `Allow-Credentials: true` |
| phpMyAdmin | Fetch login page source, grep `user:"..."` | User is `root` or `admin` |
| Roundcube version | `HEAD /webmail/CHANGELOG` → Last-Modified date | Behind current release by 1+ version |
| Open DNS resolver | `dig @SERVER_IP google.com A` | Returns valid answer |
| FTP | Port 21 open → banner grab → anon login | Anonymous login succeeds |
| Password reset oracle | POST same endpoint with valid/invalid username | Different response text = username enumerable |
| Plugin CVE | Readme.txt stable tag vs WordPress.org API latest | More than 1 minor version behind |
| dev/staging | DNS subdomain `dev.DOMAIN` | Returns 200 with no auth gate |
| TLS | openssl s_client -tls1 / -tls1_1 | Handshake succeeds (TLS <1.2 enabled) |
| Cert transparency | crt.sh JSON API | Reveals subdomains not in DNS |
| Related domains | schema.org logo URL, SPF includes, cert SANs | Different domain → run abbreviated audit |

### AI Visibility

| Probe | What to check | Flag if |
|---|---|---|
| llms.txt | `curl -sIL BASE/llms.txt` | 404 or redirects to homepage (no content) |
| AI bot rules | `robots.txt` grep for GPTBot, ClaudeBot, PerplexityBot, CCBot | Any AI bot explicitly Disallowed |
| og:type on homepage | `grep og:type` in homepage HTML | Value is `article` instead of `website` |
| og:site_name | `grep og:site_name` | Trailing punctuation, truncation, or differs from Organization name |
| JSON-LD Organization | Parse all `<script type="application/ld+json">` blocks | Organization missing `description`, `logo`, or `sameAs` |
| Brand entity | Compare Organization name, og:site_name, WebSite name, page title prefix | Any mismatch → entity confusion |
| WebSite SearchAction | grep `potentialAction\|SearchAction` | Absent → sitelinks searchbox disabled |
| Service schema | Schema types on /services/ or equivalent | Only `WebPage` with no `Service` type |
| FAQ schema | Schema types on FAQ/BUJ pages | FAQ content present but no `FAQPage` or `QAPage` |
| JobPosting schema | Schema types on vacancy/jobs pages | Job listings without `JobPosting` |
| Breadcrumb language | grep `"name": "Home"` in JSON-LD | English "Home" used on non-English primary-language site |
| Sitemap coverage | Count sub-sitemaps and content types | Major content type (portfolio, services, jobs) missing from sitemap |
| CreativeWork schema | Schema types on portfolio/work pages | Large portfolio (50+ items) with no CreativeWork schema |

---

## Output

Save report to `./audit_report.html` (current working directory). Announce the path when done. The file must be fully self-contained — no external CSS, JS, or font dependencies.

Update the top score dashboard to match actual counts after every pass. Do not leave stale numbers from the first pass.

---

## Scope Limitations

- This skill operates via HTTP only — no server access, no file system reads
- Cannot access authenticated pages, admin dashboards, or logged-in content
- Compromise detection is indicator-based from HTTP responses — a clean result does not guarantee no compromise
- WordPress-specific checks apply to WP sites; adapt Phase 2 for other CMSes (Drupal: `sites/default/settings.php`; Laravel: `.env`; Joomla: `configuration.php`)
- Port scan results depend on firewall — closed ports may be filtered, not absent
