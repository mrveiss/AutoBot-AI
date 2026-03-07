# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Bug Fixes

- *(release)* Use v-prefixed initial_tag to match tag_pattern (#1296)

- *(ci)* Add write permissions to SSOT Coverage workflow (#1293)

- *(workflow)* Use executeApiTemplate for Run Now button (#1271)

- *(voice)* Gate overlay on showVoiceOverlay so sidepanel mode works (#1275)

- *(ci)* Remove stale setup_agent.sh check from deployment-check (#1293)

- *(voice)* Add error handling decorators and HF token support (#1291)

- *(ci)* Downgrade numpy to 1.26.4 for Python 3.10 CI compatibility (#1293)

- *(metrics)* Consolidate /metrics prefix collision (#1288)

- *(ci)* Resolve CI runner failures — stale VisionView import and llama-index dep conflict (#1292, #1293)

- *(collaboration)* Remove double /api prefix on session endpoints (#1277)

- *(overseer)* Remove double /api prefix from router (#1278)

- *(router)* Remove duplicate auth router registration (#1276)

- *(analytics)* Resilient pattern analysis polling, progress phases, proper sequencing (#1274)

- *(automation)* Rewire template Run Now to WorkflowAutomationManager (#1272)

- *(knowledge)* Wire autobot_docs into chat RAG retrieval path (#1261)

- *(analytics)* Correct decorator order on 45 codebase analytics endpoints (#1262)

- *(hooks)* Deduplicate orphan issues per branch (#1258)

- *(knowledge)* Wire autobot_docs search into chat retrieval flow (#1261)

- *(analytics)* Harden codebase indexing against 502/ChromaDB errors (#1249)

- *(roles)* Unify role definitions from single registry source (#1247)

- *(analytics)* Show friendly interrupted state for orphaned pattern tasks (#1250)

- *(browser)* Screenshot viewport clips tall pages in Browser tab (#1251)

- *(slm-frontend)* Singleton WebSocket to prevent 502 thundering herd (#1248)

- *(chat)* Unify internal tag stripping to handle partial [THOUGHT tags (#1246)

- *(chat,analytics)* Message duplication, voice spam, analysis resilience (#1245)

- *(build)* Replace deleted VisionAutomationPage with GUIAutomationControls in WorkflowBuilder (#1242)

- *(orchestration)* Revert prometheus categorizer — all prometheus services are autobot (#1241)

- *(analytics)* Dedicate thread pool for heavy analytics operations (#1233)

- *(orchestration)* Default autobot filter, add endpoint column, refine prometheus scope (#1241)

- *(analytics)* Mark orphaned Redis tasks as failed on load (#1234)

- *(frontend)* Consolidate preferences into profile modal + fix [object Promise]

- *(infra)* Add worker recycling and memory limits to backend service (#1240)

- *(frontend)* Add auth to VisionMultimodalApiClient + fix RumAgent type passthrough (#1236, #1237)

- *(slm-frontend)* Show restart banner for SLM self-sync (#1231)

- *(monitoring)* Replace hardcoded IPs with ConfigRegistry (#1229)

- *(analytics)* Run pattern extraction in thread pool (#1219)

- *(analytics)* Add asyncio.Lock to pattern_analysis task state (#1221)

- *(analytics)* Cap pattern extraction to prevent OOM (#1217)

- *(llm)* Resolve Ollama endpoint via SLM discovery, fix .24 fallbacks (#1214)

- *(ci)* Replace actions/setup-python with deadsnakes PPA for Python 3.10 (#1211)

- *(analytics)* Drop+recreate ChromaDB collection instead of paginated delete (#1213)

- *(analytics)* Paginated ChromaDB clearing + upsert for problems (#1213)

- *(analytics)* Upsert problems + batch ChromaDB deletes in scanner

- *(deploy)* Add ownership fix after unarchive + enable app logging (#1209)

- *(ci)* Pin all deps to exact production versions, use Python 3.10 (#1211)

- *(analytics)* Upsert stats, async def detection, Redis task state, subprocess sync

- *(code-sync)* Fleet sync reliability + stale version tracking (#1209)

- *(ci)* Use Python 3.12 via setup-python across all workflows (#1211)

- *(analytics)* Indexing progress reads from Redis + ownership path (#1212)

- *(ci)* Upgrade llama-index 0.12→0.14 to resolve pypdf 6.x conflict (#1211)

- *(ci)* Resolve llama-index-readers-file version conflict (#1211)

- *(analytics)* Eliminate circular dependency false positives + reduce coupling (#1210)

- *(ci)* Pin langchain/llama-index deps to prevent resolution-too-deep (#1211)

- *(ci)* Commit package-lock.json for frontend CI (#1208)

- *(ci)* Repair all 6 CI/CD workflows — stale paths, missing script, permissions, queue (#1200, #1203, #1204, #1205, #1206, #1207)

- *(agents)* Use dedicated Gemma2:2b model for classification agents

- *(slm)* Use Gemma2:2b for classification agents (#1202)

- *(infra)* NavPage scoping in playwright-server + SLM ReadWritePaths (#1201)

- *(analytics)* Rewrite circular import detection with DFS + module resolution (#1197)

- *(shared)* Break circular import in autobot_shared.__init__ (#1196)

- *(lint)* Resolve pre-existing E501 line-length violations (#1174)

- *(code-sync)* Git pull on local source before caching (#1194)

- *(config)* Ollama URL resolves to inactive .24 — use autobot-llm-gpu (.20) (#1193)

- *(chat)* Migrate ChatMessages inline citations to CitationsDisplay component (#1186)

- *(analytics)* Add idle-state CSS for persistent progress container (#1190)

- *(code-sync)* Local rsync when CodeSource is on same host as SLM server (#1191)

- *(chat)* URL safety check, TS non-null assertion, a11y on CitationsDisplay (#1186)

- *(automation)* Wire up Run Now, Save, Re-run, and Edit in Canvas buttons (#1189)

- *(chat)* Log warning on used_knowledge=True with empty citations (#1186)

- *(slm/orchestration)* Reassign Set.value for Vue 3 reactivity (#1167)

- *(slm-tests)* Correct git_tracker import path in tests (#1185)

- *(slm)* Code_sync uses active CodeSource config for GitTracker (#1185)

- *(slm)* Git_tracker reads branch from active CodeSource DB record (#1185)

- *(slm-ui)* Dark-on-dark text in RoleManagementModal (#1184)

- *(code_analysis)* Reduce all function lengths to <=65 lines (#1183)

- *(ansible)* Replace file:recurse with chown --no-dereference to fix backend symlink loop

- *(ansible)* Make GitHub sync graceful when .19 has no internet

- *(backend)* Add backend symlink, fix celery_app.py import order (#1175)

- *(skills)* Add find_skill to skill-router manifest tools, fix class docstring

- *(deploy)* Replace backend symlink creation with removal, fix celery app path (#1177)

- *(skills)* Use asyncio.run in tests, guard json.JSONDecodeError in re-ranker

- *(skills)* Add scoring weight constants, strengthen tag test, add stub tags

- *(analytics)* Replace hardcoded /home/kali paths, fix PermissionError 500 (#1178)

- *(deploy)* Create backend symlink via Ansible, remove dev path (#1168)

- *(deploy)* Fix backend ownership infinite loop, create symlink via Ansible (#1168)

- *(backend)* Standardize service_registry imports to absolute top-level (#1169)

- *(ui/automation)* Move GUI Automation button into Execute group in sidebar (#1166)

- *(ui/preferences)* Use correct design token names, remove dead CSS rule (#1166)

- *(slm/orchestration)* Use n.hostname directly, extract capitalize helper (#1166)

- *(slm/orchestration)* Use n.hostname directly and add capitalize helper (#1166)

- *(backend)* Fix relative imports in agents/ that break startup

- *(slm/orchestration)* Check return values in assignRoleToNode and removeRoleFromNode (#1166)

- *(slm-nginx)* Allow Grafana iframe embedding in /monitoring/system (#1160)

- *(celery)* Add PYTHONPATH to autobot-celery systemd unit (#1162)

- *(slm)* Fix RoleStatus.status for passive/service-less roles (#1129)

- *(ansible)* Migrate slm-agent to /opt/autobot/autobot-slm-agent (#1121, #1129)

- *(slm-backend)* Correct events.py import for services.database (#1106)

- *(slm-agent)* Fix event buffer sync and version.json generation (#1106, #1107)

- *(skills)* Governance routing, nginx proxy, composable URL fixes (#947) ([#952](https://github.com/mrveiss/AutoBot-AI/pull/952))

- *(conversation)* Prevent hallucination on current-data queries (#1151)

- *(slm-frontend)* Use navigateToTab for replications tab in BackupsView (#1129)

- *(frontend)* Ensure form-input fills full width and password field has right padding

- *(llm)* Restore decorators on update_embedding_model, remove from helper (#1155)

- *(voice)* Copy VAD assets to dist and set explicit paths for MicVAD (#1150)

- *(backend)* Replace hardcoded Redis IP in autobot_memory_graph/core.py (#1148)

- *(monitoring)* Mask hardware-specific node-exporter collectors on unsupported nodes (#1147)

- *(voice)* Clear errorMessage on mode switch to prevent stale error (#1149)

- *(voice)* Add GainNode for volume boost and clear isSpeaking after speak() (#1146)

- *(voice)* Unlock AudioContext on user gesture to fix no-sound bug (#1146)

- *(frontend)* Unlock AudioContext on first chat input gesture (#1146)

- *(frontend)* Unlock AudioContext on voice toggle to fix autoplay policy (#1146)

- *(ansible)* Fix ownership of autobot-backend after unarchive (#1145)

- *(personality)* Fix save/create in SLM admin via SLM backend proxy (#1145)

- *(slm)* Add exception handling to heartbeat endpoint (#1102)

- *(chat)* Fix message duplication and ID instability (#1141)

- *(nginx)* Add WebSocket location block for /api/voice/stream on backend (#1105)

- *(chat)* Stop ] leaking into messages on type transitions (#1140)

- *(nginx)* Add WebSocket location for /api/voice/stream (#1105)

- *(plugins)* Remove double /plugins prefix in router registration (#1105)

- *(personality)* Fix voice auth token and copy voice_id in duplicate (#1135)

- *(voice)* Improve mic-access error for untrusted-cert insecure context (#1059) ([#1139](https://github.com/mrveiss/AutoBot-AI/pull/1139))

- *(browser)* Add /automation MCP dispatcher to playwright-server.js (#1138)

- *(frontend)* Fix voice profiles list always empty (#1134)

- *(encoding)* Add encoding='utf-8' to remaining open() calls (#1085)

- *(encoding)* Add encoding='utf-8' to open() calls in production code (#1085)

- *(ansible)* Migrate slm-agent to /opt/autobot/autobot-slm-agent (#1121, #1129)

- *(compliance)* Fix invalid noqa directive in performance_monitor.py (#1118)

- *(logging)* Replace console.* with logger in playwright-server.js (#1124)

- *(compliance)* Move E402 module-level imports to top (#1117)

- *(slm-backend)* Correct events.py import for services.database (#1106)

- *(slm-agent)* Fix event buffer sync and version.json generation (#1106, #1107)

- *(ansible)* Replace non-symlink nginx sites-enabled file (#1122)

- *(browser)* Add SLM browser API routes for BrowserTool (#1120)

- *(encoding)* Add utf-8 encoding to open() calls, refactor generate_report (#1085)

- *(compliance)* Encoding utf-8, Redis migration, noqa annotations (#1085, #1086)

- *(compliance)* Replace direct Redis connections with env var lookups (#1086)

- *(compliance)* Encoding utf-8, Redis client migration, logger placement (#1085, #1086)

- *(logging)* Replace print() with logging across 11 files (#1087)

- *(compliance)* Replace 9 hardcoded IPs with env var lookups (#1084)

- *(ansible)* Nginx infrastructure fixes (#1098, #1099, #1103, #1104)

- *(compliance)* Replace except Exception: pass with logger.debug (#1083)

- *(frontend)* Knowledge graph UI controls and accessibility (#1077)

- *(slm)* Nginx body size, code sync archives, batch poll spam (#1090, #1091, #1092)

- *(security)* Harden knowledge graph API endpoints (#1073) ([#1094](https://github.com/mrveiss/AutoBot-AI/pull/1094))

- *(security)* Add missing await on async factory calls (#1053)

- *(frontend)* Fix knowledge graph composable state, entity filter, Set reactivity (#1076)

- *(knowledge)* Fix 6 critical bugs in ECL pipeline runner and API (#1072)

- *(frontend)* Fix duplicate useVoiceProfiles import in useVoiceConversation (#1054)

- *(frontend)* Remove duplicate VoiceSettingsPanel import (#1054)

- *(frontend)* Fix knowledge graph composable state, entity filter, Set reactivity (#1076)

- *(slm)* Route WebSocket through nginx with SSL support (#1048)

- *(backend)* Remove duplicate orchestration router registration (#1060)

- *(chat)* Resolve message duplication from LangGraph streaming chunks (#1064)

- *(feature-flags)* Log enforcement mode default once instead of every request (#1052)

- *(chat)* Correct tempfile.mkstemp argument order in atomic write (#1051)

- *(slm)* Add node health endpoint + fix /execute→/exec path (#1062, #1063)

- *(chat)* Correct tempfile.mkstemp argument order in atomic write (#1051)

- *(backend)* Resolve startup warnings for optional routers and pydantic v2 (#1046)

- *(langchain)* Remove legacy orchestrator, port QA to ChatOllama (#1047)

- *(voice)* Add hands-free option to mode selector dropdown (#1030)

- *(voice)* Wire hands-free mode into start/stop/stateLabel (#1030)

- *(voice)* Overlay hints for hands-free + full-duplex modes (#1030)

- *(voice)* Hands-free mode integration in composable + ansible ownership (#1030)

- *(voice)* Tune Silero VAD params to ms-based API (#1030)

- *(voice)* Update overlay mode selector and add WS indicator (#1030)

- Voice TTS 403 + overlay bubble rendering + stuck state (#1042)

- *(api)* Reorder template routes to fix /categories 500 error (#1033)

- *(ansible)* Enable PostgreSQL remote access for backend (#1038)

- *(ansible)* Correct health check endpoints in deploy-aiml.yml (#1020)

- *(backend)* Align AIStackClient with actual AI Stack API routes (#1023)

- *(voice)* Shared singleton state + forced TTS in voice conversation (#1037)

- *(backend)* Remove double-prefix from remaining router modules (#1032)

- *(ansible)* Delegate rsync to Backend host + add deploy-aiml playbook (#913, #1022)

- *(backend)* Remove double-prefix from analytics router modules (#1032)

- *(infra)* Remove Ollama from .24, expose .20 Ollama to subnet (#1022)

- Remove codebase_analytics double-prefix and fix knowledge graph path (#1027, #1028)

- *(slm)* Per-node service control via systemctl fallback (#1025)

- *(backend)* AIStackClient connection status tracking and retry (#1023)

- *(slm)* Login page a11y, security, perf, and UX improvements (#1012, #1015-#1017)

- *(a11y)* Add focus-visible outline to password and MFA inputs (#1012)

- *(a11y)* Add id="main-content" to login page <main> element (#1011)

- *(slm)* Remove version string from unauthenticated login page (#1013)

- *(slm)* Remove stale services from orchestration per-node view (#1018)

- *(backend)* Resolve multiple API errors and add missing endpoints (#1005-#1010)

- *(slm)* Normalize 'error' severity to 'high' in alert count (#995)

- *(slm)* Enable auto_restart for backend and slm-server roles after code-sync

- *(mcp)* Prevent infinite loading with 20s safety timeout (#986)

- *(slm)* Run npm build after frontend code-sync (role_registry post_sync_cmd)

- *(slm)* Use nginx proxy path for noVNC to avoid mixed content (#1002)

- *(backend)* Add top-level numeric metrics to /health/detailed response (#997)

- *(slm)* Parse nested component metrics for Backend Health tab (#997)

- *(slm)* Audit log on login + Prometheus fallback for node metrics (#997, #998)

- *(slm)* Record admin login/failed-login events in audit log (#998)

- *(backend)* Lazy-import playwright so research_browser router loads on nodes without it (#982)

- *(slm)* Show full URLs on Settings API tab (#1000)

- *(slm)* Resend WS subscriptions on connect — fixes stale fleet counter (#988)

- *(frontend)* Complete fetchWithAuth migration for terminal/cache components (#977)

- *(backend)* Wire /api/orchestrator and /api/workflow-automation endpoints (#980)

- *(slm)* Remove duplicate NodeLifecyclePanel header causing double-modal (#990)

- *(frontend)* Migrate remaining raw fetch() to fetchWithAuth() (#977)

- *(frontend)* Add fetchWithAuth utility — was missing from git (#979)

- *(frontend)* Migrate raw fetch() to fetchWithAuth() across all components (#977)

- *(knowledge)* Add Document ID validation to pipeline runner (#976)

- *(slm)* Page title, disabled buttons, stale timestamps (closes #994, #999, #996, #989)

- *(frontend)* Attach JWT to WorkflowBuilderApiClient requests (#979)

- *(slm)* Resolve high-severity SLM admin bugs (#985, #987, #991, #993)

- *(rum)* Replace console.* with createLogger to fix [object Object] in critical error logs (#981)

- *(auth)* Clear expired JWT from localStorage to prevent 401 storms (#979)

- *(workflow)* Prevent 404 API failures from blocking Automation overview (#978)

- *(header)* Safe optional chaining for displayUsername avatar initial (#973)

- *(header)* Prevent [object Promise] as username display (#973)

- *(knowledge)* Show folder names in knowledge categories tree (#974)

- *(knowledge)* Update file size display after content is fetched (#975)

- *(backend)* Re-enable Phase 2 services + fix memory graph init (#970)

- *(auth)* Prevent 401 loop from stale single_user localStorage (#972)

- *(ansible)* Add playbook to correct SLM server .env port misconfigurations

- *(llm)* Remove invalid OptimizationConfig fields in _create_optimization_router

- *(chat)* Implement Web Speech API for browser mic input (#928)

- *(tts-worker)* Force-reinstall torchaudio CPU after kani-tts-2 install (#928)

- *(tts-worker)* Set HF_HOME to avoid permission denied on system user (#928)

- *(tts-worker)* Install torchaudio from CPU index alongside torch (#928)

- *(tts-worker)* Correct model ID and use kani-tts package API (#928)

- *(config)* Add config/config.yaml with Ollama localhost endpoint (#969)

- *(ansible)* Tts-worker uses CPU-only torch, add to deploy_role.yml (#928)

- *(config)* Route Ollama to localhost instead of AI Stack VM (#969)

- *(slm-backend)* Add migration to widen services.memory_bytes to BIGINT

- *(skills)* Use api._get_manager() singleton in skills discovery init

- *(slm-backend)* Fix E402 misplaced imports in 4 files

- *(frontend)* Stop polling retry storm + 401 redirect on expired auth (#967)

- *(skills)* Auto-initialize builtin skills at startup, fix API_BASE trailing slash

- *(frontend)* Fix TypeScript errors in tools views and useSkills composable (#966)

- *(frontend)* Fix all TypeScript errors so vue-tsc exits 0 (#966)

- *(ansible)* Remove stale /opt/autobot/config/ on backend node (#965)

- *(personality)* Remove duplicate router prefix in api/personality.py (#964)

- *(backend)* Fix infrastructure router auth import + PYTHONPATH (#965)

- *(frontend)* Remove service health call from chat initialization

- *(frontend)* Inject auth token in ChatRepository for all API calls

- *(ansible)* Deploy-nginx-proxy ordering + required vars (#957)

- *(ansible)* Fix PYTHONPATH, StartLimit, and loopback0 UFW rule for backend

- *(auth)* Bypass auth in SINGLE_USER mode for get_user_from_request (#960)

- *(time-sync)* Fix playbook path, gather_facts, ntpdate optionality (#955)

- *(backend)* Remove orphaned module-level create_app() in app_factory (#953)

- *(frontend)* Complete LLM config UI + mobile profile button (#936, #950)

- *(ansible)* Increase RestartSec 5→30 to outlast WDF port-state cache (#954)

- *(profile)* Make ProfileModal accessible and fix 4 root causes (#950)

- *(infra)* #954 bind backend to 172.16.168.20 + fix stale HTTP:8001 refs (#956)

- *(skills)* Guard drafts against non-array API responses

- *(slm)* Governance fetch/set use / not /governance under prefix (#947)

- *(nginx)* Add /autobot-api/ proxy for user backend skills on SLM (#947)

- *(ansible)* Use import_role for redis in Phase 3 to propagate tags

- *(backend)* Fix PatternType.TYPE_ALIAS crash and autobot_shared import (#946)

- *(skills)* Governance endpoints at / not /governance under prefix (#947)

- *(backend)* Register prometheus_endpoint router at /api/metrics

- *(skills)* Register repos+governance routers before base skills to avoid /{name} conflict

- *(skills)* Phase 3 sync - filesystem error handling, brace-safe format (#947)

- *(skills)* Path traversal guard, admin auth on mutations, SEMI_AUTO enforcement (#947)

- *(skills)* Phase 8 - error handling, trust level fix, auth interceptor (#731)

- *(skills)* Phase 7 - error handling, state guards, type annotations (#731)

- *(skills)* Phase 6 - promoter raises on git commit failure (#TBD)

- *(skills)* Phase 3 quality fixes - GitRepoSync/MCPClientSync tests, HTTP status check, narrow exceptions (#TBD)

- *(skills)* Phase 2 quality fixes - sys.executable, dataclass init=False, threading import (#926)

- *(skills)* Phase 1 quality - datetime deprecation, thread-safe engine, test docstrings

- *(slm)* Fix Prometheus metrics 401 - remove auth from /api/performance/metrics/prometheus and correct scrape path

- *(app)* Hide nav for unauthenticated users on all routes (#946)

- *(router)* Remove redirect query param from login URL

- *(ansible)* Fix grafana dashboard path + node_exporter URL + import_role for tag propagation

- *(ansible)* Update-all-nodes.yml stale autobot-user-* dir names

- *(auth)* Fix login/logout - JWT rotation + incomplete UserProfile (#946)

- *(role-registry)* Replace hardcoded /opt/autobot paths with AUTOBOT_BASE_DIR env var

- *(rbac)* Add auth to analytics endpoints + fix dict attr access in knowledge APIs (#943)

- *(slm)* Update role_registry default health_check_ports

- *(monitoring)* Scrape all fleet nodes and fix backend metrics endpoint (#944)

- *(rbac)* Complete knowledge RBAC — org admin checks + ChromaDB permission filters (#934)

- *(roles)* Keep llm role on 01-Backend (GPU access)

- *(ansible)* Correct backend port from 8001 to 8443 in production inventory

- *(code-sync)* Fix SLM self-sync silent failure

- *(slm)* Correct slm_agent role name and use node_id for ansible --limit

- *(ansible)* Correct PYTHONPATH and EnvironmentFile paths in service templates (#941)

- Replace hardcoded /home/kali/Desktop/AutoBot in 20 runtime files (#832) (#836) ([#836](https://github.com/mrveiss/AutoBot-AI/pull/836))

- *(infra)* Remove false frontend/slm-frontend conflict - nginx virtual hosts (#926)

- *(frontend)* Align KnowledgeStats page with app design system

- *(backend)* Add service-monitor endpoints for frontend health widget (#925)

- *(orchestration)* Tab subroutes + useRoles CRUD methods (#924)

- *(frontend)* Route all backend calls through nginx proxy (#923)

- *(frontend)* Resolve all TypeScript errors - vue-tsc passes clean (#920)

- *(sync)* Exclude venv/node_modules/data/logs from rsync --delete

- *(frontend)* Unify WorkflowTemplate type with WorkflowTemplateSummary (#920)

- *(slm)* Resolve ambiguous FK on User.api_keys relationship (#921)

- *(frontend)* Rename conflicting SecurityFinding/PerformanceFinding in CodebaseAnalytics (#920)

- *(frontend)* Add generics and patch method to ApiClient (#920)

- *(slm)* Resolve ambiguous FK on User.user_roles relationship (#921)

- *(orchestration)* Fix empty nodes/services page via reactive() ref unwrapping (#922)

- *(slm)* Fix AttributeError in get_slm_engine/get_autobot_engine (#921)

- *(code-sync)* Use node_id for Ansible limit; detect SLM server by IP; init SSO tables (#921)

- *(frontend)* Fix broken import paths (#920)

- *(frontend)* Align analytics dashboards with actual composable return (#920)

- *(frontend)* Remove dead browser components, fix BrowserSessionManager types (#920)

- *(frontend)* Fix logger arity, prop types, and emit signatures (#920)

- *(frontend)* Route all API calls through nginx proxy, not direct to backend (#919)

- *(ansible)* Add --break-system-packages to slm_agent pip install

- *(ansible)* Remove legacy autobot-agent.service in slm_agent role (#917)

- *(code-sync)* Use node.code_version for heartbeat status comparison (#918)

- *(ansible)* Correct SLM agent service on 01-Backend with missing --node-id (#917)

- *(frontend/backend)* Route API through nginx proxy, make health endpoint public (#916)

- *(ansible)* Wait for SLM backend ready before login in Play 1

- *(frontend/slm)* Final design tokens in App.vue + HTTPS health check fix (#901, #915)

- *(frontend/ansible)* Remaining design tokens in App.vue + frontend ownership fix (#901, #913)

- *(frontend)* Replace hardcoded design tokens in App.vue + fix build error (#901)

- *(code-sync)* Mark SLM node UP_TO_DATE in DB after successful self-sync (#913)

- *(orchestration)* Fix service health check default hosts (#915)

- *(frontend)* Replace hardcoded colors with design tokens - batch 2 (#901)

- *(code-sync)* Use sudo rsync to read code source path as any user (#913)

- *(frontend)* Replace hardcoded colors with design tokens - batch 1 (#901)

- *(code-sync)* Fix SLM Manager sync and code source node outdated status (#913)

- *(frontend)* ProfileModal.vue hardcoded colors -> design tokens (#901)

- *(error-catalog)* Graceful fallback when error_messages.yaml missing on VM (#912)

- *(frontend)* Dark theme consistency - DesktopInterface + dialogs (#901)

- *(frontend/infra)* Update all HTTP/8001 references to HTTPS/8443 (#911)

- *(frontend)* Consistent dark theme across all views (#901)

- *(knowledge)* Allow any authenticated user to view knowledge categories (#910)

- *(frontend)* Update .env.example for HTTPS/8443 backend (#911)

- *(frontend)* Fix invalid template interpolation in aria-label attribute

- *(frontend)* Resolve theme implementation bugs in #901

- *(captcha)* Move threading imports to top of file (#206)

- *(auth)* Use last_login_at instead of updated_at to prevent greenlet error (#898)

- *(frontend)* Hide navigation bar on login page

- *(frontend)* Correct button closing tag in WorkflowBuilderView

- *(user-mgmt)* Add verification script and deployment guide for #898

- *(auth)* Resolve SQLAlchemy async database authentication errors (#898)

- *(models)* Resolve SQLAlchemy forward reference and reserved word errors (#898)

- *(user-mgmt)* Specify foreign_keys for User.api_keys relationship (#888)

- *(user-mgmt)* Specify foreign_keys for User.user_roles relationship (#888)

- *(user_service)* Use correct user_roles relationship name (#888)

- *(database)* Use NullPool for async engines instead of QueuePool (#888)

- *(auth)* Authenticate against PostgreSQL database instead of config file (#888)

- *(user-backend)* Register auth router for login endpoint

- *(slm)* Prevent heartbeats from overwriting code_version (#889)

- *(ansible)* Ensure SSL certificate permissions always set for backend user (#893)

- *(ansible)* Set correct TLS certificate ownership (#892)

- *(ansible)* Fix pip module failed_when condition (#892)

- *(ansible)* Configure backend HTTPS on port 8443 (#892)

- *(ansible)* Fix requirements installation for Python 3.12 (#856)

- *(ansible)* Fix requirements.txt installation in backend role (#892)

- *(ansible)* Add remote backend deployment playbook (#856)

- *(backend)* Update systemd service to use pyenv venv path (#856)

- *(ansible)* Correct backend systemd config for Python 3.12 (#892)

- *(backend)* Use pyenv Python 3.12 directly, switch to faiss-cpu (#856)

- *(ansible)* Add parent directory to PYTHONPATH for backend imports (#891)

- *(ansible)* Remove ExecStartPre symlink that causes infinite import loops (#891)

- *(backend)* Rename reserved 'metadata' field to 'collaboration_metadata' (#891)

- *(backend)* Fix collaboration.py import and function name (#891)

- *(auth)* Correct backend protocol from HTTPS to HTTP (#876)

- *(backend)* Fix ALL remaining bare imports (#891)

- *(infra)* Automate WSL2 symlink restoration (#886)

- *(backend)* Fix inconsistent imports causing infinite symlink loop (#891)

- *(deps)* Add python-dotenv to requirements (#868)

- *(ansible)* Update database with current commit after node sync (#885)

- *(slm)* Update database with current commit after rsync deployment (#885)

- *(slm-frontend)* Use correct WebSocket composable for sync progress (#880)

- *(code-sync)* Prevent GUI sync from restarting SLM backend on non-SLM nodes (#880)

- *(memory-graph)* Create missing core.py module (#716)

- *(imports)* Update stale utils.redis_client imports (#876)

- *(slm-frontend)* Handle SLM Manager self-restart 502 gracefully

- *(api)* Migrate Pydantic regex to pattern parameter (#876)

- *(backend)* Resolve self-health-check deadlock during initialization (#876)

- *(code-sync)* Update node version in database after successful sync

- *(ansible)* Create playbook to fix backend worker deadlock (#876)

- *(slm)* Set ANSIBLE_LOCAL_TEMP in playbook_executor service

- *(ansible)* Export ANSIBLE_LOCAL_TEMP in sync script

- *(ansible)* Configure local_tmp to avoid ProtectHome conflicts

- *(ansible)* Correct infrastructure path resolution in 3 roles

- *(frontend)* Use absolute URL for backend auth check with 5s timeout (#869)

- *(ansible)* Complete Python 3.13 backend deployment configuration (#858)

- *(slm-backend)* Prevent false 'Playbook failed' during SLM server self-restart (#867)

- *(git-hook)* Use correct SLM port (443 not 8000)

- *(ansible)* Prevent race condition in SLM backend health check

- *(ansible)* Use async restart for SLM backend to prevent connection loss

- *(slm)* Pull_from_source now fetches actual git commit

- *(slm)* Upgrade Ansible to 2.17+ for module compatibility

- *(ansible)* Use vite build directly for frontend + correct SSH key

- *(ansible)* Correct SSH key path in slm-nodes inventory

- *(ansible)* Correct browser worker service name to autobot-playwright (#860)

- *(ansible)* Correct SLM backend/frontend paths in playbook (#860)

- *(slm-backend)* Pass Ansible env vars to subprocess + refactor (#860)

- *(ansible)* Use command instead of systemd module for service restart (#860)

- *(ansible)* Correct path resolution in update-all-nodes.yml (#860)

- *(slm-frontend)* Fix double-prefix bug in useCodeSource composable (#860)

- *(slm-frontend)* Fix double-prefix bug and reuse useSlmApi in CodeSourceModal (#860)

- *(config)* Update Ansible and SLM orchestrator to port 8443 (#861)

- *(frontend)* Strengthen browser cache prevention for deployments (#857)

- *(slm-frontend)* Correct API URL in CodeSourceModal to fix empty node dropdown (#860)

- *(slm-frontend)* Correct fleet services API endpoint paths

- *(script)* Update run_autobot.sh for 0.0.0.0:8443 binding (#858)

- *(deps)* Add cachetools dependency (#858)

- *(frontend)* Resolve circular dependencies and configure HTTPS backend (#857, #858)

- *(slm-frontend)* Improve error handling and diagnostics in OrchestrationView (#850)

- *(ansible)* Correct SSH key path in SLM inventory

- *(ansible)* Fix recursive template loop in reboot-node playbook

- *(ansible)* Fix Browser VM Playwright service crash loop

- *(slm-frontend)* Improve service visibility and empty states (#850)

- *(slm-backend)* Add missing OPERATIONS category to PlaybookCategory enum

- *(grafana)* Configure Grafana for embedded dashboards in SLM monitoring (#853)

- *(slm-frontend)* Add timeout and better error logging for orchestration API

- *(slm-frontend)* Handle all service status values in ServiceStatusBadge (#850)

- *(slm-frontend)* Add auth token to useRoles requests (#850)

- *(npu)* Implement FastAPI server for NPU worker port 8081 accessibility (#851) (#852) ([#852](https://github.com/mrveiss/AutoBot-AI/pull/852))

- *(slm-frontend)* Add error display and debug logging (#850)

- *(frontend)* Nginx config to listen on port 443 instead of 5173

- *(slm-frontend)* Add null safety checks for fleetServices (#850)

- *(slm-frontend)* Remove unused import in useOrchestrationManagement (#850)

- *(slm-frontend)* Address code review findings for accessibility (#754)

- *(infra)* Update CLAUDE.md and Ansible defaults for user frontend (#834)

- *(infra)* Deploy user frontend on .21 with nginx+SSL (#834)

- *(slm-frontend)* Code Source GUI improvements - auth + edit mode (#833)

- *(slm-frontend)* Fix API proxy routing to SLM backend (#834)

- *(slm)* Remove duplicate logger declaration in npu.py (#590)

- *(ansible)* Move ollama service monitoring from AI-Stack to Backend node

- *(ansible)* Glob PEP 668 check across all Python versions

- *(ansible)* Improve role resilience and make admin password configurable

- *(code-source)* Default repo path to /opt/autobot (#833)

- *(ansible)* Use autobot user for 01-Code-Source (#837)

- *(ansible)* Upgrade pip before installing large packages (#837)

- *(ansible)* Add pip timeout for large package downloads (#837)

- *(ansible)* Venv ownership + pip idempotency across roles (#837)

- *(ansible)* Frontend role package.json check order + backend_host default (#837)

- *(ansible)* Frontend NodeSource + LLM idempotency (#837)

- *(ansible)* Add missing network_subnet defaults + redis idempotency (#837)

- *(ansible)* Preserve existing DB password across redeploys (#837)

- *(ansible)* Skip internet downloads when software already installed (#837)

- *(slm)* Sync admin password from env var on every startup (#837)

- *(slm-frontend)* Wire 7 broken tool views to real API + fix 4 other issues (#835)

- *(monitoring)* Remove hardcoded dev paths + fix pre-existing violations (#832)

- *(infra)* Align paths and mark Docker-only scripts (#831)

- *(slm)* Fix 10 broken SLM frontend features (#834)

- Replace hardcoded /home/kali/Desktop/AutoBot with env-var lookup (#832)

- *(slm)* Git_tracker DB fallback for rsync deployments (#829)

- *(slm)* Update stale AGENT_CODE_PATH in code_distributor (#829)

- *(slm)* Code-source/notify now updates code-sync status and marks nodes outdated (#829)

- *(slm)* Wire LogViewer to real backend API, remove mock data (#828)

- *(slm)* Fix fleet total_system_updates double-counting global updates (#682)

- *(infra)* Code quality fixes batch 18 - final 2 files (#825)

- *(infra)* Code quality fixes batch 15 - 3 edge cases + hook config (#825)

- *(docs)* Code quality fixes batch 14 - 2 docs/examples files (#825)

- *(infra)* Code quality fixes batch 13 - 16 files (#825)

- *(infra)* Code quality fixes batch 12 - 6 files (#825)

- *(infra)* Code quality fixes batch 11 - 8 files (#825)

- *(infra)* Code quality fixes batch 9 - 6 files (#825)

- *(slm-agent)* Filter out phantom not-found/masked services from discovery

- *(infra)* Code quality fixes batch 3 - 8 files (#825)

- *(infra)* Code quality fixes batch 1 - 8 files (#825)

- *(infra)* Fix stale imports in test and utility scripts (#825)

- *(infra)* Fix stale imports + syntax errors in test scripts (#825)

- *(quality)* Code quality cleanup batch 7 - 11 files print+func fixes (#825)

- *(quality)* Code quality cleanup batch 6 - 3 more scripts (#825)

- *(quality)* Code quality cleanup batch 5 - print→logger in 5 utilities (#825)

- *(quality)* Code quality cleanup batch 4 - print→logger in 15 scripts (#825)

- *(quality)* Code quality cleanup batch 3 - 3 files (#825)

- *(quality)* Code quality cleanup batch 2 - 17 files (#825)

- *(ansible)* Harden deployment for Ubuntu 22.04 fleet (#826)

- *(imports)* Remove stale `from src.*` imports in 16 clean files (#825)

- *(user-frontend)* Complete 7 stub/incomplete component features (#823)

- *(api)* Correct endpoint URL mismatches and register feature_flags router (#822)

- *(user-frontend)* Medium/low state management bugs (#821)

- *(slm)* Update stale legacy paths and create post-commit hook (#824)

- *(user-frontend)* Critical state management bugs - WebSocket leaks, race conditions, error boundary (#820)

- *(slm)* Fix 7 frontend errors and add monitoring infra (#816)

- *(slm)* Wire up incomplete SLM functionality (#813)

- *(slm-backend)* Lower pysaml2 requirement to >=7.3.0 (#814)

- *(infra)* Assume blank host in slm_manager role (#814)

- *(infra)* Remove npm from apt packages, use NodeSource nodejs (#814)

- *(infra)* Run ansible-playbook from ansible/ dir for roles_path (#814)

- *(frontend+backend)* Resolve 6 API connectivity and configuration issues (#810)

- *(infra)* Update sync-to-slm.sh with correct paths and deploy options (#812)

- *(slm-frontend)* Handle WebSocket mixed content and auth-gated API calls (#811)

- *(infra)* Update ansible inventory and shared config (#786)

- *(slm-frontend)* Add @shared alias for autobot-shared components (#576)

- *(ansible)* Remove duplicate roles and fix playbook references (#807)

- Resolve variable shadowing bug in ServiceRegistry._load_default_services (#763)

- Update imports and test assertions for colocated structure (#734)

- Resolve remaining RAG and SSH errors (#788)

- Restore prompts/ and update path_constants for #781 reorganization (#793, #795, #796)

- Update prompt paths to resources/prompts after #781 reorganization (#793)

- Restore prompts/ directory deleted in #781 reorganization (#793) (#800) ([#800](https://github.com/mrveiss/AutoBot-AI/pull/800))

- Resolve multiple RAG and knowledge retrieval errors (#788)

- Update PROJECT_ROOT paths in infrastructure scripts for new folder structure (#790)

- Correct duplicate infrastructure path in deployment docs (#781)

- Update PROJECT_ROOT paths in scripts for new folder structure (#781)

- *(structure)* Move slm agent to autobot-slm-backend (#781)

- *(structure)* Move monitoring to autobot-slm-backend (#781)

- *(api)* Pass current_token to preserve session on password change (#635)

- *(session)* Export SessionService from services module (#635)

- *(frontend)* Address code review feedback for design system (#753)

- *(memory)* Address code review feedback in compat.py (#742)

- *(frontend)* Correct API URLs from code_intelligence to code-intelligence (#566)

- *(slm-admin)* PKI auth never requires password for node edits

- *(slm-admin)* Make credentials optional for basic node edits

- *(npu)* Align frontend API with backend NPU endpoints (#255)

- *(slm-admin)* Use dynamic WSS protocol via nginx proxy

- Pin bcrypt version for passlib compatibility

- *(#749)* Add input validation for WebSocket handlers

- *(#749)* Add error handling and input validation to history service

- *(#749)* Sanitize shell input and add utf-8 encoding

- More Python 3.8 compatibility for union types

- Python 3.8 compatibility for type annotations

- *(security)* Re-enable strict file permissions by default (#745)

- *(rag)* Improve cache handling and variable naming

- *(websockets)* Update deprecated extra_headers to additional_headers

- *(#768)* Use SSOT config instead of hardcoded URLs

- *(docs)* Correct TLS issue references from #768 to #164

- *(redis)* Support explicit TLS cert paths and remove hardcoded path (#164)

- *(celery)* Support explicit TLS cert paths from SLM (#164)

- *(backend)* Support explicit TLS cert paths from SLM (#164)

- *(linting)* Complete code style remediation (#750)

- *(tests)* Additional linting fixes for test directory (#750)

- *(tests)* Linting cleanup for test directory (#750)

- *(linting)* Comprehensive code style remediation (#750)

- *(config)* Make NPU_WORKER_WINDOWS_PORT configurable (#763)

- *(test)* Disable .env file loading in test_default_ports (#763)

- *(config)* Resolve circular imports in constants modules (#763)

- *(config)* Resolve circular import with lazy loading

- *(slm)* Improve service restart and agent code deployment (#741)

- *(llm)* Correct status endpoint to show real-time connection status (#746)

- *(slm)* Show full version numbers instead of truncated (#741)

- *(slm)* Update node version in database after sync (#741)

- *(slm)* Use UP_TO_DATE enum value instead of CURRENT (#741)

- *(slm)* Sync agent.py to Ansible role and rename Backend to Code-Source (#741)

- *(slm-agent)* Use os.getloadavg for psutil compatibility (#741)

- *(slm-agent)* Add version.py to ansible role and fix git path (#741)

- *(slm)* Python 3.8 compatibility for type hints (#741)

- *(slm)* Remove hardcoded paths, add task cleanup (#741)

- *(memory)* Handle asyncio.run in async context (#743)

- *(slm)* Auto-detect localhost for agent on SLM backend host

- *(slm)* Use localhost for agent on SLM Manager node

- *(ansible)* Set autobot user shell to bash, not nologin (#740)

- Eliminate remaining hardcoded values and naming violations (#694)

- *(slm)* Add missing AI-Stack node to inventory (#740)

- *(backend)* Remove hardcoded IPs from backend API files (#694)

- *(hooks)* Improve magic number detection in pre-commit hook (#694)

- *(frontend)* Use nginx URL for SLM Admin (https://host, not port 5174)

- *(frontend)* Restore FileBrowser.vue for chat functionality

- *(frontend)* Keep secrets route in autobot-vue

- *(redis)* Use SSLConnection class for TLS connection pools (#725)

- *(slm)* Use stored credentials for SSH and sudo in deployments (#725)

- *(slm)* Improve deployment reliability and agent compatibility

- *(slm)* Improve backup service Redis discovery and authentication (#726)

- *(security)* Fix mTLS migration tool and Redis config path (#725)

- *(security)* Update mTLS migration for on-demand app workflow (#725)

- *(slm)* Code review fixes for admin migration (#729)

- *(slm)* Fleet consistency fixes - heartbeat display and SSH simplification (#728)

- *(slm)* Add slm-agent and all roles to Manage Roles modal (#728)

- *(slm)* Use relative imports and user-writable buffer path in agent (#728)

- *(slm)* Use Tuple from typing for Python 3.8 compatibility

- *(slm)* Fix Test Connection and add lifecycle events (#728)

- *(slm-admin)* Add 'online' status to node status indicators (#728)

- *(slm)* Fix enrollment playbook task ordering and package installation (#726)

- *(slm)* Use nginx proxy URL for remote agent heartbeats (#726)

- *(slm)* Resolve enrollment flow and heartbeat connectivity issues (#726)

- *(slm)* Python 3.8 compatibility for type hints (#726)

- *(chat)* Prevent LLM hallucination during tool call streaming (#727)

- *(ansible)* Add Redis password and ensure systemd services auto-start (#724)

- Replace print/console statements with proper logging (#726)

- *(chat)* Standardize message metadata key naming (rawData → metadata)

- *(chat-api)* Complete rawData → metadata migration in chat.py

- Add missing os import in llm_interface.py

- Resolve CI/CD dependency compilation issues

- Resolve Python types namespace collision

- Convert browser API blocking file I/O to async operations

- Handle MessagePriority enum conversion in agent communication

- Handle MessageType enum conversion in agent communication

- Convert file I/O operations in API endpoints to async

- Convert knowledge base API blocking operations to async

- Convert chat API blocking file I/O operations to async

- Resolve Vite plugin version conflicts for CI/CD compatibility

- Resolve CUDA/PyTorch import issues for CI/CD compatibility

- Resolve critical linting errors and code quality issues

- Resolve TypeScript import errors and build configuration

- Update LLM failsafe agent to use correct chat_completion method

- Improve container startup handling in run_agent.sh

- Add missing logging import in orchestrator.py

- Resolve terminal input consistency issues for reliable automated testing

- Migrate deprecated Pydantic @validator to @field_validator

- Add missing config file creation in deployment-check phase

- Add missing API service methods for complete test coverage

- Update deprecated GitHub Actions to latest versions

- Update CI workflow for new file organization and branch support

- Resolve all 4 failing security integration tests

- Add python-multipart dependency for FastAPI form data handling

- Apply pre-commit hook formatting fixes to frontend tests

- Resolve final 3 backend test failures in secure command executor

- Resolve all backend test failures and flake8 linting errors

- Update package-lock.json after adding @pinia/testing dependency

- Clean up duplicate EnhancedSecurityLayer imports

- Resolve frontend test configuration issues

- Improve TypeScript configuration for testing

- Comprehensive CI test configuration improvements

- Improve CI dependency installation for NumPy compatibility

- Update CI dependencies for Ubuntu compatibility

- Improve terminal input consistency for automated testing

- Enhance CI/CD pipeline and dependencies management

- Resolve critical runtime errors preventing app startup

- Critical syntax errors preventing app startup

- Migrate FastAPI event handlers to modern lifespan pattern

- Clean up unused imports and code quality issues

- Resolve terminal WebSocket import error preventing app startup

- Eliminate all 21 bare except clauses across codebase

- Resolve critical backend hanging issues from analysis report

- Downgrade packages to resolve crypto.hash CI/CD error

- *(frontend)* Add Node.js version requirements for CI/CD compatibility

- Remove sqlite3 from requirements.txt

- *(knowledge_base)* Optimize Redis operations to prevent blocking

- Update run_agent.sh to recognize both Playwright container names

- Remove read-only noVNC volume mount to prevent package conflicts

- Change VNC port to 5901 to avoid Kali Linux TigerVNC conflict

- Use consistent VNC port mapping 5900:5900

- Correct Playwright service name and environment variable

- Change RedisInsight to use port 8002 internally and externally

- Resolve PhaseStatusIndicator API routing and code quality issues

- Resolve linting issues and improve backend chat API

- Comprehensive frontend security, performance, and accessibility improvements

- Improve terminal command filtering to allow sudo commands

- Use localhost for terminal service connections in development

- Improve terminal handling of interactive commands and timeouts

- Connect frontend terminal to working simple terminal backend

- Correct WorkflowApproval API endpoint URL

- Eliminate console error spam from legacy chat deletion

- Initialize tool registry in orchestrator constructor

- Correct workflow execute endpoint path in test script

- Remove generated data files and enhance .gitignore

- Update multi-agent model configuration to use available models

- Apply formatting and documentation updates for hardware acceleration

- Resolve chat deletion persistence issue in frontend

- Add system knowledge bridge API to resolve empty frontend sections

- Resolve LLM model alias and fact search improvements

- Resolve KB Librarian Agent method compatibility issues

- Resolve PostCSS build issues for Vue Notus Tailwind design

- Resolve message toggle persistence and improve settings synchronization

- Update frontend build artifacts after message toggle implementation

- Resolve toggle persistence and empty agent responses

- Enable message display toggles for historical messages

- Implement proper Vue reactivity for message display toggles

- Clean up unused port references and standardize port configuration

- Resolve all 390 flake8 code quality issues

- Break long lines in orchestrator.py to meet 88-character limit

- Resolve flake8 linting errors in backend API and configuration files

- Replace hardcoded tinyllama model references with deepseek-r1:14b

- Implement functional Redis background tasks and listeners

- *(slm-admin)* Correct API paths in Prometheus metrics composable (#726)

- *(slm-server)* Add paramiko to requirements for SSH connectivity

- *(slm-admin)* Pass mode prop to AddNodeModal for edit mode

- *(slm-admin)* Add auth token interceptor to API client

- *(slm-admin)* Use /api base URL for SLM backend

- *(slm-admin)* Use relative URLs for API calls in auth store

- *(slm)* Fix agent code quality issues (#726)

- *(slm)* Fix db_service code quality issues (#726)

- *(slm)* Add missing relationships and test improvements (#726)

- *(slm)* Align SLMDeployment and SLMMaintenanceWindow with spec (#726)

- *(frontend)* Add WebSocket proxy for SSH terminal and cleanup logging (#715)

- *(infrastructure)* SSH terminal encryption key and VNC setup (#715)

- *(frontend)* Add infrastructure hosts to terminal HostSelector (#715)

- *(infrastructure)* Celery worker queue configuration and task_id context (#720)

- *(frontend)* Use relative URLs for SSH/VNC terminal connections (#715)

- *(frontend)* Add missing getBackendWsUrl export to SSOT config

- *(frontend)* Convert Settings navigation to sidebar layout (#719)

- *(frontend)* Address code review issues for Feature Flags GUI (#580)

- *(chat)* Extend dedicated thread pool to all chat_history mixins (#718)

- *(chat)* Use dedicated thread pool for chat I/O operations (#718)

- *(chat)* Resolve save timeout during heavy I/O load (#718)

- *(chat)* Resolve streaming duplication and multi-step execution issues (#718)

- *(circuit-breaker)* Resolve threading deadlock in _record_failure (#712)

- *(analytics)* Add missing Path import to call_graph.py (#711)

- *(api)* Align analytics router prefixes with frontend paths (#710)

- *(chat)* Fix stale typing indicator and permissions API 404 (#709)

- *(infrastructure)* Add Celery worker availability check for system updates (#705)

- *(env-analysis)* Fix field name mismatch in frontend export (#706)

- *(tests)* Resolve TypeScript errors in composable tests (#701)

- *(utils)* Resolve TypeScript errors in utility modules (#701)

- *(core)* Resolve TypeScript errors in core modules (#701)

- *(composables)* Resolve TypeScript errors in composables (#701)

- *(components)* Resolve TypeScript errors in misc components (#701)

- *(settings)* Resolve TypeScript errors in settings components (#701)

- *(startup)* Add Redis authentication to health check

- *(security)* Resolve TypeScript errors in security components (#701)

- *(monitoring)* Resolve TypeScript errors in monitoring components (#701)

- *(knowledge)* Resolve TypeScript errors in knowledge components (#701)

- *(charts)* Resolve TypeScript errors in chart components (#701)

- *(analytics)* Resolve TypeScript errors in analytics components (#701)

- *(chat)* Resolve TypeScript errors in chat components (#701)

- *(chat)* Remove unnecessary type cast in ChatInput addMessage (#701)

- *(log-forwarding)* Replace hardcoded IPs with SSOT config (#553)

- *(ansible)* Align host groups and improve rollback safety (#682)

- *(captcha)* Add timestamp to response model and improve error logging (#206)

- *(imports)* Correct Request import from starlette.requests (#692)

- *(npu)* Change NPU worker connection errors from ERROR to DEBUG level (#699)

- *(logging)* Reduce NPU worker health check log noise (#699)

- *(settings)* Remove Hardware subtab and fix CSS in PermissionSettings (#690)

- *(chat)* Prevent message polling race conditions during approval (#680)

- *(chat)* Fix message type badge display for streaming responses (#680)

- *(auth)* Add check_admin_permission to auth_middleware (#687)

- *(api)* Add missing JSONResponse import in chat_sessions.py

- *(docs)* Enable --incremental flag as standalone option (#250)

- *(chat)* Implement Agent Zero pattern for streaming messages (#680)

- *(knowledge)* Add super().__init__() to KnowledgeBaseCore for mixin chain (#165)

- *(analytics)* Add full export endpoint for environment analysis (#631)

- *(knowledge)* Fix document name display in vectorization modal (#165)

- *(knowledge)* Fix vectorization status showing success as failed (#165)

- *(imports)* Add missing Any import in npu_worker_manager.py (#665)

- *(imports)* Add missing Any, Dict to sandbox.py typing imports

- *(logging)* Escape percent sign in startup log format string

- *(frontend)* Continue ESLint/OxLint cleanup - 92 warnings fixed (#672)

- *(lint)* Resolve 84 ESLint/OxLint warnings in frontend (#672)

- *(frontend)* Remove/prefix unused variables (#672)

- *(frontend)* Reduce chat page API timeouts and add loading feedback (#671)

- *(frontend+backend)* Fix lint errors and circular import (#672, #673, #674)

- *(chat)* Prevent message flickering during polling (#669)

- *(async)* Fix blocking file I/O in secrets API endpoints (#666)

- *(async)* Fix blocking sync checks in service monitor (#666)

- *(async)* Fix blocking Redis calls in codebase scanner (#666)

- *(async)* Fix blocking Redis calls in cache and terminal APIs (#666)

- *(threading)* Add remaining race condition fixes (#662)

- *(threading)* Add double-checked locking to singleton initializations (#662)

- *(startup)* Make NPU worker optional and prevent startup failures (#668)

- *(chat)* Fix duplicate terminal interpretation and add multi-step debug logging (#651)

- *(chat)* Multi-step tasks now complete all steps (#651)

- *(chat)* Message types and streaming refactor (#650)

- *(chat)* Stop persisting streaming chunks as separate messages

- *(knowledge)* Use SSOT get_default_llm_model for LlamaIndex config (#649)

- *(terminal)* Use shallowRef for xterm.js Terminal to prevent Vue reactivity errors

- *(config)* Migrate remaining hardcoded IPs to SSOT config (#599)

- *(knowledge)* Use SSOT config for Ollama URL (#649)

- *(frontend)* Use parseApiResponse in useKnowledgeVectorization (#648)

- *(api)* Add task recovery for pattern analysis 409 Conflict (#647)

- *(frontend)* Use latin-only Inter font subset (#646)

- *(frontend)* Replace CDN dependencies with local npm packages (#646)

- *(frontend)* Reduce noisy console warnings for expected fallbacks (#646)

- *(npu-worker)* Implement main host authoritative worker registration (#641)

- *(analytics)* Improved indexing progress display

- *(analytics)* Improve indexing progress feedback

- *(env-analyzer)* Enhanced false positive filtering (#630)

- *(env-analyzer)* Reduce false positives for API routes (#630)

- *(api)* Use /ownership subroute for ownership endpoints (#248)

- *(env-analyzer)* Reduce false positives by >90% (#630)

- *(npu-worker)* Switch to OpenVINO EP for Intel NPU support (#640)

- *(npu)* Fix YAML serialization to prevent !!python/object tags (#68)

- *(perf)* Further reduce .lower() calls in temporal_invalidation_service (#624)

- *(perf)* Cache repeated method calls to reduce CPU overhead (#624)

- *(perf)* Replace string concatenation in loops with join() (#622)

- *(perf)* Consolidate repeated file open operations (#623)

- *(analytics)* Resolve namespace conflict in EnvironmentAnalyzer import

- *(perf)* Convert 8 unbatched API calls to concurrent/batch operations (#615)

- *(perf)* Optimize nested loop complexity patterns (#616)

- *(code-analysis)* Fix false positive BUG comment detection (#617)

- *(tests)* Replace blocking sqlite3.connect with async helpers (#618)

- *(perf)* Fix N+1 query patterns with batching and parallelization (#614)

- *(threading)* Add thread-safe locking to singleton getters (#613)

- *(analytics)* Remove artificial limits on duplicate detection (#609)

- *(analytics)* Fix problems report export showing 'undefined' (#612)

- *(config)* Consolidate numeric constants to SSOT (#611)

- *(analytics)* Improve duplicate detection to find more duplicates (#609)

- *(analytics)* Fix Code Smells section filter to match actual problem types (#609)

- *(analytics)* Parallelize bug prediction + fix MD export formats (#609)

- *(config)* Consolidate LLM model defaults to single constant (#610)

- *(config)* Consolidate hardcoded config values to use SSOT (#610)

- *(analytics)* Bug prediction now analyzes all files instead of 50 (#609)

- *(status)* Fix duplicate frontend entries in System Status dialog (#606)

- *(chat)* Fix session listing and display in GUI (#605)

- *(config)* Implement single source of truth for API client timeouts (#598)

- *(gui)* Populate profile fields reactively in User Management (#595)

- *(settings)* Correct event handler signatures in LoggingSettings (#594)

- *(gui)* Resolve Settings > Services tab errors (#593)

- *(settings)* Populate Logging tab form fields correctly (#594)

- *(analytics)* Resolve KeyError in dashboard overview endpoint (#596)

- *(knowledge)* Use 300s timeout for vectorization API calls (#597)

- *(router)* Add SecretsManager as default child route (#592)

- *(ui)* Add proper password masking for secret inputs (#211)

- *(router)* Check backend auth before redirecting protected routes (#576)

- *(knowledge)* Address code review feedback for maintenance components (#588)

- *(api)* Fix Agent Registry 404 and remove Claude agent references (#577)

- *(api)* Resolve double-prefix routing and register alertmanager webhook (#574)

- *(api)* Prevent cross-language summary endpoint from auto-running analysis (#572)

- *(performance)* Reduce false positives in HTTP detection (#573)

- *(api)* Fix Settings page API endpoint mismatches (#570)

- *(performance)* Reduce false positives in blocking I/O detection (#571)

- *(frontend)* Fix TypeScript errors and consolidate code intelligence (#566)

- *(frontend)* Fix API client imports and function call syntax

- *(api)* Add asyncio.Lock for thread-safe cache access (#559)

- *(scripts)* Fix syntax errors in 8 Python files (#558)

- *(api)* Add playwright back/forward endpoints and fix debt API response handling (#552)

- *(api)* Fix settings endpoint path - add trailing slash (#552)

- *(api)* Additional endpoint path fixes and scanner improvements (#552)

- *(api)* Fix scanner bugs and remaining endpoint path mismatches (#552)

- *(api)* Handle missing backend endpoints gracefully (#552)

- *(api)* Fix SystemMonitor, visualizations, and orphan manager API paths (#552)

- *(frontend)* Fix API endpoint paths for Issue #552 - batch 4

- *(frontend)* Fix API endpoint paths for Issue #552 - batch 3

- *(frontend)* Use correct apiClient import in MemoryOrphanManager (#547)

- *(frontend)* Fix API endpoint paths for Issue #552 - batch 2

- *(memory)* Use search_entities instead of list_entities for orphan cleanup (#547)

- *(api)* Fix frontend API paths for knowledge base and terminal (#552)

- *(vectorization)* Fix vectorize_existing_fact() signature mismatch (#552)

- *(api)* Fix frontend API paths to match backend endpoints (#552)

- *(api)* Add missing router prefixes and fix frontend API paths (#552)

- *(frontend)* Correct useToast API and type annotations

- *(api)* Align frontend API paths with backend router prefixes (#552)

- *(api)* Improve endpoint scanner and fix research browser paths (#552)

- *(frontend)* Add missing /api prefix to 28 frontend API calls (#552)

- *(api)* Add missing backend endpoints for frontend API calls (#549)

- Correct Python syntax errors in 5 source files (#550)

- *(monitoring)* Fix RumDashboard async error and CodebaseAnalytics scroll (#162)

- *(analytics)* Add analytics TabType and fix BI view TypeScript errors (#545)

- *(analytics)* Handle no_data status in bug prediction and frontend (#543)

- *(analytics)* Fix Union response type in analytics_performance.py (#543)

- *(analytics)* Replace demo data with proper no_data responses (#543)

- *(stats)* Add thread safety, stale detection, and tests (#540)

- *(stats)* Show indexing status during codebase indexing (#540)

- *(backend)* Prevent tokenizer deadlocks and bound thread pool (#538, #539)

- *(config)* Use correct NetworkConstants attributes in get_distributed_services_config (#535)

- *(scripts)* Add execute permissions to logging scripts (#431)

- *(api)* Add /api/redis/health endpoint (#530)

- *(frontend/backend)* Resolve multiple errors discovered during testing (#534)

- *(api)* Resolve /api/chat/health returning 503 (#529)

- *(monitoring)* Fix unawaited coroutine and remove phase9 naming (#430)

- *(logging)* Convert print statements to structured logging (#401)

- *(logging)* Correct malformed %-style logging format specifiers (#516)

- *(logging)* Convert f-string logging to lazy %-style format (#436, #437, #438, #439, #440, #441, #442)

- *(concurrency)* Add thread-safe locking for race conditions (#481)

- *(code-intelligence)* Convert f-string logging to lazy evaluation (#497)

- *(monitoring)* Add missing buffer attributes to PerformanceMonitor (#427)

- *(rag)* Fix semantic/keyword search failures in RAG optimizer (#429)

- *(stats)* Handle timestamp metadata fields in stats counters (#428)

- *(startup)* Add execute permission to sync-frontend.sh (#426)

- *(security)* Add nosec annotations for bandit false positives

- *(issue-394)* Refactor God Classes - Extract domain packages (#394)

- *(issue-400)* Implement incremental indexing with hash comparison (#400)

- *(issue-395)* Add thread-safe lazy initialization to 4 API modules (#395)

- *(issue-397)* Fix N+1 query patterns in Redis and SQLite operations (#397)

- *(issue-396)* Convert blocking I/O to async in monitoring modules (#396)

- *(issue-381)* Remove enhanced_kb_librarian.py naming violation (#381)

- *(scripts)* Fix F811 method redefinitions and F824 unused global

- *(scripts)* Add missing imports for F821 undefined name errors

- *(lint)* Fix undefined variable and remove duplicate function

- *(security)* Replace eval() with ast.literal_eval() in security_workflow_manager

- *(scripts)* Fix flake8 F541, E722, E128 issues across 97 files (#281)

- *(security)* Add nosec comments to justified security patterns (8 HIGH issues)

- *(security)* Add usedforsecurity=False to MD5 hash calls (17 files)

- *(lint)* Remove unused imports and fix line breaks (15 violations)

- *(lint)* Convert lambda to def and add blank line

- *(lint)* Rename ambiguous variable and shadowed import

- *(style)* Clean up whitespace and unused declarations

- *(lint)* Resolve F541 and F811 violations (10 issues)

- *(critical)* Resolve 14 F821 undefined name errors

- *(scripts)* Remove 6 unused imports (F401 violations) (#216)

- *(async)* Wrap blocking sync calls in asyncio.to_thread (#362)

- *(anti-pattern)* Expand acceptable single-letter variables (#314)

- *(race-detection)* Context-aware file write race condition detection (#378)

- *(performance-analyzer)* Context-aware N+1 query detection (#371)

- *(imports)* Add missing Dict import to slash_command_handler.py

- *(analytics)* Store problems correctly with async ChromaDB collection (#388)

- *(dead-code)* Remove unused imports and fix missing asyncio (#382)

- *(performance-analyzer)* Exclude false positives in blocking I/O detection (#363-366)

- *(system)* Correct app_state import path (#384)

- *(frontend)* Rate-limit TimeoutError console spam in CacheBuster (#354)

- *(routers)* Remove archived terminal routers and fix security_assessment imports (#360)

- *(backend)* Fix broken imports in advanced_workflow module

- *(backend)* Prevent codebase indexing from blocking event loop

- *(frontend)* Split message bubbles when type changes during streaming (#352)

- *(detector)* Improve Feature Envy detection accuracy (#312)

- *(frontend)* Correct message type field mapping for workflow messages (#351)

- *(chat)* Prevent message duplication at source level (#350)

- *(frontend)* Remove SVG transitions causing Knowledge Graph bubble flickering

- *(frontend)* Prevent Grafana dashboard flickering on hover/tab switch

- *(memory-graph)* Move memory database to DB 0 for RediSearch compatibility (#55)

- *(memory-graph)* Fix wildcard search returning empty results (#55)

- *(ci)* Make Phase Validation Gate non-blocking (#349)

- *(deps)* Update numpy and pyyaml for Python 3.13 compatibility (#349)

- *(flake8)* Fix F821 undefined name violations - critical bugs

- *(ci)* Use actions/setup-node@v4 for Node.js setup (#349)

- *(ci)* Make Node.js PATH setup more robust (#349)

- *(ci)* Add Node.js PATH setup to ci.yml frontend-tests job (#349)

- *(ci)* Fix YAML syntax errors in ci.yml and phase_validation.yml (#349)

- *(ci)* Fix self-hosted runner environment issues (#349)

- *(flake8)* Remove F401 unused import violations - batch 3 (#176)

- *(ci)* Set code quality checks to warn-only mode (#349)

- *(linting)* Fix more F401 unused import violations (#176)

- *(linting)* Fix UNSAFE flake8 violations - E741, F841, F811 (#176)

- *(monitoring)* Complete ErrorMetricsCollector cleanup and fix import (#348)

- *(agent_terminal)* Remove duplicate command_approval_request persistence (#343)

- *(code-intelligence)* Add missing typing imports to code_review_engine.py

- *(agents)* Add missing Optional import to development_speedup_agent.py

- *(backend)* Add aiohttp.ClientError handling to HTTP operations (#288)

- *(backend)* Add OSError handling to async file operations (#288)

- *(agents)* Add OSError handling to async file operations (#288)

- *(utils)* Add OSError handling and convert print to logger (#288)

- *(src)* Add OSError handling to async file I/O modules (#288)

- *(src)* Add OSError handling to agents and utility modules (#288)

- *(src)* Add OSError handling to utils and chat managers (#288)

- *(src)* Add OSError handling to async file I/O operations (#288)

- *(codebase_analytics)* Add missing ast and aiofiles imports

- *(monitoring)* Add OSError handling to async file I/O operations (#288)

- *(backend/api)* Add OSError handling to async file I/O operations (#288)

- *(src)* Add OSError handling to llm_self_awareness.py export function (#288)

- *(agents)* Add OSError handling to aiofiles operations (#288)

- *(src)* Add OSError handling to aiofiles operations in 2 files (#288)

- *(scripts)* Add OSError handling to log_aggregator.py aiofiles operations (#288)

- *(services)* Add OSError handling for aiofiles operations (#288)

- *(src)* Add OSError handling for aiofiles I/O operations (#288)

- *(src)* Add OSError handling to aiofiles operations (#288)

- *(research_browser)* Add OSError handling in aiofiles generator (#288)

- *(terminal_handlers)* Add OSError handling for aiofiles operations (#288)

- Add error handling to utility async functions (#288)

- Add RedisError handling to security_workflow_manager.py (#288)

- Add error handling to 6 more async functions (#288)

- Add error handling to 42 async functions (#288)

- *(hooks)* Improve logging violation detection accuracy

- Add logging to 75 empty except blocks silently swallowing errors (#287)

- *(src)* Convert blocking file I/O to async in agent modules (#288)

- *(backend)* Convert blocking I/O to async in code_intelligence and logs (#288)

- *(backend)* Add proper error handling to async I/O operations (#288)

- *(race-conditions)* Add thread-safe locking to services and core modules (#279)

- *(race-conditions)* Add thread-safe locking to memory and tool singletons (#279)

- *(startup)* Add missing asyncio import in sequential_thinking_mcp (#279)

- *(race-conditions)* Add thread-safe locking to final 6 singleton getters

- *(race-conditions)* Complete thread-safe locking in sequential_thinking_mcp (#279)

- *(race-conditions)* Add thread-safe locking to remaining modules (#279)

- *(race-conditions)* Add thread-safe locking to utility scripts (#279)

- *(race-conditions)* Add thread-safe locking to backend services (#279)

- *(race-conditions)* Add thread-safe locking to async utilities (#279)

- *(race-conditions)* Add thread-safe locking to 29 singleton getters

- *(race-conditions)* Add thread-safe locking to 26 security and utils singletons

- *(race-conditions)* Add thread-safe locking to 8 singleton patterns

- *(race-conditions)* Add thread-safe locking to 5 singleton patterns in src/

- *(race-conditions)* Add thread-safe locking to 6 core singleton patterns

- *(race-conditions)* Add thread-safe locking to 9 singleton patterns

- *(browser_mcp)* Use in-place dict modification in rate limiter

- *(prompts)* Add asyncio lock for cache access protection

- *(analytics_precommit)* Add threading locks for global state protection

- *(websockets)* Add asyncio lock protection for NPU worker WS clients list

- *(race-conditions)* Add asyncio.Lock to codebase_analytics.py (#279)

- *(analytics)* Replace mock data with real API endpoints (#276)

- *(race-conditions)* Add asyncio.Lock to protect global state (#279)

- *(config)* Minor config manager and analytics fixes

- *(knowledge)* Fix API response handling in KnowledgeGraph.vue (#55)

- *(knowledge)* Add diagnostic logging for vectorization failures (#254)

- *(knowledge)* Add vector store initialization verification

- *(chat)* Improve message deduplication for user messages (#259)

- *(chat-workflow)* Fix trailing comma and add JSON corruption handling

- *(frontend)* Remove redundant .json() call from useKnowledgeVectorization

- *(frontend)* Remove redundant .json() calls from ApiClient responses

- *(knowledge-base)* Add ainit() alias for backward compatibility

- *(error-handling)* Add @with_error_handling to MCP tool endpoints

- *(syntax)* Fix 229 trailing comma tuple bugs across 113 files

- *(knowledge)* Address HIGH priority issues from code review (#163)

- *(style)* Add missing imports to fix F821 undefined name errors

- *(style)* Fix flake8 violations in log_aggregator.py

- *(style)* Remove unused imports from tools/ (F401)

- *(style)* Remove unused imports from tests/ (F401)

- *(style)* Minor cleanup after file splits (F401/imports)

- *(style)* Remove unused imports after file split (F401)

- *(style)* Remove unused imports from scripts/ (F401)

- *(style)* Remove unused imports from chat.py (F401)

- *(style)* Fix F401 unused imports in scripts/ subdirectories

- *(style)* Remove 50 F401 unused imports in monitoring/ (#215)

- *(style)* Fix F841 unused variables and Windows NPU worker F401 imports (#176)

- *(style)* Fix E402/F401 import order violations (#176)

- *(code-quality)* Remove unused imports F401 violations (#176)

- *(lint)* Fix E704 and W504 Flake8 violations (#176)

- *(monitoring)* Add graceful degradation to MonitoringDashboard

- *(monitoring)* Centralize hardcoded alert thresholds (#92)

- *(config)* Use environment variables for ports in reload-documentation.sh (#91)

- *(flake8)* Fix E124/E128 indentation violations

- *(flake8)* Remove unused typing imports (F401) (#176)

- *(style)* Partial flake8 cleanup - whitespace, blank lines, bare except, f-strings (#176)

- *(flake8)* Remove unused Pattern imports (F401) - 2 more files

- *(flake8)* Remove unused Pattern imports (F401)

- *(flake8)* Fix E117 over-indented code block (#176)

- *(flake8)* Add missing 'Any' import to fix F821 violations (#176)

- *(flake8)* Remove duplicate import redefinitions (F811) (#176)

- *(security)* Integrate security audit logging and authentication (#203)

- *(api)* Remove outdated TODO comments in conversation_files.py (#75)

- *(config)* Resolve configuration TODOs in llm_self_awareness and agent_config (#202)

- *(chat)* Add conversation deduplication to prevent duplicate history entries (#177)

- *(security)* Improve secrets.py input validation and status reporting (#190)

- *(style)* Partial E501 line length fixes via autopep8

- *(style)* Fix E-series spacing violations and F401 unused imports

- *(critical)* Fix E999 syntax errors, F821 undefined names, F824 unused globals

- *(style)* Fix E712, E731, E741 flake8 violations (#176)

- *(imports)* Remove F811 redefinition violations (#176)

- *(imports)* Remove 872 unused imports (F401 violations) (#178)

- Resolve F841 unused variables and async time.sleep issues (#186, #183)

- *(linting)* Remove unused variable assignments (F841) (#186)

- *(codebase-analytics)* Remove trailing commas creating tuples (#189)

- *(tests)* Remove hardcoded URLs from test files (#110-116)

- *(flake8)* Remove unnecessary f-string prefixes (F541) (#175)

- *(conversation-file-manager)* Remove commas converting Path objects to tuples

- *(codebase-analytics)* Fix f-string with broken arithmetic expression

- *(enhanced-memory)* Remove incorrect comma after raise statement

- *(npu-agent)* Fix f-string with broken hashlib.md5() call

- *(sandbox)* Fix f-string with broken list comprehension (3 instances)

- *(raise-statements)* Remove incorrect commas after raise statements

- *(conversation)* Fix f-string broken by comma insertion

- *(knowledge-mcp)* Properly fix f-string by joining into single line

- *(knowledge-mcp)* Fix f-string broken by comma insertion

- *(ai-stack-client)* Remove incorrect comma after raise ValueError statement

- *(syntax)* Fix missing commas after multi-line string parameters across entire codebase

- *(async-chat-workflow)* Add missing comma in timeout fallback response

- *(async-chat-workflow)* Add missing comma after response parameter

- *(intent-classifier)* Add missing comma after reasoning parameter

- *(filesystem-mcp)* Add missing commas in MCPTool constructors

- *(syntax)* Fix missing commas in WorkflowMessage constructor calls

- *(redis)* Migrate analysis scripts to use get_redis_client() (#89)

- *(typescript)* Complete TypeScript type safety improvements (#156)

- *(frontend)* Fix circular dependency causing blank page (#172)

- *(frontend)* Add Pinia type definition for persist option

- *(frontend)* Add missing ApiClient methods to resolve initialization errors

- *(frontend)* Use @ts-ignore for pinia persist options (#156)

- *(types)* Add TypeScript declarations for defaults.js (#172)

- *(frontend)* Fix TypeScript errors in composables (#156)

- *(ci)* Use python3 -m for all linting commands to fix PATH issues

- *(ci)* Add --break-system-packages flag to all pip install commands

- *(tests)* Correct network-constants import path in test-setup-helpers (#156)

- *(tests)* Fix remaining 5 TypeScript errors in test files (#156)

- *(ci)* Use $GITHUB_PATH to persist pyenv PATH across workflow steps

- *(frontend)* Complete remaining Issue #156 TypeScript fixes (#156)

- *(ci)* Add pyenv PATH setup to all workflows

- *(ci)* Simplify phase_validation.yml to resolve YAML parsing issues

- *(ci)* Improve Python setup and fix YAML syntax errors

- *(tests)* Fix test infrastructure TypeScript errors (#156)

- *(utils)* Fix type errors in cacheManagement, errorHandler, chunkTestUtility (#156)

- *(ci)* Fix YAML syntax error in phase_validation.yml

- *(ci)* Use system Python for self-hosted runner on Ubuntu 25.10

- *(ci)* Configure all workflows to use self-hosted runner

- *(core)* Fix type errors in ChatInterface, main.ts, rum.ts, debugUtils.ts (#156)

- *(knowledge)* Fix KnowledgeDocument type conversion in KnowledgeSearch (#156)

- *(desktop)* Add TypeScript declaration for DesktopInterface.vue (#156)

- *(browser)* Add missing pageTitle property to PopoutChromiumBrowser (#156)

- *(terminal)* Fix WorkflowAutomation explanation property type (#156)

- *(infrastructure)* Fix AddHostModal auth field handling (#156)

- *(knowledge)* Prevent Load More button from appearing in documentation modes

- *(knowledge)* Preserve tree expansion state when Load More button clicked

- *(frontend)* Fix TypeScript errors in infrastructure and knowledge components (#156)

- *(frontend)* Fix TypeScript errors in terminal, file-browser, and knowledge components (#156)

- *(frontend)* Fix TypeScript errors in UI components (#156)

- *(frontend)* Fix TypeScript errors in chat components and store (#156)

- *(frontend)* Fix TypeScript errors in 5 knowledge components (#156)

- *(frontend)* Fix KnowledgeController.ts TypeScript errors - add missing repository methods (#156)

- *(frontend)* Fix TypeScript errors in BackendSettings.vue (#156)

- *(frontend)* Fix TypeScript errors in UserManagementSettings.vue (#156)

- *(frontend)* Fix all 22 TypeScript event handling errors in DeveloperSettings.vue (#156)

- *(frontend)* Fix 95 TypeScript event handling errors in BackendSettings.vue (#156)

- *(frontend)* Fix TypeScript errors in knowledge base composables (#156)

- *(frontend)* Fix TypeScript errors in 4 critical components (#156)

- *(frontend)* Fix ApiClient Response type errors across 4 Vue components (#169)

- *(frontend)* Fix ApiClient Response type errors in 3 components (#156)

- *(scripts)* Eliminate hardcoding violations in shell scripts (#122, #125, #126)

- *(tests)* Eliminate hardcoding violations in test files (#117, #139)

- *(knowledge)* Fix Populate button and add Import for user-knowledge (#154)

- Eliminate hardcoded IPs across codebase - use NetworkConstants and new SecurityConstants

- *(archive)* Replace hardcoded localhost with MAIN_MACHINE_IP in async_llm_interface

- *(monitoring)* Replace localhost Redis with canonical get_redis_client() (#89)

- Eliminate hardcoded URLs and ports in E2E tests and monitoring (#109, #108, #99, #98)

- Eliminate 4 hardcoding violations (#141, #129, #133, #123)

- *(ci)* Add disk cleanup and --no-cache-dir to prevent disk space failure (#144)

- Eliminate ALL hardcoded IP addresses - 100% compliance achieved

- *(src)* Replace hardcoded localhost:8001 in project_state_manager.py

- *(hardcoding)* Replace hardcoded Redis IPs in analysis scripts (#134, #135, #136)

- *(frontend)* Replace hardcoded URL in cypress.config.ts

- *(debug)* Replace hardcoded URL in debug_frontend_rendering.js

- *(debug)* Replace hardcoded URLs in diagnose_frontend_issues.js

- *(debug)* Replace hardcoded URLs in debug_frontend_error.js

- *(tools)* Replace hardcoded URL in analyze_critical_env_vars.py recommendations

- *(tools)* Replace hardcoded URLs in analyze_env_vars.py examples

- Eliminate hardcoded URLs in E2E tests with centralized configuration (#111, #110)

- *(scripts)* Replace hardcoded Redis defaults in npu_worker_enhanced.py

- *(scripts)* Replace hardcoded localhost and fix missing import in system_monitor.py

- *(scripts)* Replace hardcoded IPs in verify_ssh_manager.py help text

- *(scripts)* Replace hardcoded service URLs in test_autobot_functionality.py

- *(scripts)* Replace hardcoded Redis host/port in init_memory_graph_redis.py

- *(scripts)* Replace hardcoded URLs in diagnose_backend_timeout.py

- Resolve hardcoding violations in Redis patterns and network scripts (#128, #127, #124)

- *(scripts)* Replace hardcoded URLs in npu_performance_measurement.py

- Resolve hardcoding violations in monitoring and frontend config (#137, #140)

- *(utils)* Correct indentation errors in service discovery and metrics

- *(constants)* Add Chrome debugger port and replace hardcoded URL

- *(config)* Replace hardcoded URLs in configuration managers

- *(utils)* Replace hardcoded port in performance_monitor.py

- *(core)* Use NetworkConstants for endpoint self-check

- *(tests)* Replace hardcoded URLs in api_benchmarks.py

- *(debug)* Replace hardcoded URL in capture_output.py

- *(utils)* Migrate redis_immediate_test.py to canonical pattern (#105)

- *(debug)* Replace hardcoded URLs in terminal debug scripts (#102, #103)

- *(debug)* Remove hardcoded URLs in debug_terminal.py (#101)

- *(redis)* Migrate cache.py to canonical Redis client pattern (#104)

- *(concurrency)* Add thread-safe locks to prevent race conditions (#64)

- *(chat)* Fix approval metadata field name mismatch (rawData→metadata)

- *(redis)* Add missing await for async Redis client coroutines

- *(redis)* Fix async/await mismatch in feature_flags and access_control_metrics

- *(redis)* Auto-load Redis password from environment variables

- *(workflow)* Prevent infinite approval polling loop causing 97.8% CPU usage

- *(terminal)* Filter terminal prompts from chat history

- *(redis)* Fix Redis connection stability and session ownership validation

- *(terminal)* Filter blank ANSI-only prompts from chat history

- *(redis)* Use correct socket constants for TCP keepalive options

- *(config)* Update async_config_manager to use canonical redis_client (P2 prep)

- *(redis)* Add backward compatibility for archived redis_database_manager (P1 hotfix)

- *(frontend)* Resolve Vue compilation error in KnowledgeSearch.vue

- *(approval-workflow)* Enhance chat/terminal integration and debugging

- *(terminal)* Add session auto-recreation and reusable session recovery

- *(frontend)* Resolve terminal mounting and sizing race conditions

- *(terminal)* Prevent double command execution in approval workflow

- *(chat)* Correct Ollama API endpoint for command interpretation

- *(frontend)* Correct negative vectorization count display

- *(sync)* Add timeouts to SSH commands to prevent hanging

- *(frontend-sync)* Implement correct startup order to prevent Vite module cache issues

- *(frontend)* Add missing helper functions to useKnowledgeBase composable

- Resolve knowledge base vectorization, API response handling, and terminal disposal bugs (#10640, #10641, #10642)

- *(ci)* Resolve dependency security and docker-build CI/CD failures

- *(error-handling)* Add missing imports for batch 52 migrations in terminal.py

- *(tests)* Add missing unittest import for batch 40 tests

- *(tests)* Correct batch 34 progress test rounding threshold

- *(tests)* Correct HTTPException detail strings in Batch 25 tests

- *(constants)* Add AI_STACK_HOST backward compatibility alias

- *(memory-graph)* Handle RuntimeError in entity-not-found exception handling

- *(api)* Handle both bytes and string keys in Redis fact queries

- *(knowledge-base)* Sanitize metadata arrays for ChromaDB compatibility

- *(backend)* Correct knowledge base Redis database number mapping

- *(backend)* Correct Redis async client initialization in knowledge_base

- *(backend)* Correct UnifiedConfigManager method calls in chat_workflow_manager

- *(frontend)* Clean up Vue template syntax errors from function reuse implementation

- *(frontend)* Remove duplicate class attribute in PopoutChromiumBrowser.vue

- *(setup)* Remove hardcoded LLM model from KB population script

- *(terminal)* Integrate terminal commands with chat history

- *(ansible)* Remove redundant StrictHostKeyChecking flag from ssh-copy-id

- Complete remaining infrastructure updates

- *(terminal)* Improve PTY handling and streaming interpretation

- *(terminal)* Resolve PTY race condition and enable streaming interpretation

- *(frontend)* Resolve all TypeScript compilation errors

- *(ci)* Handle missing test files gracefully in workflows

- *(ci)* Apply Black formatting to terminal.py

- *(ci)* Resolve remaining GitHub Actions build errors

- *(ci)* Apply Black formatting to remaining 2 files

- *(ci)* Resolve all GitHub Actions build errors

- *(frontend)* Add controllers directory to git tracking

- *(ci)* Resolve frontend build and Python formatting errors

- *(ci)* Add requirements-ci.txt to root for GitHub Actions

- *(frontend)* Resolve KnowledgeRepository import error in CI/CD build

- Restore git tracking for .claude/agents/ directory

- *(security)* Complete file permissions migration to modern auth (P0)

- *(git)* Exclude data directory from version control

- *(knowledge)* Prevent search timeout on empty knowledge base

- *(knowledge)* Resolve [object Promise] display issues

- *(knowledge)* Restore ManPageManager to Advanced tab

- *(knowledge)* Add initialization and reindexing functions, fix API response handling

- Implement streaming response in chat workflow manager

- Resolve Playwright viewport display issues

- Replace localhost with external IP addresses for remote access

- Remove 'consolidated' and 'fix' from API filenames

- *(backend)* Update imports and configuration for improved compatibility

- *(backend)* Enhance config service with network constants integration

- *(backend)* Enhance service monitoring and fix Chrome DevTools integration

- *(frontend)* Enhance desktop interface and VNC viewer components

- Minor API and syntax cleanups

- *(frontend)* Update Vite config for distributed architecture

- *(performance)* Update monitoring and performance fix scripts

- *(services)* Improve error handling and session management

- *(infrastructure)* Resolve ConfigHelper get_machines method error

- *(backend)* Resolve infrastructure monitor configuration error

- *(frontend)* Correct setActiveTab method call in App.vue

- *(frontend)* Correct ApiClient port detection for production builds

- *(frontend)* Correct WebSocket connection path

- *(frontend)* Correct API routing logic for production builds

- Add missing dependency version file

- *(frontend)* Resolve Vue component props and add missing navigation menus

- *(frontend)* Resolve proxy connectivity and WebSocket timeout issues

- Correct LLM sync function name in background task

- Correct Redis database configuration YAML structure

- Restore Knowledge Base Statistics display showing real data

- Resolve Keras 3 compatibility issues with Transformers library

- Complete async optimization and resolve critical WebSocket connectivity issues

- Clean up duplicate browser services and remove redundant Microsoft Playwright image

- Resolve backend blocking operations that caused timeout issues

- Use proven browser launch logic from run_agent.sh

- Improve browser auto-launch with WSL support and better error handling

- Correct backend module path for proper imports

- Correct AI stack server command to use proper module path

- Resolve Docker Compose service dependency issues

- Resolve CI/CD test failures by adding missing dependencies to requirements-ci.txt

- Apply pre-commit formatting fixes to changelog and completion reports

- Resolve Docker build issues and improve security file handling

- Resolve TypeScript configuration issues

- Resolve backend startup failures and improve orchestrator

- Resolve backend startup failures and improve Seq authentication

- Resolve linting and secret detection issues

- Improve logging configuration and directory structure

- Resolve NPU Worker connection issues during startup

- Add WebSocket broadcasting for chat responses

- Correct API endpoint in sendChatMessage to use proper chat endpoint

- Resolve duplicate function declarations in KnowledgeManager

- Comprehensive linting improvements - 50% error reduction

- Resolve 93 linting errors in error_boundaries.py

- Complete linting fixes for semantic_chunker.py - add missing newline at EOF

- Resolve linting issues in knowledge_extraction_agent.py and llm_interface_unified.py

- Clean up unused imports in system.py

- Correct API endpoint validation and remove hardcoded URLs

- Resolve critical API endpoint mismatches between frontend and backend

- Improve error handling by replacing bare except clauses

- Resolve critical undefined name errors with auto-formatting

- Resolve critical code quality issues

- Resolve terminal interactive input consistency issues

- Consolidate chat endpoint patterns to use modern API

- Complete hardcoded URL replacement across critical frontend components

- Replace hardcoded localhost:8001 URLs with configurable API client

- Add missing workflow creation methods for security scan and backup

- Complete voice interface CI/CD separation and frontend testing

- Resolve voice interface CI/CD and frontend Cypress configuration

- Improve WebSocket stability and add architecture documentation

- Add missing os import in llm_interface.py

- Resolve CI/CD dependency compilation issues

- Resolve Python types namespace collision

- Convert browser API blocking file I/O to async operations

- Handle MessagePriority enum conversion in agent communication

- Handle MessageType enum conversion in agent communication

- Convert file I/O operations in API endpoints to async

- Convert knowledge base API blocking operations to async

- Convert chat API blocking file I/O operations to async

- Resolve Vite plugin version conflicts for CI/CD compatibility

- Resolve CUDA/PyTorch import issues for CI/CD compatibility

- Resolve critical linting errors and code quality issues

- Resolve TypeScript import errors and build configuration

- Update LLM failsafe agent to use correct chat_completion method

- Improve container startup handling in run_agent.sh

- Add missing logging import in orchestrator.py

- Resolve terminal input consistency issues for reliable automated testing

- Migrate deprecated Pydantic @validator to @field_validator

- Add missing config file creation in deployment-check phase

- Add missing API service methods for complete test coverage

- Update deprecated GitHub Actions to latest versions

- Update CI workflow for new file organization and branch support

- Resolve all 4 failing security integration tests

- Add python-multipart dependency for FastAPI form data handling

- Apply pre-commit hook formatting fixes to frontend tests

- Resolve final 3 backend test failures in secure command executor

- Resolve all backend test failures and flake8 linting errors

- Update package-lock.json after adding @pinia/testing dependency

- Clean up duplicate EnhancedSecurityLayer imports

- Resolve frontend test configuration issues

- Improve TypeScript configuration for testing

- Comprehensive CI test configuration improvements

- Improve CI dependency installation for NumPy compatibility

- Update CI dependencies for Ubuntu compatibility

- Improve terminal input consistency for automated testing

- Enhance CI/CD pipeline and dependencies management

- Resolve critical runtime errors preventing app startup

- Critical syntax errors preventing app startup

- Migrate FastAPI event handlers to modern lifespan pattern

- Clean up unused imports and code quality issues

- Resolve terminal WebSocket import error preventing app startup

- Eliminate all 21 bare except clauses across codebase

- Resolve critical backend hanging issues from analysis report

- Downgrade packages to resolve crypto.hash CI/CD error

- *(frontend)* Add Node.js version requirements for CI/CD compatibility

- Remove sqlite3 from requirements.txt

- *(knowledge_base)* Optimize Redis operations to prevent blocking

- Update run_agent.sh to recognize both Playwright container names

- Remove read-only noVNC volume mount to prevent package conflicts

- Change VNC port to 5901 to avoid Kali Linux TigerVNC conflict

- Use consistent VNC port mapping 5900:5900

- Correct Playwright service name and environment variable

- Change RedisInsight to use port 8002 internally and externally

- Resolve PhaseStatusIndicator API routing and code quality issues

- Resolve linting issues and improve backend chat API

- Comprehensive frontend security, performance, and accessibility improvements

- Improve terminal command filtering to allow sudo commands

- Use localhost for terminal service connections in development

- Improve terminal handling of interactive commands and timeouts

- Connect frontend terminal to working simple terminal backend

- Correct WorkflowApproval API endpoint URL

- Eliminate console error spam from legacy chat deletion

- Initialize tool registry in orchestrator constructor

- Correct workflow execute endpoint path in test script

- Remove generated data files and enhance .gitignore

- Update multi-agent model configuration to use available models

- Apply formatting and documentation updates for hardware acceleration

- Resolve chat deletion persistence issue in frontend

- Add system knowledge bridge API to resolve empty frontend sections

- Resolve LLM model alias and fact search improvements

- Resolve KB Librarian Agent method compatibility issues

- Resolve PostCSS build issues for Vue Notus Tailwind design

- Resolve message toggle persistence and improve settings synchronization

- Update frontend build artifacts after message toggle implementation

- Resolve toggle persistence and empty agent responses

- Enable message display toggles for historical messages

- Implement proper Vue reactivity for message display toggles

- Clean up unused port references and standardize port configuration

- Resolve all 390 flake8 code quality issues

- Break long lines in orchestrator.py to meet 88-character limit

- Resolve flake8 linting errors in backend API and configuration files

- Replace hardcoded tinyllama model references with deepseek-r1:14b

- Implement functional Redis background tasks and listeners


### CI/CD

- *(release)* Add automated release workflow (#1296)

- Update GitHub Actions for new folder structure (#781)

- Switch all workflows from ubuntu-latest to self-hosted runner (#349)

- Clean up self-hosted runner specific code

- Switch all workflows back to GitHub hosted runners (ubuntu-latest)

- *(quality)* Add automated code quality enforcement


### CRITICAL

- Fix backend deadlock by moving LLM config sync to background task


### Documentation

- Add recent plan documents and session-stop orphan hook (#1259)

- *(plans)* Add pre-commit auto-formatter Claude hook design

- *(skills)* Add skill-router implementation plan (#1182)

- *(plans)* Add UI improvements implementation plan (orchestration, preferences, automation)

- *(readme)* Rewrite README as functional landing page with screenshots

- *(plans)* Link community growth plans to issue #1161

- *(plans)* Add community growth skill implementation plan

- *(plans)* Add community growth skill design document

- *(roles)* Fix copyright year to 2026, add role conflict matrix (#1129)

- *(roles)* Add comprehensive fleet role registry with schematics and DB setup (#1129)

- Update all backend URL references from :8001 to :8443 (HTTPS upgrade)

- Restructure CLAUDE.md around 6 core rules, move reference to AUTOBOT_REFERENCE.md

- Add AUTOBOT_REFERENCE.md and restructure design/plan docs

- *(claude)* Add 5 core development rules to workflow

- *(claude)* Add Rule 6 - report every discovered problem

- *(claude)* Add 5 core development rules to workflow

- Add voice conversation mode design plan

- *(plans)* Add skills system and memory hygiene implementation plans

- *(workflow)* Add debugging discipline + broaden arch confirmation scope

- *(workflow)* Add phase-boundary commit rule for context limits

- *(workflow)* Add Ansible pre-flight SSH check and SLM-first service management rule

- *(workflow)* Clarify re-stage requirement after hook auto-modifies files

- *(workflow)* Add file verification and multi-node coverage checks

- *(workflow)* Add Python version specifics to deployment checklist

- *(workflow)* Add memory hygiene policy to CLAUDE.md

- Bulk remove enterprise-grade and production-ready claims (#938)

- Remove readiness claims from additional docs and code prompts (#938)

- Issue #926 Phase 8 - architecture docs, runbooks, CLAUDE.md fix (#926)

- Remove production/enterprise readiness claims from documentation (#938)

- *(roadmap)* Update ROADMAP_2025.md with verified commit references (#698)

- *(networking)* Document WSL2 loopback limitation for backend port 8443 (#914)

- *(debugging)* Add backend debugging workflow guide (#890)

- *(deployment)* Add comprehensive frontend deployment guides (#243)

- Add implementation principles from insights analysis

- *(infrastructure)* Correct Grafana location to SLM server (#859)

- Add comprehensive Ansible deployment documentation to CLAUDE.md (#831)

- Update infrastructure documentation to reference Ansible (#831)

- *(ansible)* Add README for backend deadlock fix playbook (#876)

- Update critical documentation for service management (#863)

- Add comprehensive service management guide (#863)

- Update all documentation for port 8443 and HTTPS (#858)

- *(ansible)* Add missing README.md for centralized_logging role (verification fix)

- *(grafana)* Add changelog, health check script, and quick reference

- *(troubleshooting)* Expand troubleshooting guides with searchable index (#755)

- Add pre-commit & linting guidance to CLAUDE.md

- Add session boundaries and scope management policy to CLAUDE.md

- Add multi-agent safety, PR workflow, and release channels to CLAUDE.md (#733) ([#792](https://github.com/mrveiss/AutoBot-AI/pull/792))

- Mark documentation consolidation plan as complete (#791)

- Consolidate and reorganize documentation structure (#791)

- Update documentation for per-role infrastructure structure (#781)

- Add SLM bootstrap script design (#789)

- Update developer guides with new folder structure paths (#781)

- Update CLAUDE.md and pre-commit config for new folder structure (#781)

- *(slm)* Add PostgreSQL deployment documentation (#786)

- *(api)* Add password change endpoint documentation (#635)

- *(shared)* Add shared components directory (#635)

- *(npu)* Add NPU worker pool API documentation (#168)

- *(plan)* User password change implementation plan (#635)

- *(design)* User password change functionality design (#635)

- *(plans)* Add bug prediction realtime trends implementation plan (#637)

- *(planning)* Add NPU multi-worker pool design (#168)

- *(user-management)* Add SLM user management system design (#576)

- *(plans)* Add bug prediction real-time trends design (#637)

- *(plans)* Add design documents for sync consolidation and unified frontend style

- *(analysis)* Add comprehensive merge conflict analysis for PR #782

- *(implementation)* Add final report for issue #753

- *(frontend)* Add comprehensive preferences documentation (#753)

- *(plans)* Add folder restructure implementation plan (#781)

- *(plans)* Add per-component data directories to restructure design

- *(plans)* Add folder restructure design for role-based organization

- Add component architecture guide to prevent deployment confusion

- *(plans)* Add role-based sync completion plan (#779)

- *(plans)* Add implementation plan for Code Intelligence Dashboard (#566)

- *(plans)* Add Code Intelligence Dashboard design (#566)

- *(plans)* Add NPU semantic code search design (#207)

- *(plans)* Add NPU Fleet Integration design document

- *(#749)* Add detailed implementation plan

- *(#779)* Add implementation plan for role-based code sync

- *(plans)* Update implementation status for #751

- Add role-based code sync design document

- *(#749)* Add terminal integration finalization design

- *(#748)* Add tiered model distribution design document

- *(#778)* Add Workflow Templates implementation plan

- *(#772)* Add Code Intelligence implementation plan

- *(auth)* Add authentication and RBAC documentation - Phase 8 (#744)

- *(plans)* Add Phase 3 implementation plan (#760)

- *(plans)* Add Phase 3 client library design (#760)

- Add detailed frontend audit report and fix vitest config (#761) ([#761](https://github.com/mrveiss/AutoBot-AI/pull/761))

- *(plans)* Add Agent LLM config implementation plan (#760)

- *(plans)* Add Agent LLM configuration design (#760)

- *(plans)* Add Config Registry implementation plan (#751)

- *(plans)* Add service discovery implementation plan (#760)

- *(plans)* Add config registry consolidation design (#751)

- *(plans)* Add service discovery design for #760

- *(plans)* Add implementation plan for Knowledge Manager frontend (#747)

- *(plans)* Add Knowledge Graph enhancement design (#747)

- *(plans)* Add Knowledge Manager frontend design (#747)

- *(cache)* Use SSOT backend URL instead of localhost (#743)

- *(plans)* Add CacheCoordinator implementation plan (#743)

- *(slm)* Add detailed implementation plan for code distribution (#741)

- *(slm)* Add code distribution and version tracking design

- Update migration guides for consolidated imports (#738)

- Add layer separation implementation plan

- Add layer separation design for management vs business

- Update system-state.md for mTLS migration (#725)

- *(plans)* Add implementation plan for issue #694 config consolidation

- Add mTLS migration design and cleanup targets (#725)

- Update system-state.md for issue #729 admin migration

- Add frontend API endpoints audit report

- Add comprehensive system improvement documentation

- Browser API async improvements documentation

- Add comprehensive system documentation

- Update agent documentation and optimization roadmap

- Add codebase analysis results from profiling run

- Enhance CLAUDE.md with comprehensive development guidelines

- Update development guidelines for security and dependencies

- Add comprehensive Phase D impact and status analysis

- Update documentation structure and add comprehensive guides

- Authorize NPU worker and Redis for development acceleration

- Update CI status and test documentation

- Mark low-priority code readability improvements as completed

- Add external apps documentation structure and guidelines

- Add temporal RAG optimization research and implementation assessment

- Implement comprehensive documentation system

- Enhance CLAUDE.md with comprehensive agent system documentation

- Update CLAUDE.md with critical user interaction requirements

- Add port mappings documentation for clarity

- Update CLAUDE.md with command permission system guidelines

- Add comprehensive documentation and analysis reports

- Comprehensive production deployment readiness validation

- Ultimate implementation completion summary and final status

- Detailed metrics and monitoring system documentation

- Comprehensive documentation of major AutoBot enhancements

- Add comprehensive system status report

- Comprehensive workflow orchestration documentation update

- Advanced architecture and deployment documentation

- Comprehensive workflow orchestration documentation

- Update project roadmap with completed Phase 6 multi-agent architecture

- Add comprehensive SettingsPanel.vue component documentation

- Add comprehensive librarian and helper agents documentation

- Add knowledge base maintenance guide and sync infrastructure

- Improve CLAUDE.md with concise, actionable guidance for Claude Code

- Complete documentation restructuring with single source of truth

- Complete documentation restructuring with single source of truth

- Restructure documentation with automated validation system

- Consolidate task management into single source of truth

- Finalize unified documentation structure - exclude reports, create comprehensive index

- Restructure documentation to eliminate redundancies and create single source of truth

- Finalize unified documentation structure - exclude reports, create comprehensive index

- Restructure documentation to eliminate redundancies and create single source of truth

- Finalize unified documentation structure - exclude reports, create comprehensive index

- Create unified documentation structure with comprehensive phase validation

- Create unified documentation structure with comprehensive phase validation

- Finalize Phase 4 documentation and task tracking updates

- Correct all reports to reflect accurate implementation status

- Mark quick wins report as solved

- Mark medium priority task breakdown report as solved

- Mark high priority task breakdown report as solved

- Update reports status to reflect completed infrastructure transformation

- *(slm)* Add SLM startup procedure design (#726)

- *(slm)* Mark Phase 5 complete in design document (#726)

- *(slm)* Add Phase 5 Admin UI design document (#726)

- *(slm)* Mark Phase 4 complete in design document (#726)

- *(slm)* Add Phase 1 implementation plan (#726)

- *(security)* Add lockout recovery procedures (#700)

- Update references to renamed files (#708)

- *(examples)* Replace fake /api/users with real /api/llm/models (#710)

- *(standards)* Add function length standards to prevent Issue #665 recurrence

- *(reference)* Add industry agent system prompts for pattern analysis (#645)

- *(architecture)* Complete Phase 2 design documents for agent patterns (#645)

- *(npu-worker)* Update sync script with OpenVINO EP testing commands (#640)

- *(ssot)* Add SSOT config documentation and update shell scripts (#604)

- *(architecture)* Enhance SSOT config architecture document (#599)

- *(architecture)* Add SSOT Configuration Architecture guide (#598)

- *(workflow)* Add frontend/backend integration check requirement

- *(workflow)* Add issue completion criteria and log forwarder utility

- Complete documentation improvement roadmap (#251)

- Consolidate project roadmaps into single canonical source (#407)

- Add disaster recovery procedures (#251)

- Add Redis database schema documentation (#251)

- Add comprehensive data flow diagrams (#251)

- Add architecture overview and glossary (#251)

- *(adr)* Create Architecture Decision Records system (#251)

- *(code)* Add docstrings to 19 undocumented public functions (#377)

- *(#316)* Add docstrings to reduce undocumented functions from 792 to 135

- Add comprehensive logging standards documentation (#310)

- Update environment variables and configuration documentation

- *(features)* Add Knowledge Graph documentation (#55)

- *(chat)* Add chat knowledge service integration documentation (#249)

- Add GitHub issue links to 8 task documentation files

- Add GitHub issue links to remaining documentation files

- Archive completed feature docs, create RAG integration issue

- Archive completed implementation docs, add new feature specs

- Add comprehensive code quality violations report

- *(guidelines)* Update task tracking requirements in CLAUDE.md

- *(copyright)* Add mandatory copyright headers to all scripts

- Add pending GitHub issues tracking file

- *(copyright)* Add mandatory copyright headers to all Python files

- *(architecture)* Add config consolidation analysis and migration plan

- *(roadmap)* Update statistics to reflect actual codebase metrics

- Update system state and project documentation

- *(features)* Add comprehensive Interactive Command Support documentation (Issue #33)

- *(consolidation)* Final status update - All 10 issues closed

- *(consolidation)* Update project status - Issues #37, #38, #39, #40 ALL COMPLETE

- *(analysis)* Complete Issue #40 Full Analysis Phase - Targeted Refactoring Recommended

- *(consolidation)* Update project status - ALL WORK 100% COMPLETE ✅

- *(analysis)* Chat/Conversation consolidation assessment - Issue #40 DEFERRED

- *(consolidation)* Comprehensive consolidation project status summary

- *(analysis)* HTTP client consolidation assessment - Issue #41 NOT NEEDED

- *(redis)* Complete Redis consolidation cleanup (Issue #43)

- *(claude)* Document Issue #35 policies in CLAUDE.md

- *(centralization)* Update summary with Phase 4 cache consolidation

- Phase 4 cache consolidation audit

- Update centralization summary with P1 hotfixes #3 and #4

- *(frontend)* Document BaseButton batch 67 migration

- *(frontend)* Document BaseButton batch 66 migration

- *(frontend)* Document BasePanel batch 65 migration

- *(knowledge)* Add comprehensive reranking integration guide

- *(frontend)* Document BasePanel batch 64 migration

- *(frontend)* Document BasePanel batch 63 migration

- *(frontend)* Document BasePanel batch 62 migration

- *(frontend)* Document BasePanel batch 61 migration

- *(frontend)* Document BasePanel batch 60 migration

- *(frontend)* Document BaseModal migrations (batches 56-57)

- *(frontend)* Document BaseModal migrations (batches 53-55)

- *(frontend)* Document BaseModal migrations (batches 50-52)

- *(frontend)* Document BaseModal migrations (batches 47-49)

- *(frontend)* Document BaseAlert component creation and migration (batches 41-46)

- *(frontend)* Mark BaseButton migration as complete

- *(reusability)* Update BaseButton touch integration commit hash

- *(reusability)* Document batch 20 BaseButton migrations and update progress tracking

- *(reusability)* Batch 13 - implementation reality check

- *(reusability)* Batch 12 - deep dive findings and strategy revision

- *(reusability)* Update progress for batch 6 (FileListTable)

- *(reusability)* Update progress for batch 5 (MonitoringDashboard)

- *(system-state)* Document approval workflow fixes and improvements

- *(claude)* Update workflow and quality standards

- *(claude)* Optimize CLAUDE.md for 22% token reduction while preserving all instructions

- *(error-handling)* Add comprehensive 5-phase refactoring plan

- *(error-handling)* Add comprehensive Phase 2 migration guide with examples

- *(config)* Add llm_models.example.yaml with performance classifications

- *(config)* Add comprehensive LLM model configuration guide

- *(policy)* Add comprehensive hardcoding prevention policy

- *(config)* Enhance .env.example with comprehensive configuration guide

- *(project)* Add configuration remediation planning documents

- *(service)* Update service_client example to use NetworkConstants

- Update system state and Redis performance documentation

- *(agents)* Update all agent documentation and specifications

- *(architecture)* Add comprehensive architecture and development documentation

- *(project)* Enhance CLAUDE.md with comprehensive workflow enforcement

- *(cleanup)* Reorganize documentation into proper directory structure

- *(project)* Update CLAUDE.md with configuration improvements

- *(quality)* Add code quality implementation documentation

- *(quality)* Add code quality documentation and configuration

- *(tests)* Add modern test documentation and security architecture

- *(tasks)* Update consolidated tasks documentation

- *(service-auth)* Add service authentication deployment reports

- *(security)* Add access control and security documentation

- *(week1)* Add Week 1 database and planning documentation

- Update documentation, planning, and project guidelines

- Comprehensive project guidelines and feature documentation

- *(planning)* Add comprehensive project planning and roadmap documentation

- Enhance system documentation and architecture guides

- Update security audit report with latest findings

- Update project documentation and improve development guidelines

- Update documentation and add test results

- Update and consolidate project documentation

- Add comprehensive refactoring and architecture documentation

- Add API integration and troubleshooting documentation

- Reorganize project documentation structure

- Add comprehensive system documentation and fix reports

- Add implementation documentation and research workflows

- Add comprehensive system documentation and remaining components

- Update CLAUDE.md with latest fixes and improvements

- Remove outdated documentation files

- Complete final reports processing and organization

- Add Knowledge Manager categories troubleshooting guide

- Update documentation with project information sources and Docker modernization

- Organize project documentation and complete analysis reports

- Split CLAUDE.md into focused area-specific guides

- Add comprehensive hardcoded values guidelines

- Add comprehensive StandardizedAgent implementation summary

- Add comprehensive codebase analytics documentation and duplicate detection analysis

- Consolidate and clean up reports directory

- Update project status to 99.8% complete

- Add comprehensive production security checklist

- Add frontend API endpoints audit report

- Add comprehensive system improvement documentation

- Browser API async improvements documentation

- Add comprehensive system documentation

- Update agent documentation and optimization roadmap

- Add codebase analysis results from profiling run

- Enhance CLAUDE.md with comprehensive development guidelines

- Update development guidelines for security and dependencies

- Add comprehensive Phase D impact and status analysis

- Update documentation structure and add comprehensive guides

- Authorize NPU worker and Redis for development acceleration

- Update CI status and test documentation

- Mark low-priority code readability improvements as completed

- Add external apps documentation structure and guidelines

- Add temporal RAG optimization research and implementation assessment

- Implement comprehensive documentation system

- Enhance CLAUDE.md with comprehensive agent system documentation

- Update CLAUDE.md with critical user interaction requirements

- Add port mappings documentation for clarity

- Update CLAUDE.md with command permission system guidelines

- Add comprehensive documentation and analysis reports

- Comprehensive production deployment readiness validation

- Ultimate implementation completion summary and final status

- Detailed metrics and monitoring system documentation

- Comprehensive documentation of major AutoBot enhancements

- Add comprehensive system status report

- Comprehensive workflow orchestration documentation update

- Advanced architecture and deployment documentation

- Comprehensive workflow orchestration documentation

- Update project roadmap with completed Phase 6 multi-agent architecture

- Add comprehensive SettingsPanel.vue component documentation

- Add comprehensive librarian and helper agents documentation

- Add knowledge base maintenance guide and sync infrastructure

- Improve CLAUDE.md with concise, actionable guidance for Claude Code

- Complete documentation restructuring with single source of truth

- Complete documentation restructuring with single source of truth

- Restructure documentation with automated validation system

- Consolidate task management into single source of truth

- Finalize unified documentation structure - exclude reports, create comprehensive index

- Restructure documentation to eliminate redundancies and create single source of truth

- Finalize unified documentation structure - exclude reports, create comprehensive index

- Restructure documentation to eliminate redundancies and create single source of truth

- Finalize unified documentation structure - exclude reports, create comprehensive index

- Create unified documentation structure with comprehensive phase validation

- Create unified documentation structure with comprehensive phase validation

- Finalize Phase 4 documentation and task tracking updates

- Correct all reports to reflect accurate implementation status

- Mark quick wins report as solved

- Mark medium priority task breakdown report as solved

- Mark high priority task breakdown report as solved

- Update reports status to reflect completed infrastructure transformation


### Features

- *(deploy)* Virtualmin-style install script + SLM setup wizard (#1294)

- *(bi-reports)* Implement saved reports persistence + registration (#1295)

- *(monitoring)* Extract unique compat endpoints to registered routers (#1283)

- *(router)* Register services/advanced_workflow, delete obsolete prototype (#1280)

- *(router)* Register audit.py and knowledge_sync_service.py (#1281, #1284)

- *(knowledge)* Register knowledge_relations router, add RelationsMixin (#1279)

- *(voice)* Integrate voice side panel into ChatInterface

- *(voice)* Create VoiceConversationPanel side panel component

- *(voice)* Add voice display mode toggle to ProfileModal

- *(voice)* Add voiceDisplayMode preference to usePreferences

- *(knowledge)* Observable research panel — live browser collaboration (#1256)

- *(knowledge)* Connector management UI — list, create, edit, sync, history (#1255)

- *(knowledge)* Add source verification queue and provenance display (#1253)

- *(knowledge)* Source connector framework — file, web, database (#1254)

- *(knowledge)* Add source verification queue and provenance display (#1253)

- *(knowledge)* Source connector framework — file, web, database (#1254)

- *(knowledge)* Source provenance metadata, verification workflow, pipeline cognifiers (#1252, #1257)

- *(hooks)* Add GitHub issue enforcement hooks (#1258)

- *(orchestration)* Post-sync action badges for build, schema, restart (#1243)

- *(updates)* Add real system package discovery and combined badges (#840)

- *(browser)* Add GUI automation side panel to browser tab (#1242)

- *(chat)* Add vision eye button and wire modal results into chat (#1242)

- *(chat)* Add VisionAnalysisModal component (#1242)

- *(infra)* Merge secrets-based hosts into infrastructure hosts API

- *(slm-frontend)* Consolidate Updates & Code Sync into tabbed view (#1230)

- *(analytics)* Enable incremental indexing support (#1220)

- *(analytics)* Auto-sync when indexing an uncloned code source (#1199)

- *(monitoring)* Add hardware NPU/GPU stub endpoints and fix NPU connection test (#1190)

- *(chat)* Remove used_knowledge gate from ChatMessages citations (#1186)

- *(chat)* Show sources panel for all assistant messages (#1186)

- *(chat)* Extend CitationsDisplay for type/reliability/web (#1186)

- *(slm-ui)* Make commit hashes clickable GitHub links in CodeSyncView (#1185)

- *(chat)* Always populate citations with _build_source_list (#1186)

- *(indexing)* Run codebase indexing in isolated subprocess (#1180)

- *(indexing)* Run codebase indexing in isolated subprocess (#1180)

- *(skills)* Add skill-researcher + 3-phase gap-fill pipeline (#1182)

- *(skills)* Fall back to autonomous-skill-development when no match found

- *(skills)* Implement find_skill action with LLM re-ranking and fallback

- *(skills)* Add skill-router LLM re-ranker

- *(skills)* Add skill-router keyword scorer and tests

- *(ui/automation)* Add GUI Automation section to workflow builder sidebar (#1166)

- *(deploy)* Notify SLM of new commit after GitHub pull (#1170)

- *(ui/preferences)* Convert settings page to tabbed layout (#1166)

- *(deploy)* Switch update-all-nodes.yml to pull from GitHub on .19 (#1170)

- *(analytics)* Add code source registry backend (#1133)

- *(analytics)* Add code source registry frontend (#1133)

- *(community-growth)* Add CommunityGrowthSkill + 3 workflow templates (#1161)

- *(slm/orchestration)* Restart confirmation dialog with affected node list (#1166)

- *(slm/orchestration)* Expandable per-node rows in fleet services table (#1166)

- *(slm/orchestration)* Add category filter chips to fleet operations tab (#1166)

- *(slm/orchestration)* Add quick role assignment card to migration tab (#1166)

- *(slm-frontend)* Redirect /settings/admin/npu-workers to /fleet/npu (#1129)

- *(slm-frontend)* Remove NPU Workers from settings nav (#1129)

- *(slm-frontend)* Add Worker Registry sub-tab to NPUWorkersTab (#1129)

- *(slm)* Detect service-only roles + clean up settings nav (#1129)

- *(browser)* Screenshot-based visual browser for chat browser tab (#1130)

- *(ansible)* Add required/degraded_without to slm-agent role.json (#1129)

- *(slm-frontend)* Route-based tab management in SecurityView (#1129)

- *(slm-frontend)* Route-based tab management in SkillsView (#1129)

- *(slm-frontend)* Route-based tabs for Backups and Deployments views (#1129)

- *(slm-frontend)* Route-based tab management in FleetOverview (#1129)

- *(slm-frontend)* Add skills icon to sidebar (#1129)

- *(slm-frontend)* Update sidebar nav paths and add isItemActive helper (#1129)

- *(slm)* Register role metadata migration and extend tab routing (#1129)

- *(slm)* Tab-based routing for fleet/deployments and DB migration for role metadata (#1129)

- *(slm-frontend)* Add Roles column to infrastructure tab nodes table (#1129)

- *(slm-frontend)* Add Ansible playbook migration button and result panel (#1129)

- *(slm-frontend)* Add detected roles banner, playbook migration, fleet health refresh (#1129)

- *(slm-frontend)* Add loadRolesForNode, populate required/degraded_without in edit form (#1129)

- *(slm-frontend)* Reset required/degraded_without in openCreateRoleForm (#1129)

- *(slm-frontend)* Add required/degraded_without fields and node roles cache (#1129)

- *(slm-frontend)* Import FleetHealth/PlaybookMigrateResult types in OrchestrationView (#1129)

- *(slm-frontend)* Add fleet health and role migration composable methods (#1129)

- *(roles)* Replace DEFAULT_ROLES with complete 17-role fleet registry (#1129)

- *(architecture)* Phase 2-4 role-centric deployment — metadata, fleet health, migration (#1129)

- *(frontend)* Add exponential backoff + circuit breaker to chat message polling (#1100)

- *(voice)* Show personality voice override hint in VoiceSettingsPanel (#1135)

- *(voice)* Use effectiveVoiceId (personality override) in voice output and conversation (#1135)

- *(voice)* Add effectiveVoiceId with personality override to useVoiceProfiles (#1135)

- *(personality)* Add voice selector to SLM personality settings editor (#1135)

- *(personality)* Add voice_id to SLM frontend personality interfaces (#1135)

- *(personality)* Expose voice_id in API schemas (#1135)

- *(personality)* Add voice_id field to PersonalityProfile dataclass (#1135)

- *(compliance)* Add pre-commit hook for direct Redis connections (#1086)

- *(config)* Model-to-endpoint routing for CPU/GPU Ollama nodes (#1070)

- *(config)* Model-to-endpoint routing for CPU/GPU Ollama nodes (#1070)

- *(hooks)* Add pre-commit hook for print()/console.* detection (#1082)

- *(voice)* Add voice profile CRUD + raise TTS char limit (#1054, #1058)

- *(tts)* Replace Kani-TTS-2 with Pocket TTS engine (#1054)

- *(voice)* Add voice profiles UI + wire voice_id through pipeline (#1054)

- *(voice)* Add voice profile CRUD + raise TTS char limit (#1054, #1058)

- *(ansible)* Swap Kani-TTS-2 for Pocket TTS in tts-worker role (#1054)

- *(tts)* Replace Kani-TTS-2 with Pocket TTS engine (#1054)

- *(infra)* Replace rsync with git archive in fleet deploys (#1056)

- *(infra)* Replace rsync with git archive in fleet deploys (#1056)

- *(voice)* Add Silero VAD helpers for hands-free mode (#1030)

- *(voice)* Hands-free voice mode with VAD + Whisper transcription (#1030, #1042)

- *(ansible)* GPU-aware LLM role with conditional model pulling (#1040)

- *(chat)* Migrate to LangGraph StateGraph for chat orchestration (#1043)

- *(slm)* Remove role from node with optional data backup (#1041)

- *(slm)* Add service health counts to fleet overview + error context UI (#1019)

- *(slm)* Capture error context for failed services (#1019)

- *(backend)* Migrate ChromaDB from embedded to remote HTTP client (#1021)

- *(ansible)* Add AI Stack sync to update-all-nodes + Ollama tuning (#1022, #1020)

- *(llm)* Pull all 8 required Ollama models and add concurrency tuning (#1035)

- *(frontend)* Add voice conversation overlay with walkie-talkie mode (#1029)

- *(backend)* Add terminal execute + admin file browser endpoints (#983, #984)

- *(voice)* Wake word CPU optimization for always-on detection (#927)

- *(frontend)* Plugin Manager UI — browse, install, enable/disable plugins (#929)

- *(ansible)* Add missing system packages to backend and npu-worker roles (#931)

- *(agents)* Self-improving tasks — adaptive task refinement and outcome learning (#930)

- *(skills)* Autonomous skill development — self-gap detection (#951)

- *(tts-worker)* Conditional torch install for CPU vs GPU nodes (#928)

- *(a2a)* Security cards, distributed tracing, capability verification (#968)

- *(tts)* Voice output toggle + integration tests (#928)

- *(tts)* Kani-TTS-2 TTS worker microservice (#928)

- *(slm)* External Agent Registry — CRUD, card fetch, frontend UI (#963)

- *(personality)* Multi-profile personality system (#964)

- *(a2a)* SLM fetches A2A Agent Cards from fleet nodes (#962)

- *(backend)* Add /api/infrastructure/hosts endpoint for chat HostSelector

- *(a2a)* Implement A2A protocol Phase 1 POC (#961)

- *(backend)* Proxy SSH/service ops through SLM API (#933)

- *(overseer)* Implement task cancellation + PTY exit code detection (#935)

- *(ansible)* Inventory + playbook for nginx proxy deploy (#957)

- *(ansible)* Nginx reverse proxy on .20 for stable port 8443 (#957)

- *(settings)* NTP sync config + full IANA timezone list for fleet nodes (#955)

- *(ansible)* Add redis_exporter to redis role for Prometheus scraping

- *(monitoring)* Add clear-all alerts endpoint + button (#946)

- *(skills)* Phase 8 - SLM Skills Manager UI (repos, approvals, drafts, governance) (#926)

- *(skills)* Phase 7 - extended skills API (repos, gaps, approvals, governance) (#TBD)

- *(skills)* Phase 6 - governance engine + skill promoter (#926)

- *(skills)* Phase 4 - skill gap detector (#926)

- *(skills)* Phase 3 - repo sync engine (local/git/MCP) (#TBD)

- *(skills)* Phase 2 - MCP subprocess manager

- *(skills)* Phase 1 - DB models for skill packages, repos, approvals

- *(monitoring)* Consolidate Prometheus metrics into autobot-shared (#937)

- *(roles)* Align role names with folder structure

- *(slm)* Node selector for agent LLM endpoint (#942)

- *(slm)* Auto-seed 29 AutoBot agents on startup (#939)

- *(media)* Implement real processing for all 5 media pipelines (#932)

- *(security)* Phase 7 - internal CA, cert expiry monitoring, runbooks (#926)

- *(ansible)* Issue #926 Phase 6 - node cleanup playbook

- *(merge)* Incorporate main branch additions into Dev_new_gui

- *(slm)* Issue #926 Phase 5 - per-role code sync refactor

- *(slm)* Phase 4 complete - playbooks + remaining role clean tasks (#926)

- *(slm)* Phase 4 - Ansible role clean tasks and defaults (#926)

- *(slm)* Phase 3 - manifest-driven role assignment and health (#926)

- *(infra)* Phase 2 - role manifests, schemas, and architecture docs (#926)

- Add AutoBot custom license

- *(arch)* Phase 1 — role-based repo restructuring (#926)

- *(slm-frontend)* Redesign migration tab to role-based workflow (#924)

- *(frontend)* Complete Issue #901 - unified design system (#901)

- *(code-sync)* Mark nodes as synced via Ansible after fleet update

- *(nl-database)* Integrate Vanna.ai for natural language database queries (#723)

- *(evolution)* Code Evolution Timeline Visualization (#247)

- *(code-intelligence)* Implement intelligent merge conflict resolution (#246)

- *(ansible)* Add fleet-wide code update playbook (#880)

- *(infra)* Add automated fleet-wide code sync script

- *(plugins)* Implement Plugin SDK for extensible tool architecture (#730)

- *(ansible)* Add SSH access safety playbook and guidelines (#909)

- *(completion)* Add advanced context analyzer for code completion (#907)

- *(design)* Migrate DevSpeedupView to design system (#908, #898)

- *(design)* Migrate EvolutionView to design system (#908, #243)

- *(design)* Migrate CodeIntelligenceView to design system (#908, #899)

- *(design)* Migrate LLM components to design system (#908, #897)

- *(design)* Migrate BrowserAutomationView to design system (#908, #900)

- *(completion)* Add learning loop feedback system (#905)

- *(a11y)* Complete ARIA labels and sortable columns (#901)

- *(ml)* Add ML training pipeline for code completion (#904)

- *(a11y)* Add ARIA labels and keyboard support (#901)

- *(frontend)* Update DataTable with Technical Precision design (#901)

- *(frontend)* Update KnowledgeEntries with Technical Precision design (#901)

- *(code-completion)* Add pattern extraction infrastructure (#903)

- *(frontend)* Update FindingsTable with Technical Precision design (#901)

- *(frontend)* Phase 4 - Update AuditLogTable with Technical Precision design (#901)

- *(frontend)* Phase 3 - Update main views with Technical Precision design (#901)

- *(frontend)* Add Component Showcase page (#901)

- *(frontend)* Phase 2 - Core component redesigns (#901)

- *(frontend)* Phase 2 - Code Evolution Dashboard (#243)

- *(frontend)* Technical Precision theme foundation (#901)

- *(code-intelligence)* Integrate code evolution mining with anti-pattern detection (#243)

- *(frontend)* Add Browser Automation Dashboard (#900)

- *(frontend)* Add Code Intelligence tools (#899)

- *(vnc)* Add session-tied desktop views (#74)

- *(frontend)* Add LLM configuration panel (#897)

- *(vnc)* Add human-like behavior to desktop automation (#74)

- *(vnc)* Area 4 - Advanced Session Management (#74)

- *(vnc)* Area 3 - Desktop Context Panel (#74)

- *(frontend)* Add visibility badges to Secrets Manager (#685)

- *(slm)* Add metrics dashboard components and extend composable (#896)

- *(frontend)* Add access level badges and filtering to Knowledge Search (#685)

- *(slm)* Add comprehensive metrics dashboard (#896)

- *(vnc)* Area 2 - Agent Desktop Actions (#74)

- *(frontend)* Add hierarchical access controls to secrets UI (#685)

- *(vnc)* Area 1 - Desktop Interaction Controls (#74)

- *(frontend)* Hierarchical access levels UI for knowledge (#685)

- *(api)* Hierarchical access levels API endpoints (#685)

- *(backend)* Hierarchical access levels foundation (#685)

- *(analytics)* Persist code review pattern preferences (#638)

- *(frontend)* Add browser automation task management components (#589)

- *(ansible)* Implement UFW reset for clean firewall rules (#895)

- *(media)* Organize media processing into dedicated pipelines (#735)

- *(ansible)* Add apply-firewall.yml playbook for flexible UFW deployment (#887)

- *(ansible)* Implement role-specific UFW firewall rules (least privilege) (#894)

- *(ansible)* Add UFW firewall configuration with infrastructure subnet support (#887)

- *(ansible)* Add UFW firewall configuration with infrastructure subnet support (#887)

- *(deps)* Add celery to requirements (#892)

- *(ansible)* Add TLS certificate generation for backend (#892)

- *(backend)* Add missing aiofiles dependency and fix .env deployment (#868)

- *(ansible)* Add backend crash-loop fix playbooks (#893)

- *(ansible)* Add backend crash-loop diagnostic playbook (#893)

- *(backend)* Add conda+pyenv for Python 3.12 with faiss-gpu support (#856)

- Enforce Infrastructure as Code for all config changes

- *(slm)* Add path validation to Code Source assignment (#865)

- Add /bugfix skill for autonomous test-driven debugging

- Add /parallel skill for safe multi-agent orchestration

- *(backend)* Install Python 3.12 for GPU package compatibility (#856)

- Add comprehensive post-edit linting hooks

- Add /deploy skill for remote deployment workflow

- *(orchestration)* Deprecate run_autobot.sh, migrate to SLM orchestration (#863)

- *(backend)* Activity tracking integration hooks (#873) (#884) ([#884](https://github.com/mrveiss/AutoBot-AI/pull/884))

- *(backend)* Session collaboration API (#872) (#883) ([#883](https://github.com/mrveiss/AutoBot-AI/pull/883))

- *(backend)* Activity entity types with user attribution (#871) (#882) ([#882](https://github.com/mrveiss/AutoBot-AI/pull/882))

- *(backend)* Implement User entity and Secrets ownership model (#870) (#877) ([#877](https://github.com/mrveiss/AutoBot-AI/pull/877))

- *(frontend)* Collaborative session UI components (#874) ([#878](https://github.com/mrveiss/AutoBot-AI/pull/878))

- *(migration)* Session and secret data migration scripts (#875) ([#879](https://github.com/mrveiss/AutoBot-AI/pull/879))

- *(ansible)* Add bash script for backend deadlock fix (#876)

- *(knowledge)* Add comprehensive multi-level access control system (#679)

- *(llm)* Add tiered routing API endpoints and documentation (#696)

- *(gateway)* Implement unified Gateway for multi-channel communication (#732)

- *(slm-frontend)* Add user feedback for Sync Selected and Sync All buttons

- *(slm-frontend)* Add user feedback for Pull from Source operation

- *(slm-frontend)* Standardize commit hash display to 12-character format (#866)

- Add Celery worker systemd service (#863)

- Add simple service management wrapper (#863)

- *(grafana)* Ensure consistent configuration across both roles

- *(ansible)* Complete access_control role (P4 - FINAL)

- *(ansible)* Complete dns role (P3)

- *(ansible)* Complete distributed_setup role (P2)

- *(ansible)* Complete agent_config role (P1)

- *(ansible)* Add centralized_logging role with native Loki/Promtail deployment (#855)

- *(grafana)* Add external host support with migration playbook and documentation

- *(slm)* Migrate TLS certificate deployment to Ansible

- *(slm)* Migrate service discovery to Ansible service_facts

- *(slm)* Migrate service management to Ansible playbooks

- *(nodes)* Add role provisioning endpoint for node role assignment

- *(fleet)* Migrate Fleet Overview reboot to Ansible playbooks

- *(updates)* Migrate Updates page to Ansible playbooks

- *(code-sync)* Migrate Code Sync page to Ansible playbooks

- *(infrastructure)* Add comprehensive playbook suite to Infrastructure page

- *(ansible)* Add role-based inventory groups

- *(ansible)* Create comprehensive node provisioning playbooks

- *(slm-frontend)* Redirect old routes to unified orchestration (#850)

- *(slm-frontend)* Consolidated 5-tab orchestration view (#850)

- *(slm-frontend)* Create unified orchestration composable (#850)

- *(slm-frontend)* Extract shared orchestration components (#850)

- *(slm-backend)* Consolidate fleet endpoints into orchestration (#850)

- *(knowledge)* ECL Pipeline with Knowledge Graph, Temporal Events & Summaries (#759)

- *(knowledge)* Implement user ownership model for chat-derived knowledge (#688) (#845) ([#845](https://github.com/mrveiss/AutoBot-AI/pull/845))

- *(terminal)* Implement tab completion with dropdown suggestions (#503)

- *(slm-frontend)* Accessibility audit and WCAG improvements (#754) (#844) ([#844](https://github.com/mrveiss/AutoBot-AI/pull/844))

- *(security)* Security Assessment Workflow - parsers, ChromaDB, chat integration (#260) (#843) ([#843](https://github.com/mrveiss/AutoBot-AI/pull/843))

- Implement Skills system for modular AI capabilities (#731)

- *(slm)* Add NPU worker dashboard improvements (#590)

- Add workflow guardrails and automation from insights report

- *(slm-frontend)* Add 4 missing frontend pages for orphaned backend APIs (#562)

- *(integrations)* Implement 7 external tool integration categories (#61)

- *(ansible)* Role-based auto-provisioning + fix seed 502 (#837)

- *(analysis)* Align env analyzer with shell script filtering (#632) ([#830](https://github.com/mrveiss/AutoBot-AI/pull/830))

- *(slm)* Comprehensive performance monitoring - tracing, SLOs, alert rules (#752)

- *(observability)* Implement OpenTelemetry distributed tracing (#697)

- *(auth)* Link chat sessions to user/org/team hierarchy (#684)

- *(security)* Service auth enforcement Ansible role + operational tooling (#255)

- *(auth)* Enable user authentication on user frontend (#827)

- *(slm)* Add fleet update summary to Fleet Overview (#682)

- *(user-frontend)* Add Vision & Multimodal AI navigation and routing (#777)

- *(slm)* Enable monitoring/postgresql deployment via GUI role assignment (#816)

- *(cors)* Dynamic CORS origins from all infrastructure machines (#815)

- *(infra)* Create slm_manager Ansible role for repeatable SLM deployment (#814)

- *(auth)* Implement Phase 5 2FA/MFA and API Key management (#576)

- *(llm)* Add provider switching API endpoints and fallback config (#536)

- *(sso)* Add frontend SSO composable and callback view (#576)

- *(sso)* Implement Phase 4 SSO backend for AutoBot SLM platform (#576)

- *(infra)* Add infrastructure ansible group vars (#786)

- *(llm)* Add runtime provider switching and config (#536)

- *(slm-frontend)* Add user management settings UI (#576)

- *(files)* Enhance chat files tab to full-featured session file manager (#70)

- *(slm)* Add user management system with RBAC (#576)

- *(ansible)* Add SLM, Node-26, Node-27 to production inventory and deploy netcat (#703)

- *(ansible)* Install netcat-openbsd on all VMs for network diagnostics (#703) (#794) ([#794](https://github.com/mrveiss/AutoBot-AI/pull/794))

- *(infra)* Add iftop, mc, nano to base packages (#789)

- *(infra)* Add netcat and network diagnostics to base packages (#703, #789)

- *(infra)* Add per-role infrastructure templates for all components (#789)

- Implement SLM bootstrap script (Phase A) (#789)

- *(structure)* Populate autobot-shared with common utilities (#781)

- *(slm)* Migrate database from SQLite to PostgreSQL (#786)

- *(slm)* Add Infrastructure Wizard GUI for playbook execution (#786)

- *(slm)* Add Ansible playbooks for PostgreSQL user management databases (#786)

- *(slm-admin)* Use shared PasswordChangeForm component (#635)

- *(autobot-vue)* Add ProfileModal with password change (#635)

- *(frontend)* Create PasswordChangeForm shared component (#635)

- *(api)* Add rate limiting to password change endpoint (#635)

- *(user)* Integrate session invalidation on password change (#635)

- *(rate-limit)* Record password change attempts (#635)

- *(session)* Invalidate user sessions except current (#635)

- *(session)* Add is_token_blacklisted method (#635)

- *(session)* Add token to Redis blacklist (#635)

- *(npu)* Add pool management API endpoints (#168)

- *(npu)* Add get_npu_pool() singleton function (#168)

- *(npu)* Add task execution with retry and failover (#168)

- *(npu)* Add background health monitor (#168)

- *(npu)* Add circuit breaker logic (#168)

- *(npu)* Add health check method for workers (#168)

- *(npu)* Add worker selection algorithm (#168)

- *(npu)* Add NPUWorkerPool class initialization (#168)

- *(npu)* Add load_worker_config for YAML parsing (#168)

- *(analytics)* Real-time auto-refresh for bug prediction trends (#637) ([#784](https://github.com/mrveiss/AutoBot-AI/pull/784))

- *(npu)* Add CircuitState enum and WorkerState dataclass (#168)

- *(frontend)* Add preferences UI with full accessibility support (#753)

- *(frontend)* Achieve 10/10 code quality score for design system (#753)

- *(hooks)* Add function length enforcement pre-commit hook (#620)

- *(frontend)* Add DarkModeToggle component and design system docs (#753)

- *(frontend)* Implement unified design system with teal/emerald theme (#753)

- *(analytics)* Integrate Code Intelligence into Codebase Analytics (#566)

- *(ui)* Add role targeting to schedule modal (#779)

- *(ui)* Add code source assignment UI (#779)

- *(frontend)* Add tabbed interface and file scan to CodeIntelligenceDashboard (#566)

- *(memory)* Add backward compat methods to EnhancedMemoryManager (#742)

- *(frontend)* Add FileScanModal for single file scanning (#566)

- *(frontend)* Add Security, Performance, and Redis findings panels (#566)

- *(frontend)* Add FindingsTable component with hybrid table/card display (#566)

- *(ui)* Wire RoleManagementModal into NodesView (#779)

- *(ui)* Add role-based sync section to CodeSyncView (#779)

- *(slm-admin)* Add Error Monitoring API methods to useSlmApi (#563)

- *(slm)* Add error resolution fields to NodeEvent model (#563)

- *(slm-admin)* Integrate Error Monitoring Dashboard with API (#563)

- *(slm)* Register error monitoring API and deprecate duplicate (#563)

- *(search)* Implement NPU-accelerated semantic code search (#207)

- *(slm-server)* Add manual service scan endpoint for nodes

- *(npu)* Add backend NPU API endpoints (#255)

- *(npu)* Add authenticated service client support (#255)

- *(slm-admin)* Add NPU Workers tab to Fleet Overview (#255)

- *(npu-worker)* Add HMAC-SHA256 service authentication (#255)

- *(#749)* Add terminal settings component

- *(#749)* Add history navigation and persistence to frontend

- *(#749)* Add tab completion support to frontend terminal

- *(#749)* Add WebSocket handlers for tab completion and history

- *(#749)* Add terminal history service with Redis storage

- *(#749)* Add terminal completion service with compgen

- *(cache)* Complete CacheProtocol implementation for all caches (#743)

- *(#779)* Add frontend role management components

- *(#779)* Add sync orchestrator service and role-based sync endpoints

- *(#779)* Add node role management endpoints

- *(#779)* Update heartbeat to process role report

- *(#779)* Add role report schemas to heartbeat request

- *(#779)* Enhance agent heartbeat with role detection

- *(#779)* Add role detector module

- *(#779)* Add port scanner module for role detection

- *(#779)* Register code-source router

- *(#779)* Add code-source API for git notifications

- *(#779)* Register roles router and seed defaults on startup

- *(#779)* Add roles API endpoints

- *(#779)* Add role registry service with defaults

- *(#779)* Extend Node model with role tracking fields

- *(#779)* Add CodeSource model for git-connected nodes

- *(#779)* Add NodeRole model for assignment tracking

- *(#779)* Add Role model for code distribution

- *(config)* Add port.* keys to registry_defaults (#751)

- *(config)* Add registry_defaults for hardcoded fallbacks (#751)

- *(config)* Add get_section, set, refresh to ConfigRegistry (#751)

- *(config)* Add ConfigRegistry core with basic get (#751)

- *(#778)* Connect workflow templates UI to backend API

- Add workflow templates composable and tool interpreter prompt

- *(#772)* Implement Code Intelligence frontend dashboard

- *(tls)* Add TLS/HTTPS enablement GUI and API (#768)

- *(auth)* Add RBAC permission decorator system - Phase 6 (#744)

- *(auth)* Apply authentication to API endpoints - Phase 5 (#744)

- *(auth)* Add RBAC auth to 6 API files (batch 6) (#744)

- *(auth)* Add RBAC auth to 6 API files (batch 5) (#744)

- *(auth)* Add RBAC auth to 6 API files (batch 4) (#744)

- *(auth)* Add RBAC auth to 6 API files (batch 3) (#744)

- *(api)* Add RBAC authentication to NPU worker endpoints (#744)

- *(provider-health)* Add unified health endpoint and new providers (#746)

- *(slm-admin)* Add Agent Configuration UI (#760)

- *(frontend)* Add useServiceDiscovery Vue composable (#760)

- *(frontend)* Add discoverService() to SSOT config (#760)

- *(agent-config)* Use SLM client with local fallback (#760)

- *(slm)* Add agent seed migration script (#760)

- *(slm-client)* Add discover_service() with fallback chain (#760)

- *(slm-client)* Add ServiceDiscoveryCache class (#760)

- *(security)* Consolidate command patterns into centralized registry (#765) (#766) ([#766](https://github.com/mrveiss/AutoBot-AI/pull/766))

- *(slm)* Unify data models with shared constants (#737)

- *(slm)* Consolidate fleet tools with shared composables (#737)

- *(backend)* Integrate SLM client with startup (#760)

- *(backend)* Add SLM client for agent config (#760)

- *(slm)* Register agents router (#760)

- *(slm)* Add agents API router (#760)

- *(slm)* Add agents table migration (#760)

- *(slm)* Add Agent Pydantic schemas (#760)

- *(slm)* Add Agent model for LLM configuration (#760)

- *(slm)* Add conflicts endpoints and register routers (#760)

- *(quick-wins)* Implement 5 low-effort high-impact improvements (#756)

- *(slm)* Add discovery and config API endpoints (#760)

- *(slm)* Add migration for service discovery tables (#760)

- *(slm)* Add schemas for discovery, config, and conflicts (#760)

- *(slm)* Add service discovery models (#760)

- *(slm)* Implement scheduled code sync with cron support (#741)

- *(knowledge)* Add store state for system docs, prompts, and modals (#747)

- *(knowledge)* Complete Knowledge Manager frontend (#747)

- *(slm)* Add update notification and fix code sync (#741)

- *(slm)* Implement actual rsync-based code sync (#741)

- *(slm)* Implement fleet sync job queue (#741)

- *(slm)* Add direct server notification fallback to post-commit hook (#741)

- *(slm)* Implement code version notification system (#741)

- *(ansible)* Add code-source role for dev machine (#741)

- *(ansible)* Add emergency admin user automation (#741)

- *(ansible)* Embed version at agent deploy time (#741)

- *(slm-admin)* Add code sync badge to navigation (#741)

- *(slm-admin)* Add CodeSyncView page (#741)

- *(slm-admin)* Add useCodeSync composable (#741)

- *(api)* Add cache stats endpoint (#743)

- *(slm-agent)* Add code version to heartbeat (#741)

- *(slm-agent)* Add version module for code tracking (#741)

- *(slm)* Add node sync endpoint and code distributor (#741)

- *(llm)* Add CacheProtocol support (#743)

- *(knowledge)* Add CacheProtocol support (#743)

- *(memory)* Add CacheProtocol support (#743)

- *(slm)* Add code sync API endpoints (#741)

- *(slm)* Add background version check task (#741)

- *(cache)* Implement CacheCoordinator (#743)

- *(cache)* Add CacheProtocol interface (#743)

- *(redis)* Optimize connection pooling for memory efficiency (#743)

- *(slm)* Add GitTracker service for version monitoring (#741)

- *(slm)* Store code_version in heartbeat, return update info (#741)

- *(slm)* Extend heartbeat schemas for code version (#741)

- *(slm)* Add code_version migration script (#741)

- *(hooks)* Add hardcoded value detection pre-commit hook (#694)

- *(security)* Add TLS support to all services - Phase 5 (#725)

- *(scripts)* Add SLM VM to sync script (#729)

- *(ansible)* Add Phase 4 mTLS automation playbooks (#725)

- *(slm)* Implement SLM backend features - encryption, WebSocket, TLS workflows (#736)

- *(frontend)* Add TLS certificate management UI (#725)

- *(slm)* Add TLS certificate management via SLM API (#725)

- *(security)* Add mTLS infrastructure support (#725)

- *(slm)* Add VNC as flexible role with encrypted credentials (#725)

- *(slm-admin)* Add categorized role selection with dependencies (#726)

- *(slm-admin)* Add standard deployment wizard to DeploymentsView (#726)

- *(slm)* Add restart all services functionality (#725)

- *(slm-admin)* Add Replication UI and Blue-Green navigation (#726)

- *(slm)* Add Redis replication orchestration with Ansible (#726)

- *(slm)* Add automatic rollback with post-deployment health monitoring (#726)

- *(slm-admin)* Enhance WebSocket integration for real-time updates (#726)

- *(security)* Complete mTLS migration Phase 6 (#725)

- *(security)* Add Redis admin user for emergency recovery (#725)

- *(slm)* Add Ansible roles and enhanced backup service (#726)

- *(scripts)* Add SSOT config helper library for shell scripts (#694)

- *(config)* Add vm_definitions property to SSOT config (#694)

- *(security)* Add comprehensive mTLS verification and cutover (#725)

- *(security)* Add mTLS support to Celery and NPU worker (#725)

- *(slm)* Add dedicated Blue-Green deployments view (#726)

- *(security)* Add mTLS migration tooling and backend TLS support (#725)

- *(slm)* Complete stateful services and blue-green deployment UI (#726)

- *(slm)* Add service-level auto-restart remediation (#726)

- *(slm)* Add Fleet Tools tab to FleetOverview (#729)

- *(slm)* Migrate admin functionality to SLM (#729)

- *(slm)* Add service discovery to SLM agent (#728)

- *(slm)* Restructure ServicesView to group services by host (#728)

- *(slm)* Add tools field to roles with specific tools per role (#728)

- *(slm)* Add infrastructure for admin migration (#729)

- *(slm)* Add ai-stack role for AI tools nodes (#728)

- *(slm)* Integrate monitoring and tools into SLM admin (#729)

- *(slm)* Add LLM provider role to node roles (#728)

- *(slm)* Add service categorization with AutoBot/System filtering (#728)

- *(slm)* Enhance Deployments and Maintenance views (#728)

- *(slm)* Add fleet-wide restart and WebSocket broadcasts (#728)

- *(slm)* Add WebSocket real-time service status updates (#728)

- *(slm)* Add fleet-wide Services view and navigation (#728)

- *(slm)* Add full service lifecycle GUI integration (#728)

- *(slm)* Add service lifecycle management and auto-remediation (#728)

- *(slm)* Improve credential handling for GUI-added nodes (#722)

- *(slm)* Implement seamless node enrollment with agent deployment (#726)

- *(slm)* Add missing backend API endpoints for SLM Admin UI (#726)

- *(monitoring)* Expand service health status mappings (#726)

- Integrate consolidated terminal API and system improvements

- Integrate async database operations into agent systems

- Add system monitoring and deployment scripts

- Add comprehensive utility modules

- Add middleware and service layers

- Add advanced system modules

- Add URL validation service

- Add advanced backend API endpoints

- Add Vue components for phase progression and validation

- Add GitHub Actions workflow for phase validation

- Add Docker containerization support

- Enhance testing and debugging utilities

- Update main application and core processors

- Enhance utility modules and Redis integration

- Update core memory and knowledge systems

- Enhance computer vision and hardware acceleration

- Update Vue frontend configuration

- Implement memory optimization improvements

- Enhance backend services with improved configuration

- Enhance agents with communication protocol integration

- Implement async database operations with connection pooling

- Implement agent communication protocol

- Convert LLM interfaces to async HTTP operations

- Enhance phase validation system with comprehensive acceptance criteria

- Implement comprehensive microservice architecture evaluation

- Implement comprehensive memory usage optimization

- Implement comprehensive CI/CD security integration

- Implement comprehensive performance and security optimizations

- Implement comprehensive code optimization and API fixes

- Add optimization roadmap and monitoring dashboard

- Implement comprehensive codebase profiling and automated testing framework

- Add comprehensive backend performance profiling and analysis

- Enhance core system components with Phase D integration

- Enhance backend infrastructure and integration

- Implement enhanced Docker sandbox security features

- Implement enhanced multi-agent orchestration system

- Implement NPU-accelerated code search with Redis indexing

- Implement LLM failsafe system with 4-tier fallback

- Enhance file upload functionality for automated testing

- Add development utilities and diagnostic tools

- Update platform documentation and frontend enhancements

- Add executive summary and strategic positioning documents

- Complete reports review and infrastructure cleanup

- Intel NPU driver integration for AutoBot hardware acceleration

- Implement comprehensive project organization and file structure cleanup

- Migrate orchestrator core component to new error handling

- Migrate critical chat API endpoints to new error handling

- Implement comprehensive error handling improvements

- Implement data-at-rest encryption service (CRITICAL security fix)

- Implement quick wins from code analysis report

- *(commands)* Enhance command detection and manual system

- *(npu)* Add NPU worker client for offloading heavy computations

- *(frontend)* Implement Playwright VNC viewer and fix API endpoints

- *(playwright)* Add VNC-enabled Playwright container with visual browser automation

- *(backend)* Add Playwright health check endpoint and fix API initialization

- Add Playwright container with VNC and noVNC support

- Add comprehensive setup repair system and unified CLI

- Improve container startup process and fix Playwright mount issues

- Optimize backend performance and add NPU worker integration

- Implement comprehensive command manual knowledge base system

- Integrate CommandPermissionDialog into ChatInterface

- Add CommandPermissionDialog component with Allow/Deny/Comment options

- Implement comprehensive testing framework with CI/CD pipeline

- Add code analysis suite with automated fix agents

- Implement full PTY terminal with complete sudo support

- Enhance setup_agent.sh with comprehensive GUI testing dependencies

- Comprehensive GUI testing and validation suite

- Comprehensive terminal debugging and simplified WebSocket solution

- Add terminal debugging utility and fix WorkflowApproval 404

- Preserve complete development history with debugging artifacts

- Finalize infrastructure and development environment setup

- Comprehensive core system enhancements and optimizations

- Enhance backend API system with comprehensive improvements

- Enhance frontend UI components and services integration

- Add development artifacts and debugging infrastructure

- Add comprehensive end-to-end testing and validation suite

- Implement workflow scheduler and enhanced classification agent

- Add remaining metrics and scheduler API integration

- Add comprehensive testing suite and development artifacts

- Implement advanced security agents with dynamic tool discovery

- Implement comprehensive workflow templates system

- Enhanced workflow orchestration with metrics integration

- Implement Redis-based workflow classification system

- Workflow analysis and UI enhancement tools

- NPU worker system and advanced monitoring

- Add workflow notifications system

- Enhance chat API with workflow orchestration integration

- Add comprehensive workflow API service layer

- Integrate comprehensive workflow UI components

- Implement comprehensive multi-agent workflow orchestration

- Optimize hardware acceleration and fix frontend issues

- Add comprehensive test automation suite with Playwright integration

- Enhance backend APIs with multi-agent and hardware acceleration support

- Modernize frontend build system and routing infrastructure

- Enhance frontend UI components with modern design and functionality

- Add comprehensive test infrastructure and reporting

- Integrate multi-agent architecture with core system components

- Add comprehensive multi-agent architecture documentation and core agents

- Configure system to use uncensored models for unrestricted capabilities

- Enhance installation system for multi-agent architecture

- Complete multi-agent architecture with Knowledge Retrieval and Research agents

- Enhance configuration system with hardware acceleration integration

- Implement hardware acceleration with NPU > GPU > CPU priority

- Major frontend redesign and backend improvements

- Add knowledge base population and fix scripts

- Implement Vue Notus Tailwind CSS professional redesign

- Implement executive GUI redesign with professional styling

- Add Containerized Librarian Assistant Agent with web research capabilities

- Implement comprehensive multi-agent architecture with Tier 2 web research

- Automate config defaults fix in setup script

- Add containerized librarian assistant agent with comprehensive web research

- Add KB Librarian Agent for automatic knowledge base search

- Complete intelligent agent system implementation

- Comprehensive environment variable system to eliminate hardcoding

- Add intelligent agent system modules

- Implement secrets management hardening + default model update

- Resolve major technical debt issues

- Implement Prompt Intelligence Synchronization System - Transform agent to expert system

- *(slm)* Add monitoring dashboard and infrastructure views (#726)

- *(slm)* Add deployment UI, WebSocket API, and backend enhancements (#726)

- *(slm)* Add deployment UI components, WebSocket API, and migrations (#726)

- *(slm-admin)* Fetch roles dynamically from backend API

- *(slm-admin)* Sync roles with SLM backend definitions

- *(slm-admin)* Integrate full node management into FleetOverview

- *(slm-admin)* Add full node management functionality

- *(slm)* Implement standalone SLM backend with authentication (#726)

- *(slm)* Implement Phase 5 - Admin UI application (#726)

- *(slm)* Implement Phase 4 - Stateful Services (#726)

- *(slm)* Implement Phase 3 - Deployment Orchestration (#726)

- *(slm)* Implement Phase 2 - Health & Reconciliation (#726)

- *(slm)* Initialize default roles on database creation (#726)

- *(slm)* Add REST API for nodes and heartbeats (#726)

- *(slm)* Add Ansible role for agent deployment (#726)

- *(slm)* Add lightweight node agent with health collector (#726)

- *(slm)* Add SLM database service with CRUD operations (#726)

- *(slm)* Implement state machine for node lifecycle (#726)

- *(slm)* Add SLM database models and enums (#726)

- *(infrastructure)* Node Management UI with oVirt-style Host Enrollment (#695)

- *(security)* Migrate Ansible credentials to vault and SSH key auth (#700)

- *(infrastructure)* Add node enrollment Ansible playbook (#695)

- *(infrastructure)* Add Node Management UI with oVirt-style enrollment (#695)

- *(frontend)* Add Entity Extraction & Graph RAG Manager GUI (#586)

- *(frontend)* Add Batch Processing Manager GUI (#584)

- *(frontend)* Add Workflow Automation Builder GUI (#585)

- *(frontend)* Add Vision & Multimodal Interface GUI (#582)

- *(frontend)* Add System Validation Dashboard GUI (#581)

- *(frontend)* Add Audit Logging Dashboard GUI (#578)

- *(frontend)* Add Error Monitoring Dashboard GUI (#579)

- *(frontend)* Add Feature Flags Manager GUI (#580)

- *(backend)* Add dedicated thread pools for log and file I/O (#718)

- *(infrastructure)* Add dynamic SSH/VNC host management via secrets (#715)

- *(llm-optimization)* Implement efficient inference design (#717)

- *(security)* Add modular security package and comprehensive tests (#712)

- *(codebase-analytics)* Improve call graph resolution with import context (#713)

- *(tracing)* Enhanced distributed tracing with auto-instrumentation (#697)

- *(frontend)* Migrate 20 components to CSS design tokens - Sprints 37-41 (#704)

- *(frontend)* Migrate 4 components to CSS design tokens - Sprint 36 (#704)

- *(frontend)* Migrate 3 components to CSS design tokens - Sprint 35 (#704)

- *(frontend)* Migrate 4 components to CSS design tokens - Sprint 34 (#704)

- *(frontend)* Migrate 4 components to CSS design tokens - Sprint 33 (#704)

- *(frontend)* Migrate 4 components to CSS design tokens - Sprint 32 (#704)

- *(frontend)* Migrate 4 components to CSS design tokens - Sprint 31 (#704)

- *(frontend)* Migrate 3 components to CSS design tokens - Sprint 30 (#704)

- *(frontend)* Migrate 4 chat components to CSS design tokens - Sprint 29 (#704)

- *(frontend)* Migrate 4 UI components to CSS design tokens - Sprint 28 (#704)

- *(frontend)* Migrate 4 components to CSS design tokens - Sprint 27 (#704)

- *(frontend)* Migrate 4 components to CSS design tokens - Sprint 26 (#704)

- *(frontend)* Migrate 4 components to CSS design tokens - Sprint 25 (#704)

- *(frontend)* Migrate 4 components to CSS design tokens - Sprint 24 (#704)

- *(frontend)* Migrate 4 components to CSS design tokens - Sprint 23 (#704)

- *(frontend)* Migrate 1 component to CSS design tokens - Sprint 22 (#704)

- *(frontend)* Migrate 3 knowledge components to CSS design tokens - Sprint 21 (#704)

- *(frontend)* Migrate 4 components to CSS design tokens - Sprint 20 (#704)

- *(frontend)* Migrate 5 components to CSS design tokens - Sprint 19 (#704)

- *(frontend)* Migrate 11 components to CSS design tokens - Sprint 18 (#704)

- *(frontend)* Migrate 4 components to CSS design tokens - Sprint 17 (#704)

- *(frontend)* Migrate 3 chart components to CSS design tokens - Sprint 16 (#704)

- *(frontend)* Migrate 4 components to CSS design tokens - Sprint 15 (#704)

- *(frontend)* Migrate 2 components to CSS design tokens - Sprint 14 (#704)

- *(frontend)* Migrate 3 components to CSS design tokens - Sprint 13 (#704)

- *(frontend)* Migrate 5 components to CSS design tokens - Sprint 11 (#704)

- *(frontend)* Migrate 5 components to design tokens - Sprint 10 (#704)

- *(frontend)* Migrate 5 settings components to design tokens - Sprint 9 (#704)

- *(frontend)* Migrate 8 components to design tokens - Sprint 8 (#704)

- *(frontend)* Migrate 8 components to design tokens (#704)

- *(frontend)* Migrate 8 components to design tokens (#704)

- *(frontend)* Migrate 6 medium-impact components to design tokens (#704)

- *(frontend)* Migrate 5 analytics dashboards to design tokens (#704)

- *(frontend)* Migrate 3 high-impact components to design tokens (#704)

- *(frontend)* Migrate 8 high-impact components to design tokens (#704)

- *(knowledge)* Add unified graph endpoint for Cytoscape.js visualization (#707)

- *(frontend)* CSS Design System with centralized theming (#704)

- *(charts)* Add Cytoscape.js network views with fullscreen and detail panels (#707)

- *(log-forwarding)* Complete Phase 4 - Documentation, dashboard, auto-start (#553)

- *(log-forwarding)* Add GUI-controlled log forwarding to external systems (#553)

- *(constants)* Add QueryDefaults, CategoryDefaults, ProtocolDefaults (#694)

- *(config)* Add TLS configuration support to SSOT config (#164)

- *(pki)* Add oVirt-style automated certificate management (#164)

- *(settings)* Add Data Storage subtab and Overseer agent configs (#690)

- *(permissions)* Implement Claude Code-style Permission System v2 (#693)

- *(operations)* Add Long-Running Operations Tracker dashboard (#591)

- *(analytics)* Implement bug prediction trend tracking (#569)

- *(overseer)* Add PTY integration and command safety validation (#690)

- *(chat)* Add Overseer Agent UI integration (#690)

- *(agents)* Add Overseer Agent for task decomposition and execution

- *(settings)* Add Data Storage management panel

- *(settings)* Add settings subroutes and Infrastructure tab (#687, #544)

- *(chat)* Add distinct styling for message types and fix disappearing messages

- *(analytics)* Add LLM-based intelligent hardcoded value filtering (#633)

- *(security)* Add system package (apt) rolling updates (#682)

- *(codebase)* Integrate NPU worker for accelerated embeddings (#681)

- *(security)* Ansible rolling update system for CVE remediation (#544, #682)

- *(docs)* Add git hook for automatic documentation sync (#250)

- *(docs)* Add real-time documentation sync service (#165)

- *(docs)* Add Documentation Browser API and Chat UI components (#165)

- *(knowledge)* Integrate Windows NPU worker for embedding generation (#165)

- *(knowledge)* Fix embedding generation and add vectorization script (#165)

- *(session)* Add migration script and activity timeline UI (#608)

- *(collaboration)* Implement real-time multi-user collaboration (#608)

- *(activity)* Implement session activity tracking (#608)

- *(api)* Hook session creation to memory graph (#608)

- *(memory-graph)* Add user-centric session tracking foundation (#608)

- *(multimodal)* Add model availability status to stats endpoint (#675)

- *(analytics)* Include cross-language analysis in full scan workflow

- *(extensions)* Add extension hooks system with 22 lifecycle points (#658)

- *(agents)* Add subordinate agent delegation pattern (#657)

- *(streaming)* Implement LogItem incremental update pattern (#656)

- *(errors)* Add RepairableException for soft error recovery (#655)

- *(chat)* Implement explicit response tool with break_loop pattern (#654)

- *(config)* Add explicit LLM configuration for all agents (#652)

- *(config)* Add explicit LlamaIndex configuration settings (#649)

- *(config)* Add agent-specific LLM config module-level functions (#599)

- *(config)* Add per-agent LLM configuration support (#599)

- *(config)* Add multi-provider LLM support to SSOT config (#599)

- *(config)* Add SSOT config validation and enforcement (#642)

- *(mcp)* Add true MCP server for knowledge base (#645)

- *(agents)* Implement Phase 4 - Agent Loop, Think Tool, Message Semantics (#645)

- *(agents)* Implement Phase 3 - Event Stream, Planner, Parallel Executor (#645)

- *(npu-worker)* Add runtime log level control for crash debugging (#644)

- *(npu-worker)* Show exact device model names in GUI (#640)

- *(npu-worker)* Add onnxscript for model export (#640)

- *(npu-worker)* Add einops dependency and GUI launch scripts (#640)

- *(npu-worker)* Add PyTorch and sentence-transformers for model export (#640)

- *(auth)* Implement password change functionality (#504)

- *(analytics)* Add Code Ownership and Expertise Map (#248)

- *(scripts)* Add sync-all-vms.sh for centralized VM code sync

- *(code-intelligence)* Add Vector/Redis/LLM infrastructure stubs (#554)

- *(secrets)* Complete Secrets Management System - Issue #211

- *(npu)* Implement NPU Worker integration with re-pairing support (#640)

- *(analytics)* Complete GUI integration for semantic analysis (#554)

- *(frontend)* Migrate to SSOT configuration system (#603)

- *(frontend)* Add enhanced Bug Risk Prediction UI styles (#629)

- *(analytics)* Add export buttons to Code Problems and Statistics sections (#609)

- *(analytics)* Add per-section export functionality (MD/JSON) (#609)

- *(code-intelligence)* Integrate shared AST cache into 4 more analyzers (#607)

- *(security)* Integrate shared AST cache into SecurityAnalyzer (#607)

- *(code-intelligence)* Add shared FileListCache and ASTCache (#607)

- *(config)* Implement SSOT Phase 2 backend migration (#602)

- *(config)* Implement SSOT configuration loaders (#601)

- *(analytics)* Achieve 100/100 Security and Performance scores (#554)

- *(ui)* Add invocation info and source file to AgentRegistry cards

- *(code-intelligence)* Enhance analytics infrastructure with shared utilities (#554)

- *(code-intelligence)* Add vector infrastructure to performance and security analyzers (#554)

- *(code-intelligence)* Add analytics infrastructure to performance analyzer (#554)

- *(ui)* Redesign SecretsManager with n8n-style interface

- *(database)* Add Alembic migrations for user management (#576)

- *(code-intelligence)* Export async analyzer and infrastructure flag (#554)

- *(code-intelligence)* Enhance anti-pattern detection and add analytics infrastructure

- *(knowledge)* Add knowledge maintenance components

- *(agents)* Enhance agent registry with invocation details and source files

- *(user-management)* Implement user management system with single_user mode fix (#576)

- *(tools)* Add Agent Registry page to Developer Tools (#575)

- *(api)* Consolidate knowledge base search endpoints (#555)

- *(frontend)* Integrate ErrorHandler with notification system (#502)

- *(frontend)* Add Redis optimization panel to code intelligence

- *(frontend)* Add Code Intelligence view with health and security panels

- *(monitoring)* Add VM infrastructure health monitoring (#432)

- *(rag)* Add category-based filtering to Chat RAG retrieval (#556)

- *(agents)* Add MCP tool YAML/JSON externalization guidance (#568)

- *(agents)* Add function decomposition rules to code-reviewer (#568)

- *(browser)* Add ChatBrowser component with session management (#73)

- *(security)* Add threat intelligence frontend module (#67)

- *(api)* Separate Tools Terminal and Chat Terminal API methods (#73, #552)

- *(code-intelligence)* Integrate PatternAnalysis into report export (#208)

- *(frontend)* Add full frontend integration for Code Pattern Analysis (#208)

- *(security)* Complete threat intelligence API integrations (#67)

- *(code-intelligence)* Implement Code Pattern Detection System (#208)

- *(memory)* Add orphaned memory entity cleanup for Knowledge Graph (#547)

- *(knowledge)* Add session orphan cleanup UI and backend (#547)

- *(code-intelligence)* Implement cross-language pattern detector (#244)

- *(frontend)* Implement consistent theming system with CSS variables (#548)

- *(frontend)* Add KB facts preview and preservation in delete dialog (#547)

- *(llm)* Restore valuable features from archived LLM interfaces (#551)

- *(knowledge)* Add vectorization status refresh button (#162)

- *(analytics)* Enhance API endpoint scanner with router prefix resolution (#527)

- *(nav)* Add BI Analytics menu item to navigation (#59)

- *(analytics)* Integrate code analysis tools into GUI Analyze All workflow (#538)

- *(config)* Add environment variable priority for host/port resolution

- *(codebase-analytics)* Add duplicate code detection (#528)

- *(infrastructure)* Add retry logic to playwright-server.js (#434)

- *(analytics)* Add bug prediction data to code indexing report (#505)

- *(data)* Externalize MCP tools and knowledge data to YAML files (#515)

- *(templates)* Extract monitoring dashboard CSS to template file (#515)

- *(templates)* Extract dashboard CSS to external template files (#515)

- *(knowledge)* Enhance category filtering UI with transitions (#161)

- *(knowledge)* Add enhanced metadata system with templates and versioning (#414)

- *(knowledge)* Add ML-based tag and category suggestions (#413)

- *(knowledge)* Add collections/folders for grouping documents (#412)

- *(knowledge)* Add hierarchical category tree structure (#411)

- *(knowledge)* Add tag styling with colors and visual customization (#410)

- *(knowledge)* Issue #79 - Bulk operations and data management

- *(knowledge)* Add tag management CRUD operations (#409)

- *(knowledge)* Implement real Linux man pages knowledge base (#153)

- *(indexer)* Add new documentation paths and fix logging (#250)

- *(models)* Add extracted model classes for better organization (#392)

- *(search)* Add search quality improvements (#78)

- *(workflow)* Add multi-step task plan approval system (#390)

- *(analytics)* Count comments separately from code lines (#368)

- *(search)* GPU-accelerated vector search with FAISS-GPU + ChromaDB hybrid (#387)

- *(code-intelligence)* Add TypeScript, Vue, and Shell analyzers (#386)

- *(code-intelligence)* Add multi-language analyzer base framework (#386)

- *(performance-analyzer)* Context-aware blocking I/O detection (#385)

- *(#351, #352)* Add LLM thoughts display and multi-step task continuation

- *(http-client)* Add dynamic connection pool sizing (#65)

- *(mcp)* Add standalone Prometheus MCP server (#80)

- *(monitoring)* Add API health and multi-machine Grafana dashboards (#80)

- *(frontend)* Use GrafanaSystemMonitor for system monitoring view (#80)

- *(monitoring)* Add Prometheus MCP bridge and Grafana system monitor (#80)

- *(monitoring)* Complete Epic #80 - Prometheus + Grafana stack (#80)

- *(code-intelligence)* Implement Automated Documentation Generator (#241)

- *(code-intelligence)* Implement Test-Driven Pattern Discovery (#236)

- *(monitoring)* Phase 5 Cleanup & Deprecation (#348)

- *(monitoring)* Add Phase 4 Grafana Integration (#347)

- *(monitoring)* Add AlertManager webhook and test scripts (#346)

- *(monitoring)* Implement Phase 2 Consumer Migration (#345)

- *(monitoring)* Implement Phase 1 Prometheus Foundation (#344)

- *(#57)* Complete OpenTelemetry distributed tracing setup

- *(hooks)* Add pre-commit hook for logging standards enforcement (#309)

- *(analytics)* Integrate code intelligence analyzers (#268, #269, #270, #272)

- *(tracing)* Integrate distributed tracing in app factory (#57)

- *(tracing)* Add OpenTelemetry distributed tracing infrastructure (#57)

- *(code-intelligence)* Add LLM pattern analyzer for cost optimization (#229)

- *(code-intelligence)* Add LLM-powered code generation and auto-refactoring (#228)

- *(code-intelligence)* Add conversation flow analyzer engine (#227)

- *(code-intelligence)* Add dynamic log pattern mining engine (#226)

- *(analytics)* Add category filter tabs to Analytics Dashboard (#274)

- *(analytics)* Add unified analytics report endpoint (#271)

- *(code-intelligence)* Add code review engine module

- *(analytics)* Add function call graph visualization (#267)

- *(analytics)* Add bidirectional import tree visualization API

- *(code-intelligence)* Update bug predictor module (#224)

- *(charts)* Add ImportTreeChart component for dependency visualization

- *(ui)* Improve BasePanel and SystemMonitor components

- *(analytics)* Enhance CodebaseAnalytics with race condition detection

- *(routers)* Register all new analytics API routers

- *(ui)* Add toast notification system and chart components

- *(knowledge)* Add unified knowledge API with graph relations (#250)

- *(analytics)* Add Performance Pattern Analyzer API and Dashboard (#222)

- *(analytics)* Add Code Evolution Timeline (#247)

- *(analytics)* Add Technical Debt Calculator (#231)

- *(analytics)* Add Real-time Code Quality Dashboard (#230)

- *(analytics)* Add LLM Integration Pattern Analyzer (#229)

- *(analytics)* Add LLM-Powered Code Generation API (#228)

- *(analytics)* Add Conversation Flow Analyzer (#227)

- *(analytics)* Add Dynamic Pattern Mining from Logs (#226)

- *(analytics)* Add AI-Powered Code Review Automation (#225)

- *(analytics)* Add Bug Prediction System API and Dashboard (#224)

- *(analytics)* Add Git Pre-commit Hook Analyzer API and Dashboard (#223)

- *(code-intelligence)* Add Git Pre-commit Hook Analyzer (#223)

- *(code-intelligence)* Add Performance Pattern Analyzer (#222)

- *(code-intelligence)* Add Security Pattern Analyzer (#219)

- *(code-intelligence)* Add Redis Optimizer and Anti-Pattern Detector (#220, #221)

- *(captcha)* Add automatic OCR-based CAPTCHA solver with human fallback (#206)

- *(captcha)* Add human-in-the-loop CAPTCHA handling for web research (#206)

- *(knowledge)* Add documentation search to ChatKnowledgeService (#250)

- *(tools)* Add documentation indexing tool (#250)

- *(analysis)* Add Anti-Pattern Detection System (#221)

- *(knowledge)* Improve vectorization UX (#254)

- *(chat)* Add /scan and /security slash commands (#260)

- *(security)* Add Memory MCP entity integration (#260)

- *(security)* Add Security Assessment Workflow Manager (#260)

- *(memory)* Add list all entities endpoint for KnowledgeGraph

- *(chat)* Add conversation-aware RAG query enhancement (#249)

- *(analytics)* Add advanced analytics & BI modules (#59)

- *(knowledge)* Add category filtering to KnowledgeSearch (#161)

- *(celery)* Add configurable Celery worker settings

- *(onboarding)* Add slash commands and setup wizard (#166)

- *(frontend)* Add Knowledge Graph visualization component (#55)

- *(orchestrator)* Implement custom success criteria checking (#201)

- *(monitoring)* Add Redis error tracking and alert notification system (#204)

- *(api)* Add standardized response builder utilities (#192)

- *(error-handling)* Add frontend error handler and fix type imports (#187, #188)

- *(types)* Add typed definitions to replace Dict[str, Any] (#187)

- *(knowledge-base)* Add bulk operations and data management (#79)

- *(knowledge-base)* Add enhanced search with hybrid mode and tag filtering (#78)

- *(knowledge-base)* Add tagging system for KB organization (#77)

- *(graph)* Complete Issue #55 Phase 1 & 2 - Knowledge Graph Implementation (#55)

- *(ci)* Add pyenv setup script for self-hosted runner

- *(chat)* Integrate comprehensive intent classification system (#159)

- *(backend)* Add comprehensive intent classification system (#159)

- Code extraction initiative - Phases 3 & 4 (#148, #149)

- *(npu-worker)* Migrate Windows NPU worker to canonical Redis client pattern (#151)

- Add HTML dashboard utilities module (Phase 1) (#146)

- *(config)* Add API_BASE_URL and OLLAMA_URL to unified_config (#142)

- *(config)* Create backward compatibility shim for unified_config (#63)

- *(config)* Port CORS, security, and timeout methods to unified config (#63)

- *(mcp)* Add 4 new MCP bridge implementations

- *(infrastructure)* Add vision API and enhance core utilities

- *(frontend)* Enhance terminal and voice interface components

- *(mcp)* Enhance MCP integration with bridges and workflows

- *(voice)* Add wake word detection service and API (#54)

- *(frontend)* Add interactive command UI and stdin support (Issue #33 Phase 3)

- *(terminal)* Add interactive command support (Issue #33 Phases 1-4 Backend)

- *(monitoring+mcp)* Complete Issue #22 (Prometheus) + Issue #44 (MCP Manager)

- *(mcp)* Add Sequential and Structured Thinking MCP Bridges (Issue #45)

- *(mcp)* Complete MCP Management Interface (Issue #44)

- *(vnc)* Integrate VNC observations with AutoBot MCP framework

- *(infrastructure)* Implement Browser VM VNC with Infrastructure as Code

- *(browser)* Use headless API mode for Playwright Browser VM

- *(frontend)* Improve Browser VM integration and service discovery

- *(playwright)* Add navigation and reload endpoints for Browser VM

- *(api)* Add Playwright router as optional module

- *(vnc)* Add automatic VNC server lifecycle management

- *(kb)* Add reusable KB validation utilities to prevent NoneType errors

- *(knowledge)* Extract document features to reusable utilities & consolidate KB files (#35)

- *(frontend)* Add noVNC proxy route for desktop access at /tools/novnc

- Add new utility patterns, composables, and documentation

- *(frontend)* Integrate neural reranking controls into Knowledge Search GUI

- *(api)* Integrate advanced RAG reranking into knowledge endpoints

- *(knowledge)* Upgrade RAG reranking from simple algorithm to full cross-encoder model

- *(knowledge)* Add reusable RAG service layer with adapter pattern

- *(frontend)* Create BaseAlert component and migrate LoginForm (batch 41)

- *(buttons)* Integrate touch optimization features into BaseButton, resolve component overlap

- *(backend)* Add fast_document_scanner service

- *(ui)* Add reusable UI components and utilities foundation

- *(encoding)* Add UTF-8 enforcement utilities and documentation

- *(code-quality)* Add reusable function quality checker

- *(terminal)* Enable PTY echo for command visibility and sudo prompts

- *(knowledge)* Add comprehensive document format support for knowledge base

- *(frontend)* Display backend initialization status instead of 'Disconnected'

- *(backend)* Add initialization status tracking to health endpoint

- *(frontend)* Implement async job polling for system knowledge refresh

- *(backend)* Implement async job system for long-running knowledge operations

- *(prometheus)* Integrate workflow metrics recording into production code

- *(error-handling)* Implement Phase 1 error handling refactoring enhancements

- *(vllm)* Enable vLLM in configuration and add to setup dependencies

- Implement vLLM prefix caching optimization for 3-4x LLM throughput improvement

- *(scripts)* Add hardcoding detection and utility scripts

- *(agents)* Add conversation compaction Claude agent

- *(constants)* Create comprehensive constants infrastructure

- *(mcp)* Add TypeScript network and path constants for MCP tools

- Add CRUD endpoint tests and Ollama service optimization

- *(analytics)* Enhance codebase analytics with frontend integration

- *(system)* Add system context module with man page indexing

- *(frontend)* Add Knowledge Base V2 UI components with TypeScript type safety

- *(knowledge)* Implement Knowledge Base V2 with async Redis and proper error handling

- *(security)* Add supervised mode for guided dangerous command execution

- *(terminal)* Improve terminal approval workflow and logging

- *(terminal)* Enhance terminal logging and session persistence

- *(terminal)* Enhance terminal logging with chat session integration

- *(terminal)* Enhance command approval workflow with auto-approval and logging

- *(api)* Add management endpoints for terminal and registry systems

- *(infrastructure)* Add comprehensive infrastructure management system

- *(redis)* Add comprehensive Redis service management system

- *(ops)* Enhance cleanup script and add Ansible playbook

- *(planning)* Add Redis service management tasks and utilities

- *(frontend)* Update API clients with standardized configuration

- *(security)* Implement comprehensive API security and session ownership

- *(infrastructure)* Add centralized constants and monitoring

- *(backend)* Implement provider availability checking (P0 Task #2)

- *(backend)* Integrate provider health checking into agent config

- *(resources)* Add Windows NPU worker implementation

- *(backend)* Add provider health checking system

- *(scripts)* Add deployment, security, and automation scripts

- Add NPU workers, feature flags, and load balancing

- *(infrastructure)* Improve database, deployment, and startup

- *(frontend)* Improve chat, knowledge, and terminal UI

- *(backend)* Improve chat, knowledge, and service management

- *(security)* Implement service authentication enforcement (Week 3)

- *(backend)* Increase context window and improve streaming

- *(frontend)* Improve chat message UI and display settings

- *(frontend)* Integrate file manager into chat interface

- *(frontend)* Add conversation file manager UI components

- *(api)* Enhance chat deletion and add file tree endpoint

- *(api)* Add conversation-specific file management endpoints

- *(backend)* Add ConversationFileManager core infrastructure

- *(database)* Add conversation files schema and migration

- *(chat)* Add Redis-backed conversation persistence and transcript storage

- Enhanced components and utility scripts

- *(devops)* Deployment automation and infrastructure improvements

- *(monitoring)* Comprehensive error handling and system monitoring

- *(chat)* Enhance chat system with improved UX and backend integration

- *(knowledge)* Comprehensive knowledge management system refactoring

- Complete frontend and backend API integration improvements

- *(deployment)* Enhance distributed and native VM deployment scripts

- Add development tools and memory management enhancements

- *(analysis)* Comprehensive codebase analysis and refactoring tools

- *(backend)* Enhance API endpoints and analytics capabilities

- *(frontend)* Enhance Vue.js components and user interface

- *(backend)* Improve LLM config sync and service configuration

- *(core)* Enhance conversation management and lightweight orchestrator

- *(backend)* Enhance fast app factory with build identification and orchestrator management

- *(frontend)* Enhance knowledge management and async routing

- *(backend)* Improve service monitoring and terminal websocket management

- *(core)* Improve authentication middleware and system metrics

- *(backend)* Enhance LLM configuration synchronization

- *(core)* Enhance authentication, multimodal processing, and system metrics

- *(frontend)* Update service discovery and chat view components

- *(backend)* Enhance fast app factory and service monitoring

- *(frontend)* Enhance chat interface with unified loading and terminal fixes

- *(infrastructure)* Enhance deployment and VM management systems

- *(vm)* Enhance VM management scripts for distributed infrastructure

- *(scripts)* Improve utility scripts for VM management

- Enhance main startup script with improved options

- Add multimodal API and performance monitoring

- *(ai)* Enhance AI/ML systems with hardware acceleration

- *(backend)* Enhance API endpoints and services

- *(frontend)* Enhance Vue components with monitoring and analytics

- Implement comprehensive testing infrastructure and system tools

- Implement automated deployment and time synchronization system

- Implement enterprise security framework and compliance systems

- Implement Phase 4 enterprise monitoring and performance systems

- Modernize AutoBot application architecture and enhance distributed system

- *(frontend)* Implement robust notification system and router health monitoring

- *(frontend/backend)* Enhance loading states and API compatibility

- *(frontend)* Implement bulletproof frontend architecture with comprehensive fixes

- *(backend)* Enhance fast app factory with async improvements

- *(scripts)* Add agent Ansible reference update utility

- *(scripts)* Enhance run script with improved VM management

- *(redis)* Enhance connection testing with improved fallback configurations

- *(backend)* Enhance app factory with async LLM config sync

- Add project assets, content, and analysis resources

- *(infrastructure)* Add distributed architecture setup and deployment tools

- *(config)* Update core configuration and documentation

- *(scripts)* Enhance setup and monitoring scripts with distributed support

- *(core)* Enhance LLM interface and add distributed services

- *(backend)* Optimize application factory and startup performance

- *(backend)* Enhance API endpoints and service layer

- *(frontend)* Add enhanced service layer and type definitions

- *(frontend)* Enhance Vue components with monitoring and fallback systems

- *(frontend)* Update Vue configuration and core utilities

- *(agents)* Update agent configurations with enhanced capabilities

- *(analysis)* Add comprehensive project reports and system validation

- *(infrastructure)* Enhance distributed VM architecture and deployment

- *(frontend)* Enhance Vue components with monitoring and fallback systems

- *(monitoring)* Implement comprehensive Phase 9 performance monitoring system

- *(agents)* Enhance multi-agent coordination system with specialized roles

- *(config)* Add comprehensive configuration management system

- *(mcp)* Add comprehensive MCP AutoBot Tracker system

- Add native VM deployment support

- *(deployment)* Add comprehensive Ansible automation

- *(deployment)* Add automated frontend sync script

- *(integrations)* Add MCP servers and third-party integrations

- *(claude)* Add specialized Claude agent configurations

- *(backend)* Enhance API services and security infrastructure

- *(config)* Add comprehensive configuration and deployment scripts

- *(frontend)* Add new Vue components for system notifications and settings

- Implement core async system optimizations and dependency management

- Add backend async improvements and monitoring APIs

- Enhance frontend UI components and user experience

- Add new components and functionality modules

- Standardize chat persistence and session management API

- Improve frontend environment and proxy configuration for WSL/Docker

- Implement complete frontend category document browsing

- Comprehensive AutoBot system improvements - multiple critical fixes

- Comprehensive code quality improvements and orchestrator fixes

- Preserve containers on shutdown for faster restarts

- Add auto-browser launch in development mode

- Make run_agent_unified.sh truly unified by starting backend on host

- Optimize Docker build process to reduce unnecessary rebuilds

- Add new features and infrastructure components

- Update package dependencies and testing infrastructure

- Enhance configuration management and service integration

- Add comprehensive scripts and automation tools

- Enhance utilities, security, and infrastructure components

- Implement advanced agent orchestration and core system enhancements

- Enhance backend APIs with advanced orchestration and service improvements

- Enhance frontend components with improved functionality and accessibility

- Add comprehensive environment configuration system

- Implement unified Docker infrastructure

- Implement comprehensive UI polish and accessibility enhancements

- Implement optional enhancements and verify test suite functionality

- Implement changelog system and complete task documentation processing

- Add secure sandbox build script

- Implement log rotation and improve application lifecycle

- Modernize Docker architecture and eliminate hardcoded values

- Complete agent migrations to StandardizedAgent and add base Docker image

- Implement comprehensive Docker deduplication and Redis database separation

- Implement centralized Docker data management for prompts and knowledge base

- Implement StandardizedAgent pattern to eliminate process_request duplication

- Add comprehensive codebase analytics frontend interface

- Add intelligent VNC port detection for container/host environments

- Add comprehensive port configuration management and validation

- Update scripts to use centralized configuration

- Implement centralized configuration management to eliminate hardcoded values

- Finalize comprehensive system improvements and testing validation

- Enhance file upload testing validation with comprehensive API tests

- Implement comprehensive error boundaries and notifications

- Implement comprehensive LLM-as-Judge framework

- Add multi-device parallel async inference support

- Add NVIDIA GPU support to NPU worker with auto-device detection

- Integrate consolidated terminal API and system improvements

- Integrate async database operations into agent systems

- Add system monitoring and deployment scripts

- Add comprehensive utility modules

- Add middleware and service layers

- Add advanced system modules

- Add URL validation service

- Add advanced backend API endpoints

- Add Vue components for phase progression and validation

- Add GitHub Actions workflow for phase validation

- Add Docker containerization support

- Enhance testing and debugging utilities

- Update main application and core processors

- Enhance utility modules and Redis integration

- Update core memory and knowledge systems

- Enhance computer vision and hardware acceleration

- Update Vue frontend configuration

- Implement memory optimization improvements

- Enhance backend services with improved configuration

- Enhance agents with communication protocol integration

- Implement async database operations with connection pooling

- Implement agent communication protocol

- Convert LLM interfaces to async HTTP operations

- Enhance phase validation system with comprehensive acceptance criteria

- Implement comprehensive microservice architecture evaluation

- Implement comprehensive memory usage optimization

- Implement comprehensive CI/CD security integration

- Implement comprehensive performance and security optimizations

- Implement comprehensive code optimization and API fixes

- Add optimization roadmap and monitoring dashboard

- Implement comprehensive codebase profiling and automated testing framework

- Add comprehensive backend performance profiling and analysis

- Enhance core system components with Phase D integration

- Enhance backend infrastructure and integration

- Implement enhanced Docker sandbox security features

- Implement enhanced multi-agent orchestration system

- Implement NPU-accelerated code search with Redis indexing

- Implement LLM failsafe system with 4-tier fallback

- Enhance file upload functionality for automated testing

- Add development utilities and diagnostic tools

- Update platform documentation and frontend enhancements

- Add executive summary and strategic positioning documents

- Complete reports review and infrastructure cleanup

- Intel NPU driver integration for AutoBot hardware acceleration

- Implement comprehensive project organization and file structure cleanup

- Migrate orchestrator core component to new error handling

- Migrate critical chat API endpoints to new error handling

- Implement comprehensive error handling improvements

- Implement data-at-rest encryption service (CRITICAL security fix)

- Implement quick wins from code analysis report

- *(commands)* Enhance command detection and manual system

- *(npu)* Add NPU worker client for offloading heavy computations

- *(frontend)* Implement Playwright VNC viewer and fix API endpoints

- *(playwright)* Add VNC-enabled Playwright container with visual browser automation

- *(backend)* Add Playwright health check endpoint and fix API initialization

- Add Playwright container with VNC and noVNC support

- Add comprehensive setup repair system and unified CLI

- Improve container startup process and fix Playwright mount issues

- Optimize backend performance and add NPU worker integration

- Implement comprehensive command manual knowledge base system

- Integrate CommandPermissionDialog into ChatInterface

- Add CommandPermissionDialog component with Allow/Deny/Comment options

- Implement comprehensive testing framework with CI/CD pipeline

- Add code analysis suite with automated fix agents

- Implement full PTY terminal with complete sudo support

- Enhance setup_agent.sh with comprehensive GUI testing dependencies

- Comprehensive GUI testing and validation suite

- Comprehensive terminal debugging and simplified WebSocket solution

- Add terminal debugging utility and fix WorkflowApproval 404

- Preserve complete development history with debugging artifacts

- Finalize infrastructure and development environment setup

- Comprehensive core system enhancements and optimizations

- Enhance backend API system with comprehensive improvements

- Enhance frontend UI components and services integration

- Add development artifacts and debugging infrastructure

- Add comprehensive end-to-end testing and validation suite

- Implement workflow scheduler and enhanced classification agent

- Add remaining metrics and scheduler API integration

- Add comprehensive testing suite and development artifacts

- Implement advanced security agents with dynamic tool discovery

- Implement comprehensive workflow templates system

- Enhanced workflow orchestration with metrics integration

- Implement Redis-based workflow classification system

- Workflow analysis and UI enhancement tools

- NPU worker system and advanced monitoring

- Add workflow notifications system

- Enhance chat API with workflow orchestration integration

- Add comprehensive workflow API service layer

- Integrate comprehensive workflow UI components

- Implement comprehensive multi-agent workflow orchestration

- Optimize hardware acceleration and fix frontend issues

- Add comprehensive test automation suite with Playwright integration

- Enhance backend APIs with multi-agent and hardware acceleration support

- Modernize frontend build system and routing infrastructure

- Enhance frontend UI components with modern design and functionality

- Add comprehensive test infrastructure and reporting

- Integrate multi-agent architecture with core system components

- Add comprehensive multi-agent architecture documentation and core agents

- Configure system to use uncensored models for unrestricted capabilities

- Enhance installation system for multi-agent architecture

- Complete multi-agent architecture with Knowledge Retrieval and Research agents

- Enhance configuration system with hardware acceleration integration

- Implement hardware acceleration with NPU > GPU > CPU priority

- Major frontend redesign and backend improvements

- Add knowledge base population and fix scripts

- Implement Vue Notus Tailwind CSS professional redesign

- Implement executive GUI redesign with professional styling

- Add Containerized Librarian Assistant Agent with web research capabilities

- Implement comprehensive multi-agent architecture with Tier 2 web research

- Automate config defaults fix in setup script

- Add containerized librarian assistant agent with comprehensive web research

- Add KB Librarian Agent for automatic knowledge base search

- Complete intelligent agent system implementation

- Comprehensive environment variable system to eliminate hardcoding

- Add intelligent agent system modules

- Implement secrets management hardening + default model update

- Resolve major technical debt issues

- Implement Prompt Intelligence Synchronization System - Transform agent to expert system


### Miscellaneous

- *(fleet)* Include slm-agent code in update-all-nodes.yml (#1164)

- *(slm-agent)* Remove symlink workaround during canonical path deploy (#1163)

- *(merge)* Resolve conflicts merging main into Dev_new_gui

- *(tts)* Remove stale Kani-TTS-2 references (#1136)

- *(slm-frontend)* Remove redundant semicolons in settings views (eslint auto-fix)

- *(frontend)* Add eslint config and fix lint errors in SLM frontend

- Add venv/ to .gitignore

- *(backend)* Apply import sorting and code formatting improvements (#557)

- *(ansible)* Remove legacy autobot-agent cleanup tasks

- *(user-frontend)* Delete 30 dead JS/TS files (#818)

- Add component data directories (#781)

- *(structure)* Phase 4 - delete original folders (#781)

- *(structure)* Organize remaining unmapped folders (#781)

- *(workers)* Create NPU and browser worker stubs (#781)

- *(infra)* Copy infrastructure files (#781)

- *(user-backend)* Copy user backend to autobot-user-backend/ (#781)

- *(user-frontend)* Copy user frontend to autobot-user-frontend/ (#781)

- *(slm-frontend)* Copy SLM frontend to autobot-slm-frontend/ (#781)

- *(slm-backend)* Copy SLM backend to autobot-slm-backend/ (#781)

- *(structure)* Create new folder structure (#781)

- *(slm-server)* Remove debug exception handler

- Cleanup and memory API update

- *(config)* Update requirements and SLM install script

- *(backend)* Minor API endpoint updates

- *(analysis)* Update code analysis and refactoring scripts

- *(tests)* Remove stale SLM tests for deleted infrastructure models

- Remove test file accidentally committed

- *(security)* Exclude dev_creds_backup from version control (#725)

- *(ansible)* Add quick-fix playbook for sudo configuration

- Phase 0 cleanup for mTLS migration (#725)

- *(scripts)* Add sync-to-slm.sh for SLM deployment

- Remove obsolete backup and summary files

- Move test files to tests/ directory

- Update project configuration and static assets

- Update isort pre-commit hook to latest version (6.0.1)

- Update .gitignore for vendor and test directories

- *(frontend)* Update dependencies and add VNC proxy configuration

- Update gitignore to exclude generated reports and test data

- Clean up legacy files and update project structure

- Add configuration backups and static file updates

- Add .worktrees/ to gitignore for isolated development (#726)

- *(config)* Remove redundant MCP servers to reduce token usage

- Remove orphaned fix-agents directory (#708)

- *(settings)* Remove Data Storage from main tabs (now subtab) (#690)

- Remove archived Vue components (#621)

- *(cleanup)* Delete archived files and fix stale references (#567)

- *(cleanup)* Remove obsolete KnowledgeComponentReview view

- *(archive)* Remove archived LLM interfaces after feature restoration (#551)

- Add uncommitted visualization components, tests, and utilities (#408)

- Remove unused imports from scripts

- *(cleanup)* Remove 708 archived files (#393)

- Update chart exports and miscellaneous improvements

- Remove unused circuit breaker imports from example

- Remove unused uuid import from debug script

- Remove unused imports from utility scripts

- *(analysis)* Remove unused imports from analysis scripts

- Remove pending issues file - issues created in GitHub

- Remove 9 .backup files violating naming policy

- Clean up old session file and add database MCP analysis

- Repository cleanup - organize session summaries and scripts

- *(archive)* Add archives directory for historical documentation

- *(docs)* Remove obsolete documentation from root docs/ directory

- *(archive)* Remove weekly completion reports (weeks 1-3)

- *(archive)* Remove legacy test suite (2025-01-09)

- *(archive)* Remove obsolete maintenance scripts (2025-10-10)

- *(archive)* Remove obsolete Hyper-V deployment scripts (2025-01-09)

- *(archive)* Remove obsolete architecture fix scripts (2025-10-09)

- *(archive)* Remove obsolete lightweight orchestrator

- *(archive)* Remove unused Docker infrastructure files

- Remove obsolete todo tracking files

- Miscellaneous infrastructure and service improvements

- *(project)* Add planning docs, prompts, and backend tests

- *(core)* Update configuration, scripts, and core services

- *(repo)* Achieve 100% repository cleanliness compliance

- Reorganize MCP documentation files

- Exclude entire .claude directory from git

- *(agents)* Optimize Claude Code agents for token efficiency

- Enhance .gitignore with comprehensive exclusions

- Remove obsolete backup files

- *(archive)* Archive obsolete code and legacy implementations

- *(archive)* Remove obsolete Docker infrastructure

- *(tests)* Remove test summary and report files (part 2)

- *(tests)* Archive obsolete test files (part 1)

- Update task tracking files

- *(gitignore)* Exclude service-keys directory from version control

- Add remaining configuration and miscellaneous files

- Remove frontend fixes completion summary

- Remove completed fix documentation

- Remove obsolete prompt system files

- Update gitignore and add implementation documentation

- Add task memory snapshots

- Add debug utilities and demo scripts

- Add tests/results/ to gitignore

- Remove backup file from inappropriate location

- Configure reports folder to be ignored and remove from git tracking

- Update environment configuration for distributed architecture

- Add third-party MCP repositories to gitignore

- Remove backup file violating repository standards

- Remove reports, logs, and large files from repository

- Add external repositories to gitignore

- Process and organize analysis reports to finished status

- Update project configuration and static assets

- Update isort pre-commit hook to latest version (6.0.1)

- Update .gitignore for vendor and test directories

- *(frontend)* Update dependencies and add VNC proxy configuration

- Update gitignore to exclude generated reports and test data

- Clean up legacy files and update project structure

- Add configuration backups and static file updates


### Performance

- *(analytics)* Wrap API endpoint checker in asyncio.to_thread in report

- *(analytics)* Offload _count_files_and_lines to thread in pattern analyzer

- *(analytics)* Wrap get_code_collection with asyncio.to_thread in stats

- *(analytics)* Wrap environment analyzer init with asyncio.to_thread

- *(analytics)* Wrap blocking calls with asyncio.to_thread in endpoints

- *(analytics)* Hoist re.compile to module level in duplicate_detector (#1225)

- *(analytics)* Hoist re.compile patterns to module level (#1225)

- *(ollama)* Expose pool max_connections via SSOT config, raise default to 6, add queue depth warning (#1154)

- *(chat)* Remove 300ms artificial delays from chat workflow (#1153)

- *(llm)* Document RTX 4070 GPU in Ollama defaults (#1036)

- *(backend)* Fix /redis/health-score 504 timeout with cache + limits (#1034)

- *(startup)* Lazy-load multimodal models and DB engine (#940)

- Optimize slow API endpoints with caching and fast modes

- Comprehensive system optimization and performance tuning completion

- *(analytics)* Implement parallel file processing for codebase indexing (#711)

- *(npu)* Add parallel GPU/NPU device support for faster embeddings (#165)

- *(knowledge)* Add NPU connection warmup for faster embeddings (#165)

- *(knowledge)* Optimize NPU embedding with caching and bounded fallback (#165)

- *(frontend)* Add request deduplication for config loading (#677)

- *(frontend)* Add configurable maxRetries to ApiClient.get() (#671)

- *(async)* Fix blocking I/O in async functions (#666)

- *(codebase)* Fix blocking I/O patterns in duplicates.py (#666)

- *(api)* Wrap blocking scanner calls in asyncio.to_thread (#666)

- *(monitoring)* Fix blocking I/O in async functions (#666)

- *(api)* Parallelize sequential awaits with asyncio.gather() (#664)

- *(db)* Fix N+1 query patterns in infrastructure and monitoring (#663)

- *(frontend)* Parallelize code intelligence analyzers (#661)

- *(analytics)* Optimize ChromaDB writes with batch embeddings (#660)

- *(analytics)* Implement high-impact performance optimizations (#659)

- *(analytics)* Fix codebase indexing and analytics timeouts

- *(chat)* Pre-compile tool call regex pattern (#650)

- Parallelize version storage operations (#619)

- Parallelize batch file analysis (#619)

- Additional parallelization patterns (#619)

- Restructure dependency patterns for parallelization (#619)

- Parallelize SOC2/GDPR compliance checks (#619)

- Parallelize file hash computation and Redis lookup (#619)

- Parallelize architecture analysis (#619)

- Parallelize more sequential await patterns (#619)

- Parallelize analytics service maintenance and optimization analyses (#619)

- Parallelize more sequential await patterns (#619)

- Parallelize RAG semantic search and facts retrieval (#619)

- Fix quadratic complexity comprehensions with O(n) algorithms (#626)

- Convert list-for-lookup patterns to sets for O(1) checks (#625)

- Parallelize sequential awaits in 7 files (#619)

- Fix more repeated computation patterns (#624)

- Fix repeated computation patterns (#624)

- *(codebase-analytics)* Optimize ChromaDB indexing performance (#539)

- *(api)* Fix N+1 query patterns in Redis operations (#561)

- *(patterns)* Optimize loading of already indexed pattern data (#208)

- *(#380)* Final batch of repeated computation optimizations

- *(issue-380)* Extract Redis migration constants (#380)

- *(issue-380)* Extract container types tuple to module constant (#380)

- *(issue-380)* Extract HTTP method tuple to module constant (#380)

- *(issue-380)* Extract repeated literals to module-level constants (#380)

- *(issue-380)* Session 36 - Extract frozenset for command states

- *(issue-380)* Session 35 - Extract tuple constants in architecture evaluator

- *(issue-380)* Session 34 - Extract tuple constants for URL prefixes

- *(issue-380)* Session 33 - Extract tuple constant for config file extensions

- *(issue-380)* Session 32 - Extract tuple constants in analyzer scripts

- *(issue-380)* Session 31 - Extract tuple constants in code analysis files

- Add module-level constants for AST isinstance checks (#380)

- Add module-level constants for AST isinstance checks (#380)

- Add module-level constants for AST isinstance checks (#380)

- *(http)* Use singleton HTTP client for 60-80% overhead reduction (#65)

- *(core)* Optimize nested loop complexity patterns (#317)

- *(api)* Fix unbatched API calls using asyncio.gather() (#313)

- *(#326)* Add O(1) lookup for datetime field keys in TakeoverManager

- *(#326)* Use O(1) set lookups for repeated keyword checks

- *(#323)* Cache repeated computations outside loops

- *(#325)* Convert string concatenation to join() for O(n) performance

- *(#326)* Convert list lookups to sets for O(1) performance

- Parallelize frontend file uploads and API calls (#295)

- Fix final blocking I/O in async functions (#291)

- Parallelize frontend async operations (#295)

- Parallelize independent async operations (#295)

- Convert blocking I/O to async in batch 4 (#291)

- Convert blocking I/O to async in backend services and src modules (#291)

- Convert blocking I/O to async in src modules (#291)

- Convert blocking I/O to async in backend API modules (#291)

- Parallelize independent async operations (#295)

- *(knowledge)* Use SRANDMEMBER instead of SMEMBERS for category lookup (#258)

- *(knowledge)* Add Redis category indexes for O(1) lookups (#258)

- *(knowledge)* Optimize category filter with SCAN+pipeline (#258)

- *(knowledge)* Add performance test suite (#163)

- *(http)* Migrate npu_semantic_search.py to HTTPClient singleton (#66)

- *(knowledge-base)* Add parallel document processing for batch ingestion (#65)

- *(redis)* Optimize Redis operations and resolve timeout issues

- *(ollama)* Add thread optimization for reduced CPU usage

- Implement comprehensive backend lazy loading and performance optimizations

- Optimize frontend build and resolve Vite warnings

- Optimize slow API endpoints with caching and fast modes

- Comprehensive system optimization and performance tuning completion


### Refactoring

- *(workflow)* Consolidate api/workflow_automation into services/ version (#1285)

- *(cache)* Consolidate cache.py into cache_management.py (#1286)

- *(batch)* Consolidate batch.py into batch_jobs.py (#1287)

- *(vision)* Remove /vision route and unused vision components (#1242)

- *(analytics)* Remove debug logs + trim index_codebase to 62 lines (#1223)

- *(shared)* Consolidate duplicated network_constants + TLSMode (#1195)

- *(backend)* Fix final remaining backend. imports, remove symlink (#1177)

- *(backend)* Fix remaining function lengths in code_analysis (#1175)

- *(backend)* Fix function lengths, convert prints to logger in final files (#1175, #1181)

- *(backend)* Replace print() with logger in rag_benchmarks (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 79 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 77-78 (#1175)

- *(backend)* Remove from backend.xxx import prefix - final batch (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 76 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 75 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 74 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 72 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 71 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 70 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 68 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 67 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 66 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 65 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 64 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 63 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 62 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 61 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 60 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 59 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 58 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 57 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 56 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 55 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 54 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 53 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 51 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 50 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 49 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 48 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 47 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 46 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 45 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 44 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 43 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 42 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 40 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 38 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 37 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 36 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 35 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 34 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 33 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 32 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 31 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 30 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 29 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 28 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 27 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 23 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 22 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 21 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 20 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 19 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 18 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 17 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 16 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 15 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 14 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 13 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 12 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 11 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 10 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 9 (#1175)

- *(codebase-analytics)* Remove backend. import prefix batch 8 + fix multi-worker task state (#1175, #1179)

- *(backend)* Remove from backend.xxx import prefix batch 7 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 6 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 5 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 4 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 3 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 2 (#1175)

- *(backend)* Remove from backend.xxx import prefix batch 1 (#1175)

- *(slm/orchestration)* Reuse categoryCounts instead of duplicate fleetCategoryCounts (#1166)

- *(agents)* Consolidate librarian implementations, fix naming violations (#1152)

- *(backend)* Extract SQL constant in secrets_service (#1088)

- *(backend)* Trim docstrings and extract _build_secret_result (#1088)

- *(backend)* Extract _sum_daily_stats in analytics_embedding_patterns (#1088)

- *(slm)* Extract _get_fleet_nodes_or_raise in fleet service (#1088)

- *(slm)* Extract _build_service_ssh_cmd helper in services (#1088)

- *(slm)* Extract helper in backup service (#1088)

- *(backend)* Apply black formatting and extract helpers across backend (#1088)

- *(backend)* Apply black formatting to api/analytics and agents (#1088)

- *(backend)* Apply black formatting to agents and agent_loop (#1088)

- *(shared)* Apply function-length refactoring to redis_client (#1088)

- *(slm)* Apply function-length refactoring to SLM backend (#1088)

- *(backend)* Extract helpers to meet 65-line limit in services/utils (#1088)

- *(api)* Extract helpers to meet 65-line limit in backend API part 2 (#1088)

- *(api)* Extract helpers to meet 65-line limit in backend API part 1 (#1088)

- *(knowledge)* Architecture improvements for ECL pipeline (#1074)

- *(voice)* Extract _resumeAutoListening + auto-mode UI icons (#1030)

- *(frontend)* Update remaining views to current design tokens (#1024)

- *(frontend)* Unify Evolution, AuditLogs, BI views to design tokens (#1024)

- *(frontend)* Convert Tailwind views to scoped CSS with design tokens (#1024)

- *(config)* Drop Unified prefix from ConfigManager naming (#959)

- *(backend)* Remove dead config/health files, migrate callers (#958)

- *(ollama)* Consolidate to single OllamaProvider implementation (#949)

- *(monitoring)* Move node_exporter from Phase 7 into slm_agent role (#945)

- *(ansible)* Consolidate security configuration in browser.yml

- *(ansible)* Consolidate security configuration in aiml.yml

- Consolidate security config and register auth router

- *(ansible)* Consolidate security configuration in backend.yml (#893)

- *(infra)* Retire 6 VM management scripts superseded by Ansible (#831)

- *(slm-backend)* Remove misleading deprecation warnings

- Deprecate run_autobot.sh, move to legacy (#863)

- *(slm-frontend)* Remove redundant Infrastructure monitoring page

- *(ansible)* Rename 01-Code-Source to 01-Backend (#837)

- *(infra)* Merge duplicates + retire Ansible-redundant scripts (#831)

- *(infra)* Delete 23 obsolete shell scripts (#831)

- *(scripts)* Migrate remaining root-level infra scripts to ssot-config.sh (#809)

- *(scripts)* Migrate bulletproof, deployment, native-vm scripts to ssot-config.sh (#809)

- *(scripts)* Migrate logging, monitoring, security scripts to ssot-config.sh (#809)

- *(scripts)* Migrate utilities, vm-management, network, distributed to ssot-config.sh (#809)

- *(scripts)* Migrate infra templates, mcp tools, and tests to ssot-config.sh (#809)

- *(scripts)* Migrate component + root scripts to ssot-config.sh (#809)

- *(infra)* Extract Method refactoring batch 17 - 13 files (#825)

- *(infra)* Extract Method refactoring batch 16 - 13 files (#825)

- *(infra)* Code quality fixes batch 10 - 6 files (#825)

- *(infra)* Code quality fixes batch 10 - 5 files (#825)

- *(slm)* Extract method in 3 SLM backend files (#825)

- *(infra)* Code quality fixes batch 8 - 2 files (#825)

- Fix stale from src.* imports in tests and shared config (#806)

- Fix P0 stale from src.* imports in 7 production files (#806)

- *(user-frontend)* Migrate 6 active JS files to TypeScript (#819)

- *(user-management)* Fix function length violations in user management services (#576)

- *(config)* Complete config.yaml SSOT consolidation (#639)

- *(ansible)* Remove hardcoded IPs from playbooks and roles (#799)

- *(ansible)* Remove hardcoded IPs from playbooks and roles (#799) (#804) ([#804](https://github.com/mrveiss/AutoBot-AI/pull/804))

- Fix conftest paths and pytest discovery for colocated tests (#734)

- Colocate remaining test files with source modules (#734)

- Update pytest.ini and CI workflows for colocated tests (#734)

- Colocate frontend unit tests with source modules (#734)

- Colocate 130 test files with source modules (#734)

- Colocate tests with source files (#734) (#798) ([#798](https://github.com/mrveiss/AutoBot-AI/pull/798))

- Colocate 130 test files with source modules (#734)

- Update paths for current project structure (#781)

- *(utils)* Add utility modules to autobot-user-backend (#781)

- *(core)* Add compatibility symlinks and organize backend modules (#781)

- *(infra)* Convert NPU worker and DB stack to native systemd (#789)

- Reorganize infrastructure/ to per-role structure (#781)

- Consolidate runtime data directories (#781)

- Move playwright dependencies to autobot-browser-worker (#781)

- Clean up root folder organization (#781)

- Phase 2 - Update all imports for new folder structure (#781)

- *(services)* Extract helpers from restart_service (#665)

- *(nodes)* Extract helpers from replace_node (#665)

- *(code_sync)* Extract helpers from sync_role (#665)

- *(code-sync)* Extract helpers from run_schedule (#665)

- *(sync-orchestrator)* Extract helpers from pull_from_source (#665)

- *(reconciler)* Extract helpers from _check_node_health (#665)

- *(deployment)* Extract helpers from _execute_enrollment_playbook (#665)

- *(tls)* Extract helpers from bulk_renew_expiring_certificates (#665)

- *(deployment)* Extract helpers from enroll_node (#665)

- *(blue-green)* Move purge playbook template to module constant (#665)

- *(service-orchestrator)* Move service definitions to module constant (#665)

- *(security)* Extract helpers from get_security_overview (#665)

- *(deployment)* Extract helpers for long functions (#665)

- *(backup)* Extract helpers from execute_restore (#665)

- *(tls)* Extract helpers from rotate_tls_certificate (#665)

- *(schedule-executor)* Extract helpers from execute_schedule (#665)

- *(nodes)* Extract helpers from create_node (#665)

- *(code_sync)* Extract helpers from notify_code_version (#665)

- *(reconciler)* Extract helpers from update_node_heartbeat (#665)

- *(reconciler)* Extract helpers from _check_node_for_rollback (#665)

- *(nodes)* Extract helpers from enroll_node (#665)

- *(replication)* Extract helpers from setup_replication (#665)

- *(reconciler)* Extract helpers from _remediate_failed_service (#665)

- *(slm)* Extract helpers from test_connection (#665)

- *(slm)* Extract helpers from _run_update_job (#665)

- *(slm)* Extract helpers from _remediate_node (#665)

- *(slm)* Extract helpers from enable_tls_on_services (#665)

- *(functions)* Extract methods in 2 files to reduce function lengths (#620)

- *(slm)* Extract helpers from restart_all_node_services (#665)

- *(functions)* Extract methods in manager.py to reduce function lengths (#620)

- *(slm)* Extract helpers from verify_sync (#665)

- *(functions)* Extract methods in 4 files to reduce function lengths (#620)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in manager.py to reduce function lengths (#620)

- *(slm-server)* Extract helpers from scan_node_services (#665)

- *(memory)* Delete enhanced_memory_manager.py (#742)

- Migrate enhanced_memory_manager imports to src.memory (#742)

- *(mcp)* Extract tool definitions from _setup_handlers (#665)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(frontend)* Remove Code Intelligence as separate tab - integrate into Codebase Analytics (#566)

- *(slm-server)* Extract helpers from execute_redis_backup (#665)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(slm-server)* Extract helpers from sync_node_role (#665)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in 1 file to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in 4 files to reduce function lengths (#620)

- *(slm-server)* Extract helpers from trigger_node_sync (#665)

- *(functions)* Extract methods in 4 files to reduce function lengths (#620)

- *(functions)* Extract methods in 4 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 4 files to reduce function lengths (#620)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in 2 files to reduce function lengths (#620)

- *(functions)* Extract methods in 12 files to reduce function lengths (#620)

- *(functions)* Extract methods in 8 files to reduce function lengths (#620)

- *(functions)* Extract methods in 4 files to reduce function lengths (#620)

- *(functions)* Extract methods in 8 files to reduce function lengths (#620)

- *(functions)* Extract methods in 7 files to reduce function lengths (#620)

- *(functions)* Extract methods in 4 files to reduce function lengths (#620)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in 4 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 4 files to reduce function lengths (#620)

- *(functions)* Extract methods in 3 files to reduce function lengths (#620)

- *(functions)* Extract methods in 2 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 4 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in temporal_knowledge_manager.py (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 3 files to reduce function lengths (#620)

- *(functions)* Extract methods in 4 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in 3 files to reduce function lengths (#620)

- *(functions)* Extract methods in 2 files to reduce function lengths (#620)

- *(functions)* Extract methods in 3 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 3 files to reduce function lengths (#620)

- *(functions)* Extract methods in 3 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in 2 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in 2 files to reduce function lengths (#620)

- *(functions)* Extract methods in 2 files to reduce function lengths (#620)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in 3 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 5 files to reduce function lengths (#620)

- *(functions)* Extract methods in 4 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 3 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 6 files to reduce function lengths (#620)

- *(functions)* Extract methods in 4 files to reduce function lengths (#620)

- *(code-quality)* Batch 60 - Extract Method refactoring (#620)

- *(code-quality)* Batch 59 - Extract Method refactoring (#620)

- *(code-quality)* Batch 58 - Extract Method refactoring (#620)

- *(code-quality)* Batch 57 - Extract Method refactoring (#620)

- *(code-quality)* Batch 56 - Extract Method refactoring (#620)

- *(code-quality)* Batch 55 - Extract Method refactoring (#620)

- *(code-quality)* Batch 54 - Extract Method refactoring (#620)

- *(#749)* Extract helpers from updateLineBuffer for readability

- *(code-quality)* Batch 53 - Extract Method refactoring (#620)

- *(code-quality)* Batch 52 - Extract Method refactoring (#620)

- *(code-quality)* Batch 51 - Extract Method refactoring (#620)

- *(code-quality)* Batch 50 - Extract Method refactoring (#620)

- *(code-quality)* Batch 49 - Extract Method refactoring (#620)

- *(code-quality)* Batch 48 - Extract Method refactoring (#620)

- *(api)* Migrate generate_request_id to request_utils (#751)

- *(api)* Migrate chat_improved to use request_utils (#751)

- *(code-quality)* Batch 47 - Extract Method refactoring (#620)

- *(code-quality)* Batch 46 - Extract Method refactoring (#620)

- *(code-quality)* Batch 45 - Extract Method refactoring (#620)

- *(code-quality)* Batch 44 - Extract Method refactoring (#620)

- *(#620)* Batch 42 - refactoring of 7 functions

- *(#620)* Batch 41 - refactoring of 12 functions

- *(#620)* Batch 40 - refactoring of 13 functions

- *(#620)* Batch 39 - refactoring of 13 functions

- *(#620)* Batch 38 - refactoring of 15 functions

- *(code-intelligence)* Update cross-language detector and services

- *(#620)* Batch 37 - refactoring of 14 functions

- *(#620)* Batch 36 - refactoring of 15 functions

- *(#620)* Batch 35 - parallel refactoring of 15 functions

- *(#751)* Consolidate command execution utilities - Phase 2

- *(#620)* Batch 34 - parallel refactoring of 18 functions

- *(#620)* Batch 33 - parallel refactoring of 16 functions

- *(code-quality)* Extract helpers from RBAC decorators and GPU search (#620)

- *(code-quality)* Extract helpers from cache_response and calculate_keyword_score (#620)

- *(#620)* Extract helpers from _process_single_llm_iteration and advance_phase

- *(#620)* Extract helpers from _analyze_single_file and _build_correlation_section

- *(#620)* Extract helpers from _find_semantic_duplicates_async and analyze_prompt

- *(#620)* Extract helpers from get_model_comparison and _select_categories_for_intent

- *(code-quality)* Extract helpers for secrets/config-duplicates functions (#620)

- *(code-quality)* Extract helpers for precommit/scanner functions (#620)

- *(code-quality)* Extract helpers for duplicates/config functions (#620)

- *(code-quality)* Extract helpers and fix linting across modules - batch 20 (#620)

- *(functions)* Extract helpers for stats and log mining (#620)

- *(functions)* Extract helpers for voice and metrics (#620)

- *(functions)* Extract helpers for terminal and metrics (#620)

- *(code-quality)* Extract helpers for unified search and budget status - batch 19 (#620)

- *(code-quality)* Extract helpers for chat and RAG search - batch 18 (#620)

- *(code-quality)* Extract helpers for chain analysis and dir listing - batch 17 (#620)

- *(code-quality)* Extract helpers for checkpoint listing - batch 16 (#620)

- *(code-quality)* Extract helpers for staged file checks - batch 15 (#620)

- *(code-quality)* Extract helpers for optimization settings and conversation processing - batch 14 (#620)

- *(code-quality)* Extract helpers for prometheus and quality metrics - batch 13 (#620)

- *(code-quality)* Extract handlers for websocket and vectorization - batch 12 (#620)

- *(code-quality)* Extract helpers for analytics and terminal websocket - batch 11 (#620)

- *(code-quality)* Extract helpers for LLM provider chat_completion - batch 10 (#620)

- *(code-quality)* Extract helpers for provider, workflow, and metrics - batch 9 (#620)

- *(code-quality)* Extract helpers for recommendations and heartbeat - batch 8 (#620)

- *(code-quality)* Extract helpers from hardware_metrics - batch 7 (#620)

- *(code-quality)* Extract long functions into helpers - batch 6 (#620)

- *(code-quality)* Extract long functions into helpers (#620)

- *(config)* Make LLM config provider-agnostic (#763)

- *(config)* Remove SSOT integration from manager.py (#763)

- *(constants)* Migrate network_constants.py to ConfigRegistry (#763)

- *(constants)* Migrate model_constants.py to ConfigRegistry (#763)

- *(constants)* Migrate redis_constants.py to ConfigRegistry (#763)

- *(ai-integration)* Use env vars for cloud API URLs (#760)

- *(provider-health)* Use env vars for cloud API URLs (#760)

- *(slm-client)* Remove hardcoded URLs, use env vars (#760)

- Consolidate _get_ssot_config() using ConfigRegistry (#763) (#764) ([#764](https://github.com/mrveiss/AutoBot-AI/pull/764))

- *(config)* Migrate defaults.py to ConfigRegistry (#763)

- *(config)* Migrate compat.py to ConfigRegistry (#763)

- Consolidate generate_request_id + add ConfigRegistry (#751) (#762) ([#762](https://github.com/mrveiss/AutoBot-AI/pull/762))

- *(slm)* Archive NodesSettings.vue, consolidate to Fleet Overview (#737)

- *(cache)* Read limits from SSOT config (#743)

- *(multimodal)* Rename unified.py to processor.py (#738)

- *(tests)* Rename tests with naming violations (#738)

- *(memory)* Remove orphaned memory_manager files (#738)

- *(tests)* Remove orphaned tests importing non-existent modules (#738)

- *(multimodal)* Rename unified_multimodal_processor to multimodal_processor_impl (#738)

- *(tests)* Migrate multimodal tests to canonical imports (#738)

- *(tests)* Remove orphaned test_unified_llm_interface_p6 (#738)

- *(tests)* Remove orphaned test_unified_llm_interface (#738)

- *(slm)* Update playbooks for slm-agent service name (#740)

- *(slm)* Rename autobot-agent to slm-agent service (#740)

- *(slm)* Remove duplicate slm-agent Ansible role (#739)

- Remove 6 more orphaned files with naming violations (#694)

- Remove 11 duplicate files with naming violations (#694)

- Fix naming violations and hardcoded values (#694, #738)

- *(frontend)* Use SSOT config for SLM Admin URL

- *(backend)* Add monitoring_hardware stub for backward compatibility

- *(frontend)* Update App.vue navigation

- *(frontend)* Remove infrastructure components from autobot-vue

- *(frontend)* Remove infrastructure routes from autobot-vue

- *(backend)* Update terminal to use SLM API for SSH

- *(backend)* Remove VM services - use slm-server

- *(backend)* Clean monitoring.py - keep only app metrics

- *(backend)* Remove infrastructure monitoring - use slm-server

- *(backend)* Remove infrastructure services/models - layer separation

- *(backend)* Remove infrastructure APIs - use slm-server

- *(backend)* Remove ansible_executor - SLM handles deployments

- *(backend)* Remove SSH services - SLM handles all SSH

- *(backend)* Remove api/slm/ routes - use slm-server directly

- *(backend)* Remove services/slm/ - moved to slm-server

- *(slm)* Code review fixes for blue-green deployment (#726)

- *(slm)* Handle all SLM services in restart-all operation (#725)

- *(scripts)* Complete SSOT migration for sync-all-vms.sh (#694)

- *(scripts)* Use SSOT config in utility and monitoring scripts (#694)

- *(scripts)* Use SSOT config in VM management scripts (#694)

- *(llm)* Use SSOT for Ollama URL in unified interface (#694)

- *(config)* Use SSOT helpers for Ollama URLs (#694)

- *(llm)* Use SSOT for Ollama URL in unified interface (#694)

- *(config-manager)* Use SSOT for Ollama URL (#694)

- *(config)* Use SSOT for infrastructure config (#694)

- *(user-mgmt)* Use SSOT config for postgres host (#694)

- *(pki)* Use SSOT config for VM definitions (#694)

- *(slm)* Integrate Blue-Green as tab in Deployments view (#726)

- Implement dependency injection for core components

- Improve code readability with explanatory comments and documentation

- Consolidate duplicated terminal WebSocket implementations

- Systematic flake8 code quality cleanup - progress on main.py, llm_interface.py, orchestrator.py

- Systematic flake8 code quality cleanup - progress on main.py, llm_interface.py, orchestrator.py

- Eliminate Redis client code duplication with centralized utility

- *(slm-admin)* Split SettingsView into modular components (#726)

- *(memory)* Split autobot_memory_graph.py into modular package (#716)

- Remove unified_ prefix violations and consolidate wrappers (#714)

- Replace repair/agent naming with functional names (#708)

- Remove issue numbers from test file names (#708)

- Remove remaining _correction suffix violations (#708)

- Replace _correction/_corrector with proper names (#708)

- Rename remaining FIX/fix_ naming violations (#708)

- Rename files with _combined, _RESOLUTION, fix_ violations (#708)

- Rename files with forbidden naming suffixes (#708)

- *(scripts)* Rename JS files with forbidden _fix suffix (#708)

- *(tests)* Rename files with forbidden naming suffixes (#708)

- *(api)* Consolidate knowledge sub-routers into knowledge.py (#708)

- *(api)* Rename knowledge_search_unified to knowledge_search_combined (#708)

- *(api)* Rename knowledge files with forbidden suffixes (#708)

- *(api)* Consolidate files with forbidden naming suffixes (#708)

- *(core)* Extract helper methods from 3 functions - Batch 70 (#665)

- *(core)* Extract helper methods from 3 high-priority functions - Batch 69 (#665)

- *(core)* Extract helper methods from 4 functions - Batch 68 (#665)

- *(core)* Extract helper methods from 4 functions - Batch 67 (#665)

- *(core)* Extract helper methods from 5 functions - Batch 66 (#665)

- *(core)* Extract helper methods from 6 functions - Batch 65 (#665)

- *(core)* Extract helper methods from 5 functions - Batch 64 (#665)

- *(core)* Extract helper methods from 6 functions - Batch 63 (#665)

- *(core)* Extract helper methods from 4 functions - Batch 62 (#665)

- *(core)* Extract helper methods from 6 functions - Batch 61 (#665)

- *(core)* Extract helper methods from 6 functions - Batch 60 (#665)

- *(metrics)* Extract helper methods from _init_metrics functions (#665)

- *(issue-665)* Extract helpers in ownership, fact_extraction; fix async Redis (#665)

- *(code-quality)* Extract helper methods batch 53 (#665)

- *(metrics)* Extract helper methods from long functions (Batch 52) (#665)

- *(metrics)* Extract helper methods from long functions (Batch 51) (#665)

- *(codebase)* Extract helpers from timeout_migration, report, and ownership (#665)

- *(operations)* Extract helpers from long_running_operations and knowledge_tasks (#665)

- *(timeout)* Extract helper methods from migrate functions (#665)

- *(analytics)* Extract helper methods from long functions (#665)

- *(metrics)* Extract helper methods from _init_metrics functions (#665)

- *(functions)* Issue #665 Batches 39-41 - Parallel refactoring of 6 long functions (#665)

- *(functions)* Issue #665 Batches 36-38 - Parallel refactoring of 6 long functions (#665)

- *(functions)* Issue #665 Batches 33-35 - Parallel refactoring of 6 long functions (#665)

- *(functions)* Issue #665 Batches 30-32 - Parallel refactoring of 6 long functions (#665)

- *(functions)* Issue #665 Batches 27-29 - Parallel refactoring of 6 long functions (#665)

- *(functions)* Issue #665 Batches 24-26 - Parallel refactoring of 6 long functions (#665)

- *(functions)* Issue #665 Batches 21-23 - Parallel refactoring of 6 long functions (#665)

- *(functions)* Issue #665 Batches 18-20 - Parallel refactoring of 6 long functions (#665)

- *(functions)* Issue #665 Batches 15-17 - Parallel refactoring of 6 long functions (#665)

- *(pki,knowledge)* Extract helpers from _distribute_to_vm and import_knowledge_with_tracking (#665)

- *(pki,npu)* Extract helpers for Issue #665 Batch 13

- *(#665)* Extract helpers from execute_step and orchestrate_execution

- *(#665)* Extract helpers from handle_query and _generate_service_cert

- *(redis)* Remove unused RedisDatabaseManager from analysis script (#692)

- *(redis)* Migrate RedisDatabaseManager to get_redis_client() (#692)

- *(constants)* Migrate RAG max_results to QueryDefaults.RAG_DEFAULT_RESULTS (#694)

- *(constants)* Migrate page_size and knowledge_limit defaults (#694)

- *(constants)* Migrate offset defaults to QueryDefaults.DEFAULT_OFFSET (#694)

- *(constants)* Migrate additional files to centralized constants (#694)

- *(constants)* Migrate chat_enhanced.py role to CategoryDefaults (#694)

- *(constants)* Migrate more files to use QueryDefaults/CategoryDefaults (#694)

- *(settings)* Move Services and Hardware to Infrastructure subtabs

- *(functions)* Batch 50 - Extract helpers from 3 long functions (#665)

- *(functions)* Batch 49 - Extract helpers from 3 long functions (#665)

- *(functions)* Batch 48 - Extract helpers from 4 long functions (#665)

- *(functions)* Batch 47 - Extract helpers in chat_sessions.py and memory.py (#665)

- *(functions)* Batch 46 - Extract export helpers in environment.py (#665)

- *(functions)* Batch 45 - Extract activity helpers in chat_sessions.py (#665)

- *(functions)* Batch 44 - Extract helpers in ide_integration.py and infrastructure.py (#665)

- *(functions)* Batch 43 - Extract helpers in structured_thinking_mcp.py (#665)

- *(functions)* Batch 42 - Extract helpers from 2 backend/api files (#665)

- *(functions)* Batch 41 - Extract helpers from 2 backend/api files (#665)

- *(functions)* Batch 40 - Extract helpers from 2 backend/api files (#665)

- *(functions)* Batch 39 - Extract helpers from terminal_handlers.py (#665)

- *(functions)* Batch 38 - Extract helpers in code_intelligence.py (#665)

- *(functions)* Batch 37 - Extract helpers in analytics_cfg.py (#665)

- *(functions)* Batch 36 - Extract helpers in analytics_quality.py (#665)

- *(functions)* Batch 35 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 34 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 33 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 32 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 31 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 30 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 29 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 28 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 27 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 26 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 25 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 24 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 23 - Extract helpers from 2 long functions (#665)

- *(knowledge)* Consolidate ManPageManager to single location (#678)

- *(functions)* Batch 21 - Extract helpers from analyze_directory (#665)

- *(functions)* Batch 20 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 19 - Extract helpers from 2 long functions (#665)

- *(frontend)* Replace console statements with structured logging (#676)

- *(functions)* Batch 18 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 17 - Extract helpers from start_component (#665)

- *(functions)* Batch 16 - Extract helpers from 3 long functions (#665)

- *(functions)* Batch 15 - Extract helpers from 2 more long functions (#665)

- *(functions)* Batch 14 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 13 - Extract helpers from 2 long functions (#665)

- *(functions)* Batch 12 - Extract helpers from capture_state_snapshot (#665)

- *(functions)* Extract helpers from 2 security/metrics functions (#665)

- *(functions)* Extract helpers from 2 more functions (#665)

- *(analyzer)* Extract bottleneck creation helper (#665)

- *(functions)* Extract helpers from 2 more long functions (#665)

- *(facts)* Extract helper from delete_facts_by_session (#665)

- *(constants)* Centralize status enums and reduce config duplicates (#670)

- *(functions)* Extract helper from detect_injection (#665)

- *(functions)* Extract helpers from _configure_llama_index and search (#665)

- *(analysis)* Extract helpers from analyze() and advanced_search() (#665)

- *(security)* Extract pattern-checking helpers from _regex_analysis (#665)

- *(bug-predictor)* Extract _compute_prediction_stats helper (#665)

- *(functions)* Extract helpers from 3 more long functions (#665)

- *(functions)* Extract helpers from 2 more long functions (#665)

- *(functions)* Extract helpers from 3 long functions (#665)

- *(monitoring)* Extract helper methods from long functions (#665)

- *(functions)* Batch 4 - Long function decomposition (#620)

- *(functions)* Batch 3 - Long function decomposition (#620)

- *(agents)* Migrate 3 agents to use SSOT agent-specific config (#599)

- *(config)* Use SSOT for Redis config and fix Ollama endpoint path

- Extract helper functions from 5 long functions (#620)

- Split 5 long functions using Extract Method pattern (#620)

- *(config)* Consolidate config.yaml to user preferences only (#639)

- *(monitoring)* Remove legacy monitoring_alerts in favor of Prometheus AlertManager (#69)

- *(router)* Streamline Monitoring for OpenTelemetry migration (#546)

- *(router)* Remove orphaned analytics routes from monitoring (#546)

- *(core)* Decompose remaining 100+ line functions (#560)

- *(codebase-analytics)* Decompose long functions into helpers (#560)

- *(api)* Consolidate duplicate monitoring endpoints (#532)

- *(frontend)* Update navigation labels and remove redundant tabs (#546)

- *(frontend)* Separate BI into dedicated view with nested routes (#546)

- *(monitoring)* Rename phase9 references to autobot (#76)

- *(api)* Extract helper functions for DRY compliance (#484)

- *(api,agents)* Extract helpers from analytics modules and agents (#398)

- Extract helpers and reduce code complexity across multiple modules (#398)

- *(security,chat)* Extract helpers from threat analyzer, safety guards, and session (#398)

- *(agents,services)* Extract helpers from RAG agent and Ansible executor (#398)

- *(memory,agents)* Extract helpers from memory graph and knowledge agent (#398)

- Extract helpers and reduce code complexity across multiple modules (#398)

- *(knowledge)* Extract helpers from 6 long methods (#398)

- *(utils)* Extract helpers from multimodal performance monitor (#398)

- *(security,services)* Extract helpers from threat analyzer and invalidation service (#398)

- *(judges,services)* Extract helpers from security risk judge and redis service (#398)

- *(utils)* Extract GPU optimization passes and metrics helpers (#398)

- *(security)* Extract Memory MCP entity creation helpers (#398)

- *(core)* Extract helpers from 3 more long methods (#398)

- *(api)* Extract helpers from 2 API endpoint handlers (#398)

- *(core)* Extract helpers from 4 long methods (#398)

- *(agents,rag)* Extract helpers from 2 core modules (#398)

- *(core)* Extract helpers from 3 core modules (#398)

- *(tasks)* Extract _store_man_pages_to_kb helper (#398)

- *(tools)* Extract helpers from analyze_duplicates.py (#398)

- *(monitoring,api)* Extract helpers from long methods (#398)

- *(api)* Extract helpers from long chat.py methods (#398)

- *(knowledge)* Extract helpers from bulk.py long methods (#398)

- *(knowledge)* Extract helpers from 16 long methods (#398)

- *(knowledge)* Re-apply stats.py method extraction (#398)

- *(knowledge)* Extract helpers from long categories.py methods (#398)

- *(knowledge)* Extract helpers from long stats.py methods (#398)

- *(knowledge)* Improve stats.py logging format and refactor get_data_quality_metrics (#398)

- *(stats)* Extract helpers for get_data_quality_metrics (#398)

- *(knowledge)* Extract helper functions for code quality (#398)

- *(issue-398)* Reduce long methods in knowledge.py

- *(issue-398)* Reduce long methods in analyzers.py

- *(issue-398)* Reduce long methods in service_monitor.py

- *(issue-398)* Extract helpers in enterprise_features.py

- *(issue-398)* Extract helpers and constants in files.py

- *(issue-398)* Extract helpers to reduce method lengths in memory.py

- *(issue-398)* Extract helpers from graph_rag.py API endpoints

- *(issue-398)* Reduce long methods in codebase_analytics/scanner.py

- *(issue-398)* Reduce long methods in desktop_streaming_manager.py and knowledge_population.py

- *(frontend)* Split oversized Vue components into sub-components (#184)

- *(issue-399)* Reduce long parameter list in _build_session_data

- *(issue-372)* Reduce feature envy patterns in core modules

- *(issue-381)* Extract model_optimizer.py into model_optimization package (#381)

- *(issue-381)* Extract agent_orchestrator.py into agent_orchestration package (#381)

- *(issue-381)* Extract gpu_acceleration_optimizer.py into gpu_optimization package (#381)

- *(issue-381)* Extract enhanced_multi_agent_orchestrator into focused package (#381)

- *(issue-381)* Extract error_boundaries.py into focused package (#381)

- *(issue-381)* Extract search.py into search_components package (#381)

- *(issue-381)* Extract long_running_operations_framework into focused package (#381)

- *(issue-381)* Consolidate orchestrator.py types with orchestration package (#381)

- *(issue-381)* Extract enhanced_orchestrator into focused package (#381)

- *(issue-381)* Integrate helpers into DocGenerator class (#381)

- *(issue-381)* Extract chat_knowledge_service into focused package (#381)

- *(issue-381)* Extract llm_code_generator into focused package (#381)

- *(issue-381)* Extract conversation_flow_analyzer into focused package (#381)

- *(issue-381)* Extract computer_vision_system into focused package (#381)

- *(issue-381)* Extract performance_analyzer into focused package (#381)

- *(issue-381)* Extract workflow_templates.py into focused package (#381)

- *(issue-381)* Extract enhanced_kb_librarian into focused package (#381)

- *(issue-381)* Extract llm_interface and voice_processing into focused packages (#381)

- *(issue-381)* Extract enhanced_project_state_tracker into focused package (#381)

- *(issue-381)* Extract unified_multimodal_processor into focused package (#381)

- *(issue-381)* Extract threat_detection into focused package (#381)

- *(issue-381)* Extract context_aware_decision_system into focused package (#381)

- *(issue-381)* Extract god classes into focused packages (#381)

- *(issue-281)* Session 60 - Extract helpers from system_monitor and zero_downtime_deploy (#281)

- *(issue-281)* Extract helpers from create_incremental_backup and index_document

- *(issue-281)* Extract helpers from sync_docs and parse_and_store_tool_output

- *(issue-281)* Extract helpers from security report generators (#281)

- *(issue-281)* Extract helpers from generate_report (205→30 lines) (#281)

- *(issue-281)* Extract helpers from sync, migration, and test scripts (#281)

- *(commands)* Extract static data to module constants (#281)

- *(workflow_classifier)* Extract classification constants (#281)

- *(scripts)* Convert print() to logger in analyze_duplicates and monitoring_dashboard (#281)

- *(scripts)* Extract helpers from KB reset and monitoring (#281)

- *(analytics)* Extract demo/fallback data constants (#281)

- *(analytics)* Improve code review module structure (#281)

- *(scripts)* Extract CSS from generate_dashboard_html (#281)

- *(scripts)* Extract helpers and fix logging standards (#281)

- *(anti_pattern)* Extract anti-pattern type definitions (#281)

- *(ingest_man_pages)* Extract command list constants (#281)

- *(code_intelligence)* Extract Redis optimization type definitions (#281)

- *(issue-281)* Session 52 - Extract dashboard, test, and workflow helpers

- *(api)* Extract VNC_MCP_TOOL_DEFINITIONS constant (#281)

- *(api)* Extract SEQUENTIAL_THINKING_MCP_TOOL_DEFINITION (#281)

- *(core)* Extract DATABASE_SCHEMA constants (#281)

- *(issue-281)* Session 51 - Extract report and service status helpers

- *(api)* Extract DEMO_PREDICTION_FILES constant (#281)

- *(imports)* Remove 10 unused imports (F401)

- *(api)* Extract STRUCTURED_THINKING_MCP_TOOL_DEFINITIONS constant (#281)

- *(prometheus-mcp)* Extract MCP tool definitions to constant (#281)

- *(code-search)* Extract search examples to module constant (#281)

- *(code-intel)* Extract pattern types to module constant (#281)

- *(issue-281)* Session 50 - Extract helpers from dashboard/report generators

- *(security)* Extract injection patterns to module constants (#281)

- *(agent)* Extract agent capabilities to module constant (#281)

- *(session-49)* Extract helpers for verify_installation and export_grafana_dashboard (#281)

- *(routers)* Data-driven monitoring router loading (#281)

- Issue #281 - Extract helpers and add API docstrings

- *(search)* Issue #375 - Reduce long parameter lists with context dataclasses

- *(knowledge)* Extract _format_knowledge_entry helper (#281)

- *(scanner)* Extract helpers from scan_codebase (#281)

- *(scripts)* Extract print helpers from analyze_frontend_code (#281)

- *(functions)* Extract data and print helpers (#281)

- *(search)* Extract 6 helpers from enhanced_search_v2 (#281)

- *(routers)* Convert router loading to data-driven pattern (#281)

- *(logging)* Complete Issue #391 logging fixes and #380 optimizations

- *(fix-agents)* Complete print() to logger conversion (#391)

- *(fix-agents)* Convert print() to logger in playwright_security_fixer

- *(fix-agents)* Update playwright_security_fixer

- *(scripts)* Extract helpers from long analysis functions (#281)

- *(backend)* Improve database, knowledge MCP, and SSH services (#392)

- *(batch)* Accumulated refactoring changes (#392)

- Fix message chain violations with helper methods (#321)

- *(document_extractors)* Extract helpers for extract_from_directory (#281)

- *(workflow_templates)* Extract step definitions (#281)

- *(encoding_utils)* Extract helpers for is_terminal_prompt (#281)

- *(model_optimizer)* Extract helpers from get_optimization_suggestions (#281)

- *(monitoring_alerts)* Extract alert rule helpers from _load_default_rules (#281)

- *(tool_selector)* Extract tool mapping helpers from _initialize_tool_mappings (#281)

- *(orchestrator)* Extract helpers from process_user_request (#281)

- *(conversation)* Extract helpers from process_user_message (#281)

- *(streaming_executor)* Extract helpers from execute_with_streaming (#281)

- *(llm)* Extract helpers from _ollama_chat_completion (#281)

- *(desktop-streaming)* Extract helpers from create_session (#281)

- *(graph-entity)* Extract helpers from extract_and_populate (#281)

- *(web-research)* Extract helpers from conduct_research (#281)

- *(bug_predictor)* Extract helpers from long functions (#281)

- *(graph_rag_service)* Extract helpers from long functions (#281)

- *(knowledge/search)* Extract helper methods from 6 long functions (#281)

- *(terminal-tool)* Extract helper methods from 5 long functions (#281)

- *(intelligent_agent)* Extract confidence handlers from process_natural_language_goal (#281)

- *(knowledge_extraction)* Extract helpers from extract_facts_from_text (#281)

- *(llm_handler)* Extract helpers from 3 long functions (#281)

- *(chat_workflow/manager)* Extract helper methods from long functions (#281)

- *(service_discovery)* Extract helper methods from long functions (#281)

- *(domain_security)* Extract helper methods from long validation functions (#281)

- *(input_validator)* Extract helper methods from long validation functions (#281)

- *(enterprise_feature_manager)* Extract helpers from large functions (#281)

- *(command_manual_manager)* Extract helpers from large functions (#281)

- *(command_validator)* Extract helpers from _init_whitelist (#281)

- *(security)* Extract helper methods from security_policy_manager.py (#281)

- *(security)* Extract helper methods from conduct_secure_research (#281)

- *(langchain)* Extract helper methods from _create_tools and __init__ (#281)

- *(config)* Extract helper functions from get_default_config (#281)

- *(file-manager)* Extract helpers from all long functions (#281)

- *(operation-timeout)* Extract helpers from long functions (#281)

- *(code-quality)* Extract helper methods from system_knowledge_manager.py (#281)

- *(code-quality)* Extract helper methods from phase_progression_manager.py (#281)

- *(code-quality)* Extract helper methods from 3 more long functions (#281)

- *(code-quality)* Extract helper methods from long functions (#281)

- Async optimizations and code quality improvements (#315, #358, #361, #379)

- *(code-analysis)* Reduce deeply nested code in analyzers (#340)

- Fix Feature Envy in 5 more files - Phase 2 (#312)

- Fix Feature Envy code smells in 5 high-priority files (#312)

- Modularize oversized files and reduce coupling (#286, #290, #294)

- Add parameter object dataclasses to reduce long parameter lists (#319)

- *(constants)* Replace magic numbers with named constants (#318)

- *(payload)* Extract is_empty_value helper function (#328)

- *(validation)* Add injection pattern detection for session IDs (#328)

- *(validation)* Create shared path_validation utility (#328)

- *(#342)* Refactor ChatHistoryManager into modular mixin-based package

- *(#342)* Archive legacy chat_workflow_manager.py

- *(#286)* Split large files into modular architecture

- *(monitoring)* Reduce nesting depth in monitoring/ directory (#339)

- *(scripts)* Reduce nesting depth in scripts/ directory (#338)

- *(middleware)* Extract helpers to reduce nesting depth (#337)

- *(backend/api)* Add agent query dispatch table (#336)

- *(backend/api)* Extract relation processing helpers (#336)

- *(backend/api)* Extract dispatch tables for reduced nesting (#336)

- *(backend/api)* Extract helpers for log collection (#336)

- *(backend/api)* Extract helpers to reduce nesting depth (#336)

- *(backend)* Extract helpers to reduce nesting depth (#336)

- *(code_intelligence)* Extract helpers to reduce nesting depth (#335)

- *(agents)* Reduce nesting depth to ≤4 in 6 agent files (#334)

- *(agents)* Extract response content helpers in 4 agents (#334)

- *(agents)* Reduce nesting depth in 8 agent files (#334)

- *(agents)* Reduce nesting depth in src/agents/ modules (#334)

- *(utils)* Reduce nesting depth in src/utils/ modules (#333)

- *(chat_workflow)* Reduce nesting depth across all modules (#332)

- *(src)* Complete Issue #331 - Reduce nesting in core modules

- *(src)* Reduce deeply nested code in core modules (#331)

- *(backend)* Reduce deeply nested code in backend/api (#330)

- Consolidate ai_stack_integration.py duplicates (#292)

- Eliminate duplicate code patterns in response helpers and agent selection (#292)

- *(backend)* Convert print() statements to logging (#304)

- *(frontend)* Batch 26 - Convert console.error to logger in 13 components (#280)

- *(frontend)* Batch 25 - Convert console.error to logger in 4 components (#280)

- *(frontend)* Convert console statements to createLogger in Batch 24 (#280)

- *(frontend)* Convert console.error to logger in CaptchaNotification (#280)

- *(frontend)* Convert console statements to createLogger in Batch 23 (#280)

- *(frontend)* Convert console statements to createLogger in Batch 22 (#280)

- *(frontend)* Convert console statements to createLogger in Batch 21 (#280)

- *(utils)* Convert console statements to logger in Batch 20 (#280)

- *(api)* Convert console statements to logger in Batch 19 (#280)

- *(composables)* Convert console statements to logger in Batch 18 (#280)

- *(frontend)* Convert console statements to logger in Batch 17 (#280)

- *(frontend)* Convert console statements to logger in Batch 16 (#280)

- *(frontend)* Convert console statements to logger in Batch 15 (#280)

- *(frontend)* Convert console statements to logger in Batch 14 (#280)

- *(frontend)* Convert console statements to logger in Batch 13 (#280)

- *(frontend)* Convert console statements to logger in Batch 12 (#280)

- *(frontend)* Convert console statements to logger in Batch 11 (#280)

- *(frontend)* Convert console statements to logger in Batch 10 (#280)

- *(frontend)* Convert console statements to logger in Batch 9 (#280)

- *(frontend)* Convert console statements to structured logger in settings/voice components (#280)

- *(frontend)* Convert console statements to structured logger in Vue components (#280)

- *(frontend)* Replace console statements in utils (#280)

- *(frontend)* Replace console statements in repositories and utils (#280)

- *(frontend)* Replace console statements in composables and services (#280)

- *(frontend)* Replace console statements in TypeScript utils (#280)

- *(frontend)* Replace console statements in composables (#280)

- *(frontend)* Replace console statements with createLogger (#280)

- *(logging)* Convert debug print statements to proper logging (#280)

- *(frontend)* Improve Vue components error handling and chart safety

- *(knowledge-base)* Enhance knowledge base with improved queries

- *(scripts)* Update scripts for ModelConstants compatibility (#261)

- *(backend)* Update backend configuration and services

- *(frontend)* Remove hardcoded model names from frontend services

- *(agents)* Update agents to use centralized ModelConstants (#261)

- *(models)* Improve ModelConstants as single source of truth (#261)

- *(config)* Remove deprecated AUTOBOT_OLLAMA_MODEL from .env.example (#261)

- *(models)* Additional ModelConstants consolidation (#261)

- *(ports)* Consolidate service_discovery ports to NetworkConstants (#262)

- *(ports)* Consolidate hardcoded ports to NetworkConstants (#262)

- *(models)* Consolidate hardcoded model references to ModelConstants (#261)

- *(ports)* Consolidate hardcoded ports to NetworkConstants (#262)

- *(api)* Migrate to lazy_singleton pattern (#253)

- *(knowledge)* Improve knowledge and memory API robustness

- *(chat)* Improve chat session handling and history management

- *(config)* Update unified config manager for chat knowledge integration

- *(monitoring)* Extract HardwareMonitor to monitoring_hardware.py (#185)

- *(terminal)* Extract tool management to terminal_tools.py (#185)

- *(analytics)* Extract AnalyticsController to analytics_controller.py (#212)

- *(monitoring)* Extract utility functions to monitoring_utils.py (#185)

- *(chat)* Extract session management to chat_sessions.py (#185)

- *(analytics)* Split analytics.py into monitoring and code modules (#185)

- *(knowledge)* Extract maintenance endpoints to knowledge_maintenance.py (#185)

- *(terminal)* Extract handler classes to terminal_handlers.py (#210)

- *(knowledge)* Extract population endpoints to knowledge_population.py (#209)

- *(knowledge)* Extract search endpoints to knowledge_search.py (#209)

- *(knowledge)* Extract tags and vectorization endpoints (#209)

- *(api)* Extract models from analytics.py (#185)

- *(api)* Extract models from terminal.py (#185)

- *(api)* Extract Pydantic models from knowledge.py (#185)

- *(config)* Replace remaining hardcoded model names (#92)

- *(core)* Replace hardcoded model names with ModelConstants (#92)

- *(agents)* Replace hardcoded model names with ModelConstants (#92)

- *(config)* Use ModelConstants for fallback model (#92)

- *(config)* Add Redis connection config constants (#92)

- *(config)* Centralize hardcoded model/RAG constants (#92)

- *(debug)* Extract frontend analysis library (#148)

- *(types)* Replace Dict[str, Any] with semantic Metadata type (#187)

- *(redis-service)* Convert to singleton pattern (#205)

- *(knowledge)* Apply Metadata type alias for type safety (#187)

- *(api)* Improve type safety in RAG and hot-reload modules (#187)

- *(api)* Improve type safety across 9 API modules (#187)

- *(http)* Migrate 10 core files to HTTPClient singleton (#66)

- *(api)* Improve type safety in vision.py and database_mcp.py (#187)

- *(api)* Replace Dict[str, Any] with Metadata/JSONObject types (#187)

- *(chat-knowledge)* Replace Dict[str, Any] with Metadata type (#187)

- *(analytics)* Replace Dict[str, Any] with Metadata in models (#187)

- *(mcp-registry)* Replace Dict[str, Any] with Metadata type (#187)

- *(http-client)* Migrate 6 files to HTTPClient singleton (#66)

- *(frontend)* Migrate WebResearchSettings to centralized Pinia store (#170)

- *(constants)* Consolidate network constants into single TypeScript implementation (#172)

- Eliminate hardcoding violations and centralize constants

- *(tests)* Migrate architecture tests to use NetworkConstants and get_redis_client() (#89)

- *(analysis)* Use NetworkConstants in refactoring test script (#90)

- Extract workflow UI utilities and refactor components (Phase 2) (#147)

- Use HTML dashboard utilities in validation_dashboard_generator.py (Phase 1d) (#146)

- Use HTML dashboard utilities in scripts/performance_dashboard.py (Phase 1c) (#146)

- *(frontend)* Eliminate hardcoded IP addresses - create NetworkConstants (#90)

- Use HTML dashboard utilities in performance dashboard (Phase 1b) (#146)

- *(redis)* Migrate distributed_redis_client to canonical pattern and document health check exceptions (#89)

- *(config)* Remove self-referencing import from old unified_config (#63)

- *(code-quality)* Fix remaining bare except in semantic_chunker.py

- *(code-quality)* Replace bare except clauses with except Exception

- *(security)* Replace command_executor.py with deprecation redirect

- *(cache)* Replace knowledge_cache.py with deprecation redirect

- *(config)* Complete Phase 4 - Archive old config files and remove warnings (#63)

- Migrate 12 production files from unified_config to unified_config_manager (#63)

- *(src)* Migrate memory_manager_async.py from unified_config to unified_config_manager (#63)

- *(config)* Migrate remaining tools and test scripts to unified_config (#63)

- *(monitoring)* Migrate performance_monitor.py from unified_config to unified_config_manager (#63)

- *(config)* Complete Phase 3 config migration (#63)

- *(scripts)* Migrate validate_timeout_config.py from unified_config to unified_config_manager (#63)

- *(scripts)* Migrate verify_knowledge_consistency.py from unified_config to unified_config_manager (#63)

- *(backend)* Migrate error_monitoring.py from unified_config to unified_config_manager (#63)

- *(backend)* Migrate analytics.py from unified_config to unified_config_manager (#63)

- *(config)* Migrate scripts to unified_config (#63)

- *(backend)* Migrate llm_optimization.py from unified_config to unified_config_manager (#63)

- *(config)* Migrate src/utils files to unified_config (#63)

- *(config)* Migrate src core files to unified_config (#63)

- *(backend)* Migrate infrastructure_monitor.py from unified_config to unified_config_manager (#63)

- *(config)* Migrate research_browser.py and service_monitor.py to unified_config (#63)

- *(config)* Migrate playwright.py to unified_config (#63)

- *(tests)* Migrate test_timeout_configuration.py from unified_config to unified_config_manager (#63)

- *(config)* Migrate llm_optimization.py to unified_config (#63)

- *(config)* Migrate infrastructure_monitor.py to unified_config (#63)

- *(utils)* Migrate knowledge_base_timeouts.py from unified_config to unified_config_manager (#63)

- *(src)* Migrate llm_interface.py from unified_config to unified_config_manager (#63)

- *(src)* Migrate knowledge_base.py from unified_config to unified_config_manager (#63)

- *(config)* Migrate error_monitoring.py to unified_config (#63)

- *(src)* Migrate knowledge_base_factory.py from unified_config to unified_config_manager (#63)

- *(config)* Migrate cache.py - remove unused config_helper import (#63)

- *(src)* Migrate chat_workflow_manager.py from unified_config to unified_config_manager (#63)

- *(config)* Migrate analytics.py to unified_config (#63)

- *(src)* Migrate chat_history_manager.py from unified_config to unified_config_manager (#63)

- *(src)* Migrate autobot_memory_graph.py from unified_config to unified_config_manager (#63)

- *(src)* Migrate auth_middleware.py from unified_config to unified_config_manager (#63)

- *(backend)* Migrate celery_app.py from unified_config to unified_config_manager (#63)

- *(backend)* Migrate app_factory.py from unified_config to unified_config_manager (#63)

- *(backend)* Migrate system.py from unified_config to unified_config_manager (#63)

- *(backend)* Migrate llm.py from unified_config to unified_config_manager (#63)

- *(config)* Migrate tools and scripts to unified_config (#142)

- *(http)* Migrate 4 utility files to HTTPClient singleton (#66)

- *(http)* Migrate 4 core files to HTTPClient singleton (#66)

- *(chat)* Complete Issue #40 Phase 4 - Archive orphaned config updater and finalize documentation

- *(chat)* Phase 2 - Extract intent detection module from chat_workflow_manager (Issue #40)

- *(chat)* Phase 1 - Extract reusable utilities to eliminate duplication (Issue #40)

- *(chat)* Archive 3 orphaned chat consolidation files (Issue #40 Quick Win)

- *(logging)* Migrate 6 core files to centralized LoggingManager (Issue #42)

- *(naming)* Rename test_race_condition_fixes.py → test_concurrency_safety.py (Issue #35)

- *(naming)* Delete 11 obsolete test/script files with forbidden naming patterns (Issue #35)

- *(naming)* Delete obsolete llm_interface_fixed.py.backup (Issue #35)

- *(naming)* Rename optimized_memory_manager → adaptive_memory_manager and optimized_stream_processor → llm_stream_processor (Issue #35)

- *(naming)* Delete 5 obsolete _optimized files with 0 imports (Issue #35)

- *(naming)* Rename performance_optimized_timeouts → adaptive_timeouts (Issue #35)

- *(naming)* Rename semantic_chunker_gpu_optimized → semantic_chunker_gpu (Issue #35)

- *(knowledge)* Consolidate 3 knowledge managers via composition + facade pattern (Phase 6 - 10/10)

- *(memory)* Phase 5 improvements - Achieve 10/10 code quality score

- *(memory)* Phase 5 - Consolidate 5 memory managers into unified implementation (49% reduction)

- *(redis)* Complete P3 cleanup - remove deprecated redis_pool_manager.py

- *(cache)* Archive deprecated cache managers (P4 cleanup)

- *(cache)* Phase 4 - Cache Managers Consolidation (3→1 unified manager)

- *(redis)* Phase 3 - Cleanup deprecated redis_pool_manager files

- *(config)* Phase 2 - Consolidate config managers into unified_config_manager.py

- *(redis)* Consolidate 5 Redis managers into enhanced canonical client (P1 complete)

- *(terminal)* Complete terminal consolidation - Phase 1 & 2

- *(error-handling)* Phase 3 - core service layer error boundary integration

- *(frontend)* Migrate batch 68 RumDashboards to useAsyncOperation (Priority 1 COMPLETE)

- *(error-handling)* Migrate batch 175b - fix decorator order for 302 endpoints (BACKEND MIGRATION COMPLETE)

- *(error-handling)* Migrate batch 175a - add missing @with_error_handling decorators

- *(error-handling)* Migrate batch 174 app factory endpoints to @with_error_handling

- *(error-handling)* Migrate batch 173 endpoints to @with_error_handling (development_speedup.py COMPLETE - 100%)

- *(frontend)* Migrate batch 67 connection status to BaseButton

- *(frontend)* Migrate batch 66 MCP dashboard to BaseButton

- *(error-handling)* Migrate batch 172 endpoints to @with_error_handling (memory.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 171 endpoints to @with_error_handling (multimodal.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 170 endpoints to @with_error_handling (infrastructure.py COMPLETE - 100%)

- *(frontend)* Migrate batch 65 system knowledge manager to BasePanel

- *(error-handling)* Migrate batch 168 endpoints to @with_error_handling (workflow_automation.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 167 endpoints to @with_error_handling (code_search.py COMPLETE - 100%)

- *(frontend)* Migrate batch 64 MCP dashboard to BasePanel

- *(error-handling)* Migrate batch 166 endpoints to @with_error_handling (logs.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 165 endpoints to @with_error_handling (enterprise_features.py COMPLETE - 100%)

- *(frontend)* Migrate batch 63 knowledge stats to BasePanel

- *(error-handling)* Complete batch 164 remote_terminal.py to 100% (WebSocket endpoint)

- *(frontend)* Migrate batch 62 system monitor to BasePanel

- *(error-handling)* Migrate batch 163 endpoints to @with_error_handling (long_running_operations.py COMPLETE - 100%)

- *(frontend)* Migrate batch 61 codebase analytics to BasePanel

- *(error-handling)* Migrate batch 162 endpoints to @with_error_handling (knowledge_mcp.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 161 endpoints to @with_error_handling (llm_optimization.py COMPLETE - 100%)

- *(frontend)* Migrate batch 60 monitoring dashboard to BasePanel

- *(error-handling)* Migrate batch 160 endpoints to @with_error_handling (templates.py COMPLETE - 100%)

- *(frontend)* Migrate batch 59 voice interface to BasePanel

- *(error-handling)* Migrate batch 159 endpoints to @with_error_handling (npu_workers.py COMPLETE - 100%)

- *(frontend)* Migrate batch 58 validation dashboard to BasePanel

- *(error-handling)* Migrate batch 158 endpoints to @with_error_handling (llm_awareness.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 157 endpoints to @with_error_handling (logs.py COMPLETE - 100%)

- *(frontend)* Migrate batch 57 phase status modal to BaseModal

- *(frontend)* Migrate batch 56 chat sidebar modal to BaseModal

- *(error-handling)* Migrate batch 156 endpoints to @with_error_handling (remote_terminal.py COMPLETE - 100%)

- *(frontend)* Migrate batch 55 chat messages modal to BaseModal

- *(error-handling)* Migrate batch 155 endpoints to @with_error_handling (web_research_settings.py COMPLETE - 100%)

- *(frontend)* Migrate batch 54 redis service modal to BaseModal

- *(frontend)* Migrate batch 53 knowledge entries modal to BaseModal

- *(error-handling)* Migrate batch 154 endpoints to @with_error_handling (metrics.py COMPLETE - 100%)

- *(frontend)* Migrate batch 52 monitoring dashboard modal to BaseModal

- *(frontend)* Migrate batch 51 user management modals to BaseModal

- *(error-handling)* Migrate batch 153 endpoints to @with_error_handling (knowledge_enhanced.py COMPLETE - 100%)

- *(frontend)* Migrate batch 50 NPU workers modals to BaseModal

- *(frontend)* Migrate batch 49 secrets manager modals to BaseModal

- *(error-handling)* Migrate batch 152 endpoints to @with_error_handling (feature_flags.py COMPLETE - 100%)

- *(frontend)* Migrate batch 48 knowledge search modal to BaseModal

- *(frontend)* Migrate batch 47 terminal modals to BaseModal

- *(error-handling)* Migrate batch 151 endpoints to @with_error_handling (playwright.py COMPLETE - 100%) + fix blocker

- *(frontend)* Migrate ResearchBrowser to BaseAlert (batch 46)

- *(frontend)* Migrate MonitoringDashboard banner to BaseAlert (batch 45)

- *(error-handling)* Migrate batch 150 endpoints to @with_error_handling (enhanced_search.py COMPLETE - 100%)

- *(frontend)* Migrate ValidationDashboard to BaseAlert (batch 44)

- *(frontend)* Migrate NPUWorkersSettings to BaseAlert (batch 43)

- *(frontend)* Migrate KnowledgeUpload to BaseAlert (batch 42)

- *(frontend)* Migrate batch 40 system status indicator to BaseButton

- *(frontend)* Migrate batch 39 phase progression indicator to BaseButton

- *(frontend)* Migrate batch 38 knowledge persistence dialog to BaseButton

- *(error-handling)* Migrate batch 148 endpoints to @with_error_handling (system_validation.py COMPLETE - 100%)

- *(frontend)* Migrate batch 37 knowledge categories to BaseButton

- *(frontend)* Migrate batch 36 knowledge entries to BaseButton

- *(error-handling)* Migrate batch 146 endpoints to @with_error_handling (project_state.py COMPLETE - 100%)

- *(frontend)* Migrate batch 35 chat messages to BaseButton

- *(error-handling)* Migrate batch 145 endpoints to @with_error_handling (chat_enhanced.py COMPLETE - 100%)

- *(frontend)* Migrate batch 34 deduplication manager to BaseButton

- *(error-handling)* Migrate batch 144 endpoints to @with_error_handling (base_terminal.py COMPLETE - 100%)

- *(frontend)* Migrate batch 33 file browser header to BaseButton

- *(error-handling)* Migrate batch 143 endpoints to @with_error_handling (cache_management.py COMPLETE - 100%)

- *(frontend)* Migrate batch 31 failed vectorizations to BaseButton

- *(frontend)* Migrate batch 30 knowledge advanced to BaseButton

- *(frontend)* Migrate batch 29 knowledge browser to BaseButton

- *(frontend)* Migrate batch 28 chat input to BaseButton

- *(error-handling)* Migrate batch 141 endpoints to @with_error_handling (websockets.py COMPLETE - 100%)

- *(frontend)* Migrate batch 27 AdvancedStepConfirmationModal to BaseButton

- *(frontend)* Migrate batch 26 knowledge/services/monitoring to BaseButton

- *(error-handling)* Migrate batch 140 endpoints to @with_error_handling (services.py COMPLETE - 100%)

- *(frontend)* Migrate batch 25 terminal/chat components to BaseButton

- *(error-handling)* Migrate batch 139 endpoints to @with_error_handling (developer.py COMPLETE - 100%)

- *(frontend)* Migrate batch 24 research browser to BaseButton

- *(error-handling)* Migrate batch 138 endpoints to @with_error_handling (voice.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 137 endpoints to @with_error_handling (security.py COMPLETE - 100%)

- *(frontend)* Migrate batch 23 browser/knowledge components to BaseButton

- *(frontend)* Migrate batch 22 dialog components to BaseButton

- *(error-handling)* Migrate batch 136 endpoints to @with_error_handling (enhanced_memory.py COMPLETE - 100%)

- *(reusability)* Migrate batch 21 components to BaseButton (2 components, ~87 lines saved)

- *(error-handling)* Migrate batch 135 endpoints to @with_error_handling (state_tracking.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 134 endpoints to @with_error_handling (phase_management.py COMPLETE - 100%)

- *(reusability)* Migrate batch 20 components to BaseButton (3 components, ~157 lines saved)

- *(error-handling)* Migrate batch 133 endpoints to @with_error_handling (startup.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 132 endpoints to @with_error_handling (secrets.py COMPLETE - 100%)

- *(ui)* Batch 19 - StatusBadge final sweep (NPUWorkersSettings.vue, ~29 lines saved)

- *(ui)* Migrate batch 18 - StatusBadge enforcement (4 components, 5 patterns, ~90 lines saved)

- *(error-handling)* Migrate batch 131 endpoints to @with_error_handling (audit.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 130 endpoints to @with_error_handling (rum.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 129 endpoints to @with_error_handling (prompts.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 128 endpoints to @with_error_handling (hot_reload.py COMPLETE - 100%)

- *(reusability)* Migrate batch 16 StatusBadge enforcement

- *(error-handling)* Migrate batch 127 endpoints to @with_error_handling (redis_service.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 126 endpoints to @with_error_handling (embeddings.py COMPLETE - 100%)

- *(vue)* Adopt StatusBadge component in 3 components (batch 15)

- *(error-handling)* Migrate batch 125 endpoints to @with_error_handling (batch.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 124 endpoints to @with_error_handling (elevation.py COMPLETE - 100%)

- *(vue)* Migrate DeploymentProgressModal to shared format utilities (batch 14)

- *(error-handling)* Migrate batch 122 endpoints to @with_error_handling (settings.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 121 endpoints to @with_error_handling (orchestration.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 120 endpoints to @with_error_handling (redis.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 119 endpoints to @with_error_handling (knowledge_fresh.py COMPLETE - 100%)

- *(ui)* Migrate batch 11 component to EmptyState pattern

- *(error-handling)* Migrate batch 118 endpoints to @with_error_handling (kb_librarian.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 117 endpoints to @with_error_handling (startup.py COMPLETE - 100%)

- *(ui)* Migrate batch 10 component to EmptyState pattern

- *(ui)* Migrate InfrastructureManager view to EmptyState pattern (batch 9)

- *(error-handling)* Migrate batch 116 endpoints to @with_error_handling (knowledge_test.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 115 endpoint to @with_error_handling (frontend_config.py COMPLETE - 100%)

- *(ui)* Migrate 2 components to EmptyState pattern (batch 8)

- *(error-handling)* Migrate batch 114 endpoints to @with_error_handling (chat_knowledge.py COMPLETE - 100%)

- *(ui)* Migrate LogViewer to EmptyState pattern (batch 7)

- *(error-handling)* Migrate batch 113 endpoints to @with_error_handling (cache.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 112 endpoints to @with_error_handling (conversation_files.py COMPLETE - 100%)

- *(error-handling)* Add @with_error_handling to conversation_files.py endpoints

- *(types)* Consolidate KnowledgeStats type definition

- *(ui)* Migrate 19 components to EmptyState/BaseModal patterns

- *(error-handling)* Migrate batch 111 endpoints to @with_error_handling (auth.py COMPLETE - 100%)

- *(ui)* Migrate FileListTable to EmptyState pattern (batch 6)

- *(ui)* Migrate MonitoringDashboard to EmptyState pattern (batch 5)

- *(ui)* Migrate 4 components to EmptyState pattern (batch 4)

- *(error-handling)* Migrate batch 110 endpoints to @with_error_handling (terminal.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 109 endpoints to @with_error_handling (monitoring.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 108 endpoints to @with_error_handling (analytics.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 107 endpoints to @with_error_handling (knowledge.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 106 endpoint to @with_error_handling (agent_terminal.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 105 endpoints to @with_error_handling (monitoring_alerts.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 104 endpoints to @with_error_handling (monitoring_alerts.py batch 2 of 3)

- *(error-handling)* Migrate batch 103 endpoints to @with_error_handling (monitoring_alerts.py batch 1 of 3)

- *(error-handling)* Migrate batch 102 endpoints to @with_error_handling (validation_dashboard.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 101 endpoints to @with_error_handling (validation_dashboard.py batch 2 of 3)

- *(error-handling)* Migrate batch 100 endpoints to @with_error_handling (validation_dashboard.py batch 1 of 3)

- *(error-handling)* Migrate batch 99 endpoints to @with_error_handling (scheduler.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 98 endpoints to @with_error_handling (scheduler.py batch 2 of 3)

- *(error-handling)* Migrate batch 97 endpoints to @with_error_handling (scheduler.py batch 1 of 3)

- *(error-handling)* Migrate batch 96 endpoints to @with_error_handling (advanced_control.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 95 endpoints to @with_error_handling (advanced_control.py batch 2 of 3)

- *(error-handling)* Migrate batch 94 endpoints to @with_error_handling (advanced_control.py batch 1 of 3)

- *(error-handling)* Migrate batch 93 endpoints to @with_error_handling (service_monitor.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 92 endpoints to @with_error_handling (service_monitor.py batch 2 of 3)

- *(error-handling)* Migrate batch 91 endpoints to @with_error_handling (service_monitor.py batch 1 of 3)

- *(error-handling)* Migrate batch 90 endpoints to @with_error_handling (ai_stack_integration.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 89 endpoints to @with_error_handling (ai_stack_integration.py batch 4 of 5)

- *(error-handling)* Migrate batch 88 endpoints to @with_error_handling (ai_stack_integration.py batch 3 of 5)

- *(error-handling)* Migrate batch 87 endpoints to @with_error_handling (ai_stack_integration.py batch 2 of 5)

- *(error-handling)* Migrate batch 86 endpoints to @with_error_handling (ai_stack_integration.py batch 1 of 5)

- *(error-handling)* Migrate batch 85 endpoints to @with_error_handling (codebase_analytics.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 84 endpoints to @with_error_handling (codebase_analytics.py batch 2 of 3)

- *(error-handling)* Migrate batch 83 endpoints to @with_error_handling (codebase_analytics.py batch 1 of 3)

- *(error-handling)* Migrate batch 82 endpoints to @with_error_handling (system.py COMPLETE - 100%)

- *(error-handling)* Migrate batch 81 endpoints to @with_error_handling (system.py batch 2 of 3)

- *(error-handling)* Extract reusable CommandApprovalManager

- *(terminal)* Extract reusable echo configuration functions

- *(error-handling)* Migrate batch 79 endpoints to @with_error_handling (intelligent_agent.py COMPLETE)

- *(error-handling)* Migrate batch 78 endpoints to @with_error_handling (intelligent_agent.py first 3)

- *(error-handling)* Migrate batch 77 endpoints to @with_error_handling (agent.py command_approval, execute_command) - agent.py 100% COMPLETE

- *(error-handling)* Migrate batch 76 endpoints to @with_error_handling (agent.py receive_goal, pause_agent_api, resume_agent_api)

- *(error-handling)* Migrate batch 75 endpoints to @with_error_handling (agent_config.py FINAL 2) - 100% COMPLETE

- *(error-handling)* Migrate batch 74 endpoints to @with_error_handling (agent_config.py next 2)

- *(error-handling)* Migrate batch 73 endpoints to @with_error_handling (agent_config.py first 3)

- *(error-handling)* Migrate batch 72 endpoints to @with_error_handling (agent_enhanced.py POST /goal + GET /health/enhanced) - FINAL BATCH

- *(error-handling)* Migrate batch 71 endpoints to @with_error_handling (agent_enhanced.py POST /development/analyze + GET /agents/available + GET /agents/status)

- *(error-handling)* Migrate batch 70 endpoints to @with_error_handling (agent_enhanced.py POST /goal/enhanced + POST /multi-agent/coordinate + POST /research/comprehensive)

- *(error-handling)* Migrate batch 69 endpoints to @with_error_handling decorator (agent_terminal.py COMPLETE)

- *(error-handling)* Migrate batch 68 endpoints to @with_error_handling (agent_terminal.py next 3 endpoints)

- *(error-handling)* Migrate batch 67 endpoints to @with_error_handling (agent_terminal.py first 3 endpoints)

- *(error-handling)* Migrate batch 66 endpoints to @with_error_handling (research_browser.py final 4 endpoints)

- *(error-handling)* Migrate batch 65 endpoints to @with_error_handling (research_browser.py 3 endpoints)

- *(error-handling)* Migrate batch 64 endpoints to @with_error_handling (research_browser.py health_check + research_url)

- *(monitoring)* Integrate Prometheus task metrics in agent endpoints (Phase 3)

- *(error-handling)* Migrate batch 63 endpoints to @with_error_handling - monitoring.py COMPLETE! 🎉

- *(error-handling)* Migrate batch 62 endpoints to @with_error_handling (monitoring.py hardware/services/export)

- *(error-handling)* Migrate batch 61 endpoints to @with_error_handling (monitoring.py optimization/alerts endpoints)

- *(error-handling)* Migrate batch 60 endpoints to @with_error_handling (monitoring.py dashboard/metrics endpoints)

- *(error-handling)* Migrate batch 59 endpoints to @with_error_handling (monitoring.py first 3 endpoints)

- *(frontend)* Migrate 12 components to shared formatHelpers utilities (phase 2)

- *(frontend)* Systematic migration to shared formatHelpers utilities

- *(error-handling)* Migrate batch 58 endpoints to @with_error_handling (chat.py Mixed Pattern refinement)

- *(error-handling)* Migrate batch 57 endpoints to @with_error_handling (terminal.py POST /terminal/check-tool + POST /terminal/validate-command + GET /terminal/package-managers)

- *(error-handling)* Migrate batch 56 endpoints to @with_error_handling (terminal.py GET /audit/{id} + POST /terminal/install-tool)

- *(error-handling)* Migrate batch 55 endpoints to @with_error_handling (terminal.py POST /sessions/{id}/signal/{name} + GET /sessions/{id}/history)

- *(error-handling)* Migrate batch 54 endpoints to @with_error_handling (terminal.py POST /command + POST /sessions/{id}/input)

- *(error-handling)* Migrate batch 53 endpoints to @with_error_handling (terminal.py GET + DELETE /sessions/{id})

- *(error-handling)* Migrate batch 52 endpoints to @with_error_handling (terminal.py POST /sessions + GET /sessions)

- *(error-handling)* Migrate batch 51 endpoints to @with_error_handling (knowledge.py POST /populate_autobot_docs + GET /import/statistics)

- *(error-handling)* Migrate batch 50 endpoints to @with_error_handling (knowledge.py POST /populate_man_pages + POST /refresh_system_knowledge)

- *(error-handling)* Migrate batch 49 endpoints to @with_error_handling (knowledge.py POST /similarity_search + POST /populate_system_commands)

- *(error-handling)* Migrate batch 48 endpoints to @with_error_handling (knowledge.py GET /test_categories_main + POST /rag_search)

- *(error-handling)* Migrate batch 47 endpoints to @with_error_handling (quality/assessment + startup event)

- *(error-handling)* Migrate batch 46 endpoints to @with_error_handling (code/index + code/status)

- *(error-handling)* Migrate batch 45 endpoints to @with_error_handling (communication/patterns + usage/statistics)

- *(error-handling)* Migrate batch 44 endpoints to @with_error_handling (system/health-detailed + performance/metrics)

- *(error-handling)* Migrate batch 43 endpoints to @with_error_handling (trends/historical + dashboard/overview)

- *(error-handling)* Migrate batch 42 endpoints to @with_error_handling (collection start/stop)

- *(error-handling)* Migrate batch 41 endpoints to @with_error_handling (realtime/metrics + events/track)

- *(error-handling)* Migrate batch 40 endpoints to @with_error_handling (GET quality-metrics + communication-chains)

- *(error-handling)* Migrate 2 analytics code analysis endpoints to @with_error_handling (Batch 39)

- *(error-handling)* Migrate 2 analytics endpoints to @with_error_handling (Batch 38)

- *(error-handling)* Migrate 2 analytics endpoints to @with_error_handling (Batch 37)

- *(error-handling)* Migrate 2 analytics endpoints to @with_error_handling (Batch 36)

- *(error-handling)* Migrate 2 analytics.py endpoints (batch 35)

- *(error-handling)* Migrate POST /execute endpoint with nested error handling (batch 34)

- *(error-handling)* Migrate workflow DELETE and GET approvals endpoints (batch 33)

- *(error-handling)* Migrate batch 32 - workflow.py status and approve endpoints

- *(error-handling)* Migrate batch 31 - workflow.py simple endpoints

- *(error-handling)* Migrate batch 30 - GET /tree and GET /stats

- *(error-handling)* Migrate batch 29 - DELETE /delete and POST /create_directory

- *(error-handling)* Migrate batch 28 - POST /rename and GET /preview

- *(error-handling)* Migrate Batch 27 - file operations endpoints (GET /download, GET /view)

- *(error-handling)* Migrate Batch 26 - file management endpoints (GET /list, POST /upload)

- *(error-handling)* Migrate Batch 25 - PUT /fact/{fact_id} and DELETE /fact/{fact_id} endpoints

- *(error-handling)* Migrate Batch 24 - POST /vectorize_facts/background and GET /vectorize_facts/status

- *(error-handling)* Migrate Batch 23 - DELETE /orphans and POST /import/scan endpoints

- *(error-handling)* Migrate Batch 22 - POST /deduplicate and GET /orphans endpoints

- *(error-handling)* Migrate job deletion endpoints to @with_error_handling decorator (Batch 21)

- *(error-handling)* Migrate failed job management endpoints to @with_error_handling decorator (Batch 20)

- *(error-handling)* Migrate vectorization job endpoints to @with_error_handling decorator (Batch 19)

- *(error-handling)* Migrate POST /vectorize_facts and GET /import/status to @with_error_handling

- *(error-handling)* Migrate GET /facts/by_category and GET /fact/{fact_key} to @with_error_handling

- *(error-handling)* Migrate GET /man_pages/search and POST /clear_all to @with_error_handling

- *(error-handling)* Migrate POST /machine_knowledge/initialize and POST /man_pages/integrate to @with_error_handling

- *(error-handling)* Migrate GET /machine_profile and GET /man_pages/summary to @with_error_handling

- *(error-handling)* Migrate GET /entries and GET /detailed_stats to @with_error_handling

- *(error-handling)* Migrate 2 knowledge.py endpoints to @with_error_handling (Batch 12)

- *(error-handling)* Migrate 2 knowledge.py endpoints to @with_error_handling (Batch 11)

- *(error-handling)* Migrate 2 knowledge.py endpoints to @with_error_handling (Batch 10)

- *(error-handling)* Migrate POST /chat/direct to @with_error_handling decorator (Batch 9)

- *(error-handling)* Migrate POST /chats/{chat_id}/message to @with_error_handling decorator (Batch 8)

- *(error-handling)* Migrate list_chats endpoint to @with_error_handling decorator (Batch 7)

- *(error-handling)* Migrate session export & management endpoints to @with_error_handling decorator (Batch 6)

- *(error-handling)* Migrate session CRUD endpoints to @with_error_handling decorator (Batch 5)

- *(error-handling)* Migrate /chat/stream and session endpoints to @with_error_handling

- *(error-handling)* Migrate knowledge.py /health and /search endpoints to @with_error_handling

- *(error-handling)* Migrate /chat/stats and /chat/message endpoints to @with_error_handling

- *(error-handling)* Migrate /chat/health endpoint to @with_error_handling decorator

- *(config)* Eliminate hardcoded model classifications, achieve 100% zero hardcode compliance

- *(legacy)* Eliminate hardcoded models in consolidated workflow and backup

- *(core)* Eliminate hardcoded model names in workflow and config

- *(agent-config)* Eliminate hardcoded model names, enforce zero hardcode policy

- *(codebase)* Comprehensive refactoring with Redis consolidation and hardcoded value elimination

- *(redis)* Complete Phase 5 migration to canonical get_redis_client() utility

- *(core)* Replace hardcoded values in core system components

- *(scripts)* Replace hardcoded IPs with NetworkConstants

- *(backend)* Replace hardcoded IPs and LLM models with constants

- *(frontend)* Replace hardcoded IPs with NetworkConstants

- *(frontend-settings)* Replace hardcoded IPs in NPU/Settings services

- *(frontend-knowledge)* Replace hardcoded IPs with NetworkConstants

- *(frontend-terminal)* Replace hardcoded IPs with NetworkConstants

- *(frontend-state)* Replace hardcoded IPs with NetworkConstants

- *(frontend-settings)* Replace hardcoded IPs with NetworkConstants

- *(frontend-vnc)* Replace hardcoded IPs with NetworkConstants

- *(frontend-chat)* Replace hardcoded VNC URLs with NetworkConstants

- *(frontend-services)* Replace hardcoded IPs with NetworkConstants

- *(database)* Replace hardcoded paths with PathConstants

- *(mcp)* Replace hardcoded IPs with NetworkConstants

- *(security)* Replace hardcoded paths with PathConstants

- *(utils)* Replace hardcoded fallbacks with NetworkConstants

- *(backend)* Integrate ModelConstants for LLM configuration

- *(services)* Replace hardcoded IPs with NetworkConstants

- *(monitoring)* Replace hardcoded IPs with NetworkConstants

- *(config)* Enhance unified configuration management system

- *(constants)* Add PATH constant to public exports

- *(backend)* Enhance API services and connection management

- *(frontend)* Improve service integration and error handling

- Improve lazy initialization patterns

- Apply linter improvements to code search

- *(scripts)* Reorganize scripts into proper directory structure

- *(core)* Standardize infrastructure across all source modules

- *(tools)* Update code analysis tools for new architecture

- *(tests)* Update test configuration for new architecture

- *(analysis)* Update analysis tools for configuration-driven architecture

- *(core)* Eliminate hardcoded values in core system modules

- *(backend-api)* Eliminate hardcoded knowledge base and system configurations

- *(frontend)* Eliminate hardcoded VNC and host configurations

- *(ai-stack-client)* Eliminate hardcoded connection parameters

- *(services)* Eliminate hardcoded system information values

- *(frontend-config)* Eliminate hardcoded default configurations

- *(codebase-analytics)* Eliminate hardcoded Redis configuration

- *(knowledge)* Redesign KnowledgeCategories as category selection view

- *(knowledge)* Simplify Advanced tab to action-only interface with per-host support

- *(knowledge)* Simplify Manage tab to 3 sub-tabs

- *(knowledge)* Consolidate navigation and remove unused component

- *(frontend)* General improvements and cleanup

- *(core)* Comprehensive core infrastructure and agent system updates

- *(backend)* Comprehensive API architecture and service optimization

- *(frontend)* Infrastructure modernization and service optimization

- *(core)* Enhance scripts and source architecture with cleanup

- *(backend)* Consolidate API structure and remove deprecated endpoints

- *(frontend)* Consolidate UI components and improve architecture

- *(frontend)* Update services and configuration for distributed architecture

- Remove Docker-related files and dependencies

- Remove deprecated infrastructure and analysis tools

- Archive completed reports to reports/finished/ structure

- Reorganize project structure and enhance router configuration

- Remove obsolete nginx configuration

- *(tests)* Consolidate test files and remove root directory violations

- *(frontend)* Enhance desktop session management and chat integration

- *(backend)* Consolidate LLM interfaces and enhance system architecture

- Comprehensive system cleanup and enhancement

- Organize test files into tests/ directory

- Organize Docker configuration files

- Move configuration files to config/ directory

- Reorganize scripts into logical subdirectories

- Reorganize Docker infrastructure with environment-driven configuration

- Implement dependency injection for core components

- Improve code readability with explanatory comments and documentation

- Consolidate duplicated terminal WebSocket implementations

- Systematic flake8 code quality cleanup - progress on main.py, llm_interface.py, orchestrator.py

- Systematic flake8 code quality cleanup - progress on main.py, llm_interface.py, orchestrator.py

- Eliminate Redis client code duplication with centralized utility


### Reverted

- *(deploy)* Remove Ansible backend symlink creation task (#1175)


### SECURITY

- Fix critical eval() vulnerabilities with auto-formatting

- Fix multiple critical vulnerabilities

- Fix critical command injection vulnerabilities in elevation system


### Styling

- *(voice)* Add WS indicator CSS for full-duplex mode (#1030)

- *(frontend)* Batch 5 - design tokens in desktop/browser/file-browser/terminal (#901)

- *(frontend)* Batch 4 - design tokens in chat/collab/async components (#901)

- *(frontend)* Batch 3 - design token consistency across 16 components (#901)

- *(sync-orchestrator)* Fix line length in docstring (#665)

- *(replication)* Fix line length in setup_replication (#665)

- *(backend)* Apply black formatting to agent_config.py and prometheus_mcp.py

- *(views)* Remove redundant headers to maximize screen space (#600)

- *(frontend)* Standardize AnalyticsView styling and improve report export

- *(knowledge)* Add CSS for refresh status button (#162)

- *(logging)* Convert f-string logging to lazy evaluation in 15 directories (#499)

- *(logging)* Fix remaining f-string logging in orchestrator and memory graph (#498)

- *(logging)* Convert f-string logging to lazy evaluation in root src/ (#498)

- *(knowledge)* Apply code formatting to remaining files

- *(frontend)* Add component context to console log messages

- *(chat)* Reformat long lines for readability

- *(knowledge)* Reformat long f-string lines for readability

- Apply safe code quality fixes (formatting and whitespace)

- Fix import sorting with isort for 48 files

- Apply Black formatting to 126 Python files

- Apply Black and isort formatting to fix code quality CI/CD checks


### Testing

- *(knowledge)* Add pipeline test coverage (#1075)

- *(ide)* Fix completion endpoint tests (#906)

- *(grafana)* Add configuration verification script

- *(overseer)* Add unit tests for overseer agent system (#690)

- *(permissions)* Add unit tests for PermissionMatcher and ApprovalMemoryManager (#693)

- Update RAG weight validation test for normalization behavior (#788)

- *(rate-limit)* Verify blocking when exceeded (#635)

- *(rate-limit)* Check rate limit threshold (#635)

- *(session)* Add token hashing with SHA256 (#635)

- *(npu)* Add integration tests for worker pool (#168)

- *(config)* Add caching behavior tests for ConfigRegistry (#751)

- *(config)* Add env var fallback tests for ConfigRegistry (#751)

- *(auth)* Add RBAC permission system tests - Phase 7 (#744)

- Add test data files for file manager

- Add comprehensive test suite

- Add comprehensive test coverage for Phase D features

- Backend validation and live workflow testing

- Comprehensive workflow orchestration test suite

- *(analytics)* Add unit tests for Issue #711 parallel processing

- *(chat)* Add comprehensive unit tests for chat intent detector (#160)

- *(concurrency)* Add comprehensive thread safety tests for race condition fixes (#481)

- *(workflow)* Add comprehensive unit tests for plan approval system (#390)

- *(npu)* Add semantic search test for Issue #68 verification

- *(bug-predictor)* Add unit tests for Bug Prediction System (#224)

- *(security)* Add unit tests for Security Workflow Manager (#260)

- *(chat)* Add chat knowledge service test suite (#249)

- *(knowledge)* Add comprehensive test suite for QA Sprint (#163)

- *(chat)* Add unit tests for merge_messages deduplication

- *(npu-worker)* Add unit tests for Redis client connection pooling (#151)

- *(ci)* Trigger workflow run to verify pip installation

- *(intent)* Add comprehensive test suite + fix conversation context bugs (#159)

- Add comprehensive testing infrastructure and benchmarks

- *(knowledge)* Add comprehensive RAG integration test suite

- *(error-handling)* Add comprehensive tests for batch 77 migrations - agent.py 100% COMPLETE

- *(error-handling)* Add comprehensive tests for batch 76 migrations

- *(error-handling)* Add comprehensive tests for batch 75 migrations - agent_config.py 100% COMPLETE

- *(error-handling)* Add comprehensive tests for batch 74 migrations

- *(error-handling)* Add comprehensive tests for batch 73 migrations

- *(error-handling)* Add comprehensive tests for batch 72 migrations - FINAL BATCH

- *(error-handling)* Add comprehensive tests for batch 71 migrations

- *(error-handling)* Add comprehensive tests for batch 70 migrations

- *(error-handling)* Add comprehensive tests for batch 69 migrations (agent_terminal.py final batch)

- *(error-handling)* Add comprehensive tests for batch 68 migrations

- *(error-handling)* Add comprehensive tests for batch 67 migrations

- *(error-handling)* Add comprehensive tests for batch 66 migrations

- *(error-handling)* Add comprehensive tests for batch 65 migrations

- *(error-handling)* Add comprehensive tests for batch 64 migrations

- *(prometheus)* Add comprehensive test suite for Prometheus metrics integration

- *(error-handling)* Add comprehensive tests for batch 54 migrations

- *(error-handling)* Add comprehensive tests for batch 53 migrations

- *(error-handling)* Add comprehensive tests for batch 52 migrations

- *(error-handling)* Add comprehensive tests for batch 51 migrations

- *(error-handling)* Add comprehensive tests for batch 50 migrations

- *(error-handling)* Add comprehensive tests for batch 49 migrations

- *(error-handling)* Add comprehensive tests for batch 48 migrations

- *(error-handling)* Add comprehensive tests for batch 47 migrations

- *(error-handling)* Add comprehensive tests for batch 46 migrations

- *(error-handling)* Add comprehensive tests for batch 45 migrations

- *(error-handling)* Add comprehensive tests for batch 44 migrations

- *(error-handling)* Add comprehensive tests for batch 43 migrations

- *(error-handling)* Add comprehensive tests for batch 42 migrations

- *(error-handling)* Add comprehensive tests for batch 41 migrations

- *(error-handling)* Add comprehensive tests for batch 40 migrations

- *(error-handling)* Add comprehensive tests for batch 39 code analysis endpoints

- *(error-handling)* Add comprehensive tests for batch 38 analytics endpoints

- *(error-handling)* Add comprehensive tests for batch 37 analytics endpoints

- *(error-handling)* Add comprehensive tests for batch 36 analytics endpoints

- *(error-handling)* Add 13 comprehensive tests for batch 35 analytics endpoints

- *(error-handling)* Add 15 comprehensive tests for batch 34 POST /execute endpoint

- *(error-handling)* Add 14 comprehensive tests for batch 33 workflow endpoints

- *(error-handling)* Add comprehensive tests for batch 32 migrations

- *(error-handling)* Add comprehensive tests for batch 31 migrations

- *(error-handling)* Add comprehensive tests for batch 30 migrations

- *(error-handling)* Add comprehensive tests for batch 29 migrations

- *(error-handling)* Add comprehensive tests for batch 28 migrations

- *(error-handling)* Add comprehensive tests for Batch 27 file operation endpoints

- *(error-handling)* Add comprehensive tests for Batch 26 file management endpoints

- *(error-handling)* Add comprehensive tests for Batch 25 CRUD endpoints

- *(error-handling)* Add comprehensive tests for Batch 24 migrations

- *(error-handling)* Add comprehensive tests for Batch 23 migrations

- *(error-handling)* Add comprehensive tests for Batch 22 migrations

- *(error-handling)* Add comprehensive tests for batch 21 job deletion endpoints

- *(error-handling)* Add comprehensive tests for batch 20 failed job management endpoints

- *(error-handling)* Add comprehensive tests for batch 19 vectorization job endpoints

- *(error-handling)* Add comprehensive tests for batch 18 migrations

- *(error-handling)* Add comprehensive tests for batch 17 migrations

- *(error-handling)* Add comprehensive tests for batch 16 migrations

- *(error-handling)* Add 14 comprehensive tests for Batch 15 migrations

- *(error-handling)* Add 15 comprehensive tests for Batch 14 migrations

- *(error-handling)* Add 16 comprehensive tests for Batch 13 migrations

- *(error-handling)* Add comprehensive tests for Batch 12 knowledge endpoints

- *(error-handling)* Add comprehensive tests for Batch 11 knowledge endpoints

- *(error-handling)* Add comprehensive tests for Batch 10 knowledge endpoints

- *(error-handling)* Add comprehensive tests for Batch 9 command approval endpoint migration

- *(error-handling)* Add comprehensive tests for Batch 8 streaming endpoint migration

- *(error-handling)* Add batch 7 tests for list_chats endpoint

- *(error-handling)* Add batch 6 tests for session export & management endpoints

- *(error-handling)* Add batch 5 tests for session CRUD endpoints

- *(error-handling)* Add tests for batch 4 endpoint migrations

- *(error-handling)* Add comprehensive test suite for Phase 2a endpoint migrations

- *(error-handling)* Add comprehensive unit tests for Phase 1 enhancements

- Add agent optimization test infrastructure

- *(unit)* Improve test_agent_optimizer empty code block handling

- Add comprehensive test infrastructure

- Add comprehensive test suites and validation

- Comprehensive testing infrastructure and results

- Add comprehensive integration test suite and results

- Add comprehensive debugging and testing infrastructure

- Add comprehensive test suite and validation scripts

- Add test data files for file manager

- Add comprehensive test suite

- Add comprehensive test coverage for Phase D features

- Backend validation and live workflow testing

- Comprehensive workflow orchestration test suite


### Add

- Agent model configuration testing script

- Agent model configuration testing script


### Backup

- Preserve critical frontend component versions


### Cleanup

- Removed duplicate basic Playwright container

- Remove obsolete phase9 test suite and results

- Remove obsolete test results and debug files from root

- Remove obsolete files and reorganize project structure


### Config

- Update config.yaml.template to include new GUI settings

- *(flake8)* Add E402 to extend-ignore for intentional patterns (#176)

- *(lint)* Increase max-line-length to 120 chars (#176)

- *(knowledge)* Add RAG configuration section for reranking parameters

- Improve configuration structure and environment variable management

- Update config.yaml.template to include new GUI settings


### Data

- Update chat history with workflow orchestration examples

- Update chat history with workflow orchestration examples


### Debug

- *(database)* Add comprehensive debug logging for Issue #898

- *(ci)* Add diagnostic output for pyenv availability check


### Deploy

- Containerized workflow orchestration deployment

- Containerized workflow orchestration deployment


### Deps

- Add asyncssh for PKI certificate distribution (#166)


### Dev

- Workflow development and testing utilities

- Workflow development and testing utilities


### Hotfix

- *(P1)* Fix redis_manager.main() pattern - backend crash resolved

- *(P1)* Fix backend startup - async_redis_manager import errors


### Infra

- Add comprehensive infrastructure and deployment automation


### Security

- *(api)* Add authentication to 5 API files (#744)

- *(api)* Add authentication to 6 API files (#744)

- *(api)* Add authentication to analytics and VNC endpoints (#744)

- *(api)* Add authentication to remaining API endpoints (#744)

- *(api)* Add authentication to critical API endpoints (#744)

- *(auth)* Remove guest role and fallbacks (#744)

- Update vulnerable dependencies and installation scripts

- Enhance file upload validation and security

- Fix critical prompt injection vulnerability in chat API

- Complete dependency security audit and implement critical fixes

- Update vulnerable dependencies and installation scripts

- Enhance file upload validation and security

- Fix critical prompt injection vulnerability in chat API

- Complete dependency security audit and implement critical fixes


### Settings.json

- Update settings for new GUI features

- Update settings for new GUI features


### Temp

- Disable Gateway to test event loop (#881)

- Disable entire Phase 2 to isolate deadlock (#876)

- Disable all SLM/AI Stack blocking calls (#876)

- Disable metrics collection blocking event loop (#876)


### Tools

- Add comprehensive analysis and debugging utilities
