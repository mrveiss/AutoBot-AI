---
type: security
scope: backend
issue: 16375
---
Seven backend routers that accepted anonymous requests now require sign-in: IDE integration (`/api/ide`), the knowledge web-ingestion routes (`/api/knowledge/crawl`, `/scrape`, `/site-map` and `/extract`), run-JWT refresh (`/api/runs/{run_id}/jwt/refresh`) and web-research settings (`/api/web-research`). Reading from them, and crawling, scraping, mapping or extracting from a URL, need an authenticated user. Changing the IDE analysis configuration, and enabling, disabling, reconfiguring, testing, clearing the cache of or resetting web research, need an administrator. In the user interface, the Scrape, Crawl, Site map and Extract tabs stay available to any signed-in user; the web-research toggles are now available to administrators only. A run refreshing its own token still works: run-scoped tokens count as signed in.
