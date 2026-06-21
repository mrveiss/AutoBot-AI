# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Bug Fixes

- *(ansible)* Per-user tmp paths, site.yml roles, backend_port 8001 (#10047,#10048,#10049) (#10401) ([#10401](https://github.com/mrveiss/AutoBot-AI/pull/10401))

- *(tests)* Repair AlertManager webhook test harness path failures (#10273) (#10395) ([#10395](https://github.com/mrveiss/AutoBot-AI/pull/10395))

- *(logging)* Stop NPU-unavailable + SLM WS handshake-rejection log floods (#10391) ([#10391](https://github.com/mrveiss/AutoBot-AI/pull/10391))

- *(frontend)* Add missing qrcode dependency; drop temp type shim (#10074) (#10397) ([#10397](https://github.com/mrveiss/AutoBot-AI/pull/10397))

- *(llc)* Resolve dual agent-id keyspace wrong-column joins (#10032) (#10399) ([#10399](https://github.com/mrveiss/AutoBot-AI/pull/10399))

- *(logs)* Init long-running ops (#10385); update google pricing; quiet optional-provider warns (#10394) ([#10394](https://github.com/mrveiss/AutoBot-AI/pull/10394))

- *(deps)* Langchain 1.3.1+/1.3.2 (not 1.3.10) — keeps PVE-2026-88512 fix + resolves with websockets>=16.0 (main's >=1.3.10 is unbuildable)

- *(llc/tests)* Remove leaking sys.modules stubs masking regressions (#9995, #10140) (#10387) ([#10387](https://github.com/mrveiss/AutoBot-AI/pull/10387))

- *(constants)* Add PathConstants.TEMP_DIR + SecurityConstants.ALLOWED_WEB_PORTS (#10384) (#10390) ([#10390](https://github.com/mrveiss/AutoBot-AI/pull/10390))

- *(api)* Call with_error_handling() with parens — bare use broke routes with 422 (#10383) ([#10383](https://github.com/mrveiss/AutoBot-AI/pull/10383))

- *(nginx/csp)* Allow data: fonts in strict security-headers snippet (#10360 follow-up) (#10377) ([#10377](https://github.com/mrveiss/AutoBot-AI/pull/10377))

- *(ansible)* Role updates branch on group_names, not legacy NN-Name hostnames (#10110) (#10372) ([#10372](https://github.com/mrveiss/AutoBot-AI/pull/10372))

- *(slm-ui)* Handle 401 in code-sync + updates pollers — stop the flood (#10369) (#10370) ([#10370](https://github.com/mrveiss/AutoBot-AI/pull/10370))

- *(user-app)* Allow data: fonts in CSP; stop reporting benign ResizeObserver loop as critical (#10352) (#10364) ([#10364](https://github.com/mrveiss/AutoBot-AI/pull/10364))

- *(chat)* Add ChatHistoryManager.get_session — thinking-preferences 500 (#10352) (#10367) ([#10367](https://github.com/mrveiss/AutoBot-AI/pull/10367))

- Live frontend console errors — /usage double-prefix, ApiClient .json() misuse, CSP font-src (#10357) (#10360) ([#10360](https://github.com/mrveiss/AutoBot-AI/pull/10360))

- *(api)* Register users router so /api/users/* resolves (#10352) (#10358) ([#10358](https://github.com/mrveiss/AutoBot-AI/pull/10358))

- *(llc)* Tenant-isolate boards.py endpoints + repair board service tests (#10296, #10297) (#10356) ([#10356](https://github.com/mrveiss/AutoBot-AI/pull/10356))

- *(secrets)* Deny vault access to deactivated/soft-deleted principals (#10346) (#10351) ([#10351](https://github.com/mrveiss/AutoBot-AI/pull/10351))

- *(deploy/frontend)* Relative same-origin API base; never emit 0.0.0.0 (#10348) (#10350) ([#10350](https://github.com/mrveiss/AutoBot-AI/pull/10350))

- *(observability+ci)* Consolidate prometheus_mcp onto shared PromQL client; audit catches missing-/api calls (#10303, #10037) (#10345) ([#10345](https://github.com/mrveiss/AutoBot-AI/pull/10345))

- *(provision)* Wizard inventory stamps node_roles so tts/browser activate (#9965) (#10342) ([#10342](https://github.com/mrveiss/AutoBot-AI/pull/10342))

- *(frontend)* AdminUsersView /api prefix (404); de-flake useModal perf tests (#10036, #10275) (#10338) ([#10338](https://github.com/mrveiss/AutoBot-AI/pull/10338))

- *(provision)* Stamp node_roles into generated inventory so optional roles activate (#9965) (#10335) ([#10335](https://github.com/mrveiss/AutoBot-AI/pull/10335))

- *(deps)* Constrain tokenizers to transformers-compatible range (#10331) (#10332) ([#10332](https://github.com/mrveiss/AutoBot-AI/pull/10332))

- *(provision)* Mark-synced no longer fatal on undefined slm_manager_inventory_host (#10317) (#10319) ([#10319](https://github.com/mrveiss/AutoBot-AI/pull/10319))

- *(ci)* Give frontend vue-tsc enough heap to stop OOM-flaking the required gate (#10298) (#10318) ([#10318](https://github.com/mrveiss/AutoBot-AI/pull/10318))

- *(deploy)* Batched SLM/deployment-health follow-ups (#10285 #10248 #10264 #10274) (#10299) ([#10299](https://github.com/mrveiss/AutoBot-AI/pull/10299))

- *(llc)* Derive sprints.py create tenant from validated parent + migrate to ConfigDict (#10261, #10262) (#10290) ([#10290](https://github.com/mrveiss/AutoBot-AI/pull/10290))

- *(ci/deps)* Make vllm a GPU-only optional extra; CPU-only torch in backend image (#10251) (#10287) ([#10287](https://github.com/mrveiss/AutoBot-AI/pull/10287))

- *(slm)* Remove stray '-o' in node role-sync ssh command (#10277) (#10280) ([#10280](https://github.com/mrveiss/AutoBot-AI/pull/10280))

- *(slm)* Auto-generate shared internal API key + derive backend URL (#10263) (#10279) ([#10279](https://github.com/mrveiss/AutoBot-AI/pull/10279))

- *(graph-rag)* Add missing /health route; valid max_facts; degrade on 503 (#10011) (#10269) ([#10269](https://github.com/mrveiss/AutoBot-AI/pull/10269))

- *(security)* Resolve Semgrep SAST findings — parameterize SQL + de-hardcode secret (#9489) (#10260) ([#10260](https://github.com/mrveiss/AutoBot-AI/pull/10260))

- *(llc/security)* Enforce tenant-isolation on sprints.py endpoints (#10148) (#10258) ([#10258](https://github.com/mrveiss/AutoBot-AI/pull/10258))

- *(telegram)* De-duplicate router registration + add wiring tests (#9006) (#10272) ([#10272](https://github.com/mrveiss/AutoBot-AI/pull/10272))

- *(frontend)* Stop calling .json() on ApiClient parsed results (#10013) (#10249) ([#10249](https://github.com/mrveiss/AutoBot-AI/pull/10249))

- *(migrations)* Add organizations external_pm_type/config + kb_inheritance_weight (#10189) (#10235) ([#10235](https://github.com/mrveiss/AutoBot-AI/pull/10235))

- *(transcriber)* Bind transcript export to real storage, retire mock duplicate (#9958) (#10229) ([#10229](https://github.com/mrveiss/AutoBot-AI/pull/10229))

- *(llc)* Validate adapter_type at hire time + decompose #9008/#9033 remaining ACs (#10227) ([#10227](https://github.com/mrveiss/AutoBot-AI/pull/10227))

- *(transcriber)* Wire transcription pipeline — repair orchestrator, register providers, Celery trigger (#10128) (#10225) ([#10225](https://github.com/mrveiss/AutoBot-AI/pull/10225))

- *(migrations)* Create llc_work_products+relations, fix env.py/enum drift (#10043, #10044, #10075, #10076) (#10204) ([#10204](https://github.com/mrveiss/AutoBot-AI/pull/10204))

- *(voice)* Surface user-visible message when zero TTS voices available (#9999) (#10194) ([#10194](https://github.com/mrveiss/AutoBot-AI/pull/10194))

- *(llc)* SKIPPED heartbeat status + drain adapter stderr to sidecar (#9951, #9992) (#10146) ([#10146](https://github.com/mrveiss/AutoBot-AI/pull/10146))

- *(code-sync)* Drift checker compares frontend source (.vue/.ts/.css) so frontends are detected + rebuilt (#10120) (#10144) ([#10144](https://github.com/mrveiss/AutoBot-AI/pull/10144))

- *(ci)* Drop node_modules negation that made frontend path-filter match every file (#10022) (#10143) ([#10143](https://github.com/mrveiss/AutoBot-AI/pull/10143))

- *(llc/tests)* Repair test-isolation + liveness mock rot (#9995, #9987, #9978) (#10139) ([#10139](https://github.com/mrveiss/AutoBot-AI/pull/10139))

- *(backend)* VisionStatusResponse declares the fields the endpoint actually returns (#9986) (#10132) ([#10132](https://github.com/mrveiss/AutoBot-AI/pull/10132))

- *(frontend)* Correct web-research-settings API paths — were 404ing (#10012) (#10131) ([#10131](https://github.com/mrveiss/AutoBot-AI/pull/10131))

- *(ansible)* Add autobot_shared to ai-stack unit PYTHONPATH — stop crash loop (#10121) (#10130) ([#10130](https://github.com/mrveiss/AutoBot-AI/pull/10130))

- *(governance)* Harden automated branch pruning against deletion race (#10035, #9917) (#10112) ([#10112](https://github.com/mrveiss/AutoBot-AI/pull/10112))

- *(frontend-deploy)* Deliver VITE_* env to the production vite build (#10084) (#10108) ([#10108](https://github.com/mrveiss/AutoBot-AI/pull/10108))

- *(frontend)* Re-wire nav featureFlag filtering with fail-safe per-item defaults (#9984) (#10083) ([#10083](https://github.com/mrveiss/AutoBot-AI/pull/10083))

- *(frontend)* Repair apexcharts 5.14 type errors blocking frontend-test gate (#10091) (#10092) ([#10092](https://github.com/mrveiss/AutoBot-AI/pull/10092))

- *(memory-graph)* Create FT index + data on DB 0 so semantic search leaves SCAN fallback (#9943) (#10082) ([#10082](https://github.com/mrveiss/AutoBot-AI/pull/10082))

- *(captcha)* Use canonical config.vnc_url to avoid empty-host VNC URL (#9942) (#10081) ([#10081](https://github.com/mrveiss/AutoBot-AI/pull/10081))

- *(frontend)* Green the unit+integration suite — 89 failures, 3 uncaught errors, 7 lint errors (#9693) (#10078) ([#10078](https://github.com/mrveiss/AutoBot-AI/pull/10078))

- *(llc)* Sa.Enum columns emit member VALUES not NAMES via values_callable (#9980) (#10077) ([#10077](https://github.com/mrveiss/AutoBot-AI/pull/10077))

- *(frontend)* Strict vue-tsc — 231 → 0 type errors + 11 real runtime bugs (#9724) (#10073) ([#10073](https://github.com/mrveiss/AutoBot-AI/pull/10073))

- *(docker)* Install claude CLI from official signed apt repo (#9950) (#10067) ([#10067](https://github.com/mrveiss/AutoBot-AI/pull/10067))

- *(slm-docker)* Parameterize python version + unversioned migration interpreter for Python 3.14 (#9949) (#10071) ([#10071](https://github.com/mrveiss/AutoBot-AI/pull/10071))

- *(code-sync)* Include self-node in stage-3 currency + reliable fleet selection (#9996) (#10069) ([#10069](https://github.com/mrveiss/AutoBot-AI/pull/10069))

- *(code-sync)* Run dep-install/rebuild/restart after per-component resolve (#9982) (#10068) ([#10068](https://github.com/mrveiss/AutoBot-AI/pull/10068))

- *(shared)* Make standalone autobot_shared authoritative — kill stale-shadow on partial sync (#10020) (#10070) ([#10070](https://github.com/mrveiss/AutoBot-AI/pull/10070))

- *(settings)* Persist telemetry consent in single_user mode (#10000) (#10064) ([#10064](https://github.com/mrveiss/AutoBot-AI/pull/10064))

- *(api)* Gate all LLC endpoints with 503 in single_user mode (#10010) (#10062) ([#10062](https://github.com/mrveiss/AutoBot-AI/pull/10062))

- *(frontend)* Self-host font + externalize inline script for strict CSP (#9966) (#10065) ([#10065](https://github.com/mrveiss/AutoBot-AI/pull/10065))

- *(slm-client)* /slm/api/ws/events on nginx paths, /api/ws/events on loopback (#9967) (#10063) ([#10063](https://github.com/mrveiss/AutoBot-AI/pull/10063))

- *(ansible)* Per-user local_tmp — shared /tmp/ansible_local_tmp locked out SLM executor (#10006) (#10056) ([#10056](https://github.com/mrveiss/AutoBot-AI/pull/10056))

- *(ansible)* Guard frontend_host and slm_host with default() in update summary (#10007) (#10055) ([#10055](https://github.com/mrveiss/AutoBot-AI/pull/10055))

- *(validation)* Backup file path validation rejected all real paths; add containment (#9670) (#10054) ([#10054](https://github.com/mrveiss/AutoBot-AI/pull/10054))

- *(tests)* Repair ssot_config_test imports + eliminate ambiguous top-level tests package (#9907) (#10053) ([#10053](https://github.com/mrveiss/AutoBot-AI/pull/10053))

- *(migrations)* Baseline adoption for never-migrated DBs + strict Ansible invocation (#10001, #10026) (#10039) ([#10039](https://github.com/mrveiss/AutoBot-AI/pull/10039))

- *(docker)* Update hardened overlay chromadb for 1.x image (#9663) (#10042) ([#10042](https://github.com/mrveiss/AutoBot-AI/pull/10042))

- *(ci)* Api-wiring audit accurate + blocking; fix 5 masked double-prefix/path 404s; regen api.ts (#9864) (#10031) ([#10031](https://github.com/mrveiss/AutoBot-AI/pull/10031))

- *(ansible)* Universal /slm prefix for all SLM API calls in playbooks (#9957) (#10015) ([#10015](https://github.com/mrveiss/AutoBot-AI/pull/10015))

- *(backend)* Declare watchdog in requirements — watch-folders 500 on fresh venvs (#10009) (#10014) ([#10014](https://github.com/mrveiss/AutoBot-AI/pull/10014))

- *(backend)* Sync AgentOrgNode and Secret ORM models with their migration columns (#9899) (#9989) ([#9989](https://github.com/mrveiss/AutoBot-AI/pull/9989))

- *(backend)* Repair Alembic chain + compose migration bootstrap — fresh-DB upgrade now reaches head (#9759) (#9988) ([#9988](https://github.com/mrveiss/AutoBot-AI/pull/9988))

- *(code-sync)* Protect .env and data via shared exclude chokepoint (#9970) (#9977) ([#9977](https://github.com/mrveiss/AutoBot-AI/pull/9977))

- *(auth)* _get_jwt_secret reads ssot_config, not ConfigManager — restores all authed endpoints (#9960) (#9961) ([#9961](https://github.com/mrveiss/AutoBot-AI/pull/9961))

- *(ansible)* Co-located wizard run — frontend 4b nginx ordering + universal /slm API path (#9952 #9953) (#9954) ([#9954](https://github.com/mrveiss/AutoBot-AI/pull/9954))

- *(backend)* Mint short-lived service JWT for SLM event-stream WS (#9852) (#9944) ([#9944](https://github.com/mrveiss/AutoBot-AI/pull/9944))

- *(docker)* Dev-override entrypoints source auto-provisioned signing secret (#9910) (#9940) ([#9940](https://github.com/mrveiss/AutoBot-AI/pull/9940))

- *(ci)* Repair ansible-role-facts-test group_vars codepath (#9936) (#9941) ([#9941](https://github.com/mrveiss/AutoBot-AI/pull/9941))

- *(redis)* Create agent-memory RediSearch index on db 0 (#9904) (#9939) ([#9939](https://github.com/mrveiss/AutoBot-AI/pull/9939))

- *(config)* Replace non-existent flat config attrs with canonical vm/port refs (#9912) (#9938) ([#9938](https://github.com/mrveiss/AutoBot-AI/pull/9938))

- *(ansible)* Unblock co-located SLM Manager provisioning (#9933 #9934) (#9935) ([#9935](https://github.com/mrveiss/AutoBot-AI/pull/9935))

- *(ansible)* Make fresh-VM fleet provisioning work out-of-box (#9914 #9915) (#9916) ([#9916](https://github.com/mrveiss/AutoBot-AI/pull/9916))

- Bug sweep 2026-06-10 — 7 fixes (#9832 #9788 #9785 #9782 #9783 #9767 #9768) (#9908) ([#9908](https://github.com/mrveiss/AutoBot-AI/pull/9908))

- *(precommit)* Delegate execution to engine, remove duplicate runner (#9873) (#9889) ([#9889](https://github.com/mrveiss/AutoBot-AI/pull/9889))

- *(precommit)* Derive API check catalog from engine SSOT — adds 5 missing checks (#9873) (#9886) ([#9886](https://github.com/mrveiss/AutoBot-AI/pull/9886))

- *(api-wiring)* Resolve frontend/backend contract drift (audit #9851) (#9862) ([#9862](https://github.com/mrveiss/AutoBot-AI/pull/9862))

- *(deps)* Upgrade vega ecosystem to v6 — stop recurring Dependabot break (#9847) (#9850) ([#9850](https://github.com/mrveiss/AutoBot-AI/pull/9850))

- *(slm/fleet)* Re-land IP range + full role assignment dropped by #9837 squash (#9761) (#9855) ([#9855](https://github.com/mrveiss/AutoBot-AI/pull/9855))

- *(slm/fleet)* Compose nodes show online + every container as a node (#9761) (#9837) ([#9837](https://github.com/mrveiss/AutoBot-AI/pull/9837))

- *(auth)* Use ssot_config.misc.internal_api_key, not ConfigManager (#9781) (#9828) ([#9828](https://github.com/mrveiss/AutoBot-AI/pull/9828))

- *(llc/adapters)* Share subprocess prompt+credential handling across all 4 adapters (#9789, #9769, #9777) (#9811) ([#9811](https://github.com/mrveiss/AutoBot-AI/pull/9811))

- *(ansible)* Deliver build:slm to docs-referenced playbook (#9563 drift) (#9710) (#9792) ([#9792](https://github.com/mrveiss/AutoBot-AI/pull/9792))

- *(tests)* Wire stubbed submodules to parent so patch('services.X.Y') resolves correctly (#9780) (#9790) ([#9790](https://github.com/mrveiss/AutoBot-AI/pull/9790))

- *(extensions)* Repair None|None crash + shim duplicate builtin extensions (#9786, #9779) (#9787) ([#9787](https://github.com/mrveiss/AutoBot-AI/pull/9787))

- *(compose)* Stop single_user startup error spam — LLC scheduler gate + git_tracker guard (#9771) (#9778) ([#9778](https://github.com/mrveiss/AutoBot-AI/pull/9778))

- *(security)* Mask phone numbers before logging in whatsapp_integration (#9725) (#9774) ([#9774](https://github.com/mrveiss/AutoBot-AI/pull/9774))

- *(ci)* Keep pr-queue-gate.yml valid YAML — build comment via indented printf (#9722) (#9770) ([#9770](https://github.com/mrveiss/AutoBot-AI/pull/9770))

- *(docker)* Make compose stack run all-healthy out of the box (#9720) (#9762) ([#9762](https://github.com/mrveiss/AutoBot-AI/pull/9762))

- *(ci)* Apply .bandit config in security-tests bandit scan (#9726) (#9764) ([#9764](https://github.com/mrveiss/AutoBot-AI/pull/9764))

- *(llc/adapters)* Structured Markdown prompt + inject AUTOBOT_LLC_API_KEY env (#9622, #9623) (#9760) ([#9760](https://github.com/mrveiss/AutoBot-AI/pull/9760))

- *(sso)* Harden SSO secret migration — key validation, error context, reliable tests (#9686) (#9757) ([#9757](https://github.com/mrveiss/AutoBot-AI/pull/9757))

- *(tests)* Correct mock target for is_encryption_enabled after get_nested removal (#8954) (#9756) ([#9756](https://github.com/mrveiss/AutoBot-AI/pull/9756))

- *(llc/frontend)* Read companyId from route params across LLC dashboard views (#9626) (#9723) ([#9723](https://github.com/mrveiss/AutoBot-AI/pull/9723))

- *(security)* Correct Semgrep inline suppression placement to fix SAST failures (#9695) ([#9695](https://github.com/mrveiss/AutoBot-AI/pull/9695))

- *(transcriber)* Add missing transcript route models to resolve startup-import-smoke (#9647) ([#9647](https://github.com/mrveiss/AutoBot-AI/pull/9647))

- *(ci)* Resolve all CI failures from uv deps bump (MVA-3524) (#9631) ([#9631](https://github.com/mrveiss/AutoBot-AI/pull/9631))

- *(ci)* Run isort to fix import ordering after black reformat

- *(deps)* Upgrade FastAPI to 0.136.3 for starlette 1.0.1 compatibility

- *(ci)* Use .bandit config in security.yml bandit scans (#9694) (#9708) ([#9708](https://github.com/mrveiss/AutoBot-AI/pull/9708))

- *(ansible)* Add missing autobot_shared symlink for SLM backend (#9565) (#9707) ([#9707](https://github.com/mrveiss/AutoBot-AI/pull/9707))

- *(lint)* Resolve oxlint errors blocking frontend-tests CI (#9541) (#9705) ([#9705](https://github.com/mrveiss/AutoBot-AI/pull/9705))

- *(tests)* Replace FontAwesome selectors with Icon component classes (MVA-3922) (#9703) ([#9703](https://github.com/mrveiss/AutoBot-AI/pull/9703))

- *(ci)* Remove unused imports in MCP resources (MVA-2205) (#9689) ([#9689](https://github.com/mrveiss/AutoBot-AI/pull/9689))

- *(ci)* Create api/transcriber router to fix startup-import-smoke (#9551, MVA-3729)

- *(connectors)* Correct SourceInfo fields in OneDrive connector (#9004) (#9679) ([#9679](https://github.com/mrveiss/AutoBot-AI/pull/9679))

- *(api)* Allow setting nullable document fields to null (#9525) (#9678) ([#9678](https://github.com/mrveiss/AutoBot-AI/pull/9678))

- *(api)* Allow canvas title to be set to null (#9526) (#9677) ([#9677](https://github.com/mrveiss/AutoBot-AI/pull/9677))

- *(security)* Move SSO credentials to encrypted SystemSecret storage (MVA-1737) (#9676) ([#9676](https://github.com/mrveiss/AutoBot-AI/pull/9676))

- *(ansible)* Add AUTOBOT_BACKEND_HOST to backend.env.j2 template (#9674) ([#9674](https://github.com/mrveiss/AutoBot-AI/pull/9674))

- *(ci)* Remove console statements from test files (MVA-2605) (#9684) ([#9684](https://github.com/mrveiss/AutoBot-AI/pull/9684))

- *(ci)* Fix flake8 errors blocking Code Quality check (MVA-3524) (#9683) ([#9683](https://github.com/mrveiss/AutoBot-AI/pull/9683))

- *(ci)* Add missing tmpfs mounts for hardened-smoke-test (#9665) (#9666) ([#9666](https://github.com/mrveiss/AutoBot-AI/pull/9666))

- *(ansible)* Resolve 4 critical deployment issues (MVA-3727) (#9661) ([#9661](https://github.com/mrveiss/AutoBot-AI/pull/9661))

- *(llm)* Ensure tier field matches selected model [MVA-2022] (#9166) ([#9166](https://github.com/mrveiss/AutoBot-AI/pull/9166))

- *(ansible)* Use build:slm command for SLM frontend deployment (#9563) (#9594) ([#9594](https://github.com/mrveiss/AutoBot-AI/pull/9594))

- *(ci)* Resolve CI failures from dependabot PR #9511 (#9550) ([#9550](https://github.com/mrveiss/AutoBot-AI/pull/9550))

- *(ci)* Update Storybook visual regression baselines for theme stories (#9577)

- *(frontend)* Replace deprecated useApi with useApiClient

- *(frontend)* Convert vite.config.ts to .js to resolve oxlint parsing error (#9366) ([#9366](https://github.com/mrveiss/AutoBot-AI/pull/9366))

- *(ci)* Resolve oxlint correctness errors blocking Dev_new_gui CI

- *(hardened)* Remove postgres_password secret that broke SLM DB auth

- *(slm)* Respect SLM_DATA_DIR and SLM_CONFIG_DIR env vars in Settings

- *(ci)* Resolve Semgrep SAST blocking findings (MVA-3380) (#9630) ([#9630](https://github.com/mrveiss/AutoBot-AI/pull/9630))

- *(connectors)* Correct SourceInfo fields in OneDrive connector (MVA-3730) (#9635) ([#9635](https://github.com/mrveiss/AutoBot-AI/pull/9635))

- *(adapters)* Narrow FileNotFoundError guard to cwd-only in ClaudeCodeAdapter (#9637) (#9643) ([#9643](https://github.com/mrveiss/AutoBot-AI/pull/9643))

- *(docker)* Redirect SLM data_dir to named volume to fix hardened-smoke-test (#9560) ([#9560](https://github.com/mrveiss/AutoBot-AI/pull/9560))

- *(security)* Enforce fail-closed authorization for device JWTs (MVA-3237) (#9614) ([#9614](https://github.com/mrveiss/AutoBot-AI/pull/9614))

- *(backend)* Resolve Docker smoke-test dependency conflicts (#9465)

- *(frontend)* Resolve 5 TypeScript errors in PluginsView and SettingsView (#9477)

- *(flake8)* Remove unused imports exposed by isort (MVA-3526)

- *(backend)* Resolve Docker smoke-test dependency conflicts (#9465)

- *(frontend)* Resolve 5 TypeScript errors in PluginsView and SettingsView (#9477)

- *(semgrep)* Move nosemgrep suppressions to same line as execute() calls

- *(security)* Fix CRITICAL rate limiting vulnerabilities (#9610)

- *(ci)* Regenerate frontend types after workflow.types changes (#9499, MVA-3668)

- *(ci)* Remove unused imports flagged by autoflake (#9499, MVA-3668)

- *(ci)* Remove 4 unused imports flagged by flake8 (#9499, MVA-3665)

- *(ci)* Fix import sorting violations in code-quality check (#9499, MVA-3665)

- *(ci)* Resolve code-quality and SAST failures in SSO rate limiting PR (#9499, MVA-3665)

- *(ci)* Update vue-tsc baseline from 245 to 251 errors (#9461) ([#9461](https://github.com/mrveiss/AutoBot-AI/pull/9461))

- *(i18n)* Add 118 missing translation keys to en.json (#9537) ([#9537](https://github.com/mrveiss/AutoBot-AI/pull/9537))

- *(frontend/css)* Align default accent color to electric blue from design-tokens.css (#9040)

- *(frontend)* Resolve missing imports blocking CI builds

- *(provision-wizard)* Attribute handler failures correctly (GH#9286) (#9411) ([#9411](https://github.com/mrveiss/AutoBot-AI/pull/9411))

- *(router-registry)* Remove duplicate mobile_devices registration (MVA-3022) (#9420) ([#9420](https://github.com/mrveiss/AutoBot-AI/pull/9420))

- *(backend)* Remove deleted api.transcriber import from core_routers (#9384) ([#9415](https://github.com/mrveiss/AutoBot-AI/pull/9415))

- *(docker)* Add /app/config tmpfs mount for hardened backend/worker (#9374) ([#9374](https://github.com/mrveiss/AutoBot-AI/pull/9374))

- *(ci)* Add /app/logs tmpfs for autobot-slm in hardened config (MVA-2798) (#9373) ([#9373](https://github.com/mrveiss/AutoBot-AI/pull/9373))

- *(auth)* Correct config access for internal_api_key (#9385) ([#9385](https://github.com/mrveiss/AutoBot-AI/pull/9385))

- *(provision-wizard)* Track RUNNING HANDLER lines for failure attribution (#9286) (#9379) ([#9379](https://github.com/mrveiss/AutoBot-AI/pull/9379))

- *(codegen)* Regenerate frontend types for WorkflowTask skill fields

- *(tasks)* Normalize naive datetimes in snapshot cleanup (#9236)

- *(ci)* Upgrade frontend-test workflow to Node.js 22 (MVA-2804) (#9368) ([#9368](https://github.com/mrveiss/AutoBot-AI/pull/9368))


### CI/CD

- Fail-fast visual-regression hang + dedup codegen step + cache Playwright (#10038, #10059, #10365) (#10393) ([#10393](https://github.com/mrveiss/AutoBot-AI/pull/10393))

- *(frontend)* Drop redundant double unit-test run (#10365) (#10389) ([#10389](https://github.com/mrveiss/AutoBot-AI/pull/10389))

- *(visual-regression)* Refresh 16 stale Storybook baselines (#10320) (#10359) ([#10359](https://github.com/mrveiss/AutoBot-AI/pull/10359))

- *(visual-regression)* Fix flaky Storybook readiness — pre-fetch http-server + widen budget (#10316) (#10349) ([#10349](https://github.com/mrveiss/AutoBot-AI/pull/10349))

- *(codegen)* Emit Apache-2.0/SPDX header from gen_frontend_types.py to clear check-drift (#10149) (#10259) ([#10259](https://github.com/mrveiss/AutoBot-AI/pull/10259))

- *(gate)* Always-report refactor of code-quality / startup-import-smoke / frontend-test (#10022) (#10136) ([#10136](https://github.com/mrveiss/AutoBot-AI/pull/10136))

- *(frontend)* Set vue-tsc regression BASELINE 249→0 — guard was toothless post-#9724 (#10093) (#10097) ([#10097](https://github.com/mrveiss/AutoBot-AI/pull/10097))

- *(gate)* Run frontend-test on PRs to Dev_new_gui, not only post-merge (#10019) (#10080) ([#10080](https://github.com/mrveiss/AutoBot-AI/pull/10080))

- *(test)* Co-located deployment smoke gate (#10023) (#10079) ([#10079](https://github.com/mrveiss/AutoBot-AI/pull/10079))

- *(pr-gate)* Raise PR queue limit from 5 to 10

- PR queue gate — warn only, do not auto-close

- Enforce ≤5 open PR hard limit via GitHub Actions gate

- PR queue gate — warn only, do not auto-close

- Enforce ≤5 open PR hard limit via GitHub Actions gate


### Documentation

- *(migrations)* Fix 018 docstring column names (#10371) (#10396) ([#10396](https://github.com/mrveiss/AutoBot-AI/pull/10396))

- *(sso)* Enterprise SSO/OIDC federation build-out PRD (#8994) (#10159) ([#10159](https://github.com/mrveiss/AutoBot-AI/pull/10159))

- *(governance)* Adopt session-lifecycle protocol — .session README + workflow docs (#9918) (#10124) ([#10124](https://github.com/mrveiss/AutoBot-AI/pull/10124))

- Re-apply orphan-wiring zone indexes + remove auto-generated reports (#9711) (#10115) ([#10115](https://github.com/mrveiss/AutoBot-AI/pull/10115))

- *(funding)* Dedupe tier copy — FUNDING.md as single source of truth (#9846) (#10105) ([#10105](https://github.com/mrveiss/AutoBot-AI/pull/10105))

- *(release)* Refresh stale CHANGELOG [Unreleased] + document release workflow (#9870) (#10103) ([#10103](https://github.com/mrveiss/AutoBot-AI/pull/10103))

- *(codegen)* Document MANIFEST canonical enum coverage (#9869) (#10102) ([#10102](https://github.com/mrveiss/AutoBot-AI/pull/10102))

- *(api)* Document DateRangeParams Depends() helper (#9868) (#10052) ([#10052](https://github.com/mrveiss/AutoBot-AI/pull/10052))

- *(testing)* Document make_async_redis/patch_async_redis canonical fixtures (#9867) (#10051) ([#10051](https://github.com/mrveiss/AutoBot-AI/pull/10051))

- *(frontend)* Document useProbeBackedHealth composable (#9866) (#10050) ([#10050](https://github.com/mrveiss/AutoBot-AI/pull/10050))

- *(chromadb)* Document 0.5→1.x reindex requirement + empty-KB startup warning (#9766) (#9945) ([#9945](https://github.com/mrveiss/AutoBot-AI/pull/9945))

- *(triage)* Organize open tracker into 13 umbrella epics + dispatch queue (#9932) ([#9932](https://github.com/mrveiss/AutoBot-AI/pull/9932))

- *(arch)* Mark service-discovery modules as intentional unwired library (#9893) (#9903) ([#9903](https://github.com/mrveiss/AutoBot-AI/pull/9903))

- *(features)* Record registry-only consolidation decision (#9872) (#9898) ([#9898](https://github.com/mrveiss/AutoBot-AI/pull/9898))

- *(security)* Correct secrets cipher claim — shipped is Fernet, not AES-256 (#9894) (#9897) ([#9897](https://github.com/mrveiss/AutoBot-AI/pull/9897))

- *(features)* Record verified capability statuses (codebase-checked) (#9895) ([#9895](https://github.com/mrveiss/AutoBot-AI/pull/9895))

- *(nav)* Resolve conflict markers in 21 _index.md MOCs (#9887) (#9888) ([#9888](https://github.com/mrveiss/AutoBot-AI/pull/9888))

- Reposition around the platform model (core → SLM → modules) + surface buried features (#9871) ([#9871](https://github.com/mrveiss/AutoBot-AI/pull/9871))

- *(sso)* Document SSO secret migration process (#9687) (#9690) ([#9690](https://github.com/mrveiss/AutoBot-AI/pull/9690))

- *(code-review)* Add PR review hardening documentation and test suite (#9605) (#9618) ([#9618](https://github.com/mrveiss/AutoBot-AI/pull/9618))

- *(claude)* Restructure CLAUDE.md into lean quick-reference with sub-docs (#9659) ([#9659](https://github.com/mrveiss/AutoBot-AI/pull/9659))

- *(backend)* Add LLM model fallback documentation (GH#8998)

- *(backend)* Add Obsidian index for backend/ directory (MVA-2591)

- *(connectors)* Add OneDrive/SharePoint connector documentation (#9004)


### Features

- *(secrets)* Dependency query endpoint — GET /v2/secrets/{id}/dependencies (#10381) (#10382) ([#10382](https://github.com/mrveiss/AutoBot-AI/pull/10382))

- *(secrets)* Secret-dependency graph — what depends on a secret (#10374) (#10375) ([#10375](https://github.com/mrveiss/AutoBot-AI/pull/10375))

- *(llc)* Aggregate card enrichment for Portfolio/Program/Project browsers + velocity sparkline (#10232) (#10373) ([#10373](https://github.com/mrveiss/AutoBot-AI/pull/10373))

- *(llc/frontend)* Wire BacklogView drag-reorder + suggest-AC to #9861 backends (#10040) (#10361) ([#10361](https://github.com/mrveiss/AutoBot-AI/pull/10361))

- *(secrets)* Access transparency — who can access a secret (#10343) (#10344) ([#10344](https://github.com/mrveiss/AutoBot-AI/pull/10344))

- *(secrets)* Reconciliation sweep closes revoke-resurrection gate (#10337) (#10340) ([#10340](https://github.com/mrveiss/AutoBot-AI/pull/10340))

- *(secrets)* Dual-write connector credentials into the unified store (#10333) (#10334) ([#10334](https://github.com/mrveiss/AutoBot-AI/pull/10334))

- *(secrets)* Flagged unified-read + SQLite fallback in ConnectorCredentialStore (#10326) (#10327) ([#10327](https://github.com/mrveiss/AutoBot-AI/pull/10327))

- *(workflows)* Conditional branching execution (#9036) + per-run API key injection (#9037) (#10325) ([#10325](https://github.com/mrveiss/AutoBot-AI/pull/10325))

- *(analytics+error-monitoring)* Retire dead engagement duplicate; Prometheus-backed error metrics (#9959, #9983) (#10314) ([#10314](https://github.com/mrveiss/AutoBot-AI/pull/10314))

- *(secrets)* Import legacy SQLite secrets store → unified envelope (#10312) (#10313) ([#10313](https://github.com/mrveiss/AutoBot-AI/pull/10313))

- *(media)* AI video generation — Runway provider + async API + generate_video tool (#9016) (#10308) ([#10308](https://github.com/mrveiss/AutoBot-AI/pull/10308))

- *(llc)* UI integration — reachable boards + adapter-selectable agent hire (#10219) (#10293) ([#10293](https://github.com/mrveiss/AutoBot-AI/pull/10293))

- *(search)* WebSearchProvider abstraction + SearXNG and Brave backends (#9022, #9023) (#10292) ([#10292](https://github.com/mrveiss/AutoBot-AI/pull/10292))

- *(secrets)* Migrate PG legacy Fernet secrets → envelope, in-place (#10286) (#10295) ([#10295](https://github.com/mrveiss/AutoBot-AI/pull/10295))

- *(transcriber/frontend)* Implement ProjectsView + ProjectDetailView (#10289) (#10291) ([#10291](https://github.com/mrveiss/AutoBot-AI/pull/10291))

- *(connectors)* Surface GitLab/Gitea/Forgejo connectors in the create UI (#9011) (#10283) ([#10283](https://github.com/mrveiss/AutoBot-AI/pull/10283))

- *(chat)* In-folder search + folder archive (#8987) (#10282) ([#10282](https://github.com/mrveiss/AutoBot-AI/pull/10282))

- *(llm)* Reasoning-effort cluster — wire effort into providers + per-conversation UI (#9017/#9468/#9460/#9471/#9531) (#10276) ([#10276](https://github.com/mrveiss/AutoBot-AI/pull/10276))

- *(connectors)* Surface OneDrive/SharePoint connector in create API + UI with OAuth connect (#9004) (#10271) ([#10271](https://github.com/mrveiss/AutoBot-AI/pull/10271))

- *(llc/adapters)* Subscription quota auto-pause + secrets-backed gh_token (#10218, #10217) (#10257) ([#10257](https://github.com/mrveiss/AutoBot-AI/pull/10257))

- *(sso)* PKCE (S256) on the OIDC authorization-code flow (#10150) (#10254) ([#10254](https://github.com/mrveiss/AutoBot-AI/pull/10254))

- *(lint)* Guard against ApiClient envelope misuse (.json()/.data on parsed results) (#10025) (#10268) ([#10268](https://github.com/mrveiss/AutoBot-AI/pull/10268))

- *(connectors)* Surface Google Drive connector in create API + UI with OAuth connect (#9003) (#10265) ([#10265](https://github.com/mrveiss/AutoBot-AI/pull/10265))

- *(whatsapp)* Wire inbound webhook route + dispatch to chat pipeline (#9007) (#10266) ([#10266](https://github.com/mrveiss/AutoBot-AI/pull/10266))

- *(auth)* Default to single_company + seed unified admin from SLM creds (#10199) (#10243) ([#10243](https://github.com/mrveiss/AutoBot-AI/pull/10243))

- *(llc)* Parse CLI token usage and report to LLC budget (#10220) (#10242) ([#10242](https://github.com/mrveiss/AutoBot-AI/pull/10242))

- *(transcriber/frontend)* ASR provider selector in settings (#10147) (#10237) ([#10237](https://github.com/mrveiss/AutoBot-AI/pull/10237))

- *(transcriber)* User-selectable cloud ASR providers + diarizing-provider orchestrator path (#10147) (#10236) ([#10236](https://github.com/mrveiss/AutoBot-AI/pull/10236))

- *(#9929)* Per-account theme persistence (#8988) + admin shared-links view & 500-bug fix (#8996) (#10233) ([#10233](https://github.com/mrveiss/AutoBot-AI/pull/10233))

- *(secrets)* /api/v2/secrets FastAPI router over SecretsCoordinator (#10240) (#10241) ([#10241](https://github.com/mrveiss/AutoBot-AI/pull/10241))

- *(llc/frontend)* Portfolio → Program → Project browser views (#9628) (#10231) ([#10231](https://github.com/mrveiss/AutoBot-AI/pull/10231))

- *(auth)* Seed default admin into autobot_users at startup (idempotent, Postgres-gated) (#10199) (#10230) ([#10230](https://github.com/mrveiss/AutoBot-AI/pull/10230))

- *(transcriber/frontend)* Build TranscriptView with waveform player + segment sync, consume #9466 audio API (#10129) (#10226) ([#10226](https://github.com/mrveiss/AutoBot-AI/pull/10226))

- *(rbac)* Service_management permission gates the SLM surface — ordinary users 403 + no SLM nav (#10198) (#10222) ([#10222](https://github.com/mrveiss/AutoBot-AI/pull/10222))

- *(secrets)* Seed secrets:* RBAC permissions for team/role vaults (#10223) (#10224) ([#10224](https://github.com/mrveiss/AutoBot-AI/pull/10224))

- *(auth)* SLM verifies authority RS256 tokens via cached JWKS (Pattern B) (#10197) (#10215) ([#10215](https://github.com/mrveiss/AutoBot-AI/pull/10215))

- *(secrets)* SecretsCoordinator — resolve→authorize→service orchestration (#10213) (#10214) ([#10214](https://github.com/mrveiss/AutoBot-AI/pull/10214))

- *(auth)* Authority token-validate/introspect + RBAC metadata API (#10195) (#10212) ([#10212](https://github.com/mrveiss/AutoBot-AI/pull/10212))

- *(rag)* CAG context-augmented retrieval strategy + dispatcher behind enable_cag flag (#9018 Phase 1) (#10211) ([#10211](https://github.com/mrveiss/AutoBot-AI/pull/10211))

- *(frontend)* Entity anchor click handler for chat messages (#9479) (#10206) ([#10206](https://github.com/mrveiss/AutoBot-AI/pull/10206))

- *(auth)* RS256 + JWKS for the identity authority — public-key token verification (#10196) (#10205) ([#10205](https://github.com/mrveiss/AutoBot-AI/pull/10205))

- *(secrets)* PrincipalFacts DB resolver from membership tables (#10190) (#10192) ([#10192](https://github.com/mrveiss/AutoBot-AI/pull/10192))

- *(kb)* Wire in the ChromaDB / vector-store explorer (#8999) (#10142) ([#10142](https://github.com/mrveiss/AutoBot-AI/pull/10142))

- *(code-sync)* Generate ansible inventory from DB node registry — node_id hosts + local self-node (#10110) (#10141) ([#10141](https://github.com/mrveiss/AutoBot-AI/pull/10141))

- *(secrets)* UnifiedSecretsService — envelope CRUD + sharing (#10111) (#10134) ([#10134](https://github.com/mrveiss/AutoBot-AI/pull/10134))

- *(llc/sprint)* Project timeline + Gantt view for sprint planning (#9020) (#10133) ([#10133](https://github.com/mrveiss/AutoBot-AI/pull/10133))

- *(secrets)* RBAC authorization policy (pure) — accessible_vaults + authorize (#10113) (#10135) ([#10135](https://github.com/mrveiss/AutoBot-AI/pull/10135))

- *(governance)* Merge-blocking findings gate via blocks-merge label (#10024) (#10125) ([#10125](https://github.com/mrveiss/AutoBot-AI/pull/10125))

- *(transcriber)* Waveform + ranged audio playback API on recordings router (#9466) (#10122) ([#10122](https://github.com/mrveiss/AutoBot-AI/pull/10122))

- *(connectors)* OAuth authorize/callback flow + auto-refresh resolver (#9019) (#10087) ([#10087](https://github.com/mrveiss/AutoBot-AI/pull/10087))

- *(secrets)* Envelope store schema — secrets cols + secret_grants table (#10099) (#10100) ([#10100](https://github.com/mrveiss/AutoBot-AI/pull/10100))

- *(secrets)* Canonical vault/principal namespace — VaultRef + kinds (#10094) (#10096) ([#10096](https://github.com/mrveiss/AutoBot-AI/pull/10096))

- *(secrets)* Envelope-crypto core — root key, per-vault KEK, DEK wrapping (#10089) (#10090) ([#10090](https://github.com/mrveiss/AutoBot-AI/pull/10090))

- *(llc)* GitHub PR ↔ work-item linking for LLC adapters (#9625) (#10061) ([#10061](https://github.com/mrveiss/AutoBot-AI/pull/10061))

- *(llc/api)* Backlog reorder + suggest-AC, org-chart enrichment, full work-items tenant scoping (#9861) (#10034) ([#10034](https://github.com/mrveiss/AutoBot-AI/pull/10034))

- *(llc)* Agent run replay — record, replay, diff, fixture export (#9034) (#10030) ([#10030](https://github.com/mrveiss/AutoBot-AI/pull/10030))

- *(llc/budget)* Token-based budget mode with shadow cost tracking (#8997) (#9998) ([#9998](https://github.com/mrveiss/AutoBot-AI/pull/9998))

- *(llc/frontend)* Company selector + LLC sidebar navigation spine (#9627) (#9997) ([#9997](https://github.com/mrveiss/AutoBot-AI/pull/9997))

- *(llc/scheduler)* Rate-limit detection + backoff for registry adapters (#9773) (#9993) ([#9993](https://github.com/mrveiss/AutoBot-AI/pull/9993))

- *(code-sync)* One-click full-pipeline update — orchestration endpoint + pipeline UI (#9971) (#9991) ([#9991](https://github.com/mrveiss/AutoBot-AI/pull/9991))

- *(frontend)* Wire failure-analysis diagnostics UI to causal-inference endpoints (#9892) (#9974) ([#9974](https://github.com/mrveiss/AutoBot-AI/pull/9974))

- *(frontend)* Wire error-monitoring dashboard to backend endpoints (#9891) (#9973) ([#9973](https://github.com/mrveiss/AutoBot-AI/pull/9973))

- *(frontend)* Wire vision automation panel to /api/vision endpoints (#9890) (#9972) ([#9972](https://github.com/mrveiss/AutoBot-AI/pull/9972))

- *(llc/budget)* Provision per-agent budget — hire-time auto-create + explicit endpoint (#9901) (#9981) ([#9981](https://github.com/mrveiss/AutoBot-AI/pull/9981))

- *(llc)* Optional workIntent on work-item checkout — audit trail + similarity warn (#9532) (#9976) ([#9976](https://github.com/mrveiss/AutoBot-AI/pull/9976))

- *(backend)* Mount transcripts router with real storage backing (#9863) (#9955) ([#9955](https://github.com/mrveiss/AutoBot-AI/pull/9955))

- *(llc)* Compose-runnable subprocess agents — CLI gate, image bake-in, env passthrough (#9793) (#9948) ([#9948](https://github.com/mrveiss/AutoBot-AI/pull/9948))

- *(slm)* Add canonical postgres + scheduler roles to role registry (#9853) (#9946) ([#9946](https://github.com/mrveiss/AutoBot-AI/pull/9946))

- *(docker)* Auto-provision signing secrets — compose works out-of-the-box (#9905) (#9906) ([#9906](https://github.com/mrveiss/AutoBot-AI/pull/9906))

- *(llc)* Make LLC module functional end-to-end — wire 7 paths, org-chart endpoint, e2e + CI gate (#9861) (#9902) ([#9902](https://github.com/mrveiss/AutoBot-AI/pull/9902))

- *(llc/scheduler)* Route claude_code heartbeats through adapter registry + run-scoped key (#9622, #9623) (#9772) ([#9772](https://github.com/mrveiss/AutoBot-AI/pull/9772))

- *(admin)* Telemetry and analytics opt-out (#9035) (#9704) ([#9704](https://github.com/mrveiss/AutoBot-AI/pull/9704))

- *(ci)* Enforce pre-commit hooks to prevent code-quality CI failures (MVA-2111) (#9698) ([#9698](https://github.com/mrveiss/AutoBot-AI/pull/9698))

- *(ui)* Add LLM fallback status visibility to Admin UI (MVA-2999) (#9421) ([#9421](https://github.com/mrveiss/AutoBot-AI/pull/9421))

- *(llm)* Extract thinking_tokens from Anthropic response usage (MVA-3089) (#9452) ([#9452](https://github.com/mrveiss/AutoBot-AI/pull/9452))

- *(ci)* Add auto-fix workflow for code formatting violations (#9181) ([#9181](https://github.com/mrveiss/AutoBot-AI/pull/9181))

- *(kb)* Wire KB folder watcher into backend lifecycle (#9000) (#9599) ([#9599](https://github.com/mrveiss/AutoBot-AI/pull/9599))

- *(llc)* Implement 3-tier configurable timeout in LLC adapters (#9521, MVA-3019, MVA-3020) ([#9555](https://github.com/mrveiss/AutoBot-AI/pull/9555))

- *(telegram)* Wire Telegram bot router into integration registry (#9006) (#9544) ([#9544](https://github.com/mrveiss/AutoBot-AI/pull/9544))

- *(slm/auth)* Add callback URL allowlist validation for OAuth (#9500) (#9509) ([#9509](https://github.com/mrveiss/AutoBot-AI/pull/9509))

- *(ui)* Add theme preset system with 12 named themes (#8988) (#9502) ([#9502](https://github.com/mrveiss/AutoBot-AI/pull/9502))

- *(frontend)* Add Ember theme toggle to Settings UI (#9274) (#9481) ([#9481](https://github.com/mrveiss/AutoBot-AI/pull/9481))

- *(agent)* Add entity anchor UI convention to chat system prompt (#9297) (#9478) ([#9478](https://github.com/mrveiss/AutoBot-AI/pull/9478))

- *(context-window)* Wire adaptive budget scaling for unknown models (#9294)

- *(security)* Add comprehensive SSO/OIDC security test suite (MVA-3398)

- *(auth)* Implement device JWT authentication with security controls (#9493)

- *(frontend)* Add thinking badge to MessageItem component (MVA-3091)

- *(settings)* Wire device management UI into settings view (MVA-3024)

- *(chat)* Add thinking metadata to response schema and SSE stream (MVA-3090)

- *(kb)* Auto-watch folder for KB ingestion — automatically ingest new files added to monitored directories (#9000)

- *(connectors)* Add Google Drive knowledge base connector (#9003)

- *(llm)* Quota-triggered model fallback (GH#8998) (#9442) ([#9442](https://github.com/mrveiss/AutoBot-AI/pull/9442))

- *(chat)* Wire context overflow protection into chat endpoints (#9043) (#9427) ([#9427](https://github.com/mrveiss/AutoBot-AI/pull/9427))

- *(mobile)* Add push notification delivery module and integration tests (GH#4463)

- *(workflows)* Add switch/case nodes and JSONPath conditions (#9036)

- *(theme)* Add Ember warm palette theme variant + icon set (#9274)

- *(admin)* Add retention policy CRUD API and DB schema (MVA-3145, GH#8995)

- *(llc/budget)* Token-based budget UI in CostDashboard (GH#8997)

- *(observability)* Add Prometheus metrics and Grafana dashboard for mobile device pairing

- *(MVA-3085)* Add Mobile Devices tab to settings view with device pairing UI

- *(transcriber)* Add transcript editing API (MVA-2173) (#9350) ([#9350](https://github.com/mrveiss/AutoBot-AI/pull/9350))

- *(connectors)* Add Microsoft OneDrive/SharePoint connector (#9004)

- *(voice-bundle)* Register voice bundle routers (#8605) (#9382) ([#9382](https://github.com/mrveiss/AutoBot-AI/pull/9382))

- *(mobile)* Build QR code pairing dialog component (MVA-2993)

- *(connectors)* Enable GitLab/Gitea/Forgejo connectors in API (#9011)


### Miscellaneous

- *(deps)* Bump the uv group across 4 directories with 5 updates (#10354) ([#10354](https://github.com/mrveiss/AutoBot-AI/pull/10354))

- *(deps)* Bump the pip group across 3 directories with 3 updates (#10353) ([#10353](https://github.com/mrveiss/AutoBot-AI/pull/10353))

- *(deps)* Bump the pip group across 2 directories with 2 updates (#10256) ([#10256](https://github.com/mrveiss/AutoBot-AI/pull/10256))

- *(deps)* Bump the uv group across 3 directories with 5 updates (#10245) ([#10245](https://github.com/mrveiss/AutoBot-AI/pull/10245))

- *(deps)* Bump npm deps — dompurify 3.4.11 (security), storybook 10.4.6 (#10311) (#10328) ([#10328](https://github.com/mrveiss/AutoBot-AI/pull/10328))

- *(deps)* Bump pip security deps — cryptography 49.0.0, python-multipart 0.0.32, pypdf 6.13.3, torch 2.12.1/torchvision 0.27.1 (#10310) (#10330) ([#10330](https://github.com/mrveiss/AutoBot-AI/pull/10330))

- *(deps)* Bump the npm_and_yarn group across 6 directories with 3 updates (#10244) ([#10244](https://github.com/mrveiss/AutoBot-AI/pull/10244))

- *(deps)* Bump the uv group across 3 directories with 4 updates (#10216) ([#10216](https://github.com/mrveiss/AutoBot-AI/pull/10216))

- *(deps)* Widen Dependabot grouping to collapse the PR flood + gate python/ubuntu minor (#10191) ([#10191](https://github.com/mrveiss/AutoBot-AI/pull/10191))

- *(license)* Add SPDX header enforcement hook + backfill post-sweep files (#9840) (#10127) ([#10127](https://github.com/mrveiss/AutoBot-AI/pull/10127))

- *(license)* Document github-mcp-server provisioning in THIRD-PARTY-NOTICES (#9791) (#10116) ([#10116](https://github.com/mrveiss/AutoBot-AI/pull/10116))

- *(deps)* Bump the npm_and_yarn group across 5 directories with 3 updates (#10098) ([#10098](https://github.com/mrveiss/AutoBot-AI/pull/10098))

- *(triage)* 2026-06-12 umbrella restore + delta triage — reopen U1/U2, file 42 follow-ups (part of #9919, part of #9920) (#10033) ([#10033](https://github.com/mrveiss/AutoBot-AI/pull/10033))

- *(lifespan)* Extract @requires_postgres decorator + gate remaining Postgres paths (#9913 #9765) (#9937) ([#9937](https://github.com/mrveiss/AutoBot-AI/pull/9937))

- *(scripts)* Add API wiring audit (frontend/backend contract + dead-surface) (#9849) ([#9849](https://github.com/mrveiss/AutoBot-AI/pull/9849))

- *(license)* Relicense AutoBot to Apache-2.0 (#9826) (#9830) ([#9830](https://github.com/mrveiss/AutoBot-AI/pull/9830))

- *(deps-dev)* Bump npm-run-all2 in /autobot-frontend (#9807) ([#9807](https://github.com/mrveiss/AutoBot-AI/pull/9807))

- *(deps)* Bump actions/cache from 4 to 5 (#9810) ([#9810](https://github.com/mrveiss/AutoBot-AI/pull/9810))

- *(deps)* Bump actions/checkout from 4 to 6 (#9809) ([#9809](https://github.com/mrveiss/AutoBot-AI/pull/9809))

- *(deps)* Bump the all-minor-patch group (#9806) ([#9806](https://github.com/mrveiss/AutoBot-AI/pull/9806))

- *(deps)* Update numpy requirement (#9823) ([#9823](https://github.com/mrveiss/AutoBot-AI/pull/9823))

- *(deps)* Update fastapi requirement (#9822) ([#9822](https://github.com/mrveiss/AutoBot-AI/pull/9822))

- *(deps)* Update transformers requirement (#9821) ([#9821](https://github.com/mrveiss/AutoBot-AI/pull/9821))

- *(deps)* Update openvino requirement from >=2026.1.0 to >=2026.2.0 (#9820) ([#9820](https://github.com/mrveiss/AutoBot-AI/pull/9820))

- *(deps)* Update mcp requirement from >=1.27.1 to >=1.27.2 (#9818) ([#9818](https://github.com/mrveiss/AutoBot-AI/pull/9818))

- *(deps)* Update soundfile requirement in /autobot-tts-worker (#9817) ([#9817](https://github.com/mrveiss/AutoBot-AI/pull/9817))

- *(deps)* Update vulture requirement from >=2.11 to >=2.16 (#9816) ([#9816](https://github.com/mrveiss/AutoBot-AI/pull/9816))

- *(deps)* Update torchvision requirement (#9814) ([#9814](https://github.com/mrveiss/AutoBot-AI/pull/9814))

- *(deps)* Update transformers requirement (#9813) ([#9813](https://github.com/mrveiss/AutoBot-AI/pull/9813))

- *(deps)* Update aiohttp requirement (#9812) ([#9812](https://github.com/mrveiss/AutoBot-AI/pull/9812))

- *(deps)* Bump the all-minor-patch group with 2 updates (#9808) ([#9808](https://github.com/mrveiss/AutoBot-AI/pull/9808))

- *(deps)* Bump the all-minor-patch group (#9805) ([#9805](https://github.com/mrveiss/AutoBot-AI/pull/9805))

- *(deps)* Update openai requirement in /autobot-backend (#9803) ([#9803](https://github.com/mrveiss/AutoBot-AI/pull/9803))

- *(deps)* Update boto3 requirement in /autobot-backend (#9802) ([#9802](https://github.com/mrveiss/AutoBot-AI/pull/9802))

- *(deps)* Update pypdf requirement in /autobot-backend (#9801) ([#9801](https://github.com/mrveiss/AutoBot-AI/pull/9801))

- *(deps)* Bump the all-minor-patch group (#9799) ([#9799](https://github.com/mrveiss/AutoBot-AI/pull/9799))

- *(deps)* Bump python (#9797) ([#9797](https://github.com/mrveiss/AutoBot-AI/pull/9797))

- *(deps)* Group Dependabot minor/patch updates to reduce PR flood (#9755) (#9758) ([#9758](https://github.com/mrveiss/AutoBot-AI/pull/9758))

- *(deps)* Bump vega-functions (#9702) ([#9702](https://github.com/mrveiss/AutoBot-AI/pull/9702))

- *(deps)* Bump the uv group across 3 directories with 2 updates

- *(deps)* Bump the npm_and_yarn group across 4 directories with 1 update (#9518) ([#9518](https://github.com/mrveiss/AutoBot-AI/pull/9518))

- *(deps)* Bump the pip group across 2 directories with 2 updates (#9511) ([#9511](https://github.com/mrveiss/AutoBot-AI/pull/9511))

- *(deps)* Bump vega-functions (#9402) ([#9402](https://github.com/mrveiss/AutoBot-AI/pull/9402))

- Trigger CI

- *(deps)* Bump sqlalchemy from 2.0.43 to 2.0.50 (#9438) ([#9438](https://github.com/mrveiss/AutoBot-AI/pull/9438))

- *(deps)* Update anthropic requirement from >=0.104.1 to >=0.105.2 (#9439) ([#9439](https://github.com/mrveiss/AutoBot-AI/pull/9439))

- *(deps)* Bump beautifulsoup4 from 4.13.4 to 4.14.3 (#9440) ([#9440](https://github.com/mrveiss/AutoBot-AI/pull/9440))

- *(deps)* Update pypdf2 requirement from >=3.0.0 to >=3.0.1 (#9436) ([#9436](https://github.com/mrveiss/AutoBot-AI/pull/9436))

- *(deps)* Bump python-json-logger from 3.3.0 to 4.1.0 (#9434) ([#9434](https://github.com/mrveiss/AutoBot-AI/pull/9434))

- *(deps)* Bump psutil from 6.1.1 to 7.2.2 (#9433) ([#9433](https://github.com/mrveiss/AutoBot-AI/pull/9433))

- *(deps)* Update llama-index requirement (#9432) ([#9432](https://github.com/mrveiss/AutoBot-AI/pull/9432))

- *(deps)* Update fastapi requirement (#9423) ([#9423](https://github.com/mrveiss/AutoBot-AI/pull/9423))

- *(deps)* Update tokenizers requirement (#9424) ([#9424](https://github.com/mrveiss/AutoBot-AI/pull/9424))

- *(deps)* Update openvino requirement (#9429) ([#9429](https://github.com/mrveiss/AutoBot-AI/pull/9429))

- *(deps)* Update redis requirement (#9430) ([#9430](https://github.com/mrveiss/AutoBot-AI/pull/9430))

- *(deps)* Bump vue-router in /autobot-slm-frontend (#9405) ([#9405](https://github.com/mrveiss/AutoBot-AI/pull/9405))

- *(deps)* Update requests requirement (#9428) ([#9428](https://github.com/mrveiss/AutoBot-AI/pull/9428))

- *(deps)* Update transformers requirement in /autobot-tts-worker (#9425) ([#9425](https://github.com/mrveiss/AutoBot-AI/pull/9425))

- *(deps)* Update pytest-asyncio requirement (#9422) ([#9422](https://github.com/mrveiss/AutoBot-AI/pull/9422))

- *(deps-dev)* Bump @storybook/vue3 from 10.4.1 to 10.4.2 in /autobot-slm-frontend ([#9404](https://github.com/mrveiss/AutoBot-AI/pull/9404))

- *(deps-dev)* Bump eslint-plugin-vue from 10.9.1 to 10.9.2 in /autobot-slm-frontend ([#9403](https://github.com/mrveiss/AutoBot-AI/pull/9403))

- *(deps)* Bump actions/upload-pages-artifact from 3 to 5 (#9399) ([#9399](https://github.com/mrveiss/AutoBot-AI/pull/9399))

- *(deps)* Bump actions/deploy-pages from 4 to 5 (#9400) ([#9400](https://github.com/mrveiss/AutoBot-AI/pull/9400))

- *(deps)* Bump github/codeql-action from 3.27.1 to 4.36.1 (#9401) ([#9401](https://github.com/mrveiss/AutoBot-AI/pull/9401))

- *(deps)* Update weasyprint requirement in /autobot-backend (#9386) ([#9386](https://github.com/mrveiss/AutoBot-AI/pull/9386))

- *(deps)* Update fastapi requirement in /autobot-backend (#9388) ([#9388](https://github.com/mrveiss/AutoBot-AI/pull/9388))

- *(deps)* Update boto3 requirement in /autobot-backend (#9390) ([#9390](https://github.com/mrveiss/AutoBot-AI/pull/9390))

- *(deps)* Update redis requirement in /autobot-slm-backend (#9391) ([#9391](https://github.com/mrveiss/AutoBot-AI/pull/9391))

- *(deps)* Update uvicorn requirement in /autobot-slm-backend (#9392) ([#9392](https://github.com/mrveiss/AutoBot-AI/pull/9392))

- *(deps)* Update sqlalchemy requirement in /autobot-slm-backend (#9393) ([#9393](https://github.com/mrveiss/AutoBot-AI/pull/9393))

- *(deps)* Bump vue-i18n from 11.3.2 to 11.4.4 in /autobot-frontend (#9394) ([#9394](https://github.com/mrveiss/AutoBot-AI/pull/9394))

- *(deps-dev)* Bump @vitest/ui in /autobot-frontend (#9396) ([#9396](https://github.com/mrveiss/AutoBot-AI/pull/9396))

- *(deps-dev)* Bump @vitest/coverage-v8 in /autobot-frontend (#9398) ([#9398](https://github.com/mrveiss/AutoBot-AI/pull/9398))

- *(deps)* Update sqlalchemy requirement in /autobot-backend (#9389) ([#9389](https://github.com/mrveiss/AutoBot-AI/pull/9389))

- *(deps)* Bump the pip group across 2 directories with 1 update (#9363) ([#9363](https://github.com/mrveiss/AutoBot-AI/pull/9363))

- *(deps)* Bump chromadb from 1.2.1 to 1.5.9 in /requirements-ci ([#9106](https://github.com/mrveiss/AutoBot-AI/pull/9106))

- *(deps)* Bump the npm_and_yarn group across 3 directories with 2 updates (#8976) ([#8976](https://github.com/mrveiss/AutoBot-AI/pull/8976))

- *(deps)* Bump langsmith in the pip group across 1 directory (#8282) ([#8282](https://github.com/mrveiss/AutoBot-AI/pull/8282))

- *(deps)* Bump the npm_and_yarn group across 1 directory with 3 updates (#8267) ([#8267](https://github.com/mrveiss/AutoBot-AI/pull/8267))

- *(deps)* Bump the pip group across 2 directories with 1 update (#7681) ([#7681](https://github.com/mrveiss/AutoBot-AI/pull/7681))

- *(deps)* Bump @protobufjs/utf8 (#7679) ([#7679](https://github.com/mrveiss/AutoBot-AI/pull/7679))


### Refactoring

- *(frontend)* Migrate VisionMultimodalApiClient vision methods to canonical ApiClient + shared types (#9985) (#10250) ([#10250](https://github.com/mrveiss/AutoBot-AI/pull/10250))

- *(slm)* Identify SLM by group/role facts, not hardcoded node name (#9956) (#10066) ([#10066](https://github.com/mrveiss/AutoBot-AI/pull/10066))

- *(ansible)* Consolidate autobot-backend.service.j2 templates (#10005) (#10057) ([#10057](https://github.com/mrveiss/AutoBot-AI/pull/10057))

- *(code-intelligence)* Adopt modular security/ package, shim monolith (#9856) (#10029) ([#10029](https://github.com/mrveiss/AutoBot-AI/pull/10029))

- *(extensions)* Collapse duplicate extensions/ package into middleware/ (#9794) (#10004) ([#10004](https://github.com/mrveiss/AutoBot-AI/pull/10004))

- *(llc/scheduler)* Extract PollLoopScheduler base for poll-loop schedulers (#9842) (#10003) ([#10003](https://github.com/mrveiss/AutoBot-AI/pull/10003))

- *(llc/api)* Shared get_session + service_dep DI helper across routers (#9843) (#9994) ([#9994](https://github.com/mrveiss/AutoBot-AI/pull/9994))

- *(llc/adapters/tests)* Hoist shared adapter test helpers into conftest fixtures (#9844) (#9990) ([#9990](https://github.com/mrveiss/AutoBot-AI/pull/9990))

- *(llc/adapters)* Share probe_pid/terminate_pid primitives in subprocess_support (#9839) (#9979) ([#9979](https://github.com/mrveiss/AutoBot-AI/pull/9979))

- *(shared)* Promote guarded env_float/env_int to autobot_shared (#9841) (#9964) ([#9964](https://github.com/mrveiss/AutoBot-AI/pull/9964))

- *(llc/frontend)* Consolidate tree-build, status-color, run-status mapping (#9909) (#9969) ([#9969](https://github.com/mrveiss/AutoBot-AI/pull/9969))

- *(slm)* Extract compose fleet seeder/heartbeat into services/compose_fleet (#9854) (#9947) ([#9947](https://github.com/mrveiss/AutoBot-AI/pull/9947))

- *(dedup)* Eliminate code duplication via behavior-preserving extraction (#9794) (#9865) ([#9865](https://github.com/mrveiss/AutoBot-AI/pull/9865))

- *(llc/adapters)* Extract shared SubprocessLifecycleAdapter base (#9834) (#9835) ([#9835](https://github.com/mrveiss/AutoBot-AI/pull/9835))

- *(llc)* Consolidate config, terminal-status helper, key validation + fix broken test (#9776, #9777, #9763) (#9829) ([#9829](https://github.com/mrveiss/AutoBot-AI/pull/9829))

- *(voice-rbac)* Consolidate admin role check using _require_admin() Depends pattern (#9450) ([#9450](https://github.com/mrveiss/AutoBot-AI/pull/9450))

- *(schemas)* Consolidate SelfUpdateResponse into NodeSyncResponse (#9196) (#9455) ([#9455](https://github.com/mrveiss/AutoBot-AI/pull/9455))

- *(voice-rbac)* Break circular import by extracting shared helpers (#8980)

- *(rbac)* Use Depends(_require_admin) in voice_bundle_user.py (#8983)

- *(security)* Consolidate SSRF guards into ssrf_guard.py (GH #6533) ([#7539](https://github.com/mrveiss/AutoBot-AI/pull/7539))


### Styling

- *(base)* Apply Black formatting to 5 files in Dev_new_gui (MVA-2892)


### Testing

- *(migrations)* #10026 case 2 — 018 converts legacy naive timestamps + tz round-trip (#10026) (#10368) ([#10368](https://github.com/mrveiss/AutoBot-AI/pull/10368))

- *(sso)* Rate-limit throttle tests (#9611) + callback host-case test fix (#10255) (#10270) ([#10270](https://github.com/mrveiss/AutoBot-AI/pull/10270))

- *(voice-rbac)* Repair voice-bundle admin tests so audit-emit assertions run (#8977) (#10207) ([#10207](https://github.com/mrveiss/AutoBot-AI/pull/10207))

- *(circuit-breaker)* Add unit tests for reset_on_success modes (#9431) (#10041) ([#10041](https://github.com/mrveiss/AutoBot-AI/pull/10041))

- *(frontend)* E2E tests for thinking mode toggle and indicator (MVA-3092) (#9418) ([#9418](https://github.com/mrveiss/AutoBot-AI/pull/9418))

- *(circuit-breaker)* Add tests for reset_on_success feature (#9293) (#9503) ([#9503](https://github.com/mrveiss/AutoBot-AI/pull/9503))

- *(transcriber)* Expand composable test coverage for useSseProgress and useTranscriberApi (#9209) (#9482) ([#9482](https://github.com/mrveiss/AutoBot-AI/pull/9482))

- *(auth)* Fix device JWT test mocks for async session

- *(MVA-3028)* Add unit and integration tests for reasoning effort backend


### Cleanup

- *(transcriber/frontend)* Export RecordingStatus type from useTranscriberApi (#9207) (#10106) ([#10106](https://github.com/mrveiss/AutoBot-AI/pull/10106))

- *(transcriber)* Consolidate _DEFAULT_USER in transcripts.py into deps.DEFAULT_USER (#9513) (#10104) ([#10104](https://github.com/mrveiss/AutoBot-AI/pull/10104))


### Consolidation

- Promote AIStackClient.connection_status to ConnectionStatus enum (#10008) (#10145) ([#10145](https://github.com/mrveiss/AutoBot-AI/pull/10145))

- *(migrations)* Shared alembic guard helpers — has_table/has_column/ensure_pg_enum (#10027) (#10072) ([#10072](https://github.com/mrveiss/AutoBot-AI/pull/10072))


### Dedup

- *(#9859 Family G)* Extract shared scoped CSS from chat components via @reference (#10306) (#10366) ([#10366](https://github.com/mrveiss/AutoBot-AI/pull/10366))

- *(#9859 Family B)* Extract shared scoped CSS from analytics panels (#10304) (#10341) ([#10341](https://github.com/mrveiss/AutoBot-AI/pull/10341))

- *(#9859 Family F)* Extract shared scoped CSS from marketplace/plugins views (#10305) (#10336) ([#10336](https://github.com/mrveiss/AutoBot-AI/pull/10336))

- *(#9859 Family A)* Extract shared scoped CSS from analytics dashboards (#10301) (#10329) ([#10329](https://github.com/mrveiss/AutoBot-AI/pull/10329))

- *(#9859 Family E)* Extract shared scoped CSS from orphan managers (#10302) (#10322) ([#10322](https://github.com/mrveiss/AutoBot-AI/pull/10322))

- *(#9859 Family C)* Extract shared scoped CSS from source modals (#10300) (#10315) ([#10315](https://github.com/mrveiss/AutoBot-AI/pull/10315))


### Enhancement

- *(transcriber/frontend)* Extract inline-edit pattern into useInlineEdit composable (#9205) (#10107) ([#10107](https://github.com/mrveiss/AutoBot-AI/pull/10107))

- *(transcriber/frontend)* Extract file download blob pattern into useFileDownload() composable (#9204) (#9417) ([#9417](https://github.com/mrveiss/AutoBot-AI/pull/9417))

- *(transcriber/frontend)* Extract AiAnalysisPanel SSE streaming into useAiAnalysis() composable (#9203) (#9407) ([#9407](https://github.com/mrveiss/AutoBot-AI/pull/9407))

- *(transcriber/frontend)* Replace KbPushButton manual polling with useKbStatus() composable (#9206)


### Harden

- *(secrets)* Concurrency-safe register via ON CONFLICT (#10374 follow-up) (#10376) ([#10376](https://github.com/mrveiss/AutoBot-AI/pull/10376))


### Merge

- Incorporate main lineage into Dev_new_gui (Dev_new_gui authoritative)


### Release

- Dev_new_gui → main (#9300) ([#9300](https://github.com/mrveiss/AutoBot-AI/pull/9300))


### Security

- *(transcriber)* Strict ownership in can_access — fix DEFAULT_USER IDOR (#9968) (#10228) ([#10228](https://github.com/mrveiss/AutoBot-AI/pull/10228))

- *(bandit)* Replace repo-wide category skips with per-call-site nosec (#9709) (#10028) ([#10028](https://github.com/mrveiss/AutoBot-AI/pull/10028))

- *(frontend)* Override shell-quote >=1.8.4 — fix critical GHSA-w7jw-789q-3m8p (#9857) (#9858) ([#9858](https://github.com/mrveiss/AutoBot-AI/pull/9858))

- *(docker)* Remove static fallback JWT/session signing secrets from compose (#9775) (#9827) ([#9827](https://github.com/mrveiss/AutoBot-AI/pull/9827))

- *(telegram)* Encrypt bot token in Redis storage (#9606) (#9675) ([#9675](https://github.com/mrveiss/AutoBot-AI/pull/9675))

- *(sso)* Fix SSRF URL-allowlist bypass in OAuth callback (MVA-3542) (#9673) ([#9673](https://github.com/mrveiss/AutoBot-AI/pull/9673))

- *(telegram)* Encrypt bot token in Redis storage (#9606) (#9650) ([#9650](https://github.com/mrveiss/AutoBot-AI/pull/9650))

- *(webhooks)* Implement fail-closed authentication (GH#9657) (#9660) ([#9660](https://github.com/mrveiss/AutoBot-AI/pull/9660))

- *(bedrock)* Add AWS credential format validation at provider init (#9640) (#9645) ([#9645](https://github.com/mrveiss/AutoBot-AI/pull/9645))

- *(sso)* Configure FastAPI to read X-Forwarded-For headers for rate limiting (#9616, MVA-3671)

- *(sso)* Implement rate limiting on SSO endpoints (#9499)

- *(slm/sso)* Encrypt SSO client secrets at rest with AES-256-GCM (#9501) (#9507) ([#9507](https://github.com/mrveiss/AutoBot-AI/pull/9507))

- *(kb)* Add admin permission check to watch folder read endpoints (#9000)

- *(api)* Sanitize error responses codebase-wide to prevent information leakage (#9312) (#9409) ([#9409](https://github.com/mrveiss/AutoBot-AI/pull/9409))

- *(streams)* Sanitize remaining SSE exception leaks (#9410) (#9413) ([#9413](https://github.com/mrveiss/AutoBot-AI/pull/9413))

- *(streams)* Sanitize exception details in SSE error events (#9360) ([#9408](https://github.com/mrveiss/AutoBot-AI/pull/9408))

- *(deps)* Add uuid override to mcp-autobot-tracker — evict natural's nested uuid@9 (#5665) (#5674) ([#5674](https://github.com/mrveiss/AutoBot-AI/pull/5674))

- *(deps)* Bump uuid 8/9/11 → 14.0.0 — fix buffer bounds check CVE (#5665) (#5669) ([#5669](https://github.com/mrveiss/AutoBot-AI/pull/5669))

- *(deps)* Bump vulnerable dependencies to fix all open Dependabot alerts (#5656) (#5663) (#5664) ([#5664](https://github.com/mrveiss/AutoBot-AI/pull/5664))


## [0.3.0] - 2026-04-21

### Bug Fixes

- *(provision)* Validate stale code_source has vega dep before build (#9284) (#9364) ([#9364](https://github.com/mrveiss/AutoBot-AI/pull/9364))

- *(config)* Make backend.server_host optional with 0.0.0.0 default (GH#9232) (#9370) ([#9370](https://github.com/mrveiss/AutoBot-AI/pull/9370))

- *(base)* Delete obsolete api/transcriber.py (MVA-2891) (#9371) ([#9371](https://github.com/mrveiss/AutoBot-AI/pull/9371))

- *(transcriber/export)* Fix segment key mismatch + IDOR vulnerabilities (#9198) (#9330) ([#9330](https://github.com/mrveiss/AutoBot-AI/pull/9330))

- *(ansible)* Create autobot_shared symlink for slm-agent imports (#9225) (#9328) ([#9328](https://github.com/mrveiss/AutoBot-AI/pull/9328))

- *(i18n)* Add missing nav keys to non-English locales (#9197) (#9334) ([#9334](https://github.com/mrveiss/AutoBot-AI/pull/9334))

- *(ssot_config)* Use localhost as REDIS_HOST default instead of empty string (#9325) ([#9325](https://github.com/mrveiss/AutoBot-AI/pull/9325))

- *(security)* Add CodeQL exclusion for validated SSRF guard (MVA-2605) (#9319) ([#9319](https://github.com/mrveiss/AutoBot-AI/pull/9319))

- *(code-sync)* Restore SSH rsync for multi-server SLM self-update (#9195) (#9337) ([#9337](https://github.com/mrveiss/AutoBot-AI/pull/9337))

- *(agent-loop)* Move CONTRADICTION_SURFACE_THRESHOLD to AgentLoopConfig (#9053) (#9342) ([#9342](https://github.com/mrveiss/AutoBot-AI/pull/9342))

- *(chat/folders)* Allow moving folders to root via parent_id=null (#9352) ([#9352](https://github.com/mrveiss/AutoBot-AI/pull/9352))

- *(ci)* Add /app/autobot-backend/logs tmpfs for hardened config (MVA-2798) (#9362) ([#9362](https://github.com/mrveiss/AutoBot-AI/pull/9362))

- *(slm-agent)* Fix update_url path mismatch (#9290) (#9345) ([#9345](https://github.com/mrveiss/AutoBot-AI/pull/9345))

- *(ansible)* Suppress /sys/class/infiniband warning on WSL2 (GH#9282) (#9346) ([#9346](https://github.com/mrveiss/AutoBot-AI/pull/9346))

- *(backend)* Restore execution_snapshots router registration (GH#9229) (#9339) ([#9339](https://github.com/mrveiss/AutoBot-AI/pull/9339))

- *(code-sync)* Update node version in DB after SLM self-update (#9224) (#9324) ([#9324](https://github.com/mrveiss/AutoBot-AI/pull/9324))

- *(ansible)* Suppress /sys/class/infiniband gather_facts warning on WSL2 (#9282) ([#9326](https://github.com/mrveiss/AutoBot-AI/pull/9326))

- *(ci)* Merge console.log and phase validation fixes for PR #9300 (#9320) ([#9320](https://github.com/mrveiss/AutoBot-AI/pull/9320))

- *(ansible)* Add REDIS_HOST env vars to slm-agent systemd unit (#9226) ([#9310](https://github.com/mrveiss/AutoBot-AI/pull/9310))

- *(transcriber)* Replace @vue:updated with watch() for status changes (#9208) (#9304) ([#9304](https://github.com/mrveiss/AutoBot-AI/pull/9304))

- *(config)* Merge YAML config with defaults to ensure required keys (#9232) (#9305) ([#9305](https://github.com/mrveiss/AutoBot-AI/pull/9305))

- *(ci)* Ensure Docker cache directory exists before build (MVA-2519) (#9309) ([#9309](https://github.com/mrveiss/AutoBot-AI/pull/9309))

- *(voice)* Rename get_provider_registry to get_speech_provider_registry (#9231) (#9308) ([#9308](https://github.com/mrveiss/AutoBot-AI/pull/9308))

- *(voice)* Wire filename_hint parameter through detect_language (#9230)

- *(lint)* Remove unused imports and fix line length

- *(landing)* Simplify logo to single-color mark, no background (#9298)

- *(landing)* Fix logo visibility on light background (#9298)

- *(pages)* Run jekyll build from docs/ working directory

- *(deps)* Align vega-lite version with override (5.23.0 exact)

- *(pages)* Switch to GitHub Actions + Jekyll 4 for Pages build

- *(docs)* Replace color-mix() with rgba() in Ember SCSS scheme

- *(analytics)* Replace GTM with GA4 tag G-ZV9XT0XSWR

- *(landing)* Redesign logo mark for standalone use (#9298)

- *(landing)* Remove Polar.sh bounty references (#9298)

- *(telegram)* Wire _api_method gateway routing to TelegramBotService methods (#9299) ([#9299](https://github.com/mrveiss/AutoBot-AI/pull/9299))

- *(hooks)* Block -b/-B/-c branch creation on main tree (#6512)

- *(deps)* Add vega major-version ignore rules to dependabot.yml (#9219)

- *(execution)* Add thread-safety to SnapshotIndex read operations (GH#8968) (#9277) ([#9277](https://github.com/mrveiss/AutoBot-AI/pull/9277))

- *(ansible)* Use valid group names in wizard-generated inventory (#9288) ([#9288](https://github.com/mrveiss/AutoBot-AI/pull/9288))

- *(ansible)* Add script to remove orphaned/unreachable inventory nodes (#9289) ([#9289](https://github.com/mrveiss/AutoBot-AI/pull/9289))

- *(ansible)* Phase 4c nginx co-location runs despite Phase 4a health check timeout ([#9287](https://github.com/mrveiss/AutoBot-AI/pull/9287))

- *(voice-rbac)* Guard success emit() to prevent audit failures crashing endpoint (GH#8982) (#9278) ([#9278](https://github.com/mrveiss/AutoBot-AI/pull/9278))

- *(frontend)* Add vega-lite as direct dep to complete Rolldown build fix

- *(code-quality)* Remove unused imports and fix E501 in context_overflow and microsoft365 (#9190) ([#9190](https://github.com/mrveiss/AutoBot-AI/pull/9190))

- *(frontend/css)* Remove conflicting teal primary color overrides in dark mode (#9040)

- *(provisioning)* Remove env vars with defaults from validation manifest (#9182) ([#9182](https://github.com/mrveiss/AutoBot-AI/pull/9182))

- *(embed)* Abort SSE reader on widget disconnect to prevent memory leak (#9101)

- *(analytics)* Replace hardcoded Dev Tools text with i18n (#8756) (#9169) ([#9169](https://github.com/mrveiss/AutoBot-AI/pull/9169))

- *(integrations)* Correct py_vapid API usage in generate_vapid_keys() (GH#4459)

- *(plugin-sdk)* Consolidate duplicate plugin SDK to autobot_shared (MVA-2021) (#9167) ([#9167](https://github.com/mrveiss/AutoBot-AI/pull/9167))

- *(security)* Harden Microsoft365Integration against injection attacks

- *(ci)* Sync Ansible slm_agent role + fix chromadb hardened-smoke crash (#9157) ([#9157](https://github.com/mrveiss/AutoBot-AI/pull/9157))

- *(rbac)* Remove duplicate VALID_BUNDLES assignment (#9090) (#9153) ([#9153](https://github.com/mrveiss/AutoBot-AI/pull/9153))

- *(frontend)* CSS z-index scale — define semantic z-index tokens (#9039) ([#9155](https://github.com/mrveiss/AutoBot-AI/pull/9155))

- *(frontend)* Dual primary color — resolve OKLCH/hex conflict in CSS tokens (#9040) ([#9154](https://github.com/mrveiss/AutoBot-AI/pull/9154))

- *(slm-frontend)* Add admin SSO/OIDC settings page ([#9149](https://github.com/mrveiss/AutoBot-AI/pull/9149))

- *(ci)* Remove unused imports blocking code-quality check (#9147) ([#9147](https://github.com/mrveiss/AutoBot-AI/pull/9147))

- *(sso)* Remove provider_id from OAuth callback query params (#MVA-1734) (#9146) ([#9146](https://github.com/mrveiss/AutoBot-AI/pull/9146))

- *(frontend)* Add vega as explicit dep to fix Rolldown/Vite8 build failure (#9143) ([#9143](https://github.com/mrveiss/AutoBot-AI/pull/9143))

- *(ci)* Resolve Black formatting and oxlint errors on Dev_new_gui (#9142) ([#9142](https://github.com/mrveiss/AutoBot-AI/pull/9142))

- *(llm-routing)* Call public chat_completion() instead of private _chat_completion_impl() (#8960) (#9137) ([#9137](https://github.com/mrveiss/AutoBot-AI/pull/9137))

- *(agent-loop)* Add refutation_source to Assertion.to_dict() (#9069) (#9136) ([#9136](https://github.com/mrveiss/AutoBot-AI/pull/9136))

- *(embed)* Clear shadow DOM on re-mount and surface errorMsg (GH#9046 GH#9067) ([#9131](https://github.com/mrveiss/AutoBot-AI/pull/9131))

- *(auth)* Remove duplicate indexes in chat_shared_links migration 049 (#9129) ([#9132](https://github.com/mrveiss/AutoBot-AI/pull/9132))

- *(auth)* Reject shared link ops when Redis owner unknown — IDOR cold-cache bypass (#9128) ([#9133](https://github.com/mrveiss/AutoBot-AI/pull/9133))

- *(sso+connectors+tests)* SAML relay-state tests, singleton DI, voice-rbac helpers, belief-state method (#9075 #9099 #9113 #9114) (#9123) ([#9123](https://github.com/mrveiss/AutoBot-AI/pull/9123))

- *(code-quality)* Reformat 7 Python files to pass black --line-length=120 (#9116) ([#9119](https://github.com/mrveiss/AutoBot-AI/pull/9119))

- *(embed+rbac)* Gitignore dist-embed/, remove unused import, fix storybook pkg ([#9115](https://github.com/mrveiss/AutoBot-AI/pull/9115))

- *(agent-loop)* Configurable contradiction threshold + belief state logging (#9053 #9054) ([#9112](https://github.com/mrveiss/AutoBot-AI/pull/9112))

- *(voice-rbac)* Guard emit in except + use stored_bundle_name in audit (#9096 #9098) (#9111) ([#9111](https://github.com/mrveiss/AutoBot-AI/pull/9111))

- *(embed)* Error state + dark CSS + SSE abort (#9070 #9100 #9101) (#9108) ([#9108](https://github.com/mrveiss/AutoBot-AI/pull/9108))

- *(voice-rbac+embed)* Dedup tool count + add embed message endpoint (#9045 #9047) ([#9110](https://github.com/mrveiss/AutoBot-AI/pull/9110))

- *(backend)* Migration rename 047→048, copilot DEVNULL stderr, snapshot user_id doc (#9094 #9095 #9097) (#9109) ([#9109](https://github.com/mrveiss/AutoBot-AI/pull/9109))

- *(backend)* Async/sync violations in push, system health, and Celery hooks (#9071 #9091 #9093) ([#9104](https://github.com/mrveiss/AutoBot-AI/pull/9104))

- *(connectors)* Replace deprecated asyncio.get_event_loop() with get_running_loop() (#9092) (#9102) ([#9102](https://github.com/mrveiss/AutoBot-AI/pull/9102))

- *(websocket)* Move auth token from URL query param to Sec-WebSocket-Protocol header (#9077)

- *(websocket)* Stop 403 flood — pass auth token in WS URL, accept before close (#9077)

- *(provisioning)* Startup_validation.py checks non-existent env vars (#9084) (#9085) ([#9085](https://github.com/mrveiss/AutoBot-AI/pull/9085))

- *(slm-agent)* Reduce memory footprint and add systemd memory limits (#9086) (#9088) ([#9088](https://github.com/mrveiss/AutoBot-AI/pull/9088))

- *(backend)* Wrong import crash + raw exception exposure in health endpoint (#9055 #9065) (#9081) ([#9081](https://github.com/mrveiss/AutoBot-AI/pull/9081))

- *(code-sync)* Unify all SLM sync paths to use Ansible full-machine update (#9073)

- *(voice-rbac)* Security audit findings — audit emit, VALID_BUNDLES drift, missing test assertions (#8977) (#9001) ([#9001](https://github.com/mrveiss/AutoBot-AI/pull/9001))

- *(code-sync)* Self-update button now runs full Ansible update for all roles (#9073)

- *(frontend/css)* Correct --font-sans token to Inter (#9013) ([#9076](https://github.com/mrveiss/AutoBot-AI/pull/9076))

- *(provisioning)* Resolve backend health check timeout (MVA-1633, GH#8947) (#8951) ([#8951](https://github.com/mrveiss/AutoBot-AI/pull/8951))

- *(sso)* Replace in-memory OAuth state dict with Redis-backed storage (MVA-1733) (#9074) ([#9074](https://github.com/mrveiss/AutoBot-AI/pull/9074))

- *(ci)* Group consecutive GITHUB_STEP_SUMMARY redirects (SC2129) (#8917) (#9052) ([#9052](https://github.com/mrveiss/AutoBot-AI/pull/9052))

- *(code-sync)* Add --no-group --no-owner to local rsync to fix permission errors (#9073)

- *(chat)* Restore visual distinctness between same-background message types

- *(backend)* Correct import path in tool_handler.py (#8986) (#9002) ([#9002](https://github.com/mrveiss/AutoBot-AI/pull/9002))

- *(voice)* Restore dropped features from add/add conflict resolution (#8969)

- *(llc)* Wire croniter dep + start LivenessMonitor and BudgetWatchdog (#9027 #9028 #9029) (#9031) ([#9031](https://github.com/mrveiss/AutoBot-AI/pull/9031))

- *(llc/models)* Consolidate HeartbeatRunStatus into LLCRunStatus (#8970)

- *(llc/models)* Export ActivityEventType from llc/models/__init__.py (#8971)

- *(llc/models)* Export TemplateCategory from llc/models/__init__.py (#8972)

- *(voice-rbac)* Re-read DB after commit in set_user_bundle (#8981) ([#8992](https://github.com/mrveiss/AutoBot-AI/pull/8992))

- *(backend)* Use getattr fallback for storage_dir on AutoBotConfig (#8978) (#8985) ([#8985](https://github.com/mrveiss/AutoBot-AI/pull/8985))

- *(rbac)* Enforce admin-only authorization on PUT /voice/users/{user_id}/bundle (GH#8969) ([#8974](https://github.com/mrveiss/AutoBot-AI/pull/8974))

- *(backend)* Surface startup errors in /api/health for provisioning visibility (GH#8947) ([#8964](https://github.com/mrveiss/AutoBot-AI/pull/8964))

- *(tests)* Correct provider registry mock patches in Claude escalation tests (#8961)

- *(llm-routing)* Use provider registry in route_with_escalation (#8961)

- *(llm-routing)* Use get_tiered_router() singleton in route_with_escalation (#8959)

- *(backend)* Replace get_nested with getattr in is_encryption_enabled (GH#8950) ([#8952](https://github.com/mrveiss/AutoBot-AI/pull/8952))

- *(ansible)* Add AUTOBOT_AUDIT_LOG_FILE to backend.env.j2 template (#8936) ([#8938](https://github.com/mrveiss/AutoBot-AI/pull/8938))

- *(security)* Deny KB write when project not found in artifact_ingestor

- *(llc/kb)* Fail-closed authorization on write guard — remove overly broad exception handlers (GH#8598)

- *(voice)* Migrate _SESSION_TTL to ssot_config canonical pattern (GH#8718) ([#8935](https://github.com/mrveiss/AutoBot-AI/pull/8935))

- *(npu-worker)* Wire get_inference_config into load_model for early architecture validation (GH#8690) ([#8934](https://github.com/mrveiss/AutoBot-AI/pull/8934))

- *(security)* Replace hardcoded audit log fallback with env-var resolver (GH#8929) ([#8932](https://github.com/mrveiss/AutoBot-AI/pull/8932))

- *(backend)* Replace AutoBotConfig.get() with get_config_manager() in chat_history/base.py (GH#8929) (#8931) ([#8931](https://github.com/mrveiss/AutoBot-AI/pull/8931))

- *(ci)* Resolve actionlint violations in frontend-test.yml and phase_validation.yml (#8917)

- *(slm-agent)* Grant read access to /var/log/autobot/ansible.log via ACL (GH#8925-2)

- *(slm-agent)* Add autobot user to systemd-journal group for log access (GH#8925-1)

- *(backend)* Guard against empty audit_log_file path in SecurityLayer (MVA-1503) (#8923) ([#8923](https://github.com/mrveiss/AutoBot-AI/pull/8923))

- *(ci)* Black formatting + missing Icon imports for CI health (MVA-1524) (#8927) ([#8927](https://github.com/mrveiss/AutoBot-AI/pull/8927))

- *(autobot_shared)* Move retry_mechanism into autobot_shared to fix slm-agent startup crash (MVA-1493) (#8921) ([#8921](https://github.com/mrveiss/AutoBot-AI/pull/8921))

- *(backend)* Str() wrap on single_user_mode fixes bool.lower() crash (MVA-1492) ([#8920](https://github.com/mrveiss/AutoBot-AI/pull/8920))

- *(ansible)* Fix pre-flight code sync skipped in wizard deployments

- *(ansible)* Fix ownership of autobot-backend dir after code sync

- *(backend)* Resolve startup crash from AutoBotConfig.get() AttributeError (MVA-1489) ([#8918](https://github.com/mrveiss/AutoBot-AI/pull/8918))

- *(installer)* Remove redis/chroma from SLM-Manager install

- *(ci)* Add /chroma/.chroma tmpfs to hardened overlay (GH#8913, MVA-1484) ([#8915](https://github.com/mrveiss/AutoBot-AI/pull/8915))

- *(installer)* Remove co-located backend from SLM-Manager install

- *(ansible)* Scope localhost.yml to SLM-Manager components only

- *(ci)* Fix Docker smoke-test disk-full and hardened chromadb failures (MVA-1470) (#8912) ([#8912](https://github.com/mrveiss/AutoBot-AI/pull/8912))

- *(ci)* Resolve pre-existing actionlint shellcheck violations (MVA-1472) ([#8911](https://github.com/mrveiss/AutoBot-AI/pull/8911))

- *(ansible)* Add slm_node_id to localhost.yml single-host inventory (#8909) ([#8910](https://github.com/mrveiss/AutoBot-AI/pull/8910))

- *(visual)* Increase Storybook regression timeout for 1154 stories (MVA-1467) ([#8908](https://github.com/mrveiss/AutoBot-AI/pull/8908))

- *(ci)* Pin dorny/paths-filter to node24-compatible hash (MVA-1470) ([#8907](https://github.com/mrveiss/AutoBot-AI/pull/8907))

- *(ansible)* Remove dead backend symlink task (#8905) ([#8906](https://github.com/mrveiss/AutoBot-AI/pull/8906))

- *(a2a)* Trust audit SQLite defaults to /tmp — lost on reboot (MVA-1464, GH#8742) ([#8900](https://github.com/mrveiss/AutoBot-AI/pull/8900))

- *(backend)* Restore correct audit_middleware import (MVA-1466) (#8901) ([#8901](https://github.com/mrveiss/AutoBot-AI/pull/8901))

- *(frontend)* Extend ESLint no-console override to service-worker.js, sw-cache-bust.js, and scripts (GH#8896) (#8902) ([#8902](https://github.com/mrveiss/AutoBot-AI/pull/8902))

- *(frontend)* Fix pre-existing ESLint failures blocking CI (MVA-1460, GH#8896) (#8899) ([#8899](https://github.com/mrveiss/AutoBot-AI/pull/8899))

- *(frontend)* Reduce vue-tsc errors from 239 back to baseline 188 (MVA-1451) ([#8898](https://github.com/mrveiss/AutoBot-AI/pull/8898))

- *(ansible+backend)* Remove stale WSL2 overrides, fix config.ollama_port, rename knowledge_eval (MVA-1454) ([#8895](https://github.com/mrveiss/AutoBot-AI/pull/8895))

- *(llm_shared)* Replace config.ollama_host/port with config.ollama_url (MVA-1444) (#8893) ([#8893](https://github.com/mrveiss/AutoBot-AI/pull/8893))

- *(a2a)* Migrate trust_score.py from logging.getLogger to get_logger (#8889) ([#8889](https://github.com/mrveiss/AutoBot-AI/pull/8889))

- *(coordination)* Move WatchError import to module top-level (GH#8707) (#8886) ([#8886](https://github.com/mrveiss/AutoBot-AI/pull/8886))

- *(coordination)* Remove spurious type-ignore on AgentBudget (GH#8708, MVA-1351) (#8885) ([#8885](https://github.com/mrveiss/AutoBot-AI/pull/8885))

- *(llc/kb)* Add @pytest.mark.asyncio to all async tests in test_kb_inheritance.py (GH#8597) (#8884) ([#8884](https://github.com/mrveiss/AutoBot-AI/pull/8884))

- *(llc)* HandoffBriefGenerator H2A status guard unreachable (GH#8650, MVA-1344) (#8883) ([#8883](https://github.com/mrveiss/AutoBot-AI/pull/8883))

- *(agent-loop)* Classify RETRY-class errors as LOW before HIGH check (GH#8649) (#8881) ([#8881](https://github.com/mrveiss/AutoBot-AI/pull/8881))

- *(ansible)* Bind SLM backend to 0.0.0.0 and fix health check URL (MVA-1423) ([#8880](https://github.com/mrveiss/AutoBot-AI/pull/8880))

- *(ci)* Add nosemgrep waivers for import boundary violations (MVA-1422) ([#8879](https://github.com/mrveiss/AutoBot-AI/pull/8879))

- *(belief-state)* Truncate ReadFileExtractor hash to 8 chars (MVA-1432) ([#8876](https://github.com/mrveiss/AutoBot-AI/pull/8876))

- *(ci)* Remove unused imports in context_window_manager_test.py

- *(belief-state)* RunCommandExtractor multi-port key collision (MVA-1431) ([#8875](https://github.com/mrveiss/AutoBot-AI/pull/8875))

- *(ci)* Add ArchitectureFamily and get_architecture_family to llm_shared __all__

- *(llc)* Drain HandoffService background tasks on shutdown (GH#8651) ([#8855](https://github.com/mrveiss/AutoBot-AI/pull/8855))

- *(agent-loop)* _should_continue() respects per-severity error budget (GH#8649) ([#8856](https://github.com/mrveiss/AutoBot-AI/pull/8856))

- *(llc/kb)* Always archive_collection in try/finally (GH#8654) ([#8853](https://github.com/mrveiss/AutoBot-AI/pull/8853))

- *(llc/kb)* Propagate work_item_id through search_with_inheritance (GH#8599) ([#8852](https://github.com/mrveiss/AutoBot-AI/pull/8852))

- *(task-workspace)* Propagate preserved workspace_dir to local var on allocation failure (GH#8687, MVA-1335) ([#8851](https://github.com/mrveiss/AutoBot-AI/pull/8851))

- *(llc)* Catch ValueError from _parse_llm_text_response in HandoffBriefGenerator (GH#8652) ([#8850](https://github.com/mrveiss/AutoBot-AI/pull/8850))

- *(nav)* Gate Canvas nav item behind VITE_FEATURE_CANVAS flag (GH#8758) ([#8849](https://github.com/mrveiss/AutoBot-AI/pull/8849))

- *(llc/kb)* Replace dst.add() with dst.upsert() in SprintKbSummarizer (GH#8655) ([#8844](https://github.com/mrveiss/AutoBot-AI/pull/8844))

- *(ci)* Remove unused imports to resolve autoflake CI violations (MVA-1333) ([#8843](https://github.com/mrveiss/AutoBot-AI/pull/8843))

- *(rbac)* Replace userId guard with Symbol token in openBundleModal (GH#8705, MVA-1337) ([#8835](https://github.com/mrveiss/AutoBot-AI/pull/8835))

- *(ansible)* Deploy ChromaDB via redis role for fleet database nodes (MVA-1319 / GH#8786) ([#8836](https://github.com/mrveiss/AutoBot-AI/pull/8836))

- *(llc/kb)* Archive ChromaDB sprint collection only after confirmed write (MVA-1341) (#8833) ([#8833](https://github.com/mrveiss/AutoBot-AI/pull/8833))

- *(security)* Move nosec annotations to flagged lines (MVA-1320) (#8829) ([#8829](https://github.com/mrveiss/AutoBot-AI/pull/8829))

- *(deps)* Correct langchain floor to >=1.3.0 in backend and AI-stack requirements (MVA-1330) ([#8830](https://github.com/mrveiss/AutoBot-AI/pull/8830))

- *(infra)* Add autobot-chromadb.service to deploy pipeline (GH#8786) (#8828) ([#8828](https://github.com/mrveiss/AutoBot-AI/pull/8828))

- *(ansible)* Replace ansible_user_id with lookup('env','USER') — resolves remote_user race (MVA-1314) (#8822) ([#8822](https://github.com/mrveiss/AutoBot-AI/pull/8822))

- *(frontend)* Merge duplicate Icon imports into single statements (GH#8601) (#8821) ([#8821](https://github.com/mrveiss/AutoBot-AI/pull/8821))

- *(tests)* Use allRoutePaths() in nav-items-coverage for child routes (GH#8818) (#8819) ([#8819](https://github.com/mrveiss/AutoBot-AI/pull/8819))

- *(nav)* Guard Canvas profile menu item behind VITE_FEATURE_CANVAS flag (GH#8758) (#8817) ([#8817](https://github.com/mrveiss/AutoBot-AI/pull/8817))

- *(frontend)* Resolve 155 oxlint errors blocking frontend-tests CI (GH#8771) (#8816) ([#8816](https://github.com/mrveiss/AutoBot-AI/pull/8816))

- *(frontend)* Add bookmark icon to ICONS registry (GH#8698) (#8815) ([#8815](https://github.com/mrveiss/AutoBot-AI/pull/8815))

- *(install)* Clean stale git lock files before checkout (MVA-1293) ([#8814](https://github.com/mrveiss/AutoBot-AI/pull/8814))

- *(onboarding)* Add dismiss button and clear errors on step change (GH#8760) (#8810) ([#8810](https://github.com/mrveiss/AutoBot-AI/pull/8810))

- *(a2a)* Use logging.getLogger instead of get_logger in trust_score.py (GH#8741, MVA-1269) ([#8807](https://github.com/mrveiss/AutoBot-AI/pull/8807))

- *(coordination)* Remove spurious type-ignore on AgentBudgetTracker.subscribe_changes (GH#8708, MVA-1262) ([#8806](https://github.com/mrveiss/AutoBot-AI/pull/8806))

- *(voice)* Replace hardcoded _SESSION_TTL with AUTOBOT_VOICE_REALTIME_SESSION_TTL env-var (GH#8718, MVA-1267) ([#8805](https://github.com/mrveiss/AutoBot-AI/pull/8805))

- *(coordination)* Move WatchError import to top of shared_runtime_bag.py (MVA-1261) ([#8803](https://github.com/mrveiss/AutoBot-AI/pull/8803))

- *(a2a)* Replace bare module-level guard in get_trust_manager() with lazy_singleton() (MVA-1270) ([#8802](https://github.com/mrveiss/AutoBot-AI/pull/8802))

- *(rbac)* Guard openBundleModal against stale in-flight bundle fetch (GH#8705, MVA-1258) ([#8800](https://github.com/mrveiss/AutoBot-AI/pull/8800))

- *(llc)* Replace module-level GoalService() singleton with lazy_singleton (GH#8738) ([#8801](https://github.com/mrveiss/AutoBot-AI/pull/8801))

- *(security)* Resolve bandit medium+ findings blocking security-tests CI (MVA-1231) ([#8776](https://github.com/mrveiss/AutoBot-AI/pull/8776))

- *(task-workspace)* Preserve workspace_dir on transient allocation failure

- *(llc/kb)* Wrap llm.chat() in try/except and cap prompt input in SprintKbSummarizer (GH#8656, MVA-1252) ([#8777](https://github.com/mrveiss/AutoBot-AI/pull/8777))

- *(tests)* Replace sys.modules guard with unconditional attr patch in test_goal_ancestry_layer (MVA-1251) ([#8775](https://github.com/mrveiss/AutoBot-AI/pull/8775))

- *(layers)* Replace .lower() on bool TIERED_CONTEXT_ENABLED with bool() (MVA-1250) ([#8774](https://github.com/mrveiss/AutoBot-AI/pull/8774))

- *(coordination/hook)* Fix duplicate endswith — exempt test_*.py ([#8794](https://github.com/mrveiss/AutoBot-AI/pull/8794))

- *(knowledge)* Add mobile sidebar collapse toggle with drawer overlay ([#8787](https://github.com/mrveiss/AutoBot-AI/pull/8787))

- *(task-workspace)* Preserve workspace_dir on transient allocation failure ([#8789](https://github.com/mrveiss/AutoBot-AI/pull/8789))

- *(a2a)* Persist trust audit DB to data dir instead of /tmp ([#8778](https://github.com/mrveiss/AutoBot-AI/pull/8778))

- *(llc/kb)* Write kb_summary sentinel for small sprints (<=10 docs) ([#8782](https://github.com/mrveiss/AutoBot-AI/pull/8782))

- *(404)* Change primary button to 'Go Home' → /home, fix icon/label mismatch (GH#8754) (#8792) ([#8792](https://github.com/mrveiss/AutoBot-AI/pull/8792))

- *(nav)* Distinguish SLM Admin external link from internal nav items (#8753) ([#8781](https://github.com/mrveiss/AutoBot-AI/pull/8781))

- *(accessibility)* Add role=listbox and arrow key nav to onboarding preset cards (GH#8752) (#8779) ([#8779](https://github.com/mrveiss/AutoBot-AI/pull/8779))

- *(ci)* Add celery-beat service to docker-compose.yml (GH#8666, MVA-1248) ([#8773](https://github.com/mrveiss/AutoBot-AI/pull/8773))

- *(storybook)* Fix 3 pre-existing syntax/import errors blocking Storybook build (MVA-1223) (#8770) ([#8770](https://github.com/mrveiss/AutoBot-AI/pull/8770))

- *(ci)* Downgrade typescript from ~6.0.3 to ~5.9.0 in autobot-frontend (#8769) ([#8769](https://github.com/mrveiss/AutoBot-AI/pull/8769))

- *(security)* Resolve qs CVE-2026-8723 and idna CVE-2026-45409 (MVA-1212) ([#8768](https://github.com/mrveiss/AutoBot-AI/pull/8768))

- *(ci)* Suppress pre-existing mypy type errors in autobot_shared/ (MVA-1214) ([#8767](https://github.com/mrveiss/AutoBot-AI/pull/8767))

- *(ci)* Suppress pre-existing bandit B310 in cli/doctor.py (MVA-1208) ([#8764](https://github.com/mrveiss/AutoBot-AI/pull/8764))

- *(startup)* Use stdlib logging in retry_mechanism to break circular import (MVA-1209) (#8765) ([#8765](https://github.com/mrveiss/AutoBot-AI/pull/8765))

- *(llc)* Narrow FileNotFoundError catch to workspace path only (MVA-1192) ([#8763](https://github.com/mrveiss/AutoBot-AI/pull/8763))

- *(ci)* Remove unused imports flagged by autoflake (MVA-1198) ([#8747](https://github.com/mrveiss/AutoBot-AI/pull/8747))

- *(config)* Replace get_logger with logging.getLogger in all config submodules

- *(ci)* Resolve pids_limit conflict in Docker Compose smoke tests (MVA-1181) ([#8730](https://github.com/mrveiss/AutoBot-AI/pull/8730))

- *(llc)* Close stdout fd, retry on missing workspace, clear stale env var (MVA-1153) ([#8722](https://github.com/mrveiss/AutoBot-AI/pull/8722))

- *(design-tokens)* Add .btn-error CSS + ButtonVariant type (GH#8684) ([#8727](https://github.com/mrveiss/AutoBot-AI/pull/8727))

- *(db)* Resolve duplicate Alembic revision ID 20260525_043 (MVA-1185) ([#8728](https://github.com/mrveiss/AutoBot-AI/pull/8728))

- *(security)* Require admin role on GET /api/tasks/{id}/workspace (GH#8686, MVA-1180) ([#8726](https://github.com/mrveiss/AutoBot-AI/pull/8726))

- *(design-tokens)* BaseBadge BADGE_VARIANTS as const + merge dual watchEffect in BaseButton (MVA-1161) (#8713) ([#8713](https://github.com/mrveiss/AutoBot-AI/pull/8713))

- *(voice-rbac)* Fix VoiceBundleInfo stories — share state via provide/inject (MVA-1162) ([#8710](https://github.com/mrveiss/AutoBot-AI/pull/8710))

- *(coordination)* Add None guard to all 6 SharedRuntimeBag Redis methods (MVA-1158 CR must-fix) ([#8709](https://github.com/mrveiss/AutoBot-AI/pull/8709))

- *(stories)* Constrain size argType options to canonical tokens (MVA-354) ([#8702](https://github.com/mrveiss/AutoBot-AI/pull/8702))

- *(orchestration)* Prevent _enforce_limit from evicting active worktrees (MVA-1154) (#8699) ([#8699](https://github.com/mrveiss/AutoBot-AI/pull/8699))

- *(deps)* Bump langchain 1.2.24→1.3.1 — version does not exist on PyPI (MVA-1159) ([#8696](https://github.com/mrveiss/AutoBot-AI/pull/8696))

- *(ci)* Health-check CI failures — Black/oxlint/OpenTelemetry/redis-shim (MVA-1141) ([#8679](https://github.com/mrveiss/AutoBot-AI/pull/8679))

- *(ci)* Make croniter soft dependency in llc/api/routines.py (MVA-1119 follow-up) ([#8670](https://github.com/mrveiss/AutoBot-AI/pull/8670))

- *(ci)* Make croniter a soft dependency in llc/api/routines.py (MVA-1119)

- *(startup)* Chromadb hang + missing imports regression (MVA-1119) ([#8646](https://github.com/mrveiss/AutoBot-AI/pull/8646))

- *(llc)* Add agent_id fallback to actor_id extraction in set_coworker (MVA-1029) (#8663) ([#8663](https://github.com/mrveiss/AutoBot-AI/pull/8663))

- *(frontend)* Add preserveSymlinks to main frontend Vite config (pinia resolution)

- *(ci)* Add pinia devDep to terminal plugin; remove unused TYPE_CHECKING import

- *(frontend)* Remove duplicate Icon imports from 25 component files (fix smoke-test)

- *(ansible/redis)* Use 127.0.0.1 for nightly Redis backup cron (MVA-1037) ([#8593](https://github.com/mrveiss/AutoBot-AI/pull/8593))

- *(ansible)* Deploy health check scripts from code_source before chmod (MVA-1038) ([#8592](https://github.com/mrveiss/AutoBot-AI/pull/8592))

- *(llc/migrations)* ALTER TYPE membershiprole ADD VALUE 'lead' (MVA-1028) ([#8591](https://github.com/mrveiss/AutoBot-AI/pull/8591))

- *(frontend)* Remove duplicate import Icon in KnowledgeBrowserHeader.vue

- *(ci)* Resolve 246 startup-import-smoke failures (MVA-947)

- *(frontend)* Fix duplicate Icon import and malformed router routes (unblock smoke-test)

- *(llc/services)* Resolve circular import in services/__init__.py (#8485) (#8588) ([#8588](https://github.com/mrveiss/AutoBot-AI/pull/8588))

- *(docker)* Copy autobot-plugins before npm ci — fix smoke-test CI failure (#8587) ([#8587](https://github.com/mrveiss/AutoBot-AI/pull/8587))

- *(slm-agent)* Add ConditionPathExists guard to prevent crash loop (#MVA-1036) (#8586) ([#8586](https://github.com/mrveiss/AutoBot-AI/pull/8586))

- *(llc/kb)* Fix concurrent AsyncSession, JSON shape, orphaned tasks, unnecessary LLCRAGAssembler (#8566 #8567 #8569 #8570) ([#8585](https://github.com/mrveiss/AutoBot-AI/pull/8585))

- *(llc/kb)* Dead import LLCWorkItem in inheritance.py (GH#8568) ([#8582](https://github.com/mrveiss/AutoBot-AI/pull/8582))

- *(security)* Fix path traversal guard, restore coworker endpoint, migration idempotency (MVA-1023) ([#8581](https://github.com/mrveiss/AutoBot-AI/pull/8581))

- *(llc)* Address LLC API/model gaps (#8479 #8478 #8476 #8474 #8462 #8461 #8493) ([#8578](https://github.com/mrveiss/AutoBot-AI/pull/8578))

- *(llc)* Fix 18 LLC functional bugs from sprint discovery (MVA-1013) (#8577) ([#8577](https://github.com/mrveiss/AutoBot-AI/pull/8577))

- *(llc)* Restore missing enums, auth, migrations, SAST, CI (#8558 #8505 #8504 #8515 #8501 #8506 #8516) (#8576) ([#8576](https://github.com/mrveiss/AutoBot-AI/pull/8576))

- *(llc/enums)* Add missing CoWorkerType enum (#8558) (#8565) ([#8565](https://github.com/mrveiss/AutoBot-AI/pull/8565))

- *(llc)* Consolidate budget SELECT, fix str cast, add sprint columns migration, stub assignee display (#8461 #8462 #8474 #8476)

- Ws org_id propagation, portability TOCTOU+dragleave, ansible health-check guard (#8492 #8561 #8562 #8483)

- *(llc/sprint)* Add SELECT FOR UPDATE to lifecycle, strip status from PATCH (#8479 #8478)

- *(llc/scheduler)* Store poll task ref, fix ZADD NX, write context_snapshot, wire AutoBotAgentAdapter (#8494 #8498 #8499 #8490)

- *(llc)* Noload lazy for LLCRoutine.runs, fix falsy-zero token fallback (#8496 #8493)

- *(llc/kb)* Address round-2 CR findings in sprint KB summarizer (GH#8238)

- *(llc)* Fix 4 CR bugs in board controls — liveness/scheduler/service/api (GH#8256) (#8563) ([#8563](https://github.com/mrveiss/AutoBot-AI/pull/8563))

- *(llc)* Address 2 CR bugs in PR 8556 agent capability indexing (MVA-998)

- *(llc/kb)* Address 3 hard blockers in PR 8554 (GH#8241)

- *(llc)* Address all 10 CR findings from PR #8553 review (GH#8239)

- *(llc/health/probe)* Apply 5 SCA CR fixes from PR-8540 review

- *(llc/models)* Restore HeartbeatInvocationSource, HeartbeatRunStatus, ContextMode enums

- *(llc/kb)* Address 3 CR runtime bugs in sprint KB summarizer (GH#8238)

- *(llc/controls)* Raise AgentNotFoundError when agent row missing (#8538)

- *(llc/frontend)* Address 2 CR blockers + 4 confirmed bugs in CompanyPortabilityView (#8250)

- *(llc/frontend)* Address 3 CR bugs in CompanyPortabilityView (#8250)

- *(llc)* Repair syntax errors and apply Black+isort to LLC API/service files

- *(llc)* Address 4 CR crash bugs in company import (MVA-968)

- *(llc)* Address 2 CR blockers in PR #8521 outbound PM sync

- *(llc)* Resolve 6 CR blockers in PR 8518 — route shadowing, query_text, config, status codes, error handling, ordering (GH#8236, MVA-961)

- Resolve 6 CI/CD failures blocking PRs #8497 and #8503 (Issue #8506) (#8513) ([#8513](https://github.com/mrveiss/AutoBot-AI/pull/8513))

- *(deps)* Bump celery to 5.6.3 to resolve kombu 5.6.2 conflict (#8512) ([#8512](https://github.com/mrveiss/AutoBot-AI/pull/8512))

- *(llc/8225)* Address CR round-6 — shared singleton, 404 oracle fix

- *(llc/8225)* Address CR round-5 findings

- *(llc/8225)* Only bump last_heartbeat_at on SUCCEEDED runs (MVA-923)

- *(llc/8225)* Address CR round-4 — SQL join, route collision, tenant fail-open, task drain

- *(llc/8225)* Properly start LLC HeartbeatScheduler in lifespan + pre-auth trigger_heartbeat

- *(llc/8225)* Address CR round-3 findings — tenant isolation, task GC, cron safety, shutdown

- *(llc)* Address remaining HIGH findings from PR #8497 CR

- *(llc)* Guard _create_run against missing org in _handle_due_agent

- *(llc/8225)* Address CR round-2 findings — trigger_manual race, auth, agent-drop, test

- *(llc/8225)* Address CR round-2 blockers — company_id, multi-worker race, auth prefix

- *(llc)* Company_id UUID type — join agents table, guard None on run creation (#8225)

- *(llc)* Rename migration 033→036, split heartbeat_runs to its own migration (#8225)

- *(llc)* Auth, cron validation, schedule lifecycle, double-dispatch (GH#8229)

- *(llc/8229)* Address CR round-3 blockers and high findings

- *(llc/tests)* Set explicit None on mock routine fields for Pydantic RoutineRead (GH#8229)

- *(llc/8229)* Address CR round-2 blockers in routines scheduler

- *(migrations)* Update migration 034 down_revision from 032 to 033

- *(llc)* Sync routines to updated model/service signatures (GH#8229)

- *(auth)* Forward user_id from JWT payload in authenticate_websocket ([#8489](https://github.com/mrveiss/AutoBot-AI/pull/8489))

- *(auth)* Forward user_id from JWT payload in authenticate_websocket

- *(llc/tests)* Align BudgetExhausted assertion with actual exception message format

- *(llc/adapter)* Address 5 second-round CR blockers (MVA-898 round 2)

- *(llc/adapter)* Address 4 CodeReviewer blockers from PR #8480

- *(ansible)* Sync autobot-plugins + Vite preserveSymlinks for file: workspace packages (MVA-893) (#8482) ([#8482](https://github.com/mrveiss/AutoBot-AI/pull/8482))

- *(llc)* Address MVA-820 CR medium-priority findings for GH#8211 (#8456) ([#8456](https://github.com/mrveiss/AutoBot-AI/pull/8456))

- *(llc)* Address MVA-858 code review findings — work item service (GH#8213) (#8454) ([#8454](https://github.com/mrveiss/AutoBot-AI/pull/8454))

- *(tests)* Set rich_payload=None in _make_cell to fix JSON export tests ([#8449](https://github.com/mrveiss/AutoBot-AI/pull/8449))

- *(pattern_analysis)* GH#8438 purge-all scope + GH#8439 checkpoint/resume + GH#8440 blocking IO ([#8444](https://github.com/mrveiss/AutoBot-AI/pull/8444))

- *(analytics)* GH#8436 source_id isolation + GH#8437 no_path sentinel 404 ([#8443](https://github.com/mrveiss/AutoBot-AI/pull/8443))

- *(analytics)* Fix 3 Celery migration regressions (GH#8433 critical, GH#8434, GH#8435) ([#8442](https://github.com/mrveiss/AutoBot-AI/pull/8442))

- *(ansible)* Replace | last(N) with [-N:] slice to fix Jinja2 crash log display (MVA-786) (#8428) ([#8428](https://github.com/mrveiss/AutoBot-AI/pull/8428))

- *(skills/hub)* Address P0+P1 review findings (#8432) ([#8432](https://github.com/mrveiss/AutoBot-AI/pull/8432))

- *(frontend)* Migrate TerminalWindow.vue CSS to design tokens (GH#8427) (#8431) ([#8431](https://github.com/mrveiss/AutoBot-AI/pull/8431))

- *(terminal)* Emit commandExecuted before buffer clear in frontend BaseXTerminal (#8422) (#8425) ([#8425](https://github.com/mrveiss/AutoBot-AI/pull/8425))

- *(terminal-plugin,vnc-plugin)* Batch W — ensureMap guard, no-console, VncHost type (#8417 #8418 #8419) (#8429) ([#8429](https://github.com/mrveiss/AutoBot-AI/pull/8429))

- *(slm-backend)* Defer annotations in replication/backup to fix X|None crash

- *(slm-backend)* Replace callable builtin with Callable type in playbook_executor

- *(cache)* Replace threading.Lock with asyncio.Lock in LRUCacheManager.clear() (#8421) (#8423) ([#8423](https://github.com/mrveiss/AutoBot-AI/pull/8423))

- *(frontend)* KnowledgePersistenceDialog bulk-action buttons disabled when all selected (#8395) (#8410) ([#8410](https://github.com/mrveiss/AutoBot-AI/pull/8410))

- *(api)* Align AdapterTestResponse fields with EnvironmentTestResult.to_dict() (#8379) ([#8379](https://github.com/mrveiss/AutoBot-AI/pull/8379))

- *(vector-store)* Batch U — 5 discovery fixes #8404 #8405 #8406 #8407 #8408 ([#8420](https://github.com/mrveiss/AutoBot-AI/pull/8420))

- *(llm-cache,classification,knowledge)* Batch S — 4 discovery follow-ups (#8399 #8398 #8401 #8402) ([#8409](https://github.com/mrveiss/AutoBot-AI/pull/8409))

- *(vector-store)* #8390 cache_max_size bug, #8391 VectorWriteBuffer, #8392 CollectionTierManager (#8400) ([#8400](https://github.com/mrveiss/AutoBot-AI/pull/8400))

- *(classification,llm-cache)* Batch M-B — crash guards and cache integrity (GH#8381 GH#8382 GH#8383 GH#8384) ([#8397](https://github.com/mrveiss/AutoBot-AI/pull/8397))

- *(vector-search)* Batch M-A — 5 bugs GH#8385 GH#8386 GH#8387 GH#8388 GH#8389 ([#8396](https://github.com/mrveiss/AutoBot-AI/pull/8396))

- *(frontend)* Resolve pre-existing TS errors in KnowledgePersistenceDialog (GH#8380) (#8393) ([#8393](https://github.com/mrveiss/AutoBot-AI/pull/8393))

- *(llm/events/models)* Batch J — resume_download, Ollama pull, channel guard, SA2 annotations (#8373) ([#8373](https://github.com/mrveiss/AutoBot-AI/pull/8373))

- FAISS IVFPQ wire-in + arch_family correctness (#8357 #8359 #8360 #8361) (#8372) ([#8372](https://github.com/mrveiss/AutoBot-AI/pull/8372))

- *(api)* Align EnterpriseFeatureEnableAll + AnalyticsEvolutionExport response schemas (#8313, #8314) ([#8362](https://github.com/mrveiss/AutoBot-AI/pull/8362))

- *(orchestrator)* Use asyncio.get_running_loop() in set_phi2_enabled (#8330) ([#8341](https://github.com/mrveiss/AutoBot-AI/pull/8341))

- SLM crash-loop (GH#8141) + heartbeat event drop (GH#8340) ([#8342](https://github.com/mrveiss/AutoBot-AI/pull/8342))

- *(frontend)* KnowledgePersistenceDialog reads response.data for pending_items/compiled (#8322) ([#8331](https://github.com/mrveiss/AutoBot-AI/pull/8331))

- DataResponse bypass, web_crawler test patches, chromadb NameError (#8300, #8306, #8308) ([#8327](https://github.com/mrveiss/AutoBot-AI/pull/8327))

- *(api/health)* Wire NPU worker into npu_acceleration capability flag (#6768) ([#8318](https://github.com/mrveiss/AutoBot-AI/pull/8318))

- *(llm)* Ollama tool wiring — tool_choice, format conflict, review fixes (#7911) ([#8311](https://github.com/mrveiss/AutoBot-AI/pull/8311))

- Unified_audit OOM/TTL + PersistStrategy.REDIS + chat_knowledge null data (#8301–#8304) ([#8315](https://github.com/mrveiss/AutoBot-AI/pull/8315))

- *(models,connectors,config,ci)* Discovery fixes #8271 #8275 #8276 #8281 ([#8317](https://github.com/mrveiss/AutoBot-AI/pull/8317))

- *(connectors)* Four resilience regressions from PR #8277 (#8283, #8284, #8285, #8286) ([#8288](https://github.com/mrveiss/AutoBot-AI/pull/8288))

- *(connectors)* Propagate crawl errors to SyncResult and only checkpoint crawled seeds (#8296, #8297)

- *(connectors)* Four resilience regressions from PR #8277 (#8283, #8284, #8285, #8286)

- *(install)* Add asyncpg connect timeout + Python import smoke test (MVA-514) (#8279) ([#8279](https://github.com/mrveiss/AutoBot-AI/pull/8279))

- *(initialization)* Close #6690 gaps — strict default + Ansible + test (#8280) ([#8280](https://github.com/mrveiss/AutoBot-AI/pull/8280))

- *(frontend)* SW IP-gate, ChatController race warn, polling circuit-breaker (#6767/#6766/#6765) (#8287) ([#8287](https://github.com/mrveiss/AutoBot-AI/pull/8287))

- *(frontend/css)* Replace space-x-* with gap-* in App.vue (#7899) (#8272) ([#8272](https://github.com/mrveiss/AutoBot-AI/pull/8272))

- *(slm-backend+backend)* Revert Mapped[X|None] PEP 604 codemod + fix ChromaDB health URL (#8266 #8265) ([#8269](https://github.com/mrveiss/AutoBot-AI/pull/8269))

- Debug discoveries #6769 (ChromaDB missing), #6770 (circuit-breaker total_calls=0), #6771 (i18n 59 missing keys) ([#8097](https://github.com/mrveiss/AutoBot-AI/pull/8097))

- *(hooks)* Fix BRANCH_ARG extraction — GNU grep 3.7 rejects variable-length lookbehinds (#6512)

- *(hooks)* Strengthen branch checkout blocking in main worktree (#6512)

- *(code-analysis)* Tune DUPLICATE_CLASS_SHAPE threshold + extract problem-dict helper + consolidation fixes (#6780, #6759, #6757) (#8099) ([#8099](https://github.com/mrveiss/AutoBot-AI/pull/8099))

- *(backend)* Phase 3 batch 27 — typed agent payloads, smoke test, create_chat_response cleanup (#6703, #6732, #6411) (#8095) ([#8095](https://github.com/mrveiss/AutoBot-AI/pull/8095))

- *(frontend/ui)* Fix update banner false-positive, plugin list parsing, replace UnifiedLoadingView (#6775, #6774, #6698) (#8092) ([#8092](https://github.com/mrveiss/AutoBot-AI/pull/8092))

- *(nginx)* Add CSP header to frontend HTML and SPA fallback locations (#6814) ([#8088](https://github.com/mrveiss/AutoBot-AI/pull/8088))

- *(ansible)* Wrap SLM health check in block/rescue so diagnostics run on failure (#7919) ([#8085](https://github.com/mrveiss/AutoBot-AI/pull/8085))

- *(ansible)* Add pre-health-check service state detection to fast-fail on crashed SLM (#7920) ([#8084](https://github.com/mrveiss/AutoBot-AI/pull/8084))

- *(ci)* Resolve Black formatting regressions — 2 syntax errors + 105 files reformatted (#7879) ([#8083](https://github.com/mrveiss/AutoBot-AI/pull/8083))

- *(frontend/types)* Triage and fix high-impact TS errors across 41 files (#7511) ([#8076](https://github.com/mrveiss/AutoBot-AI/pull/8076))

- *(toast)* Use canonical durations in chat notify() wrapper (MVA-351) ([#8075](https://github.com/mrveiss/AutoBot-AI/pull/8075))

- *(llm/tiered-routing)* _score_length accepts tokenizer callable, falls back to char/4 (#7348) (#7930) ([#7930](https://github.com/mrveiss/AutoBot-AI/pull/7930))

- *(toast)* Align duration constants with canonical spec Section 5 (MVA-345) (#8038) ([#8038](https://github.com/mrveiss/AutoBot-AI/pull/8038))

- *(a11y)* Aria-label remediation - Severity-2 views and charts (MVA-333) (#8036) ([#8036](https://github.com/mrveiss/AutoBot-AI/pull/8036))

- *(frontend)* Fix 4 vue-tsc errors in LLMApiKeysView — restore baseline to 93 (MVA-177, closes #7653) (#8031) ([#8031](https://github.com/mrveiss/AutoBot-AI/pull/8031))

- *(analyzer)* _detect_data_clumps KeyError + LSP required-param description (#7518, #7519) (#8015) ([#8015](https://github.com/mrveiss/AutoBot-AI/pull/8015))

- *(security-ci)* Correct YAML indentation in dependency-security job (#8051) ([#8051](https://github.com/mrveiss/AutoBot-AI/pull/8051))

- *(ansible/ai-stack)* Stop chromadb service before venv recreation (MVA-79) (#8045) ([#8045](https://github.com/mrveiss/AutoBot-AI/pull/8045))

- *(install)* Resolve fresh-install backend health check timeout (MVA-514)

- *(config)* Use runtimeHttpProto() in slmAdminUrl + ssot-config tests (GH #6837) (#7907) ([#7907](https://github.com/mrveiss/AutoBot-AI/pull/7907))

- *(orchestration)* Resolve TYPE_CHECKING import cycle by moving AgentPerformance (#6831) ([#7890](https://github.com/mrveiss/AutoBot-AI/pull/7890))

- *(slm-client)* Pass auth token as query param to stop /api/ws/events reconnect spam (#6839) ([#7885](https://github.com/mrveiss/AutoBot-AI/pull/7885))

- *(ansible)* Add ansible_host fallback to ansible_default_ipv4.address callsites (#6840) ([#7884](https://github.com/mrveiss/AutoBot-AI/pull/7884))

- *(nginx/slm)* Add /openapi.json /docs /redoc to standalone-mode block (#6843) ([#7883](https://github.com/mrveiss/AutoBot-AI/pull/7883))

- *(slm-backend)* Prevent indefinite hang on database connection timeout (#7689)

- *(web_fetch/robots)* Replace unreachable defensive guard with assertion (#7461) (#7865) ([#7865](https://github.com/mrveiss/AutoBot-AI/pull/7865))

- *(autobot_shared)* Remove bare ConfigRegistry import for independent importability (#7526) (#7864) ([#7864](https://github.com/mrveiss/AutoBot-AI/pull/7864))

- *(frontend)* Correct getUserById/getGroupById return types (GH#7541) (#7859) ([#7859](https://github.com/mrveiss/AutoBot-AI/pull/7859))

- *(constants)* Remove 21 duplicate class definitions from ssot_constants.py (GH#7747) ([#7853](https://github.com/mrveiss/AutoBot-AI/pull/7853))

- *(a11y)* Convert KnowledgePromptEditor prompt-item divs to button elements (#7720) (#7849) ([#7849](https://github.com/mrveiss/AutoBot-AI/pull/7849))

- *(slm-frontend)* Align MonitoringError with RecentError API shape, remove stopgap cast (#7768) (#7828) ([#7828](https://github.com/mrveiss/AutoBot-AI/pull/7828))

- *(pre-commit)* Extend no-literal-ttl-seconds hook to catch BinOp patterns (#7779) (#7827) ([#7827](https://github.com/mrveiss/AutoBot-AI/pull/7827))

- *(canvas)* Declare bleach and weasyprint as explicit deps (MVA-362 security) ([#7819](https://github.com/mrveiss/AutoBot-AI/pull/7819))

- *(security-ci)* Align upload-artifact and download-artifact to v4 (#7816) ([#7816](https://github.com/mrveiss/AutoBot-AI/pull/7816))

- *(rbac)* Defer clear_cache to after session commit to close flush→publish race (GH#7605) ([#7809](https://github.com/mrveiss/AutoBot-AI/pull/7809))

- *(tests)* Restore performance_benchmarks tests — fix imports + rename for pytest collection (#7132) (#7789) ([#7789](https://github.com/mrveiss/AutoBot-AI/pull/7789))

- *(rbac)* Close pubsub before reconnect and use pipeline for bulk cache clear (#7788) ([#7788](https://github.com/mrveiss/AutoBot-AI/pull/7788))

- *(npu-worker)* Correct root() return type Dict[str,str] → Dict[str,Any] (MVA-342) (#7771) ([#7771](https://github.com/mrveiss/AutoBot-AI/pull/7771))

- *(celery)* Import knowledge_tasks and memory_tasks in tasks/__init__.py (MVA-341) (#7775) ([#7775](https://github.com/mrveiss/AutoBot-AI/pull/7775))

- *(slm-frontend)* Reconcile FleetCert type — remove local interface and unsafe cast (GH#7767) (#7781) ([#7781](https://github.com/mrveiss/AutoBot-AI/pull/7781))

- *(backend)* Add startup warning when SLM_AUTH_TOKEN is unset (GH#7713) (#7780) ([#7780](https://github.com/mrveiss/AutoBot-AI/pull/7780))

- *(config,chromadb,constants)* Circular import + chromadb provenance + ssot_constants missing items (GH#7765, GH#7762, GH#7750) (#7777) ([#7777](https://github.com/mrveiss/AutoBot-AI/pull/7777))

- *(chromadb)* Canonical provenance keys in DocIndexerService + create_collection injection (GH#7761, GH#7762) ([#7774](https://github.com/mrveiss/AutoBot-AI/pull/7774))

- *(nginx)* Re-include security headers in /slm/index.html sub-location (#7737) (#7758) ([#7758](https://github.com/mrveiss/AutoBot-AI/pull/7758))

- *(toast)* Use canonical durations in chat notify() wrapper (MVA-351) (#7739) ([#7739](https://github.com/mrveiss/AutoBot-AI/pull/7739))

- *(tools)* Enforce worktree isolation for parallel agents (#6512, MVA-391)

- *(nginx)* DRY security headers via nginx snippets (#6842) (#7736) ([#7736](https://github.com/mrveiss/AutoBot-AI/pull/7736))

- *(toast)* Align duration constants with canonical spec Section 5 (MVA-345) (#7729) ([#7729](https://github.com/mrveiss/AutoBot-AI/pull/7729))

- *(analyzer)* _detect_data_clumps KeyError + LSP required-param description (#7518, #7519) (#7733) ([#7733](https://github.com/mrveiss/AutoBot-AI/pull/7733))

- *(ci)* Standardize artifact action versions + fix cleanup-worktrees.sh Phase 3 exit (#7712, #7537) (#7732) ([#7732](https://github.com/mrveiss/AutoBot-AI/pull/7732))

- *(ci)* Align artifact action versions to v4 in security.yml (GH#7712) ([#7728](https://github.com/mrveiss/AutoBot-AI/pull/7728))

- *(security-ci)* Correct YAML indentation to restore dependency-security job (MVA-350, GH#7711) ([#7727](https://github.com/mrveiss/AutoBot-AI/pull/7727))

- *(a11y)* Aria-label remediation - Severity-2 views and charts (MVA-333) ([#7723](https://github.com/mrveiss/AutoBot-AI/pull/7723))

- *(a11y)* KnowledgePromptEditor aria-label audit and remediation (MVA-324) ([#7719](https://github.com/mrveiss/AutoBot-AI/pull/7719))

- *(a11y)* Aria-label remediation — ServiceMessageTimeline + ChatFilePanel (#MVA-323, #MVA-329) ([#7716](https://github.com/mrveiss/AutoBot-AI/pull/7716))

- *(a11y)* Aria-label remediation for 10 zero-accessibility icon-only buttons (MVA-332) ([#7721](https://github.com/mrveiss/AutoBot-AI/pull/7721))

- *(a11y)* Add aria-label to 10 icon-only buttons (MVA-335) (#7722) ([#7722](https://github.com/mrveiss/AutoBot-AI/pull/7722))

- *(a11y)* VisualBrowserPanel aria-label audit & remediation (MVA-322) ([#7717](https://github.com/mrveiss/AutoBot-AI/pull/7717))

- *(a11y)* Aria-label remediation - BaseButton contract + P1-P4 patches (MVA-317) (#7715) ([#7715](https://github.com/mrveiss/AutoBot-AI/pull/7715))

- *(ansible)* Write SLM_AUTH_TOKEN to autobot-backend.env — stops WS 403 storm (#7689) ([#7707](https://github.com/mrveiss/AutoBot-AI/pull/7707))

- *(health-check)* Correct WSL2 endpoints — backend IP, ChromaDB v2, SLM path (GH#7688) ([#7706](https://github.com/mrveiss/AutoBot-AI/pull/7706))

- *(ci/deploy)* Address review blockers on PR #7703 — safe repo path + pipefail (MVA-291)

- *(ci/deploy)* Move health-check cron to Ansible, remove /tmp wrapper (MVA-291)

- *(ci)* Resolve all flake8/autoflake/Black/bandit/mypy violations on Dev_new_gui (MVA-282) ([#7699](https://github.com/mrveiss/AutoBot-AI/pull/7699))

- *(scheduler)* Replace per-worker singleton with Redis-backed leader election (MVA-160 / #6556) ([#7656](https://github.com/mrveiss/AutoBot-AI/pull/7656))

- *(scheduler)* Replace per-worker singleton with Redis-backed leader election (#6556)

- *(openai-compat)* Omit cost_usd:null from non-streaming usage object (MVA-202) ([#7675](https://github.com/mrveiss/AutoBot-AI/pull/7675))

- *(ci/visual-regression)* Remove stale baselines for regeneration (GH#7410)

- *(ci/visual-regression)* Integrate Storybook visual test fixes (GH#7410)

- *(auth)* Mint new JWT before revoking old in refresh_run_jwt (MVA-170) ([#7664](https://github.com/mrveiss/AutoBot-AI/pull/7664))

- *(arch-chat)* Address 4 CodeReviewer blockers from PR #7652 (MVA-195)

- *(frontend)* Fix 4 vue-tsc errors in LLMApiKeysView — restore baseline to 93 (MVA-177, closes #7653) (#7673) ([#7673](https://github.com/mrveiss/AutoBot-AI/pull/7673))

- *(mcp)* Map JSON-RPC -32003 scope-denied to HTTP 403 in FastAPI router (MVA-171) ([#7667](https://github.com/mrveiss/AutoBot-AI/pull/7667))

- *(auth)* Add missing await on get_current_user in openai_compat._get_user (MVA-169) ([#7662](https://github.com/mrveiss/AutoBot-AI/pull/7662))

- *(frontend)* Remove double .json() parse in useAuditApi.getFailedOperations (#7538) ([#7649](https://github.com/mrveiss/AutoBot-AI/pull/7649))

- *(security)* Add path-prefix guard — run JWT only valid on /api/runs/ and /api/mcp/ (MVA-91) (#7650) ([#7650](https://github.com/mrveiss/AutoBot-AI/pull/7650))

- *(security)* Add denylist rejection test and fix TTL env var in docs (MVA-145) ([#7640](https://github.com/mrveiss/AutoBot-AI/pull/7640))

- *(sec)* Resolve PR #7534 post-rebase blockers (MVA-144, #7534) ([#7638](https://github.com/mrveiss/AutoBot-AI/pull/7638))

- *(dedup)* Use circuit_breaker.CircuitState — the canonical shared definition (#7636) ([#7636](https://github.com/mrveiss/AutoBot-AI/pull/7636))

- *(openai-compat)* Streaming cost SSE chunk now a valid ChatCompletionChunk (MVA-138) (#7632) ([#7632](https://github.com/mrveiss/AutoBot-AI/pull/7632))

- *(dedup)* Consolidate slack_approval_integration.CircuitState into shared analyzer module (MVA-139) (#7631) ([#7631](https://github.com/mrveiss/AutoBot-AI/pull/7631))

- *(ci)* Remove 2 remaining F401 unused imports blocking code-quality (MVA-137) (#7630) ([#7630](https://github.com/mrveiss/AutoBot-AI/pull/7630))

- *(ai-stack)* Wire Ollama backing service + CI watchdog + security regression tests (#6228) (#7626) ([#7626](https://github.com/mrveiss/AutoBot-AI/pull/7626))

- *(security)* Suppress CodeQL py/full-ssrf false positive in fetch_safe_url (#6533) (#7622) ([#7622](https://github.com/mrveiss/AutoBot-AI/pull/7622))

- *(security)* Patch SSRF in skill catalog importer and suppress false-positive stack-trace alerts (MVA-129) (#7621) ([#7621](https://github.com/mrveiss/AutoBot-AI/pull/7621))

- *(llm-keys)* Use async Redis client with null guard and pipeline list_keys (#6590) (#7619) ([#7619](https://github.com/mrveiss/AutoBot-AI/pull/7619))

- *(ansible/ai-stack)* Stop chromadb service before venv recreation (MVA-79) (#7614) ([#7614](https://github.com/mrveiss/AutoBot-AI/pull/7614))

- *(ci)* Bump Node 20 → 22 in CI workflows for oxlint 1.58 vite.config.ts loading (closes #7506) (#7524) ([#7524](https://github.com/mrveiss/AutoBot-AI/pull/7524))

- *(analyzer + dups)* Consolidate CircuitState + HardwareDevice + tune enum threshold (#6755 round 3) (#7520) ([#7520](https://github.com/mrveiss/AutoBot-AI/pull/7520))

- *(ansible)* Add cache_valid_time: 3600 to apt update_cache tasks (#6719) (#7595) ([#7595](https://github.com/mrveiss/AutoBot-AI/pull/7595))

- *(backend)* Canonical datetime_now() helper and eliminate datetime.utcnow() drift (#7436) (#7593) ([#7593](https://github.com/mrveiss/AutoBot-AI/pull/7593))

- *(media/image)* Patch _vision_processor_checked instead of nonexistent _VISION_PROCESSOR_AVAILABLE (#6844) (#7571) ([#7571](https://github.com/mrveiss/AutoBot-AI/pull/7571))

- *(onboarding)* Wrap apply_preset Redis writes in MULTI/EXEC transaction (#6577) (#7567) ([#7567](https://github.com/mrveiss/AutoBot-AI/pull/7567))

- *(plugins)* Namespace installed SET by source to prevent name collisions (#7366) (#7533) ([#7533](https://github.com/mrveiss/AutoBot-AI/pull/7533))

- *(rbac)* Replace in-process cache with Redis L2 + pub/sub invalidation (MVA-123) ([#7603](https://github.com/mrveiss/AutoBot-AI/pull/7603))

- *(frontend)* Fix response.data envelope bug in ShareKnowledgeDialog (#7502) ([#7540](https://github.com/mrveiss/AutoBot-AI/pull/7540))

- *(ansible/redis)* Wire TLS variables into redis-stack.conf.j2 (#6955) ([#7530](https://github.com/mrveiss/AutoBot-AI/pull/7530))

- *(auth)* Gate single_user /login bypass behind AUTOBOT_DEV_AUTH_BYPASS (#6838) ([#7521](https://github.com/mrveiss/AutoBot-AI/pull/7521))

- *(infra)* Refresh PHASE_CRITERIA paths + fix result-shape + Redis check (closes #7496) (#7516) ([#7516](https://github.com/mrveiss/AutoBot-AI/pull/7516))

- *(ci)* Green up Phase Validation + Code Quality (#7496) (#7505) ([#7505](https://github.com/mrveiss/AutoBot-AI/pull/7505))

- *(analyzer)* Skip parent-child + Protocol-impl pairs in duplicate_class_shape (#7501) (#7503) ([#7503](https://github.com/mrveiss/AutoBot-AI/pull/7503))

- *(multimodal)* LSP exception contract — VisionProcessor + VoiceProcessor (#6755 round 1) (#7495) ([#7495](https://github.com/mrveiss/AutoBot-AI/pull/7495))

- *(chat/search_web)* Thread max_pages through snippet path for parity with fetch_full (closes #7479) (#7493) ([#7493](https://github.com/mrveiss/AutoBot-AI/pull/7493))

- *(async/fs)* Migrate 13 Path.read/write_text sites in async paths to to_thread (closes #7467) (#7492) ([#7492](https://github.com/mrveiss/AutoBot-AI/pull/7492))

- *(async)* Codebase-wide asyncio.run → run_or_schedule consistency sweep (#7469 round 4) (#7488) ([#7488](https://github.com/mrveiss/AutoBot-AI/pull/7488))

- *(async)* Migrate sync-entry asyncio.run sites to run_or_schedule (#7469 round 3) (#7485) ([#7485](https://github.com/mrveiss/AutoBot-AI/pull/7485))

- *(scripts)* Adopt set -euo pipefail in start-services.sh (closes #7455) (#7484) ([#7484](https://github.com/mrveiss/AutoBot-AI/pull/7484))

- *(async)* Migrate 3 cascade-required asyncio.run sites to run_or_schedule (#7469 round 2) (#7483) ([#7483](https://github.com/mrveiss/AutoBot-AI/pull/7483))

- *(async)* Hoist asyncio-run-or-schedule defensive helper to autobot_shared (#7469 round 1) (#7474) ([#7474](https://github.com/mrveiss/AutoBot-AI/pull/7474))

- *(ansible/provision)* Ensure SLM frontend node_modules before rebuild (closes #7472) (#7473) ([#7473](https://github.com/mrveiss/AutoBot-AI/pull/7473))

- *(async)* Pre-commit hook blocking sync I/O in async paths (#7444 gate) (#7471) ([#7471](https://github.com/mrveiss/AutoBot-AI/pull/7471))

- *(test/memory)* Migrate working_memory test + fix wrong-namespace patch (#7280 round 9) (#7433) ([#7433](https://github.com/mrveiss/AutoBot-AI/pull/7433))

- *(rag)* Defensive embedding-provenance guard at ChromaDB write chokepoint (#6514 MVP) (#7429) ([#7429](https://github.com/mrveiss/AutoBot-AI/pull/7429))

- *(test/skills)* Migrate LLMInterface patches to get_llm_service factory (#7398) (#7419) ([#7419](https://github.com/mrveiss/AutoBot-AI/pull/7419))

- *(ci/visual-regression)* Bump test timeout + upload first-run baselines (#7410) (#7418) ([#7418](https://github.com/mrveiss/AutoBot-AI/pull/7418))

- *(security)* Export VAR= form + chained-cmd separator + SHELL hardening (#7406) (#7415) ([#7415](https://github.com/mrveiss/AutoBot-AI/pull/7415))

- *(test/audit)* Add SESSION_EXPORT to required AuditAction set (#7399) (#7413) ([#7413](https://github.com/mrveiss/AutoBot-AI/pull/7413))

- *(test/security)* Un-xfail auth_bypass + role_confusion as test rot (#7384 sub-fixes #2, #3) (#7407) ([#7407](https://github.com/mrveiss/AutoBot-AI/pull/7407))

- *(frontend)* UX audit — aria-labels, i18n key, SetupWizard form labels (#7389) (#7394) ([#7394](https://github.com/mrveiss/AutoBot-AI/pull/7394))

- *(security)* Argument-aware risk for docker/find/DNS attack flags (#7384) (#7393) ([#7393](https://github.com/mrveiss/AutoBot-AI/pull/7393))

- *(test/retrieval_learner)* Scope hset assertion to pattern keys (#7386) (#7387) ([#7387](https://github.com/mrveiss/AutoBot-AI/pull/7387))

- *(test/security)* Mock command_executor + xfail layered failures (#7376) (#7385) ([#7385](https://github.com/mrveiss/AutoBot-AI/pull/7385))

- *(security)* Detect dangerous env-var prefix injection (#7375) (#7382) ([#7382](https://github.com/mrveiss/AutoBot-AI/pull/7382))

- *(test/security)* Test rot in security_edge_cases assertions (#7367 phase 1) (#7377) ([#7377](https://github.com/mrveiss/AutoBot-AI/pull/7377))

- *(test/notif)* Migrate to canonical async-redis fixture + fix wrong-namespace patch (#7280 round 2) (#7374) ([#7374](https://github.com/mrveiss/AutoBot-AI/pull/7374))

- *(plugins)* Make install/detail endpoints source-aware (#6524) (#7365) ([#7365](https://github.com/mrveiss/AutoBot-AI/pull/7365))

- *(plugins)* Relocate marketplace_sources off /plugins prefix (#6523) (#7364) ([#7364](https://github.com/mrveiss/AutoBot-AI/pull/7364))

- *(format)* Make targets need 'bash scripts/format.sh' (closes #7361) (#7362) ([#7362](https://github.com/mrveiss/AutoBot-AI/pull/7362))

- *(intelligence)* Unblock IntelligentAgent demo cascade — 5 reference-rot bugs (#7245, #7246) (#7341) ([#7341](https://github.com/mrveiss/AutoBot-AI/pull/7341))

- *(test/utils)* Patch event_manager.get_event_manager (lazy_singleton accessor) (#7184) (#7337) ([#7337](https://github.com/mrveiss/AutoBot-AI/pull/7337))

- *(plugins)* Harden _remote_plugin_to_entry against bad remote payloads (#6525) (#7335) ([#7335](https://github.com/mrveiss/AutoBot-AI/pull/7335))

- *(voice)* Collapse 2 isSpeaking watchers into 1 — eliminates hands-free cooldown double-trigger (#6823) (#7334) ([#7334](https://github.com/mrveiss/AutoBot-AI/pull/7334))

- *(system-health)* Reject sync probes at registration time (#6918) (#7332) ([#7332](https://github.com/mrveiss/AutoBot-AI/pull/7332))

- *(codegen)* Bypass package __init__.py via spec_from_file_location (#7269 followup) (#7331) ([#7331](https://github.com/mrveiss/AutoBot-AI/pull/7331))

- *(audit-script)* Catch dynamic import() / require() / .d.ts FP classes (#6872 part 2) (#7330) ([#7330](https://github.com/mrveiss/AutoBot-AI/pull/7330))

- *(test/marketplace)* Pass enums + source_id to list_catalog direct calls (closes #7251) (#7329) ([#7329](https://github.com/mrveiss/AutoBot-AI/pull/7329))

- *(tests)* Patch get_async_redis_client at consumer namespace + AsyncMock wrap (#7215 followup) (#7279) ([#7279](https://github.com/mrveiss/AutoBot-AI/pull/7279))

- *(ci)* Update vue-tsc baseline 248 → 250 to match Dev_new_gui state (closes #7227) (#7276) ([#7276](https://github.com/mrveiss/AutoBot-AI/pull/7276))

- *(test/workflow)* UTC ISO suffix is +00:00, not Z (#7238) (#7260) ([#7260](https://github.com/mrveiss/AutoBot-AI/pull/7260))

- *(ansible/redis)* TLS lines conditional on cert existence (#6701) (#7259) ([#7259](https://github.com/mrveiss/AutoBot-AI/pull/7259))

- *(deploy)* Loosen autobot-celery-beat dependency on celery worker (#6580) (#7252) ([#7252](https://github.com/mrveiss/AutoBot-AI/pull/7252))

- *(test/marketplace)* Unblock collection — repoint imports past #6534 enum migration (#7237) (#7250) ([#7250](https://github.com/mrveiss/AutoBot-AI/pull/7250))

- *(audit-script)* Skip entry-point runners + correct worktree-relative path check (#7128b) (#7244) ([#7244](https://github.com/mrveiss/AutoBot-AI/pull/7244))

- *(ci)* Pydantic[email] in CI framework reqs to unblock startup-import-smoke (closes #7225 partial) (#7243) ([#7243](https://github.com/mrveiss/AutoBot-AI/pull/7243))

- *(ansible/browser)* T64 audit for noble — add defensive libatk1.0-0t64 (closes #7220) (#7235) ([#7235](https://github.com/mrveiss/AutoBot-AI/pull/7235))

- *(tests)* Wrap async patch return_values with AsyncMock (#7216 — 77 sites) (#7234) ([#7234](https://github.com/mrveiss/AutoBot-AI/pull/7234))

- *(frontend)* Vue-tsc regression-guard CI + worktree-gotcha doc note (closes #7227) (#7233) ([#7233](https://github.com/mrveiss/AutoBot-AI/pull/7233))

- *(test/worker)* Assert on envelope-wrapped result shape (#7154) (#7230) ([#7230](https://github.com/mrveiss/AutoBot-AI/pull/7230))

- *(tests)* Repoint 9 src.* mock paths #7176 missed (#6987 part 5/N) (#7215) ([#7215](https://github.com/mrveiss/AutoBot-AI/pull/7215))

- *(ansible/browser)* Use libasound2t64 on noble (closes #7207) (#7208) ([#7208](https://github.com/mrveiss/AutoBot-AI/pull/7208))

- *(orchestration)* Build_dag accepts both edge shapes (#7010 cluster 3 partial) (#7205) ([#7205](https://github.com/mrveiss/AutoBot-AI/pull/7205))

- *(backend)* Wrap markdownify hard-import with optional_import (#7166) (#7204) ([#7204](https://github.com/mrveiss/AutoBot-AI/pull/7204))

- *(test)* Repoint 7 mock paths from nonexistent utils.redis_client to canonical (#7202) (#7209) ([#7209](https://github.com/mrveiss/AutoBot-AI/pull/7209))

- *(test/security)* Update 2 tests for SecurityPolicy refactor (#7147) (#7199) ([#7199](https://github.com/mrveiss/AutoBot-AI/pull/7199))

- *(orchestration+retry)* NotImplementedError propagates through executor + retry (#7010 cluster 5) (#7198) ([#7198](https://github.com/mrveiss/AutoBot-AI/pull/7198))

- *(ansible)* Replace ansible_X facts with ansible_facts['X'] (closes #7180) (#7197) ([#7197](https://github.com/mrveiss/AutoBot-AI/pull/7197))

- *(backend/chat)* _clear_and_restore_session uses add_messages_batch (#7025) (#7196) ([#7196](https://github.com/mrveiss/AutoBot-AI/pull/7196))

- *(orchestration)* Causal executor — validation gate, summary case, trace wording (#7010 cluster 4) (#7190) ([#7190](https://github.com/mrveiss/AutoBot-AI/pull/7190))

- *(orchestration)* Dry-run report shape + NotificationConfig double-kwarg (#7010 cluster 3 partial) (#7186) ([#7186](https://github.com/mrveiss/AutoBot-AI/pull/7186))

- *(test/monitoring)* Repoint 8 src.* mock paths to autobot_shared.redis_client (#6987 part 4/N) (#7181) ([#7181](https://github.com/mrveiss/AutoBot-AI/pull/7181))

- *(ansible/redis)* Pin Redis Stack repo to jammy on noble (closes #7178) (#7179) ([#7179](https://github.com/mrveiss/AutoBot-AI/pull/7179))

- *(tests)* Drop nonexistent 'src.' prefix from 43 mock paths (#6987) (#7176) ([#7176](https://github.com/mrveiss/AutoBot-AI/pull/7176))

- *(orchestration)* DAG branch pruning preserves diamond join nodes (#7010 cluster 1) (#7172) ([#7172](https://github.com/mrveiss/AutoBot-AI/pull/7172))

- *(orchestration)* CHECKPOINT_TTL = 30 days + add refresh_ttl() method (#7010 cluster 2, closes #3231 partial) (#7169) ([#7169](https://github.com/mrveiss/AutoBot-AI/pull/7169))

- *(audit-script)* Filter test_*.py + detect router_registry callers (#7128, #7109) (#7168) ([#7168](https://github.com/mrveiss/AutoBot-AI/pull/7168))

- *(tests)* Rename 44 dotted-test-filenames to underscore form (closes #7082) (#7167) ([#7167](https://github.com/mrveiss/AutoBot-AI/pull/7167))

- *(install.sh)* Generate localhost.yml with network_subnet/gateway/slm_host (closes #7162) (#7164) ([#7164](https://github.com/mrveiss/AutoBot-AI/pull/7164))

- *(test/security)* Unbreak 3 src.* mock paths in enhanced_security_layer_test (#6987 part 3/N) (#7160) ([#7160](https://github.com/mrveiss/AutoBot-AI/pull/7160))

- *(packaging)* Add [project.optional-dependencies] test group (closes #7156 partial) (#7159) ([#7159](https://github.com/mrveiss/AutoBot-AI/pull/7159))

- *(frontend/i18n)* Pass count as 3rd arg to t() for plural keys (#6976) (#7158) ([#7158](https://github.com/mrveiss/AutoBot-AI/pull/7158))

- *(test/worker)* Unbreak src.* mock path in worker_node_test (#6987 part 2/N) (#7153) ([#7153](https://github.com/mrveiss/AutoBot-AI/pull/7153))

- *(frontend/ui)* EmptyState stories use correct prop name 'message' (#6874) (#7152) ([#7152](https://github.com/mrveiss/AutoBot-AI/pull/7152))

- *(ansible)* Pre-flight git commands fail with dubious ownership on shared hosts (closes #7150) (#7151) ([#7151](https://github.com/mrveiss/AutoBot-AI/pull/7151))

- *(install)* Prefer device-shipped PPA repos; sweep stale .list duplicates (closes #7144) (#7145) ([#7145](https://github.com/mrveiss/AutoBot-AI/pull/7145))

- *(frontend/i18n)* Add 4 missing en.json keys for graph loading + retry (#7079) (#7143) ([#7143](https://github.com/mrveiss/AutoBot-AI/pull/7143))

- *(ansible/slm_manager)* Cleanup stale Ansible PPA source files before adding (#7140) (#7141) ([#7141](https://github.com/mrveiss/AutoBot-AI/pull/7141))

- *(ansible)* Replace removed community.general.yaml callback (closes #7137) (#7138) ([#7138](https://github.com/mrveiss/AutoBot-AI/pull/7138))

- *(packaging)* Autobot_shared/pyproject.toml — drop unused `requests`, add 5 missing deps (closes #7119) (#7133) ([#7133](https://github.com/mrveiss/AutoBot-AI/pull/7133))

- *(test/perf)* Migrate performance_benchmarks.performance_test.py off LLMInterface (#7041) (#7131) ([#7131](https://github.com/mrveiss/AutoBot-AI/pull/7131))

- *(orchestration)* WorkflowDocumenter migrate chat_completion → chat (#7042) (#7118) ([#7118](https://github.com/mrveiss/AutoBot-AI/pull/7118))

- *(rlm/evaluator)* Log/verdict consistency + INDETERMINATE for evaluator failures (#6697) (#7116) ([#7116](https://github.com/mrveiss/AutoBot-AI/pull/7116))

- *(backend/cache)* RedisCache.set_json default= covers dataclasses + Pydantic (#6696) (#7117) ([#7117](https://github.com/mrveiss/AutoBot-AI/pull/7117))

- *(backend/codebase-analytics)* Await AsyncChromaDBCollection.get/.delete directly (#6695) (#7115) ([#7115](https://github.com/mrveiss/AutoBot-AI/pull/7115))

- *(api/chat)* Wire chat endpoint through LLMService.chat() — closes silent canned-response regression (#7047) (#7101) ([#7101](https://github.com/mrveiss/AutoBot-AI/pull/7101))

- *(ansible/provision)* Call mark-synced for each provisioned node (#7103) ([#7107](https://github.com/mrveiss/AutoBot-AI/pull/7107))

- *(install)* Preserve existing SLM_ADMIN_PASSWORD on reinstall (#7075) ([#7106](https://github.com/mrveiss/AutoBot-AI/pull/7106))

- *(slm-agent)* Version.json commit always empty — Jinja default() doesn't fall back on empty string ([#7100](https://github.com/mrveiss/AutoBot-AI/pull/7100))

- *(slm-frontend)* Provision state survives navigation + WS disconnect (#7096) (#7099) ([#7097](https://github.com/mrveiss/AutoBot-AI/pull/7097))

- *(ansible/provision)* Regression from #7051 — load role_*_active facts via vars_files for SLM-triggered provision ([#7093](https://github.com/mrveiss/AutoBot-AI/pull/7093))

- *(orchestrator)* Unpack is_provider_healthy tuple — guard now actually fires (#7069) (#7078) ([#7078](https://github.com/mrveiss/AutoBot-AI/pull/7078))

- *(ci)* Docker-smoke-test informational curls tolerate SIGPIPE under pipefail (closes #7066) (#7067) ([#7067](https://github.com/mrveiss/AutoBot-AI/pull/7067))

- *(deps)* Bump langchain-core floor from 1.2.28 to 1.2.31 (#7049) (#7065) ([#7065](https://github.com/mrveiss/AutoBot-AI/pull/7065))

- *(ansible/venv)* Health-check + auto-recreate broken venv (#7052) (#7061) ([#7061](https://github.com/mrveiss/AutoBot-AI/pull/7061))

- *(ansible/slm-admin-ui)* User=root → User=autobot (#7054) (#7059) ([#7059](https://github.com/mrveiss/AutoBot-AI/pull/7059))

- *(backend)* Complete #3185 migration — 3 missed callers + 1 broken constructor (#6983) (#7036) ([#7036](https://github.com/mrveiss/AutoBot-AI/pull/7036))

- *(ansible/cleanup)* Correct SLM Manager guard — use inventory_hostname (#7031 follow-up to #7035) (#7043) ([#7043](https://github.com/mrveiss/AutoBot-AI/pull/7043))

- *(ansible/cleanup)* SLM Manager owns autobot-slm-* dirs — guard 7 wipe tasks (#7031) (#7035) ([#7035](https://github.com/mrveiss/AutoBot-AI/pull/7035))

- *(slm-admin-ui)* Pin self-signed cert via --cacert; drop misplaced OnFailure (#7024) (#7030) ([#7030](https://github.com/mrveiss/AutoBot-AI/pull/7030))

- *(ssot)* Replace 3 hardcoded 172.16.168.20 references — restore green SSOT gate (#7028) (#7029) ([#7029](https://github.com/mrveiss/AutoBot-AI/pull/7029))

- *(ansible/grafana)* Apt_repository update_cache:false — survives flaky PPA (#6719) (#7023) ([#7023](https://github.com/mrveiss/AutoBot-AI/pull/7023))

- *(ci)* Startup-import-smoke uses requirements-ci.txt to dodge torch/vllm conflict (#7018) (#7021) ([#7021](https://github.com/mrveiss/AutoBot-AI/pull/7021))

- *(ci)* Startup-import-smoke must run pip install from autobot-backend/ (#7001) (#7013) ([#7013](https://github.com/mrveiss/AutoBot-AI/pull/7013))

- *(tools/audit)* Widen scan-dirs + tracker regex + add tests (closes #6927, #6928, #6929) (#6995) ([#6995](https://github.com/mrveiss/AutoBot-AI/pull/6995))

- *(knowledge)* Tag regex `*` → `+` rejects empty/whitespace tags (#6672) (#6968) ([#6968](https://github.com/mrveiss/AutoBot-AI/pull/6968))

- *(ci)* Make pip install failures in startup-import-smoke surface (closes #6947) (#6966) ([#6966](https://github.com/mrveiss/AutoBot-AI/pull/6966))

- *(frontend)* Replace console.warn in iconMappings with createLogger (#6806) (#6962) ([#6962](https://github.com/mrveiss/AutoBot-AI/pull/6962))

- *(backend)* Migrate async_chat_workflow imports (#6950 follow-up)

- *(backend)* Migrate dependency_container to LLMService (closes #6950)

- *(deps)* Align OpenTelemetry suite to 1.41.1 (#6948)

- *(hooks)* Tighten temp filter + AST-aware getenv IP-fallback validator (closes #6782, #6783) (#6882) ([#6882](https://github.com/mrveiss/AutoBot-AI/pull/6882))

- *(frontend)* Restore Storybook devDependencies (#6873) (#6932) ([#6932](https://github.com/mrveiss/AutoBot-AI/pull/6932))

- *(frontend)* Dedupe /api/system/health polling — one canonical poller (#6773) (#6834) ([#6834](https://github.com/mrveiss/AutoBot-AI/pull/6834))

- *(frontend/theme)* Apply dark theme via data-theme attribute, not class (#6772) (#6833) ([#6833](https://github.com/mrveiss/AutoBot-AI/pull/6833))

- *(schemas)* Resolve 3 cross-module class-name collisions discovered by #6798 (#6799) (#6803) ([#6803](https://github.com/mrveiss/AutoBot-AI/pull/6803))

- Ssot-config runtime protocol for all URL builders + wire smoke test to CI (#6789 #6795) (#6801) ([#6801](https://github.com/mrveiss/AutoBot-AI/pull/6801))

- 4-issue retrospective batch — regex= audit, MissingDep subscript, smoke-test cross-module collision check, SW silent on cert (#6790 #6793 #6794 #6798) (#6800) ([#6800](https://github.com/mrveiss/AutoBot-AI/pull/6800))

- *(chat)* Single-source-of-truth session_id — eliminates 4-IDs-per-send churn (#6745, #6746) (#6781) ([#6781](https://github.com/mrveiss/AutoBot-AI/pull/6781))

- *(code-analysis)* LSP positional-arity rule was inverted — child widening preconditions is correct LSP (#6755) (#6778) ([#6778](https://github.com/mrveiss/AutoBot-AI/pull/6778))

- *(media)* Restore parent constructor signature on 5 BasePipeline subclasses (#6755) (#6777) ([#6777](https://github.com/mrveiss/AutoBot-AI/pull/6777))

- *(code-analysis)* Treat docstring + raise NotImplementedError as stub in LSP detector (#6755) (#6776) ([#6776](https://github.com/mrveiss/AutoBot-AI/pull/6776))

- *(frontend/chat)* Remove remaining appStore.setLoading() misuses — eliminates per-poll screen flicker (#6694) (#6764) ([#6764](https://github.com/mrveiss/AutoBot-AI/pull/6764))

- *(api/health)* Rename misleading agent_count → ai_stack_agent_count (#8) (#6763) ([#6763](https://github.com/mrveiss/AutoBot-AI/pull/6763))

- *(nginx)* Route /openapi.json /docs /redoc to backend instead of SPA fallback (#6761) ([#6761](https://github.com/mrveiss/AutoBot-AI/pull/6761))

- *(backend/chat)* Use add_messages_batch with canonical disk shape — restores user/assistant persistence (#6744) (#6760) ([#6760](https://github.com/mrveiss/AutoBot-AI/pull/6760))

- *(security+frontend)* Debug-session batch 3 — CSP wss tighten, ssot https detection (#6751) ([#6751](https://github.com/mrveiss/AutoBot-AI/pull/6751))

- *(voice)* Deepen TTS streaming pipeline 1 -> 3 chunks ahead to absorb worker jitter (#6752) (#6753) ([#6753](https://github.com/mrveiss/AutoBot-AI/pull/6753))

- *(backend/chat)* Replace hard-coded 1h TTL with configurable 24h default (#6743) (#6750) ([#6750](https://github.com/mrveiss/AutoBot-AI/pull/6750))

- *(p2-batch)* Debug-session batch 2 — redis_exporter IP, ApexCharts race, Agent Registry tabs (#6749) ([#6749](https://github.com/mrveiss/AutoBot-AI/pull/6749))

- *(api)* Delete 1183 dead @with_error_handling decorators above @router across 129 files (#6706) (#6741) ([#6741](https://github.com/mrveiss/AutoBot-AI/pull/6741))

- *(agents)* Add in-process default is_available to StandardizedAgent — unblocks backend boot (#6659 follow-up) (#6731) ([#6731](https://github.com/mrveiss/AutoBot-AI/pull/6731))

- *(ansible)* Roll out bounded shell apt-get update to all role-level callsites (#6719) (#6730) ([#6730](https://github.com/mrveiss/AutoBot-AI/pull/6730))

- *(ansible)* Bounded shell apt-get update across 5 SLM-Manager-bound roles (#6719) (#6729) ([#6729](https://github.com/mrveiss/AutoBot-AI/pull/6729))

- *(ansible/nginx)* Bounded shell apt-get update — survives PPA timeouts even when cache is stale (#6719) (#6728) ([#6728](https://github.com/mrveiss/AutoBot-AI/pull/6728))

- *(frontend/ws)* Revert double /ws/ prefix in LiveEventService URL (#6727) ([#6727](https://github.com/mrveiss/AutoBot-AI/pull/6727))

- *(ansible/nodejs)* Add cache_valid_time so transient PPA timeouts don't abort Phase 0 (#6719) (#6726) ([#6726](https://github.com/mrveiss/AutoBot-AI/pull/6726))

- *(p0+p1)* Debug-session batch — 5 fixes (WS URL, playwright 500, base.css, orchestrator 500, AbortError) (#6718) ([#6718](https://github.com/mrveiss/AutoBot-AI/pull/6718))

- *(ansible/nginx)* Add cache_valid_time so transient PPA timeouts don't abort Phase 0 (#6719) (#6720) ([#6720](https://github.com/mrveiss/AutoBot-AI/pull/6720))

- *(integrations)* Execute_action returns error dict instead of raising on unknown action (#6658) (#6711) ([#6711](https://github.com/mrveiss/AutoBot-AI/pull/6711))

- *(agents)* Restore parent constructor signature on LLMFailsafe + DataAnalysis (#6660) (#6710) ([#6710](https://github.com/mrveiss/AutoBot-AI/pull/6710))

- *(agents)* Unify is_available as abstract async on BaseAgent (#6659) (#6709) ([#6709](https://github.com/mrveiss/AutoBot-AI/pull/6709))

- *(tests)* Rename _resolve_source_or_404 → _resolve_source_root_or_404 (#6675) (#6708) ([#6708](https://github.com/mrveiss/AutoBot-AI/pull/6708))

- *(frontend)* WS auth + chat history blanking — closes #6692, #6693, #6700 (#6705) ([#6705](https://github.com/mrveiss/AutoBot-AI/pull/6705))

- *(api)* Remove 23 stacked-duplicate @with_error_handling decorators across 9 files (#6633) (#6713) ([#6713](https://github.com/mrveiss/AutoBot-AI/pull/6713))

- *(backend)* Forward-ref Optional[Stub] type annotations in log_forwarding + validation_dashboard (#6666 follow-up) (#6707) ([#6707](https://github.com/mrveiss/AutoBot-AI/pull/6707))

- *(quality)* Surface backend status:"no_data" in dashboard instead of silent zeros (#6671) (#6683) ([#6683](https://github.com/mrveiss/AutoBot-AI/pull/6683))

- *(quality)* Invalidate code_quality:latest* Redis cache on scan completion (#6669) (#6682) ([#6682](https://github.com/mrveiss/AutoBot-AI/pull/6682))

- *(quality)* Plumb source_id into ChromaDB stats lookup with per-source fallback (#6670) (#6681) ([#6681](https://github.com/mrveiss/AutoBot-AI/pull/6681))

- *(deploy)* Only set AUTOBOT_TLS_CA_PATH when SLM CA cert exists at deploy time (#6677) (#6688) ([#6688](https://github.com/mrveiss/AutoBot-AI/pull/6688))

- *(slm-backend)* Clean up 4 SSOT-CI hardcoded-value violations (#6678) (#6687) ([#6687](https://github.com/mrveiss/AutoBot-AI/pull/6687))

- *(backend)* Guard playwright + docker optional-dep imports (#6667) (#6686) ([#6686](https://github.com/mrveiss/AutoBot-AI/pull/6686))

- *(backend)* Guard 5 missing-internal-module imports + add mcp __init__.py (#6666) (#6685) ([#6685](https://github.com/mrveiss/AutoBot-AI/pull/6685))

- *(backend)* Correct Orchestrator.max_parallel_tasks attribute path (#6665) (#6680) ([#6680](https://github.com/mrveiss/AutoBot-AI/pull/6680))

- *(backend)* Import MODERATE_RISK_PATTERNS from constants.terminal_constants (#6664) (#6679) ([#6679](https://github.com/mrveiss/AutoBot-AI/pull/6679))

- *(frontend)* Single Agents nav entry — Activity reached via /agents tabs (#6634 follow-up) (#6674) ([#6674](https://github.com/mrveiss/AutoBot-AI/pull/6674))

- *(slm-client)* URL-aware permissive SSL — accept self-signed cert on loopback (#6654) (#6657) ([#6657](https://github.com/mrveiss/AutoBot-AI/pull/6657))

- *(test)* Repair chat_agent_test.py patch target — services.mcp_dispatch.get_mcp_dispatcher (#6651) (#6656) ([#6656](https://github.com/mrveiss/AutoBot-AI/pull/6656))

- *(agents)* Rename Liskov-violating _build_success_response overrides in KnowledgeRetrievalAgent + EnhancedSystemCommandsAgent (#6650) (#6655) ([#6655](https://github.com/mrveiss/AutoBot-AI/pull/6655))

- *(chat)* Unblock chat from GUI — rename ChatAgent helper + repair AI Stack health probe (#6648, #6649) (#6653) ([#6653](https://github.com/mrveiss/AutoBot-AI/pull/6653))

- *(schemas)* Wire knowledge-graph DTOs to memory.py endpoints (#6620) (#6662) ([#6662](https://github.com/mrveiss/AutoBot-AI/pull/6662))

- *(schemas)* Unshadow UsageRecordRequest LLM-analytics variant (#6636) (#6652) ([#6652](https://github.com/mrveiss/AutoBot-AI/pull/6652))

- *(frontend)* Defend getFileIcon and getFileIconByMimeType against non-string input — fixes KnowledgeBrowser crash (#6645) (#6647) ([#6647](https://github.com/mrveiss/AutoBot-AI/pull/6647))

- *(schemas)* Wire 10 advanced-control + 2 validation-dashboard responses (#6623) (#6646) ([#6646](https://github.com/mrveiss/AutoBot-AI/pull/6646))

- *(schemas)* Wire 7 wake-word response DTOs (#6622) (#6644) ([#6644](https://github.com/mrveiss/AutoBot-AI/pull/6644))

- *(frontend)* Derive WebSocket scheme from window.location at runtime — fixes mixed-content block on HTTPS pages (#6642) (#6643) ([#6643](https://github.com/mrveiss/AutoBot-AI/pull/6643))

- *(schemas)* Wire EmbeddingStatsResponse to GET /stats (#6618) (#6641) ([#6641](https://github.com/mrveiss/AutoBot-AI/pull/6641))

- *(schemas)* Wire AgentConfigDetailResponse to GET /agents/{id} (#6619) (#6640) ([#6640](https://github.com/mrveiss/AutoBot-AI/pull/6640))

- *(schemas)* Wire FileRisk/PredictionResult to bug-prediction response models (#6617) (#6637) ([#6637](https://github.com/mrveiss/AutoBot-AI/pull/6637))

- *(chat)* Propagate h-full through ChatView's keep-alive so chat layout fills viewport (#6615) (#6625) ([#6625](https://github.com/mrveiss/AutoBot-AI/pull/6625))

- *(backend)* Restore chat init paths — chat_history_manager kwarg, ensure_initialized, get_default_client kwarg call (#6613) (#6614) ([#6614](https://github.com/mrveiss/AutoBot-AI/pull/6614))

- *(backend)* Default DataResponse.success=True so bare DataResponse(data=...) callers work (#6609) (#6611) ([#6611](https://github.com/mrveiss/AutoBot-AI/pull/6611))

- *(backend)* P0 boot crash — rename duplicate ProviderInfo/ConnectionTestRequest in schemas_workflows.py (#6604) (#6605) ([#6605](https://github.com/mrveiss/AutoBot-AI/pull/6605))

- *(install)* Out-of-the-box install now deploys autobot-backend on the SLM Manager host (#6600) (#6602) ([#6602](https://github.com/mrveiss/AutoBot-AI/pull/6602))

- *(backend)* Replace deprecated FastAPI regex= with pattern= (#6584) (#6587) ([#6587](https://github.com/mrveiss/AutoBot-AI/pull/6587))

- *(backend)* Use get_task_tracker() factory in desktop_streaming_manager (#6583) (#6586) ([#6586](https://github.com/mrveiss/AutoBot-AI/pull/6586))

- *(frontend)* Correct misleading offline banner copy (#6565) (#6585) ([#6585](https://github.com/mrveiss/AutoBot-AI/pull/6585))

- *(api)* Swap @with_error_handling/@router decorator order on 1801 endpoints across 188 files (#6558) (#6578) ([#6578](https://github.com/mrveiss/AutoBot-AI/pull/6578))

- *(backend)* Restore 4 orphan annotation imports from #6042 schema migration (#6569 #6570 #6571 #6572) (#6575) ([#6575](https://github.com/mrveiss/AutoBot-AI/pull/6575))

- *(chat)* Move @with_error_handling below @router.* on 16 endpoints (#6537) (#6562) ([#6562](https://github.com/mrveiss/AutoBot-AI/pull/6562))

- *(plugins)* Bundle 3 marketplace polish fixes — empty-url 422, refetch on delete, locale newlines (#6527 #6528 #6529) (#6551) ([#6551](https://github.com/mrveiss/AutoBot-AI/pull/6551))

- *(plugins)* Swap @with_error_handling below @router on 8 marketplace routes (#6532) (#6546) ([#6546](https://github.com/mrveiss/AutoBot-AI/pull/6546))

- *(api)* Re-add pydantic imports removed by #6042 migration (#6536) (#6538) ([#6538](https://github.com/mrveiss/AutoBot-AI/pull/6538))

- *(i18n)* Remove stale nav.* keys from non-English locales + add parity test (#6498) (#6541) ([#6541](https://github.com/mrveiss/AutoBot-AI/pull/6541))

- *(chat)* Align response_model with wire format + add get_statistics (#6490 #6497) (#6530) ([#6530](https://github.com/mrveiss/AutoBot-AI/pull/6530))

- *(plugins)* SSRF guard, auth on /catalog source_id, decorator order, reset stale source (#6481) (#6510) ([#6510](https://github.com/mrveiss/AutoBot-AI/pull/6510))

- *(chat)* Type 13 bare response_model=DataResponse annotations (#6410) (#6489) ([#6489](https://github.com/mrveiss/AutoBot-AI/pull/6489))

- *(chat_sessions)* Remove dead response_model on export endpoint (#6412) (#6460) ([#6460](https://github.com/mrveiss/AutoBot-AI/pull/6460))

- *(agent)* Rename local variable coordination_time → execution_time after #6406 rename (#6413) (#6457) ([#6457](https://github.com/mrveiss/AutoBot-AI/pull/6457))

- *(execution_strategies)* Wrap _execute_single_task in _safe_execute, route all 6 call sites — task exceptions can no longer bypass result recording (#6459) (#6462) ([#6462](https://github.com/mrveiss/AutoBot-AI/pull/6462))

- *(execution_strategies)* Catch dep-failure RuntimeError in sequential, stop pipeline on stage failure, remove unused imports (#6438 #6439 #6440) (#6443) ([#6443](https://github.com/mrveiss/AutoBot-AI/pull/6443))

- *(execution_strategies)* 4 bugs from discovery audit (#6428 #6429 #6430 #6431) (#6433) ([#6433](https://github.com/mrveiss/AutoBot-AI/pull/6433))

- *(enhanced_orchestration)* 4 targeted fixes from discovery audit (#6419 #6420 #6421 #6422) (#6423) ([#6423](https://github.com/mrveiss/AutoBot-AI/pull/6423))

- *(app)* Hide About footer on /chat pages

- *(nav)* Remove noVNC nav item + make chat tabs separate routes (#6414 #6415) (#6416) ([#6416](https://github.com/mrveiss/AutoBot-AI/pull/6416))

- *(api)* Remove unused datetime import from ai_stack_integration.py (#6390)

- *(workflow_runner)* 5 targeted bug fixes from #5058 review (#6381 #6382 #6383 #6391 #6394) ([#6395](https://github.com/mrveiss/AutoBot-AI/pull/6395))

- *(backend)* Emit USER_LOGOUT event in auth.py logout endpoint (#6367) (#6376) ([#6376](https://github.com/mrveiss/AutoBot-AI/pull/6376))

- *(frontend)* Use page protocol (http/https) in buildHostVncUrl — prevent mixed-content on TLS (#6361) (#6363) ([#6363](https://github.com/mrveiss/AutoBot-AI/pull/6363))

- *(frontend)* Hide About footer on login page — /about requires auth

- *(frontend)* Add /api prefix to path in useDocumentationSearch (#6356) (#6358) ([#6358](https://github.com/mrveiss/AutoBot-AI/pull/6358))

- *(api/voice)* Correct decorator order and remove duplicate @with_error_handling on all routes (#6352) (#6357) ([#6357](https://github.com/mrveiss/AutoBot-AI/pull/6357))

- *(frontend)* Add /api prefix to voice/voices and personality/active paths in useVoiceProfiles (#6351)

- *(skills/mcp_trace)* Cap input_params at 4 KB before Redis storage to prevent memory bloat (#6314) (#6349) ([#6349](https://github.com/mrveiss/AutoBot-AI/pull/6349))

- *(integrations)* Wire github and slack integrations to shared Redis rate limiter (#6311) (#6346) ([#6346](https://github.com/mrveiss/AutoBot-AI/pull/6346))

- *(skills)* Restructure builtin skill files into subdir/SKILL.md format for LocalDirSync discovery (#6336) (#6345) ([#6345](https://github.com/mrveiss/AutoBot-AI/pull/6345))

- *(api/long_running_operations)* Move from core_routers to feature_routers — already has _OPERATIONS_AVAILABLE graceful degradation (#6306) (#6343) ([#6343](https://github.com/mrveiss/AutoBot-AI/pull/6343))

- *(autobot_shared/network_constants)* Get_websocket_url() returns wss:// when TLS enabled (#6303) (#6342) ([#6342](https://github.com/mrveiss/AutoBot-AI/pull/6342))

- *(autobot_shared/ssot_config)* Omit TLS port from WebSocket URL — routes through nginx 443 (#6302) (#6341) ([#6341](https://github.com/mrveiss/AutoBot-AI/pull/6341))

- *(frontend)* Update WEBSOCKET_LOCAL to /api/ws path — missed by #6232 (#6301) (#6340) ([#6340](https://github.com/mrveiss/AutoBot-AI/pull/6340))

- *(autobot_shared/missing_dep)* Add __bool__=False; fix is-None guards in validation_dashboard, analyzers (#6339) ([#6339](https://github.com/mrveiss/AutoBot-AI/pull/6339))

- *(pki)* Implement certificate renewal with key preservation option (#4312) (#6294) ([#6294](https://github.com/mrveiss/AutoBot-AI/pull/6294))

- *(api/long_running_operations)* Restore HTTP 503 guards bypassed by MissingDep (#6289) (#6293) ([#6293](https://github.com/mrveiss/AutoBot-AI/pull/6293))

- *(code_analysis)* Remove dead self.config assignment in OwnershipAnalyzer (#6288) (#6292) ([#6292](https://github.com/mrveiss/AutoBot-AI/pull/6292))

- *(api/orchestration)* Remove unused SuccessResponse import (#6290) (#6291) ([#6291](https://github.com/mrveiss/AutoBot-AI/pull/6291))

- *(backend)* Apply MissingDep to remaining callable None-stubs in 6 API/analysis modules (#6285) (#6286) ([#6286](https://github.com/mrveiss/AutoBot-AI/pull/6286))

- *(frontend/backend)* Correct WebSocket URL path and HTTPS port (#6232) (#6283) ([#6283](https://github.com/mrveiss/AutoBot-AI/pull/6283))

- *(frontend)* Rename imported apiClient → httpClient in useWorkflowBuilder to resolve duplicate identifier build error (#6281)

- *(ci)* Add npm overrides for @typescript-eslint/utils and @vue/eslint-config-typescript TypeScript 6 peer dep (#6218)

- *(backend)* Replace callable None-stubs with MissingDep in 5 files (#6276) (#6280) ([#6280](https://github.com/mrveiss/AutoBot-AI/pull/6280))

- *(backend)* Add diagnostic detail to AI Stack error messages (#6234) (#6279) ([#6279](https://github.com/mrveiss/AutoBot-AI/pull/6279))

- *(backend)* Promote websockets and live_events routers to core_routers — eliminate silent degradation (#6229) (#6277) ([#6277](https://github.com/mrveiss/AutoBot-AI/pull/6277))

- *(docker)* Install CPU-only torch/torchvision to eliminate CUDA build bloat (#6220) (#6275) ([#6275](https://github.com/mrveiss/AutoBot-AI/pull/6275))

- *(ci)* Update smoke test timeout message to 7.5 min to match max_attempts=45 (#6255) (#6273) ([#6273](https://github.com/mrveiss/AutoBot-AI/pull/6273))

- *(docker)* Remove redundant /var/log/nginx tmpfs mount (#6254) (#6272) ([#6272](https://github.com/mrveiss/AutoBot-AI/pull/6272))

- *(frontend/backend)* Unify WebSocket URL to /api/ws in ssot-config and frontend-config endpoint (#6232) (#6271) ([#6271](https://github.com/mrveiss/AutoBot-AI/pull/6271))

- *(backend)* Define __all__ once outside try/except in training/__init__.py (#6265) (#6270) ([#6270](https://github.com/mrveiss/AutoBot-AI/pull/6270))

- *(backend)* Extract MissingDep sentinel to autobot_shared, use NoReturn typing (#6261, #6264) (#6269) ([#6269](https://github.com/mrveiss/AutoBot-AI/pull/6269))

- *(frontend)* Add missing getCssVar import to ResourceHeatmap and CodebaseAnalytics (#6263) (#6268) ([#6268](https://github.com/mrveiss/AutoBot-AI/pull/6268))

- *(composables)* Move fetchWithAuth exemption comments inline across 6 files (#6256) (#6266) ([#6266](https://github.com/mrveiss/AutoBot-AI/pull/6266))

- *(backend)* Surface specific error type/message in AI Stack client error messages (#6234) (#6262) ([#6262](https://github.com/mrveiss/AutoBot-AI/pull/6262))

- *(frontend)* Add missing usePollingJob import to ResourceHeatmap.vue (#6251) (#6260) ([#6260](https://github.com/mrveiss/AutoBot-AI/pull/6260))

- *(backend)* Replace module-level instantiation with lazy singletons in ide_integration.py (#6225) (#6259) ([#6259](https://github.com/mrveiss/AutoBot-AI/pull/6259))

- *(backend)* Replace None-stubs with sentinel in training/__init__.py (#6223) (#6258) ([#6258](https://github.com/mrveiss/AutoBot-AI/pull/6258))

- *(backend)* Register long_running_operations router — fixes HTTP 500 on /api/long-running/* (#6227) (#6253) ([#6253](https://github.com/mrveiss/AutoBot-AI/pull/6253))

- *(frontend)* Add missing usePollingJob import to CustomDashboard (#6231) (#6249) ([#6249](https://github.com/mrveiss/AutoBot-AI/pull/6249))

- *(docker)* Apply nginx worker/log fixes to nginx-ssl.conf, extend smoke poll to 45 attempts, add SLM health check (#6246 #6247 #6248)

- *(composables)* Make AbortSignal required in useFetchEndpoint fetcher callback (#6226) (#6245) ([#6245](https://github.com/mrveiss/AutoBot-AI/pull/6245))

- *(composables)* Use intermediate unknown cast for QualityDrillDown in useCodeQualityData (#6222) (#6244) ([#6244](https://github.com/mrveiss/AutoBot-AI/pull/6244))

- *(docker)* Nginx worker_processes 1, frontend depends_on service_healthy, smoke test checks backend health (#6240 #6241 #6242)

- *(composables)* Add ApprovalResponse type to useCommandApproval apiClient.post calls (#6221) (#6243) ([#6243](https://github.com/mrveiss/AutoBot-AI/pull/6243))

- *(ci)* Catch RuntimeError in ML optional-dep guards — 19 except ImportError → (ImportError, RuntimeError) (#6219) (#6238) ([#6238](https://github.com/mrveiss/AutoBot-AI/pull/6238))

- *(tooling)* Extend check_response_models hook to catch import-after-decorator ordering (#6143) (#6237) ([#6237](https://github.com/mrveiss/AutoBot-AI/pull/6237))

- *(docker)* Add /var/lib/nginx and /var/log/nginx tmpfs mounts and redirect nginx logs to stdout/stderr (#1809)

- *(docker)* Switch backend and SLM Dockerfiles to python:3.12-slim-bookworm (#6213) (#6218) ([#6218](https://github.com/mrveiss/AutoBot-AI/pull/6218))

- *(ci)* Pin torchvision>=0.26.0 and catch RuntimeError in ML imports to fix smoke test startup crash (#904)

- *(backend)* Replace bare singleton aliases with get_*() pattern at all call sites (#6196) (#6217) ([#6217](https://github.com/mrveiss/AutoBot-AI/pull/6217))

- *(api)* Move @with_error_handling below @router.* in workflow_export.py — 7 endpoints (#6194) (#6216) ([#6216](https://github.com/mrveiss/AutoBot-AI/pull/6216))

- *(deploy)* Add Ansible task to clear stale .pyc files after source sync (#6193) (#6215) ([#6215](https://github.com/mrveiss/AutoBot-AI/pull/6215))

- *(ci)* Increase smoke test timeout 15→30min for cold Docker build

- *(deps)* Correct -e ../autobot-shared path to -e ../autobot_shared in 3 requirements files (#6191) (#6212) ([#6212](https://github.com/mrveiss/AutoBot-AI/pull/6212))

- *(composables)* Migrate bare fetchWithAuth to useFetchEndpoint in analytics composables batch 2 (#6152) (#6211) ([#6211](https://github.com/mrveiss/AutoBot-AI/pull/6211))

- *(composables)* Migrate bare fetchWithAuth to useFetchEndpoint in analytics composables batch 1 (#6152) (#6210) ([#6210](https://github.com/mrveiss/AutoBot-AI/pull/6210))

- *(composables)* Add AbortController to useHostSelection loadHosts (#6136) (#6209) ([#6209](https://github.com/mrveiss/AutoBot-AI/pull/6209))

- *(composables)* Correct TS cross-type assertion in useKnowledgeGraphRAG

- *(error_boundaries)* Add INFRASTRUCTURE to get_status_code_for_category map

- *(backend)* 3 implementation gaps from provisioning debug session

- *(knowledge)* Resolve TS2339 type errors in useKnowledgeGraph (#6040) (#6197) ([#6197](https://github.com/mrveiss/AutoBot-AI/pull/6197))

- *(backend)* Add task_tracker alias and fix modern_ai_integration import

- *(docker)* Match autobot-shared hyphen in requirements filter regex ([#6171](https://github.com/mrveiss/AutoBot-AI/pull/6171))

- *(orchestration)* Add missing AgentCapability members to orchestration/types.py

- *(api)* Remove response_model from 204 No Content route in npu_workers.py

- *(api)* Remove invalid context= kwarg from with_error_handling in branch_health.py

- *(backend)* Resolve 5 import/definition errors preventing backend startup

- *(deps)* Restore typescript 6.0.3, use npm overrides to satisfy openapi-typescript peer dep ([#6148](https://github.com/mrveiss/AutoBot-AI/pull/6148))

- *(deps)* Downgrade typescript 6.0.3→5.8.3 to satisfy openapi-typescript peer dep (#6139) ([#6144](https://github.com/mrveiss/AutoBot-AI/pull/6144))

- *(api)* Add missing List import to a2a.py

- *(api)* Add missing with_error_handling/ErrorCategory import to analytics_precommit

- *(api)* Move late-placed schema imports before route decorators in 3 files

- *(config)* Consolidate model_constants.get_lm_studio_url to use config.llm.lmstudio_host (#6125) (#6131) ([#6131](https://github.com/mrveiss/AutoBot-AI/pull/6131))

- *(api)* Add response_model to 5 missed natural_language_search endpoints (#6115) (#6130) ([#6130](https://github.com/mrveiss/AutoBot-AI/pull/6130))

- *(api)* Add response_model to 5 missed knowledge_graph_routes endpoints (#6116) (#6129) ([#6129](https://github.com/mrveiss/AutoBot-AI/pull/6129))

- *(ci)* Add --build flag to docker smoke test compose up

- *(api)* Add missing DataResponse import to agent_config and validation_dashboard

- *(api)* Add response_model=DataResponse to GET /analyze in development_speedup.py (#6112) (#6118) ([#6118](https://github.com/mrveiss/AutoBot-AI/pull/6118))

- *(api)* Move RISKY_COMMAND_PATTERNS and MODERATE_RISK_PATTERNS from schemas_terminal.py to security.py (#6093) (#6111) ([#6111](https://github.com/mrveiss/AutoBot-AI/pull/6111))

- *(frontend)* Replace 29 direct fetch() calls with fetchWithAuth (#5945) (#6083) ([#6083](https://github.com/mrveiss/AutoBot-AI/pull/6083))

- *(api)* Add 6 missing fields to CostTrackingRecordResponse — restores full LLMUsageRecord shape (#5995) (#5998) ([#5998](https://github.com/mrveiss/AutoBot-AI/pull/5998))

- *(api)* Add 6 missing fields to CostTrackingRecordResponse — restores full LLMUsageRecord shape (#5995) (#5997) ([#5997](https://github.com/mrveiss/AutoBot-AI/pull/5997))

- *(api)* Add UsageRecentResponse wrapper and wire GET /usage/recent response_model (#5976) (#5986) ([#5986](https://github.com/mrveiss/AutoBot-AI/pull/5986))

- *(api)* Add UsageRecentResponse wrapper and wire GET /usage/recent response_model (#5976) (#5981) ([#5981](https://github.com/mrveiss/AutoBot-AI/pull/5981))

- *(config)* Correct code_source_dir default + expose new env vars in Ansible template (#5980) ([#5980](https://github.com/mrveiss/AutoBot-AI/pull/5980))

- *(lint)* Restrict _var_dict_keys/_returned_var_names to function scope, add attribute bypass tests (#5964 #5965) (#5978) ([#5978](https://github.com/mrveiss/AutoBot-AI/pull/5978))

- *(services)* Extract 300s timeout constant in concurrent_limiter.py (#5959) (#5975) ([#5975](https://github.com/mrveiss/AutoBot-AI/pull/5975))

- *(api)* Replace hardcoded localhost:1234 LM Studio URL with LMSTUDIO_HOST env var in system.py (#5957) (#5974) ([#5974](https://github.com/mrveiss/AutoBot-AI/pull/5974))

- *(auth)* Replace hardcoded @autobot.local domain with AUTOBOT_AUTH_DOMAIN config (#5954) (#5973) ([#5973](https://github.com/mrveiss/AutoBot-AI/pull/5973))

- *(services)* Extract 300s timeout constant in concurrent_limiter.py (#5959) (#5971) ([#5971](https://github.com/mrveiss/AutoBot-AI/pull/5971))

- *(knowledge)* Replace hardcoded llama3.2:latest model default with config-backed value (#5958) (#5970) ([#5970](https://github.com/mrveiss/AutoBot-AI/pull/5970))

- *(api)* Replace hardcoded localhost:1234 LM Studio URL with LMSTUDIO_HOST env var in system.py (#5957) (#5969) ([#5969](https://github.com/mrveiss/AutoBot-AI/pull/5969))

- *(desktop)* Replace hardcoded VNC password path with AUTOBOT_VNC_PASSWD_FILE env var (#5956) (#5968) ([#5968](https://github.com/mrveiss/AutoBot-AI/pull/5968))

- *(backend)* Derive service registry hostnames from deployment.domain config (#5955) (#5967) ([#5967](https://github.com/mrveiss/AutoBot-AI/pull/5967))

- *(auth)* Replace hardcoded @autobot.local domain with AUTOBOT_AUTH_DOMAIN config (#5954) (#5966) ([#5966](https://github.com/mrveiss/AutoBot-AI/pull/5966))

- *(backend)* Replace hardcoded /opt/autobot/code_source with env var in branch_metrics and branch_health (#5953) (#5963) ([#5963](https://github.com/mrveiss/AutoBot-AI/pull/5963))

- *(api)* Add @with_error_handling to skills_repos, integration_database, integration_cloud (#5947) (#5962) ([#5962](https://github.com/mrveiss/AutoBot-AI/pull/5962))

- *(services)* Replace get_redis_client(async_client=True) with get_async_redis_client in semantic_query_cache (#5943) (#5961) ([#5961](https://github.com/mrveiss/AutoBot-AI/pull/5961))

- *(api)* Revert response_model=DataResponse to None for 309 variable-return endpoints across full API directory (#5928) (#5934) ([#5934](https://github.com/mrveiss/AutoBot-AI/pull/5934))

- *(frontend)* Replace DefineComponent<{},{},any> stubs with proper prop types (#5020) ([#5920](https://github.com/mrveiss/AutoBot-AI/pull/5920))

- *(api)* Revert response_model=DataResponse to None for 61 variable-return endpoints (#5904) (#5917) ([#5917](https://github.com/mrveiss/AutoBot-AI/pull/5917))

- *(agents)* Rename live event channel agent: → heartbeat: for heartbeat events (#4444) (#5908) ([#5908](https://github.com/mrveiss/AutoBot-AI/pull/5908))

- *(chat)* Reset showMobileSidebar on desktop viewport resize (#4446) (#5906) ([#5906](https://github.com/mrveiss/AutoBot-AI/pull/5906))

- *(truncation)* Skip whitespace-snap for CJK text in _snap_to_char_boundary (#4436) (#5907) ([#5907](https://github.com/mrveiss/AutoBot-AI/pull/5907))

- *(agents)* Replace naive [:2000] truncation with ToolOutputFilter in command_explanation_service (#5885) (#5901) ([#5901](https://github.com/mrveiss/AutoBot-AI/pull/5901))

- *(tool_output_filter)* Wire dead code, singleton, prepare_and_filter, pytest summary (#5891-#5895) ([#5899](https://github.com/mrveiss/AutoBot-AI/pull/5899))

- *(api)* Revert response_model=DataResponse to None for plain-dict endpoints (#5896) (#5897) ([#5897](https://github.com/mrveiss/AutoBot-AI/pull/5897))

- *(composables)* Add _pending counter to useLoadingState + unit tests (#5881 #5883) ([#5890](https://github.com/mrveiss/AutoBot-AI/pull/5890))

- *(planner)* Wire available_tools default, fix byte logging, rm name collision, trim template (#5870 #5871 #5872 #5873) (#5879) ([#5879](https://github.com/mrveiss/AutoBot-AI/pull/5879))

- *(planner)* Wire available_tools default, fix byte logging, rm name collision, trim template (#5870 #5871 #5872 #5873) (#5877) ([#5877](https://github.com/mrveiss/AutoBot-AI/pull/5877))

- *(api)* Replace unjustified response_model=None with DataResponse (#5843) (#5868) ([#5868](https://github.com/mrveiss/AutoBot-AI/pull/5868))

- *(composables)* Suppress spurious AbortError log/callback in useFetchEndpoint (#5859) (#5866) ([#5866](https://github.com/mrveiss/AutoBot-AI/pull/5866))

- *(composables)* Forward AbortSignal in useFetchEndpoint + expose abort() for clean reset (#5823 #5824) (#5857) ([#5857](https://github.com/mrveiss/AutoBot-AI/pull/5857))

- *(knowledge)* Wrap sync chromadb calls in asyncio.to_thread + type collections as BaseCollection (#5800 #5804) (#5856) ([#5856](https://github.com/mrveiss/AutoBot-AI/pull/5856))

- *(chat)* Use real stream_completion in multi-model compare; fix lazy init race (#5013 #5023) (#5854) ([#5854](https://github.com/mrveiss/AutoBot-AI/pull/5854))

- *(knowledge)* Wrap sync chromadb calls in asyncio.to_thread + type collections as BaseCollection (#5800 #5804) (#5853) ([#5853](https://github.com/mrveiss/AutoBot-AI/pull/5853))

- *(composables)* Forward AbortSignal in useFetchEndpoint + expose abort() for clean reset (#5823 #5824) (#5851) ([#5851](https://github.com/mrveiss/AutoBot-AI/pull/5851))

- *(chat)* Use real stream_completion in multi-model compare; fix lazy init race (#5013 #5023) (#5850) ([#5850](https://github.com/mrveiss/AutoBot-AI/pull/5850))

- *(knowledge)* Wrap sync chromadb calls in asyncio.to_thread + type collections as BaseCollection (#5800 #5804) (#5849) ([#5849](https://github.com/mrveiss/AutoBot-AI/pull/5849))

- *(api)* Change response_model=DataResponse→None for streaming/binary endpoints (#5317 follow-up) (#5845) ([#5845](https://github.com/mrveiss/AutoBot-AI/pull/5845))

- *(planner)* Pass real tool descriptions to compress_description + use AsyncRedisClientLockedMixin (#5826 #5828) (#5839) ([#5839](https://github.com/mrveiss/AutoBot-AI/pull/5839))

- *(composables)* Always pass AbortSignal to fetcher regardless of param arity (#5801) (#5836) ([#5836](https://github.com/mrveiss/AutoBot-AI/pull/5836))

- *(api)* Rate-limit /v1/chat/completions; add get_provider_by_name; validate stream_completion async gen (#5132) (#5816) ([#5816](https://github.com/mrveiss/AutoBot-AI/pull/5816))

- *(api)* Rate-limit /v1/chat/completions; add get_provider_by_name; validate stream_completion async gen (#5132) (#5806) ([#5806](https://github.com/mrveiss/AutoBot-AI/pull/5806))

- *(composables)* Add AbortController to useApiResource — abort prior in-flight on refresh() (#5179) (#5796) ([#5796](https://github.com/mrveiss/AutoBot-AI/pull/5796))

- *(cleanup)* Remove phantom dirs from _resolve_cache_directories (#5082) (#5795) ([#5795](https://github.com/mrveiss/AutoBot-AI/pull/5795))

- *(composables)* Abort in-flight requests on concurrent refresh() in useApiResource (#5179) (#5787) ([#5787](https://github.com/mrveiss/AutoBot-AI/pull/5787))

- *(agent_terminal)* Use server deadline_ts for approval countdown to prevent clock drift (#5024) (#5779) ([#5779](https://github.com/mrveiss/AutoBot-AI/pull/5779))

- *(infra)* Remove orphaned shared/config requirements files and Dependabot entry (#5750) (#5777) ([#5777](https://github.com/mrveiss/AutoBot-AI/pull/5777))

- *(redis)* Add chromadb lock + migrate to AsyncRedisClientLockedMixin in detector.py (#5769 #5768) (#5775) ([#5775](https://github.com/mrveiss/AutoBot-AI/pull/5775))

- *(redis)* Guard set_budget_alert and get_all_budget_alerts against None Redis (#5767) (#5774) ([#5774](https://github.com/mrveiss/AutoBot-AI/pull/5774))

- *(deps)* Remove dead /config dependabot entry targeting non-existent path (#5751) (#5758) ([#5758](https://github.com/mrveiss/AutoBot-AI/pull/5758))

- *(infra)* Use SCRIPT_DIR-relative path for requirements.txt in celery worker (#5753) (#5754) ([#5754](https://github.com/mrveiss/AutoBot-AI/pull/5754))

- *(i18n)* Add missing knowledge.connectors.tier keys to 10 non-English locales (#5056) (#5749) ([#5749](https://github.com/mrveiss/AutoBot-AI/pull/5749))

- *(i18n)* Convert analytics.sources.share to object in 10 non-English locales (#5021) (#5747) ([#5747](https://github.com/mrveiss/AutoBot-AI/pull/5747))

- *(redis)* Add double-checked lock to _get_redis_client in detector.py (#5729) (#5746) ([#5746](https://github.com/mrveiss/AutoBot-AI/pull/5746))

- *(tests)* Skip torch-dependent tests when torch is stubbed (#5737) (#5744) ([#5744](https://github.com/mrveiss/AutoBot-AI/pull/5744))

- *(ansible)* Split playwright-browsers recurse into dir/file loops (#5085) (#5743) ([#5743](https://github.com/mrveiss/AutoBot-AI/pull/5743))

- *(docs)* Update browser worker README port 3000→9001 (#5084) (#5742) ([#5742](https://github.com/mrveiss/AutoBot-AI/pull/5742))

- *(sync-queue)* Schedule prune_done via Celery Beat (#5081) (#5741) ([#5741](https://github.com/mrveiss/AutoBot-AI/pull/5741))

- *(deps)* Add dependabot monitoring for autobot-infrastructure/shared/config requirements (#5685) (#5738) ([#5738](https://github.com/mrveiss/AutoBot-AI/pull/5738))

- *(deps)* Remove redundant @types/uuid from mcp-autobot-tracker and mcp-task-manager-server (#5684) (#5736) ([#5736](https://github.com/mrveiss/AutoBot-AI/pull/5736))

- *(deps)* Pin cryptography>=46.0.7 and python-multipart>=0.0.26 in knowledge-base-mcp pyproject.toml (#5683) (#5735) ([#5735](https://github.com/mrveiss/AutoBot-AI/pull/5735))

- *(deps)* Add dependabot.yml ignore rules for deleted config/ manifest paths (#5682) (#5734) ([#5734](https://github.com/mrveiss/AutoBot-AI/pull/5734))

- *(tests)* Resolve 126 optimization test failures — @patch compat + torch skip markers (#5728) (#5733) ([#5733](https://github.com/mrveiss/AutoBot-AI/pull/5733))

- *(redis)* Fix unawaited bug in analytics_infrastructure/detector; migrate 4 services to AsyncRedisClientMixin (#5708) (#5727) ([#5727](https://github.com/mrveiss/AutoBot-AI/pull/5727))

- *(redis)* Remove dead _initialized state from RedisEventStreamManager (#5709) (#5726) ([#5726](https://github.com/mrveiss/AutoBot-AI/pull/5726))

- *(redis)* Fix unawaited bug in analytics_infrastructure/detector; migrate 4 services to AsyncRedisClientMixin (#5708) (#5725) ([#5725](https://github.com/mrveiss/AutoBot-AI/pull/5725))

- *(backend)* Remove redundant safe_http_detail in duplicates.py (#5722) (#5724) ([#5724](https://github.com/mrveiss/AutoBot-AI/pull/5724))

- *(slm)* Remove ansible output from reboot HTTP 500 detail (#5721) (#5723) ([#5723](https://github.com/mrveiss/AutoBot-AI/pull/5723))

- *(redis)* Fix unawaited coroutine in 4 analytics services; migrate analytics_service to AsyncRedisClientMixin (#5707) (#5718) ([#5718](https://github.com/mrveiss/AutoBot-AI/pull/5718))

- *(redis)* Fix unawaited coroutine + migrate to AsyncRedisClientMixin in saved_reports and analytics_llm_patterns (#5704) (#5717) ([#5717](https://github.com/mrveiss/AutoBot-AI/pull/5717))

- *(slm)* Remove ansible output and str(exc) from HTTP responses in nodes.py (#5713) (#5716) ([#5716](https://github.com/mrveiss/AutoBot-AI/pull/5716))

- *(backend)* Adopt safe_http_detail() in 5 exception handlers to restore debug logging (#5712) (#5715) ([#5715](https://github.com/mrveiss/AutoBot-AI/pull/5715))

- *(frontend)* Replace manual script-strip regex with sanitizeHtml utility (#5711) (#5714) ([#5714](https://github.com/mrveiss/AutoBot-AI/pull/5714))

- *(security)* SSH RejectPolicy — clearer error + setup-ssh-known-hosts playbook + docs (#5677) ([#5689](https://github.com/mrveiss/AutoBot-AI/pull/5689))

- *(code_intelligence)* Update redis_optimizer suggestion and test fixtures to use get_async_redis_client (#5670) (#5690) ([#5690](https://github.com/mrveiss/AutoBot-AI/pull/5690))

- *(vision)* Restore watch(refreshInterval) to restart polling on interval change (#5660) (#5686) ([#5686](https://github.com/mrveiss/AutoBot-AI/pull/5686))

- *(tests)* Correct get_async_redis_client patch targets in 4 test files (#5655) (#5667) ([#5667](https://github.com/mrveiss/AutoBot-AI/pull/5667))

- *(redis)* Replace get_redis_client(async_client=True) with await get_async_redis_client() in two services (#5659) (#5666) ([#5666](https://github.com/mrveiss/AutoBot-AI/pull/5666))

- *(llm-cache)* Unify get_llm_cache / get_llm_cache_async to one singleton (#5657) (#5662) ([#5662](https://github.com/mrveiss/AutoBot-AI/pull/5662))

- *(frontend)* Port.browser default 3000→9001; resolveHost fallback for all vm.* hosts (#5642, #5646)

- *(ui)* Migrate all remaining EmptyState icon=\"fas fa-*\" to IconName (#5643) (#5652) ([#5652](https://github.com/mrveiss/AutoBot-AI/pull/5652))

- *(security)* Tune prompt-injection sanitizer LOG_ONLY rules from prod telemetry (#5197) (#5649) ([#5649](https://github.com/mrveiss/AutoBot-AI/pull/5649))

- *(tests)* Correct get_redis_client patch path in working_memory and agent_diary tests (#5624) (#5648) ([#5648](https://github.com/mrveiss/AutoBot-AI/pull/5648))

- *(tests)* Add factory-exception retry test to lazy_singleton (#5631) (#5647) ([#5647](https://github.com/mrveiss/AutoBot-AI/pull/5647))

- *(ui)* Replace FA class strings in EmptyState callers with IconName values (#5616) (#5633) ([#5633](https://github.com/mrveiss/AutoBot-AI/pull/5633))

- *(ui)* Type DataTable emptyIcon prop as IconName for type-safe icon passing (#5630) (#5638) ([#5638](https://github.com/mrveiss/AutoBot-AI/pull/5638))

- *(frontend)* Fall back to window.location.hostname when VITE_BACKEND_HOST unset (#5627)

- *(chat_workflow)* Guard AsyncRedisSaver import for redisvl compatibility (#5623)

- *(memory)* Replace broken mixed singleton pattern in compat.py (#5622)

- *(backend)* Correct UnboundLocalError in get_extension_manager and get_slash_command_handler (#5626)

- *(config)* Correct Ports.browser default from 3000 to 9001 (#5620) (#5621) ([#5621](https://github.com/mrveiss/AutoBot-AI/pull/5621))

- *(ansible)* Correct browser service port from 3000 (Grafana) to 9001 (#5608)

- *(api)* Standardize connector endpoint response shape (#5210) (#5617) ([#5617](https://github.com/mrveiss/AutoBot-AI/pull/5617))

- *(ui)* Migrate CommandPermissionDialog to script setup + add focus trap (#5588) (#5614) ([#5614](https://github.com/mrveiss/AutoBot-AI/pull/5614))

- *(ui)* Convert HostSelector host-item divs to semantic buttons (#5587) (#5613) ([#5613](https://github.com/mrveiss/AutoBot-AI/pull/5613))

- *(backend)* Add missing now_utc imports to 4 services/utils files (#5602) (#5611) ([#5611](https://github.com/mrveiss/AutoBot-AI/pull/5611))

- *(provision)* WSL2 frontend_backend_host override in Phase 4c (#5608)

- *(backend)* Add missing now_utc imports to 4 services/utils files (#5602) (#5609) ([#5609](https://github.com/mrveiss/AutoBot-AI/pull/5609))

- *(backend)* Override backend_host to 10.255.255.254 on WSL2 hosts (#5608)

- *(provision)* Always show task name in heartbeat, add missing hints (#5607)

- *(backend)* Increase health check window from 5min to 10min (#5605)

- *(backend)* Restore models.heartbeat import block split by event_types import (#5580)

- *(backend)* Move lazy_singleton import out of malformed try block in tracker.py

- *(ansible)* Initialize PostgreSQL cluster when package pre-installed but data dir missing (#5603)

- *(knowledge)* Separate fetch-layer errors from Redis-down state (#5590) (#5601) ([#5601](https://github.com/mrveiss/AutoBot-AI/pull/5601))

- *(ui)* Accessibility gap fixes from #4806 audit (#5592 #5593 #5594 #5595) (#5598) ([#5598](https://github.com/mrveiss/AutoBot-AI/pull/5598))

- *(tests)* Correct FactsMixin import path in fake_kb.py + restore FactsMixin import in test_facts_dedup.py (#5557)

- *(knowledge)* Convert CATEGORY_METADATA examples from str to List[str]

- *(VisualBrowserPanel)* Normalize URL input correctly for localhost + bare words (#5139) (#5570) ([#5570](https://github.com/mrveiss/AutoBot-AI/pull/5570))

- *(infra)* Add missing parse_utc_iso/now_utc imports + fix 3 fromisoformat patterns (#5513) (#5566) ([#5566](https://github.com/mrveiss/AutoBot-AI/pull/5566))

- *(backend)* Add missing now_utc imports to 49 files from datetime migration (#5514) (#5567) ([#5567](https://github.com/mrveiss/AutoBot-AI/pull/5567))

- *(setup_wizard)* Move re import to module level in _extract_failure_summary

- *(provisioning)* Replace 'exit code 2' with human-readable failure summary

- *(backend)* Add missing now_utc import to 8 api modules causing startup NameError

- *(time_utils)* Delete utc_timestamp_z, migrate workflow_versioning, remove orphaned timezone imports (#5539 #5540 #5541) ([#5546](https://github.com/mrveiss/AutoBot-AI/pull/5546))

- *(models)* DateTime(timezone=True) + Alembic migration for skills and process_run (#5538) ([#5545](https://github.com/mrveiss/AutoBot-AI/pull/5545))

- *(analytics)* ExportReport race — use useFetchEndpoint context hook (#5455) (#5531) ([#5531](https://github.com/mrveiss/AutoBot-AI/pull/5531))

- *(backend)* Remaining datetime.utcnow() + time.gmtime() sites (#5199) (#5534) ([#5534](https://github.com/mrveiss/AutoBot-AI/pull/5534))

- *(backend)* Time_provider.py datetime.now() → now_utc() + infra session bug (#5513) (#5532) ([#5532](https://github.com/mrveiss/AutoBot-AI/pull/5532))

- *(schemas)* Migrate ReindexWithContextResponse from inline to knowledge/schemas/ (#5503) (#5524) ([#5524](https://github.com/mrveiss/AutoBot-AI/pull/5524))

- *(slm-backend)* Migrations_applied.applied_at TIMESTAMP → TIMESTAMPTZ (#5515) (#5516) ([#5516](https://github.com/mrveiss/AutoBot-AI/pull/5516))

- *(slm-backend)* Adopt DateTime(timezone=True) columns + datetime.now(timezone.utc) (#5385) (#5502) ([#5502](https://github.com/mrveiss/AutoBot-AI/pull/5502))

- *(backend)* Adopt now_utc() + parse_utc_iso in sso_integration.py (#5419 P2 batch 5) (#5493) ([#5493](https://github.com/mrveiss/AutoBot-AI/pull/5493))

- *(backend)* Adopt now_utc() across 40 pure-producer sites (#5419 P2 batch 3) (#5489) ([#5489](https://github.com/mrveiss/AutoBot-AI/pull/5489))

- *(backend)* Adopt parse_utc_iso across 24 pure-parser sites (#5419 P2 batch 2) (#5482) ([#5482](https://github.com/mrveiss/AutoBot-AI/pull/5482))

- *(backend)* Adopt parse_utc_iso + now_utc() in 8 mixed files (#5419 P2 batch 4) (#5491) ([#5491](https://github.com/mrveiss/AutoBot-AI/pull/5491))

- *(schemas)* Correct QueryKnowledgeResponse fields to match search response shape (#5487) (#5490) ([#5490](https://github.com/mrveiss/AutoBot-AI/pull/5490))

- *(backend)* P2 top-5 files parse_utc_iso adoption (#5419 P2 partial) (#5479) ([#5479](https://github.com/mrveiss/AutoBot-AI/pull/5479))

- *(knowledge)* Bulk.py + stats.py adopt parse_utc_iso (paired-parser migration) (#5475) (#5478) ([#5478](https://github.com/mrveiss/AutoBot-AI/pull/5478))

- *(backend)* Captcha_human_loop param-based timing + agent.py dual-purpose split (#5351) (#5477) ([#5477](https://github.com/mrveiss/AutoBot-AI/pull/5477))

- *(composables)* SelectAll O(n²) → O(n+m) in useKnowledgeVectorization (#5412) (#5452) ([#5452](https://github.com/mrveiss/AutoBot-AI/pull/5452))

- *(tools)* Install_skills.sh relative-path resolution (follow-up to #5447 / PR #5458) (#5471) ([#5471](https://github.com/mrveiss/AutoBot-AI/pull/5471))

- *(backend)* Task_queue/security_policy/planner producer-not-migrated regression (#5469) (#5470) ([#5470](https://github.com/mrveiss/AutoBot-AI/pull/5470))

- *(backend)* P2 top-5 files parse_utc_iso adoption (#5419 P2 partial) (#5468) ([#5468](https://github.com/mrveiss/AutoBot-AI/pull/5468))

- *(backend)* P1 state-recovery parse_utc_iso adoption (#5419 P1) (#5467) ([#5467](https://github.com/mrveiss/AutoBot-AI/pull/5467))

- *(autobot_shared)* Parse_utc_iso raises ValueError on non-str input (#5464) (#5465) ([#5465](https://github.com/mrveiss/AutoBot-AI/pull/5465))

- *(utils)* Background_task_manager aware-naive TypeError — silent timeout leak (#5419 P0) (#5462) ([#5462](https://github.com/mrveiss/AutoBot-AI/pull/5462))

- *(composables)* Systematic onUnmounted/onMounted guard audit across composables (#5406) (#5450) ([#5450](https://github.com/mrveiss/AutoBot-AI/pull/5450))

- *(lint+api)* 3 Layer-N+1 gaps from PR #5424 review (#5418, #5426, #5427) (#5434) ([#5434](https://github.com/mrveiss/AutoBot-AI/pull/5434))

- *(dialogs)* Immediate: true on 10 focus watches + extract useBodyScrollLock (closes #5421 #5422) (#5433) ([#5433](https://github.com/mrveiss/AutoBot-AI/pull/5433))

- *(api)* _is_session_in_range naive>=aware regression from PR #5414 (#5420) (#5424) ([#5424](https://github.com/mrveiss/AutoBot-AI/pull/5424))

- *(infra)* Wire SemanticChunker into verify_knowledge_consistency.py (#5396 follow-up) (#5416) ([#5416](https://github.com/mrveiss/AutoBot-AI/pull/5416))

- *(backend)* Adopt parse_utc_iso() at 11 fromisoformat(.replace(\"Z\", \"+00:00\")) sites (#5398) (#5414) ([#5414](https://github.com/mrveiss/AutoBot-AI/pull/5414))

- *(lint)* Worktree exclusion + path-aware suggestions + test allowlist (#5393, #5394, #5397) (#5405) ([#5405](https://github.com/mrveiss/AutoBot-AI/pull/5405))

- *(utils/simple_optimization_test)* Redirect imports to current GPU chunker (#5395) (#5403) ([#5403](https://github.com/mrveiss/AutoBot-AI/pull/5403))

- *(composables)* Guard onUnmounted with onScopeDispose in useThumbnailWorker + useTimeout (#5347) (#5399) ([#5399](https://github.com/mrveiss/AutoBot-AI/pull/5399))

- *(analytics)* Promise.allSettled in runCodeIntelligenceAnalysis — preserve partial success (#5387) (#5391) ([#5391](https://github.com/mrveiss/AutoBot-AI/pull/5391))

- *(slm/infra)* Migrate datetime.utcnow().isoformat() to aware UTC inline (#5381) (#5384) ([#5384](https://github.com/mrveiss/AutoBot-AI/pull/5384))

- *(backend)* Migrate datetime.utcnow().isoformat() in tests + migration scripts (#5263) (#5380) ([#5380](https://github.com/mrveiss/AutoBot-AI/pull/5380))

- *(security)* Threat_detection naive/aware datetime mismatches (#5350) (#5377) ([#5377](https://github.com/mrveiss/AutoBot-AI/pull/5377))

- *(analytics)* Wire code-intel findings + delete 4 orphans + harden audit (#5365) (#5374) ([#5374](https://github.com/mrveiss/AutoBot-AI/pull/5374))

- *(knowledge_vectorization)* Restore @with_error_handling on 2 endpoints (#5358) (#5361) ([#5361](https://github.com/mrveiss/AutoBot-AI/pull/5361))

- *(composables)* Guard useDebounce onUnmounted with onScopeDispose (#5318) (#5345) ([#5345](https://github.com/mrveiss/AutoBot-AI/pull/5345))

- *(frontend)* Wire searchManPages + formatKey properly (was undefined at runtime) (#5315) (#5344) ([#5344](https://github.com/mrveiss/AutoBot-AI/pull/5344))

- *(database)* Swap 6 SQLAlchemy column defaults from datetime.utcnow to now_utc (#5305) (#5320) ([#5320](https://github.com/mrveiss/AutoBot-AI/pull/5320))

- *(codebase-analytics)* Normalize HardcodedValue contract — backend↔frontend shape drift (#5290) (#5307) ([#5307](https://github.com/mrveiss/AutoBot-AI/pull/5307))

- *(codebase-analytics)* Wire hardcoded-values panel — was fetched but never rendered (#5277) (#5284) ([#5284](https://github.com/mrveiss/AutoBot-AI/pull/5284))

- *(analytics)* Scope codebase export endpoints by source_id (#5266)

- *(repository)* Unwrap SystemRepository settings/config response shapes (#5214) (#5260) ([#5260](https://github.com/mrveiss/AutoBot-AI/pull/5260))

- *(repository)* Unwrap SystemRepository health/info/metrics response shapes (#5212) (#5259) ([#5259](https://github.com/mrveiss/AutoBot-AI/pull/5259))

- *(backend)* Split /api/health into distinct GET and HEAD operation_ids (#5222) (#5258) ([#5258](https://github.com/mrveiss/AutoBot-AI/pull/5258))

- *(backend)* Replace 11 invalid mixed-format datetime.utcnow().isoformat() + "Z" sites with utc_timestamp() (#5238) (#5243) ([#5243](https://github.com/mrveiss/AutoBot-AI/pull/5243))

- *(repository)* Unwrap KnowledgeRepository stats response shapes (#5215) (#5240) ([#5240](https://github.com/mrveiss/AutoBot-AI/pull/5240))

- *(repository)* Systematic audit + fix of response.data silent casts (#5207) (#5228) ([#5228](https://github.com/mrveiss/AutoBot-AI/pull/5228))

- *(knowledge-connectors)* Align testConnector + syncConnector with backend response shapes (#5203 #5204) (#5227) ([#5227](https://github.com/mrveiss/AutoBot-AI/pull/5227))

- *(knowledge-connectors)* Unpack wrapped backend response shapes in KnowledgeRepository (#5200) (#5202) ([#5202](https://github.com/mrveiss/AutoBot-AI/pull/5202))

- *(frontend)* Cytoscape Retry button now re-initializes the graph (#5173)

- *(rag-benchmarks)* Require ≥1 test_id access before labeling held_out_score (#5160) (#5165) ([#5165](https://github.com/mrveiss/AutoBot-AI/pull/5165))

- *(frontend)* FunctionCallGraph 'cytoscape is not defined' - complete #3998 lazy-load refactor (#5158)

- *(knowledge/backends)* Dedup guard on InMemory update, wrap list_collections, expand contract tests (#5133 #5134 #5135) (#5144) ([#5144](https://github.com/mrveiss/AutoBot-AI/pull/5144))

- *(codebase-analytics)* Import get_redis_client instead of get_async_redis_client (#5099) (#5124) ([#5124](https://github.com/mrveiss/AutoBot-AI/pull/5124))

- *(ui)* Real focus trap via keydown in HostSelectionDialog + BaseModal (#5016)

- *(api)* /v1/chat/completions emits usage in final streaming chunk when include_usage=true (#5019)

- *(agent_loop)* Canonicalize APPROVAL_REQUIRED event_type to uppercase (#5014, #4959)

- *(codebase-analytics)* Scope getCodebaseStats + getProblemsReport by source_id (#5111) (#5113) ([#5113](https://github.com/mrveiss/AutoBot-AI/pull/5113))

- *(typescript)* Drop misleading '| null' from fetchStats return type (#5103) (#5118) ([#5118](https://github.com/mrveiss/AutoBot-AI/pull/5118))

- *(frontend)* DocumentationSearchSidebar uses apiClient directly — remove broken destructuring (#5095) (#5115) ([#5115](https://github.com/mrveiss/AutoBot-AI/pull/5115))

- *(cleanup)* Exclude chromadb/redis/sqlite files from cleanup_generated_files walks (#5083) (#5090) ([#5090](https://github.com/mrveiss/AutoBot-AI/pull/5090))

- *(knowledge)* Degrade /connectors/health on Redis failure + skip corrupted records (#5054 #5055) (#5088) ([#5088](https://github.com/mrveiss/AutoBot-AI/pull/5088))

- *(llm)* Export OpenRouter and NousPortal providers from llm_providers (#5017)

- *(ansible)* Install Playwright browsers to shared PLAYWRIGHT_BROWSERS_PATH accessible to service user (#4662)

- *(sync-queue)* Priority ordering, atomic claim, path dedup (#5078 #5079 #5080)

- *(media)* Add circuit breaker, pooled session, and correct title parsing to Jina Reader fast-path (#5022)

- *(rag)* Gate /rag/benchmark/run behind admin permission + modernize asyncio calls (#5018)

- *(knowledge)* Remove dead Response-property reads in useKnowledgeBase (#5012)

- *(media)* SSRF defense in Jina Reader fast-path — resolve hostnames and reject private IPs (#5015)

- *(mobile)* Make Dashboard, Agents, Knowledge, Settings views responsive at ≤768px (#4445)

- *(media)* Add pytest.importorskip guard for bs4 in pipeline_test.py (#4533)

- *(nav)* Remove redundant admin v-if and overflow-hidden from desktop nav container

- *(nav)* Measure real dropdown width for edge clamping; only restore focus on keyboard dismiss

- *(nav)* NavOverflowMenu viewport clamp, resize listener, focus management, a11y improvements

- *(nav)* Add Escape key handler on NavOverflowMenu dropdown container for keyboard accessibility

- *(nav)* Correct gap arithmetic and add itemCount watch in useNavOverflow

- *(i18n)* Add 81 missing translation keys to en.json (#4982)

- *(i18n)* Add 4 missing nav error keys to 10 non-English locale files (#4965)

- *(api)* Register user_management router in feature_routers.py

- *(ansible/install)* Fix install failures on fresh installs (#4571) ([#4571](https://github.com/mrveiss/AutoBot-AI/pull/4571))

- *(ui)* Add missing ARIA roles and labels to BaseModal, DataTable, HostSelectionDialog (#4806)

- *(agent_loop)* Bridge APPROVAL_REQUIRED events to LiveEventManager for frontend dialog (#4959)

- *(rag)* Guard metadata None dereference and clamp hybrid_score to [0,1] in _deduplicate_and_rank (#4939 #4943)

- *(knowledge)* Set _running=True during loop execution so re-init guard is effective (#4937)

- *(scheduler)* Normalize day-7 in range-step tokens like '1-7/2' in _normalize_dow_field (#4944)

- *(mesh)* Correct graspologic ImportError log message — no restart needed after #4924 (#4936)

- *(knowledge)* Propagate dep_error from extractors so missing tree-sitter is counted as failed not skipped (#4938)

- *(mesh)* Store community_cluster_task on app.state and cancel on shutdown (#4946)

- *(infrastructure)* Use os.environ.get() instead of unexpanded shell variable in sys.path.append (#4945)

- *(frontend)* Suppress TS2591 on lazy require() calls in submitApprovalDecision (#4952)

- *(frontend)* Wire tool approval dialog to POST /api/agent-terminal/tools/approve/{approval_id} (#4952)

- *(rag)* Remove unused call import in rag_service_mesh_test (#4765)

- *(rag)* Store mesh components on app.state; build per-instance NeuralMeshRetriever in RAGService.initialize() (#4765)

- *(rag)* Cache synthesis_schema singleton in _get_kb_synthesis_context (#4654)

- *(layout,nav)* Restore chat input layout fixes and /desktop removal lost in merge

- *(knowledge)* O(1) ancestor lookup in LineageService via get_by_run_id (#4788)

- *(rag)* Memoize hash cache in _filter_stale_chunks with 60s TTL (#4723) ([#4951](https://github.com/mrveiss/AutoBot-AI/pull/4951))

- *(rag)* Memoize hash cache in _filter_stale_chunks with 60s TTL (#4723)

- *(knowledge)* Use asyncio.Lock to prevent hash cache write race in CodeIndexer (#4895) ([#4940](https://github.com/mrveiss/AutoBot-AI/pull/4940))

- *(knowledge)* Use asyncio.Lock to prevent hash cache write race in CodeIndexer (#4895)

- *(knowledge)* Move /index/code to background task with status polling (#4912) ([#4934](https://github.com/mrveiss/AutoBot-AI/pull/4934))

- *(knowledge)* Move /index/code to background task with status polling (#4912)

- *(chat)* Rename mislabeled Overseer toggle label from 'Explain' to 'Overseer'

- *(i18n)* Add missing nav.applicationError/unexpectedError/loadingTimeout keys

- *(cli,browser)* Correct config merge and remove task_id filter in approval subscribe

- *(cli,kb,browser)* Wire approval pub/sub, KB categories, WebResearcher init

- *(knowledge)* Guard against empty-string content in _split_and_embed (#4921) (#4933) ([#4933](https://github.com/mrveiss/AutoBot-AI/pull/4933))

- *(mesh)* Retry graspologic import with 24h backoff instead of permanent exit (#4924)

- *(mesh)* Downgrade graspologic ImportError log from CRITICAL to WARNING (#4923)

- *(knowledge)* Replace string startswith path check with Path.is_relative_to() (#4925)

- *(knowledge)* Make POST /index/code non-blocking via background task (#4912) (#4932) ([#4932](https://github.com/mrveiss/AutoBot-AI/pull/4932))

- *(rag)* Apply provenance_adjustment() to hybrid_score in _deduplicate_and_rank (#4914) (#4931) ([#4931](https://github.com/mrveiss/AutoBot-AI/pull/4931))

- *(mesh)* Add 5-minute startup delay before first Leiden clustering run (#4919) (#4930) ([#4930](https://github.com/mrveiss/AutoBot-AI/pull/4930))

- *(scheduler)* Handle range+step expressions in _normalize_dow_field — 1-7 no longer raises ValueError (#4918) (#4927) ([#4927](https://github.com/mrveiss/AutoBot-AI/pull/4927))

- *(knowledge)* CodeIndexer call-graph scope, save_cache mkdir, async upsert+rglob, method test (#4908 #4909 #4910 #4911 #4913) (#4926) ([#4926](https://github.com/mrveiss/AutoBot-AI/pull/4926))

- *(knowledge)* TTL on pending_approval Redis key, POST /loop/reject endpoint, _running guard in re-init (#4915 #4916 #4917)

- *(knowledge)* Floor regression analyze score at _MIN_SCORE_DELTA not 0.0 (#4794)

- *(knowledge)* Surface tree-sitter ImportError to /index/code caller (#4898)

- *(mesh)* Raise ImportError from cluster_graph so loop exits on missing graspologic (#4896)

- *(knowledge)* Validate root_dir path in /index/code to prevent traversal (#4894)

- *(testing)* Replace hardcoded HookPoint count with enum-driven config coverage check (#4887)

- *(scheduler)* Normalize cron 7=Sunday in _parse_cron_field (#4888)

- *(ci)* Fix ServiceURLs string literals — add f-prefix to all broken URL interpolations (#4305)

- *(knowledge)* Floor analyze score at 0 so failed experiments produce lessons (#4794)

- *(knowledge)* Replace single-level oversized chunk split with recursive retry up to depth 4 (#4702)

- *(scheduler)* Normalize cron 7=Sunday in _parse_cron_field (#4888) (#4893) ([#4893](https://github.com/mrveiss/AutoBot-AI/pull/4893))

- *(testing)* Replace hardcoded HookPoint count with enum-driven config coverage check (#4887) (#4892) ([#4892](https://github.com/mrveiss/AutoBot-AI/pull/4892))

- *(knowledge)* Persist _pending_approval to Redis to survive server restart (#4792) (#4886) ([#4886](https://github.com/mrveiss/AutoBot-AI/pull/4886))

- *(knowledge)* Guard get_loop_orchestrator() against None llm_service race (#4791) (#4885) ([#4885](https://github.com/mrveiss/AutoBot-AI/pull/4885))

- *(knowledge)* CodeIndexer cache path, async index_file, node ID collision (#4851 #4852 #4853) (#4884) ([#4884](https://github.com/mrveiss/AutoBot-AI/pull/4884))

- *(provisioning)* Add creates guard to Playwright install — skip if already installed (#4855) (#4882) ([#4882](https://github.com/mrveiss/AutoBot-AI/pull/4882))

- *(middleware)* Apply body size check before exemption check — /save was unguarded (#4865) (#4881) ([#4881](https://github.com/mrveiss/AutoBot-AI/pull/4881))

- *(scheduler)* Cron day-of-week standard convention — 0=Sunday not 0=Monday (#4863) (#4880) ([#4880](https://github.com/mrveiss/AutoBot-AI/pull/4880))

- *(agents)* Correct orchestrator source_file path in agent_config.py (#4867) (#4876) ([#4876](https://github.com/mrveiss/AutoBot-AI/pull/4876))

- *(ui)* Add getSystemStatusAriaLabel to App.vue setup() return (#4862) (#4868) ([#4868](https://github.com/mrveiss/AutoBot-AI/pull/4868))

- *(knowledge)* Pipeline xadd+hset in log_run() to prevent partial write (#4873) (#4878) ([#4878](https://github.com/mrveiss/AutoBot-AI/pull/4878))

- *(testing)* Rename test_hash_none_vs_empty_string_differ — tests no-args not None (#4875) (#4877) ([#4877](https://github.com/mrveiss/AutoBot-AI/pull/4877))

- *(config)* Remove unused ModelManager import from agent_config.py (#4872) (#4874) ([#4874](https://github.com/mrveiss/AutoBot-AI/pull/4874))

- *(ui)* Add getSystemStatusAriaLabel to App.vue setup() return (#4862) (#4866) ([#4866](https://github.com/mrveiss/AutoBot-AI/pull/4866))

- *(provisioning)* Complete agent model config — all 15 agents now have PROVIDER/ENDPOINT/MODEL (#4854)

- *(mesh)* Add fetch_edges + promote_to_anchor forwarding methods to MeshDBAdapter (#4837)

- *(knowledge)* Extend _cron_matches_now to evaluate day/month/weekday fields (#4793)

- *(ui)* Fix 3 remaining accessibility gaps — toast icon aria-hidden, status dot aria-hidden, aria-label anti-pattern (#4821)

- *(testing)* Replace deprecated get_event_loop() in test_first_turn_priming.py (#4848)

- *(agent_loop)* Resolve _compute_tool_call_hash type collision and _make_tool None gap (#4847)

- *(agent_loop)* Set _halted_on_repetition=True in _execute_tools on repetition halt (#4846)

- *(provisioning)* Four out-of-box gaps — Playwright, AI Stack models, /save injection, SLM TLS

- *(i18n)* Translate operations.view.* keys into 10 non-English locales (#4825)

- *(testing)* Update stale lambda docstrings in test_mmr_diversity.py (#4828)

- *(mesh)* Remove unused networkx import in _split_community (#4820)

- *(rag)* Throttle SessionAdaptiveReranker eviction to once per 60s (#4827) (#4831) ([#4831](https://github.com/mrveiss/AutoBot-AI/pull/4831))

- *(testing)* Update stale lambda docstrings in test_mmr_diversity.py (#4828) (#4830) ([#4830](https://github.com/mrveiss/AutoBot-AI/pull/4830))

- *(knowledge)* Cap AutonomousLoopOrchestrator._history at 100 entries using deque (#4795) (#4824) ([#4824](https://github.com/mrveiss/AutoBot-AI/pull/4824))

- *(testing)* Mock CrossEncoder availability in test_mmr_diversity (#4786) (#4823) ([#4823](https://github.com/mrveiss/AutoBot-AI/pull/4823))

- *(rag)* Add TTL eviction to SessionAdaptiveReranker (#4787) (#4822) ([#4822](https://github.com/mrveiss/AutoBot-AI/pull/4822))

- *(desktop)* Use correct i18n key desktop.contextPanel.title for toggle button (#4812) (#4814) ([#4814](https://github.com/mrveiss/AutoBot-AI/pull/4814))

- *(ui)* Accessibility & interaction — focus rings, touch targets, ARIA labels, Escape key (#4803) (#4804) ([#4804](https://github.com/mrveiss/AutoBot-AI/pull/4804))

- *(testing)* Update test_causal_reasoning.py to use llama_index stubs instead of xfail (#4749) (#4808) ([#4808](https://github.com/mrveiss/AutoBot-AI/pull/4808))

- *(testing)* Update test_synthesize_docs_happy_path to account for AnalyzerService LLM calls (#4785) (#4807) ([#4807](https://github.com/mrveiss/AutoBot-AI/pull/4807))

- *(frontend)* Add missing operations.view.* i18n keys to all 11 locales (#4801) (#4802) ([#4802](https://github.com/mrveiss/AutoBot-AI/pull/4802))

- *(mcp)* Update knowledge-base-mcp requires-python to >=3.12 (#4719) (#4800) ([#4800](https://github.com/mrveiss/AutoBot-AI/pull/4800))

- *(backend)* Update startup_validator.py minimum Python version check from 3.8 to 3.12 (#4718) (#4799) ([#4799](https://github.com/mrveiss/AutoBot-AI/pull/4799))

- *(testing)* Update test_total_hook_count_increased expected HookPoint count to match current enum (#4740) (#4798) ([#4798](https://github.com/mrveiss/AutoBot-AI/pull/4798))

- *(testing)* Use timezone-aware datetime.now(timezone.utc) in TestIsTaskStale (#4698) (#4797) ([#4797](https://github.com/mrveiss/AutoBot-AI/pull/4797))

- *(backend)* Remove duplicate api.user_management router registration from feature_routers.py (#4708) (#4796) ([#4796](https://github.com/mrveiss/AutoBot-AI/pull/4796))

- *(rag)* Remove duplicate register_shared_mesh_retriever import in lifespan.py (#4766) (#4790) ([#4790](https://github.com/mrveiss/AutoBot-AI/pull/4790))

- *(frontend)* Add /desktop nav entry to App.vue navItems (#4778) (#4789) ([#4789](https://github.com/mrveiss/AutoBot-AI/pull/4789))

- *(rag)* Add enable_rlm_refinement and enable_session_adaptive_reranking to RAGConfig.to_dict() (#4725) (#4783) ([#4783](https://github.com/mrveiss/AutoBot-AI/pull/4783))

- *(frontend)* Add /operations nav entry and nav.operations i18n key (#4270) (#4780) ([#4780](https://github.com/mrveiss/AutoBot-AI/pull/4780))

- *(slm-frontend)* CoLocatedApiUrlGuard now clarifies it only guards builds, not vite dev server (#4652) (#4775) ([#4775](https://github.com/mrveiss/AutoBot-AI/pull/4775))

- *(frontend)* Add @types/three and remove @ts-ignore in KnowledgeGraph3D.vue (#4437) (#4764) ([#4764](https://github.com/mrveiss/AutoBot-AI/pull/4764))

- *(rag)* Wire NeuralMeshRetriever into all RAGService instances, not just GraphRAGService (#4757) (#4763) ([#4763](https://github.com/mrveiss/AutoBot-AI/pull/4763))

- *(frontend)* Resolve TerminalService.ts TS2352 unsafe cast to SessionInfo[] (#4701) (#4756) ([#4756](https://github.com/mrveiss/AutoBot-AI/pull/4756))

- *(frontend)* Resolve CacheService.ts TS2352 unsafe Window cast (#4700) (#4755) ([#4755](https://github.com/mrveiss/AutoBot-AI/pull/4755))

- *(frontend)* Resolve App.vue TS2322 SVG fill-rule and Booleanish errors (#4699) (#4754) ([#4754](https://github.com/mrveiss/AutoBot-AI/pull/4754))

- *(rag)* Correct _hybrid_search closure — remove erroneous tuple unpack (#4724) (#4753) ([#4753](https://github.com/mrveiss/AutoBot-AI/pull/4753))

- *(merge)* Apply #4677 MAP-Elites + #4678 AnalyzerService with conflict resolution

- *(knowledge)* Wire SynthesisProvenanceLog.log_run into KBSynthesizer._synthesize_cluster (#4656)

- *(testing)* Fix import path for property_graph in test_property_graph.py (#4730)

- *(testing)* Fix import of think_causally in test_causal_reasoning.py (#4729)

- *(testing)* Lazy-load BROWSER_TOOL_NAMES in tool_registry to break circular import (#4557)

- *(usage)* Replace redis.keys() with async scan_iter in get_all_user_costs, get_all_agent_costs, _fetch_model_costs (#4443)

- *(rag)* Call _filter_stale_chunks() in _fallback_basic_search — stale paths were returned on fallback path (#4721)

- *(testing)* Patch get_async_redis_client in TestStoreFeedbackInStream — was patching non-existent get_redis_client (#4720)

- *(backend)* Trust self-signed cert for internal WebSocket connections (#4664)

- *(deployment)* Add missing AUTOBOT_*_ENDPOINT env vars to agent service config (#4661)

- *(rag)* Remove dead NeuralMeshRetriever injection gate from RAGService (#4686)

- *(knowledge)* Validate synthesis_schema source paths on load — log warning for missing paths (#4695)

- *(rag)* Validate source paths on retrieved chunks — log and filter stale paths (#4689)

- *(knowledge)* Pass llm_service to DocIndexerService so KB synthesis runs (#4655)

- *(rag)* Wire advanced_search_with_refinement into RAGService (#4696)

- *(rag)* Wire expanded_queries into _retrieve_hybrid_results (#4685)

- *(tools)* Replace hardcoded _BUILTIN_TOOL_SCHEMAS with imported constants (#4561)

- *(knowledge)* Log oversized chunk errors explicitly instead of silent drop (#4665)

- *(npu-worker)* Log NPU unavailable warning once at startup, not per-request (#4666)

- *(tts-worker)* Migrate FastAPI on_event to lifespan handler (#4667)

- *(drift-checker)* Update compute_drift docstring after total_compared rename (#4653)

- *(chat)* Distinguish API error from missing data in loadEssentialChatData (#4537)

- *(analytics)* Declare realTimeEnabled in CodebaseOverviewPanel Props (#4546)

- *(analytics)* Add missing 'components' field to HealthScore interface (#4545)

- *(analytics)* Type v-for idx as number in AdvancedAnalytics (#4544)

- *(chat)* Use createNewChat return value in pushLocalOnlySessions (#4536)

- *(knowledge)* Remove incorrect await on ChromaDB Collection objects (#4663)

- *(orchestrator)* Add missing LongTermMemoryManager.initialize() call (#4660)

- *(frontend)* Tokenize remaining multi-value and non-standard border-radius values (#4638) (#4648) ([#4648](https://github.com/mrveiss/AutoBot-AI/pull/4648))

- *(frontend)* Replace hardcoded border-radius in chart tooltip JS strings with design tokens (#4637) (#4647) ([#4647](https://github.com/mrveiss/AutoBot-AI/pull/4647))

- *(frontend)* Replace hardcoded inline style CSS values with design tokens (#4636) (#4646) ([#4646](https://github.com/mrveiss/AutoBot-AI/pull/4646))

- *(slm-frontend)* CoLocatedApiUrlGuard throws instead of warn to abort broken builds (#4632) (#4645) ([#4645](https://github.com/mrveiss/AutoBot-AI/pull/4645))

- *(ansible)* Replace hardcoded UFW port cleanup with playwright_ports_legacy list (#4633) (#4644) ([#4644](https://github.com/mrveiss/AutoBot-AI/pull/4644))

- *(drift-checker)* Exclude expected-drift paths from total_compared count (#4631) (#4643) ([#4643](https://github.com/mrveiss/AutoBot-AI/pull/4643))

- *(knowledge)* Substitute {documents} placeholder in synthesis_schema prompt templates (#4634) (#4641) ([#4641](https://github.com/mrveiss/AutoBot-AI/pull/4641))

- *(deps)* Add autobot-slm-frontend to dependabot.yml (#4616) (#4630) ([#4630](https://github.com/mrveiss/AutoBot-AI/pull/4630))

- *(knowledge)* Migrate knowledge_models.py from Pydantic V1 @validator to V2 @field_validator (#4615) (#4628) ([#4628](https://github.com/mrveiss/AutoBot-AI/pull/4628))

- *(deps)* Add autobot-slm-frontend to dependabot.yml (#4616) (#4625) ([#4625](https://github.com/mrveiss/AutoBot-AI/pull/4625))

- *(knowledge)* Migrate knowledge_models.py from Pydantic V1 @validator to V2 @field_validator (#4615) (#4624) ([#4624](https://github.com/mrveiss/AutoBot-AI/pull/4624))

- *(ansible)* Remove stale UFW port 3000 rule after playwright_port change to 9001 (#4609) (#4621) ([#4621](https://github.com/mrveiss/AutoBot-AI/pull/4621))

- *(slm-frontend)* Warn when VITE_API_URL unset in co-located build (#4603) (#4620) ([#4620](https://github.com/mrveiss/AutoBot-AI/pull/4620))

- *(slm)* Exclude deployment-generated files from drift detector report (#4610) (#4622) ([#4622](https://github.com/mrveiss/AutoBot-AI/pull/4622))

- *(a2a)* Add logger.debug on JWT sub decode failure in _decode_jwt_sub (#4607) (#4619) ([#4619](https://github.com/mrveiss/AutoBot-AI/pull/4619))

- *(a2a)* Slide a2a:tasks set TTL in get_task() alongside task and audit keys (#4604) (#4617) ([#4617](https://github.com/mrveiss/AutoBot-AI/pull/4617))

- *(a2a)* Evict stale IP entries from _rate_buckets to prevent memory leak (#4595) (#4602) ([#4602](https://github.com/mrveiss/AutoBot-AI/pull/4602))

- *(a2a)* Expire a2a:tasks tracking set to prevent unbounded growth (#4594) (#4601) ([#4601](https://github.com/mrveiss/AutoBot-AI/pull/4601))

- *(a2a)* Eliminate double list_tasks() scan in task_stats() (#4593) (#4600) ([#4600](https://github.com/mrveiss/AutoBot-AI/pull/4600))

- *(a11y)* Add focus-visible outlines for keyboard navigation (#4592) (#4598) ([#4598](https://github.com/mrveiss/AutoBot-AI/pull/4598))

- *(frontend)* Replace hardcoded z-index values with design tokens (#4591) (#4597) ([#4597](https://github.com/mrveiss/AutoBot-AI/pull/4597))

- *(frontend)* Replace hardcoded box-shadow values with design tokens (#4560) (#4599) ([#4599](https://github.com/mrveiss/AutoBot-AI/pull/4599))

- *(chat)* Keep ChatInput fixed at bottom — move scroll to messages container

- *(nginx)* Add no-cache headers for /slm/index.html to prevent stale bundle caching

- *(slm-frontend)* Correct code source defaults to /opt/autobot/code_source + Dev_new_gui

- *(frontend)* Replace hardcoded box-shadow values with design tokens (#4560)

- *(frontend)* Replace hardcoded colors with design tokens in status, secrets, terminal settings, voice panels (#4578) (#4584) ([#4584](https://github.com/mrveiss/AutoBot-AI/pull/4584))

- *(terminal)* Replace hardcoded palette colors with design tokens in Terminal (#4577) (#4583) ([#4583](https://github.com/mrveiss/AutoBot-AI/pull/4583))

- *(frontend)* Replace hardcoded hex colors with design tokens in HeartbeatPanel, WorkflowTemplateGallery, ProfileModal (#4576) (#4582) ([#4582](https://github.com/mrveiss/AutoBot-AI/pull/4582))

- *(ui)* Replace hardcoded palette colors with design tokens in TouchFriendlyButton (#4575) (#4581) ([#4581](https://github.com/mrveiss/AutoBot-AI/pull/4581))

- *(chat)* Replace hardcoded palette colors with design tokens in overseer messages (#4574) (#4579) ([#4579](https://github.com/mrveiss/AutoBot-AI/pull/4579))

- *(chat)* Replace hardcoded palette colors with design tokens in message components (#4573) (#4580) ([#4580](https://github.com/mrveiss/AutoBot-AI/pull/4580))

- *(slm-frontend)* Fix broken beforeEnter guard on /maintenance/updates route

- *(chat)* Add missing context field to LLMIterationContext (#4264)

- *(ansible)* Change playwright_port from 3000 to 9001 to avoid Grafana conflict

- *(install)* Fix unit name parsing for failed/orphaned autobot-* services

- *(frontend)* Replace all hardcoded Tailwind palette colors with design tokens

- *(install)* Stop all autobot-* units before removing unit files in --uninstall

- *(ansible)* Fix PostgreSQL readiness check and duplicate task keys

- *(frontend)* Fix blank icons in ActivityFeed and correct z-index token values

- *(a2a)* Raise a2a_task_ttl default from 60s to 3600s for Redis persistence (#4551) (#4553) ([#4553](https://github.com/mrveiss/AutoBot-AI/pull/4553))

- *(tools)* Validate arguments for direct-dispatch tools, not just MCP (#4529) (#4552) ([#4552](https://github.com/mrveiss/AutoBot-AI/pull/4552))

- *(agent)* Inject first_turn_note into LLM user message on first turn (#4528) (#4550) ([#4550](https://github.com/mrveiss/AutoBot-AI/pull/4550))

- *(frontend)* Fix 3 hardcoded color violations breaking dark/light theme

- *(llm)* Ollama stream uses correct endpoint; vllm uses correct LLMResponse fields (#4525, #4527)

- *(ci)* Remove stale gitlink for .claude/worktrees/issue-4347

- *(kb)* Add process_query to KBLibrarianAgent and runtime config attrs (#4531) (#4542) ([#4542](https://github.com/mrveiss/AutoBot-AI/pull/4542))

- *(a2a)* Correct routing for research and knowledge_retrieval agents (#4530) (#4541) ([#4541](https://github.com/mrveiss/AutoBot-AI/pull/4541))

- *(agents)* Extract LLMResponse.content in system_commands agent (#4532) (#4540) ([#4540](https://github.com/mrveiss/AutoBot-AI/pull/4540))

- *(analytics)* Add missing useAggregationMemo imports (#4538) (#4539) ([#4539](https://github.com/mrveiss/AutoBot-AI/pull/4539))

- *(frontend)* Eliminate hardcoded colors and undefined CSS vars across components

- *(llm)* Opt-in chat_template only; ollama uses generate endpoint for pre-rendered prompts (#4524, #4525)

- *(lint)* Add missing blank line after _build_skill_context in prompt_manager (E305)

- *(theme)* Replace hardcoded colors with CSS design-token variables (#4527)

- *(llm)* Wire chat_template_loader into ollama and vllm providers (#4518) (#4523) ([#4523](https://github.com/mrveiss/AutoBot-AI/pull/4523))

- *(truncation)* Optimize large file handling for 10MB+ files (#4397) (#4513) ([#4513](https://github.com/mrveiss/AutoBot-AI/pull/4513))

- *(truncation)* Add binary file detection and safe handling (#4396) (#4512) ([#4512](https://github.com/mrveiss/AutoBot-AI/pull/4512))

- *(a2a)* Replace in-process task store with Redis for worker isolation (#4502) (#4508) ([#4508](https://github.com/mrveiss/AutoBot-AI/pull/4508))

- *(a2a)* Use attribute access on LLMResponse in task_executor (#4501) (#4507) ([#4507](https://github.com/mrveiss/AutoBot-AI/pull/4507))

- *(truncation)* Preserve JSON/XML structure integrity on truncation (#4395) (#4511) ([#4511](https://github.com/mrveiss/AutoBot-AI/pull/4511))

- *(frontend)* Register wired components in index files (#4323) (#4517) ([#4517](https://github.com/mrveiss/AutoBot-AI/pull/4517))

- *(frontend)* Replace generic type params with 'as Type' casts to survive linter (#4425) (#4504) ([#4504](https://github.com/mrveiss/AutoBot-AI/pull/4504))

- *(knowledge)* Add missing web/internet platform tool YAML definitions (#4428) (#4505) ([#4505](https://github.com/mrveiss/AutoBot-AI/pull/4505))

- *(frontend)* Add -p tsconfig.app.json to vue-tsc calls so TS errors are caught (#4424) (#4506) ([#4506](https://github.com/mrveiss/AutoBot-AI/pull/4506))

- *(chat)* Push local-only sessions to backend in bidirectional sync (#4431) (#4493) ([#4493](https://github.com/mrveiss/AutoBot-AI/pull/4493))

- *(analytics)* Update usePrometheusMetrics to use useApi() response format (#4426) (#4494) ([#4494](https://github.com/mrveiss/AutoBot-AI/pull/4494))

- *(tools)* Add ast.literal_eval fallback for malformed LLM JSON in tool calls (#4483) (#4497) ([#4497](https://github.com/mrveiss/AutoBot-AI/pull/4497))

- *(agents)* Wire SlackNotificationIntegration into agent loop (#4308) (#4480) ([#4480](https://github.com/mrveiss/AutoBot-AI/pull/4480))

- *(frontend)* Distinguish errors from empty responses in batch API (#4353) (#4479) ([#4479](https://github.com/mrveiss/AutoBot-AI/pull/4479))

- *(usage)* Add nav link, fix CSV auth, and use useApi() in UsageView (#4465, #4466, #4467) (#4478) ([#4478](https://github.com/mrveiss/AutoBot-AI/pull/4478))

- *(workers)* Add __all__ exports to new worker modules (#4322) (#4477) ([#4477](https://github.com/mrveiss/AutoBot-AI/pull/4477))

- *(frontend)* Restore generic type safety in useVirtualList (#4434) (#4475) ([#4475](https://github.com/mrveiss/AutoBot-AI/pull/4475))

- *(doc_indexer)* Handle circular symlinks in _compute_file_hash and _normalize_path (#4433) (#4474) ([#4474](https://github.com/mrveiss/AutoBot-AI/pull/4474))

- *(media)* Enable TLS certificate verification in LinkPipeline (#4427) (#4471) ([#4471](https://github.com/mrveiss/AutoBot-AI/pull/4471))

- *(lint)* Fix blank line violations in usage.py (#1807) (#4468) ([#4468](https://github.com/mrveiss/AutoBot-AI/pull/4468))

- *(lint)* Fix remaining E501 in ValueError message (#1807)

- *(lint)* Remove unused import and fix E501 lines in llm_cost_tracker (#1807)

- *(lint)* Remove unused import and fix E501 violations in llm_cost_tracker.py (#4450) ([#4450](https://github.com/mrveiss/AutoBot-AI/pull/4450))

- *(typescript)* Resolve code analysis type errors (#4363)

- *(typescript)* Resolve browser automation and dev tools type errors (#4362)

- *(analytics)* Add missing useGroupingMemo import to CodeSmells, Declarations, CodeReviewDashboard

- *(truncation)* Ensure UTF-8 multi-byte character boundary safety (#4394) (#4418) ([#4418](https://github.com/mrveiss/AutoBot-AI/pull/4418))

- *(doc_indexer)* Handle hash cache edge cases for symlinks, permissions, path normalization (#4382) (#4416) ([#4416](https://github.com/mrveiss/AutoBot-AI/pull/4416))

- *(typescript)* Resolve collaboration and secrets management type errors (#4361) (#4409) ([#4409](https://github.com/mrveiss/AutoBot-AI/pull/4409))

- *(typescript)* Resolve knowledge UI component type errors (#4359) (#4408) ([#4408](https://github.com/mrveiss/AutoBot-AI/pull/4408))

- *(typescript)* Resolve analytics and Prometheus metrics type errors (#4358) (#4407) ([#4407](https://github.com/mrveiss/AutoBot-AI/pull/4407))

- *(discovery)* Correct scheduler path and skill_management exports (#4398 #4399) (#4406) ([#4406](https://github.com/mrveiss/AutoBot-AI/pull/4406))

- *(cron_scheduler)* Correct nested path reference (#4398) (#4404) ([#4404](https://github.com/mrveiss/AutoBot-AI/pull/4404))

- *(skill_management)* Add missing __init__.py exports (#4399) (#4403) ([#4403](https://github.com/mrveiss/AutoBot-AI/pull/4403))

- *(knowledge)* Force full indexing when collection empty despite cache (#4350) (#4377) ([#4377](https://github.com/mrveiss/AutoBot-AI/pull/4377))

- *(knowledge)* Force full indexing when collection empty despite cache (#4350)

- *(api)* Return explicit error indicator for failed batch API (#4354)

- *(api)* Return explicit error indicator for failed batch API (#4354)

- *(frontend)* Cleanup promises on ChatInterface unmount (#4355) (#4368) ([#4368](https://github.com/mrveiss/AutoBot-AI/pull/4368))

- *(typescript)* Resolve 56 errors in useKnowledgeBase.ts (#4357)

- *(typescript)* Resolve 47+ errors in chat components (#4360)

- Resolve TypeScript errors in frontend components (#4328)

- *(frontend)* Correct BaseButton import path in CodeEvolutionTimeline (#4349)

- *(frontend)* Prevent chat sessions loss on empty backend response (#4328) (#4351) ([#4351](https://github.com/mrveiss/AutoBot-AI/pull/4351))

- *(knowledge)* Fix NameError in TaskStatusManager static methods

- *(knowledge)* Fix all async background task executions in knowledge population

- *(frontend)* Correct invalid TailwindCSS utility classes in build

- *(frontend)* Set VITE_BACKEND_HOST env var and support HEAD on health endpoint

- Wire RelationshipViewer component in EntityDetail panel (#4272)

- *(components)* Wire orphaned component CausalChainViewer (#4274)

- *(components)* Wire orphaned component TouchFriendlyButton (#4275)

- *(components)* Wire orphaned component OperationFilters (#4277)

- *(components)* Wire orphaned component TerminalHeader (#4281)

- *(components)* Wire orphaned component TerminalHeader (#4281)

- *(terminal)* Wire TerminalStatusBar component in Terminal view (#4285) (#4320) ([#4320](https://github.com/mrveiss/AutoBot-AI/pull/4320))

- *(devops)* Systemd-created log files have wrong ownership (#4309) (#4318) ([#4318](https://github.com/mrveiss/AutoBot-AI/pull/4318))

- *(ci)* Verify all workflows use supported action versions (#4293) (#4314) ([#4314](https://github.com/mrveiss/AutoBot-AI/pull/4314))

- *(branching)* Add target branch guard to prevent commits on main (#4113) (#4313) ([#4313](https://github.com/mrveiss/AutoBot-AI/pull/4313))

- *(provisioning)* Replace timeout-based health check with retry-based approach

- *(provisioning)* Increase backend health check timeout to 180s

- *(devops)* Ensure log directory/files have correct ownership in provision playbook

- Resolve metaclass conflict in SQLAlchemy models (#4300)

- *(slack)* Add comprehensive error handling for API operations (#4161) ([#4306](https://github.com/mrveiss/AutoBot-AI/pull/4306))

- *(ci)* Update deprecated action versions from v6/v7 to current stable v4 (#4296) ([#4301](https://github.com/mrveiss/AutoBot-AI/pull/4301))

- *(config)* Update Black line-length from 88 to 120 in .claude/settings.json (#4298) ([#4303](https://github.com/mrveiss/AutoBot-AI/pull/4303))

- *(ci)* Fix phase_validation_system.py broken imports (#4297) ([#4302](https://github.com/mrveiss/AutoBot-AI/pull/4302))

- *(test)* Resolve merge conflict in executor_artifacts_test.py

- *(agent-loop)* Guard tool args, sentinel halt, propagate error to LLM (#3859 #3862 #3868 #3874 #3877) ([#4299](https://github.com/mrveiss/AutoBot-AI/pull/4299))

- Remove unresolved merge conflict marker from executor_artifacts_test.py

- *(tests)* ParallelToolExecutor test fixture - fix JSON serialization in artifact test (#4226) (#4243) ([#4243](https://github.com/mrveiss/AutoBot-AI/pull/4243))

- *(ci)* Resolve Phase Validation workflow action versions and script paths (#4125)

- *(ci)* Exclude test files from AWS key grep to prevent false positives (#4127) (#4238) ([#4238](https://github.com/mrveiss/AutoBot-AI/pull/4238))

- Complete PR #4213 implementation - add missing ExperimentTask and build_task_inference_params (#3259)

- *(slack)* Add comprehensive error handling to API calls (#4161)

- *(tests)* Add missing tool_dispatcher argument to ParallelToolExecutor fixture (#4226)

- *(security)* Move service auth enforcement tests to correct location (#3394) (#4228) ([#4228](https://github.com/mrveiss/AutoBot-AI/pull/4228))

- Add error handling for diff generation (#4172) (#4190) ([#4190](https://github.com/mrveiss/AutoBot-AI/pull/4190))

- Add size limits to artifact output (#4173) (#4191) ([#4191](https://github.com/mrveiss/AutoBot-AI/pull/4191))

- Standardize tool result format parsing (#4174) (#4192) ([#4192](https://github.com/mrveiss/AutoBot-AI/pull/4192))

- *(ci)* Resolve flake8 violations (#4158) (#4177) ([#4177](https://github.com/mrveiss/AutoBot-AI/pull/4177))

- *(events)* Validate artifact serialization (#4178) (#4199) ([#4199](https://github.com/mrveiss/AutoBot-AI/pull/4199))

- *(llm)* Remove unused imports in model_param_registry_test (#3257) (#4205) ([#4205](https://github.com/mrveiss/AutoBot-AI/pull/4205))

- *(ci)* Add required env-file flag to docker compose commands (#4123) (#4220) ([#4220](https://github.com/mrveiss/AutoBot-AI/pull/4220))

- *(install)* Validate critical services exist before Ansible deployment (#4124) (#4134) ([#4134](https://github.com/mrveiss/AutoBot-AI/pull/4134))

- *(ci)* Update Security Scanning workflow action versions (#4127) (#4153) ([#4153](https://github.com/mrveiss/AutoBot-AI/pull/4153))

- *(ci)* Resolve dependency conflicts in CI/CD pipeline (#4126) (#4135) ([#4135](https://github.com/mrveiss/AutoBot-AI/pull/4135))

- *(install)* Validate critical services exist before Ansible deployment (#4124) (#4146) ([#4146](https://github.com/mrveiss/AutoBot-AI/pull/4146))

- *(slm)* Monitor slm-agent.service on all nodes (#4129) (#4133) ([#4133](https://github.com/mrveiss/AutoBot-AI/pull/4133))

- *(slm)* Create slm-admin-ui service for frontend health monitoring (#4120) (#4122) ([#4122](https://github.com/mrveiss/AutoBot-AI/pull/4122))

- *(install)* Distribute autobot-slm-agent in step [3/7] (#4116) (#4121) ([#4121](https://github.com/mrveiss/AutoBot-AI/pull/4121))

- *(knowledge)* Fix TaskStatusManager @classmethod bugs and add tests (#4103)

- *(slm)* Resolve pyopenssl/pysaml2 dependency conflict (#4106)

- *(backend)* Sync docs directory for knowledge base population (#4100)

- *(ansible)* AI Stack systemd services use correct EnvironmentFile path (#4088)

- *(ai-stack)* ChromaDB health check uses correct endpoint

- *(frontend)* Correct ssot-config import in LiveEventService

- *(frontend)* LiveEventService uses wrong host for WebSocket connection

- *(ansible)* ChromaDB host detection for co-located vs distributed deployments

- *(backend)* Add missing get_redis_client import in advanced_cache_manager.py

- *(frontend)* Remove broken pause/resume calls in visibility handler (#3999)

- *(causality)* Resolve 3 critical causal reasoning blocking issues

- *(knowledge)* Inject redis client, fix entity type patterns, key prefix, config model name, UTC datetime (#3384)

- *(infrastructure)* Change Playwright service port from 3000 to 9001 (#4052)

- *(browser)* Resolve Playwright Chromium launch failure (#4060) (#4066) ([#4066](https://github.com/mrveiss/AutoBot-AI/pull/4066))

- *(analytics)* Use vLLM model name in cache key (instead of Ollama default) (#4054) (#4065) ([#4065](https://github.com/mrveiss/AutoBot-AI/pull/4065))

- *(frontend)* Resolve CodebaseAnalytics dashboard rendering gaps (#4063) (#4067) ([#4067](https://github.com/mrveiss/AutoBot-AI/pull/4067))

- *(infrastructure)* Resolve ChromaDB protobuf mismatch and Playwright port conflict

- *(redis)* Await coroutine before ping in KB initialization (#3962) (#4051) ([#4051](https://github.com/mrveiss/AutoBot-AI/pull/4051))

- *(analytics)* Add data validation to all CodeQualityDashboard loaders

- *(analytics)* Validate complexity data structure before accessing properties

- *(frontend)* Remove invalid Tailwind class font-inherit from FileBrowserHeader

- *(perf)* Add request deduplication and debouncing for batch status API (#4006) (#4028) ([#4028](https://github.com/mrveiss/AutoBot-AI/pull/4028))

- *(frontend)* Handle null/undefined score in QualityScoreBadge (#4016) (#4044) ([#4044](https://github.com/mrveiss/AutoBot-AI/pull/4044))

- Lazy-load Cytoscape chart components (#3998) (#4018) ([#4018](https://github.com/mrveiss/AutoBot-AI/pull/4018))

- Memoize filteredSecrets computation with cache (#4000) (#4020) ([#4020](https://github.com/mrveiss/AutoBot-AI/pull/4020))

- Add visibilitychange listener to pause message polling (#3999) (#4021) ([#4021](https://github.com/mrveiss/AutoBot-AI/pull/4021))

- *(perf)* Lazy-load large components and add CSS containment (#4003, #4005) (#4029) ([#4029](https://github.com/mrveiss/AutoBot-AI/pull/4029))

- *(perf)* Add request deduplication and debouncing for batch status API (#4006) (#4026) ([#4026](https://github.com/mrveiss/AutoBot-AI/pull/4026))

- *(perf)* Replace deep watcher with length-based watch on KnowledgeGraph3D (#4004) (#4025) ([#4025](https://github.com/mrveiss/AutoBot-AI/pull/4025))

- *(perf)* Replace deep watcher with individual property watchers on TerminalSettings (#4002) (#4024) ([#4024](https://github.com/mrveiss/AutoBot-AI/pull/4024))

- *(perf)* Replace deep watcher with shallow length watch on TerminalOutput (#4001) (#4023) ([#4023](https://github.com/mrveiss/AutoBot-AI/pull/4023))

- *(perf)* Lazy-load large components and add CSS containment (#4003, #4005)

- *(redis)* Await async Redis client coroutine in KB initialization (#3962) (#4027) ([#4027](https://github.com/mrveiss/AutoBot-AI/pull/4027))

- *(config)* Migrate chat_history/base.py to ssot_config, eliminate double ConfigManager instantiation (#3945) (#4019) ([#4019](https://github.com/mrveiss/AutoBot-AI/pull/4019))

- Prevent toFixed() error on undefined quality_threshold in KnowledgeVerificationQueue

- *(frontend)* Migrate vite config from deprecated esbuildOptions to rolldownOptions (#3967) (#3996) ([#3996](https://github.com/mrveiss/AutoBot-AI/pull/3996))

- Fetch real audit logs from backend API in SecretAuditLog (#3988) (#3991) ([#3991](https://github.com/mrveiss/AutoBot-AI/pull/3991))

- Fetch real secrets from backend API in SecretVault (#3987) (#3995) ([#3995](https://github.com/mrveiss/AutoBot-AI/pull/3995))

- Fetch real participant roles from session API in ParticipantList (#3986) (#3994) ([#3994](https://github.com/mrveiss/AutoBot-AI/pull/3994))

- *(frontend)* Fetch users from API in InviteUserDialog (#3985) (#3992) ([#3992](https://github.com/mrveiss/AutoBot-AI/pull/3992))

- Fetch user/group names from API in ShareKnowledgeDialog (#3984)

- *(kb)* Add ChromaDB service monitoring to health checks and API (#3461)

- *(deps)* Relax protobuf constraint to <7.0.0 for opentelemetry compatibility (#3971)

- *(frontend)* Remove duplicate KnowledgeRepository instance from KnowledgeSearch (#3969)

- *(sec)* Document vanna CVE monitoring (#3445)

- *(deps)* Resolve protobuf version incompatibility with chromadb (#3971)

- Remove non-existent LLMInterface.initialize() calls (#3974)

- Add missing scrollbars to file lists and upload progress

- *(hardening)* Enhance hook to catch single-quoted path literals (#3939) (#3968) ([#3968](https://github.com/mrveiss/AutoBot-AI/pull/3968))

- *(frontend)* Remove duplicate :repository prop in KBSearchResultPanel (#3970) ([#3970](https://github.com/mrveiss/AutoBot-AI/pull/3970))

- *(config)* Add depth limit to deep_merge on non-sync paths (#3931)

- *(security)* Add CodeQL suppression for well-hardened xdotool command execution (#3938)

- *(config)* Add depth limit to deep_merge on non-sync paths (#3931)

- *(redis)* Resolve coroutine handling in KB async Redis initialization (#3962)

- *(deployment)* Add PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python to ChromaDB systemd service

- *(llm)* Use DEFAULT_LLM_MODEL instead of ROUTING_MODEL in think_tool/rlm (#3948) (#3960) ([#3960](https://github.com/mrveiss/AutoBot-AI/pull/3960))

- *(config)* Remove broken UnifiedConfig imports from code_analysis (#3937) (#3959) ([#3959](https://github.com/mrveiss/AutoBot-AI/pull/3959))

- *(hardening)* Expand hardcoding-prevention hook to detect single-quoted literals (#3939)

- *(frontend)* Remove as-any cast and deduplicate KnowledgeRepository in KBSearchResultPanel (#3940)

- *(analytics)* Record correct vLLM model name in chat_completion_optimized (#3943)

- *(config)* Raise _SYNC_MAX_DEPTH to accommodate 6+ level payloads (#3946)

- *(llm)* Use DEFAULT_LLM_MODEL in think_tool and rlm modules (#3948)

- *(frontend)* Remove as-any cast and duplicate KnowledgeRepository in KBSearchResultPanel (#3940)

- *(security)* Path traversal guard on terminal transcript writes (#3164) ([#3942](https://github.com/mrveiss/AutoBot-AI/pull/3942))

- *(security)* Path traversal guard on terminal transcript writes (#3164) (#3941) ([#3941](https://github.com/mrveiss/AutoBot-AI/pull/3941))

- *(security)* Address CodeQL clear-text-storage, logging, and injection alerts (#3205) (#3930) ([#3930](https://github.com/mrveiss/AutoBot-AI/pull/3930))

- *(test)* Add await manager.initialize() to 4 ChatHistoryManager sites in concurrency_safety_test (#3916) (#3927) ([#3927](https://github.com/mrveiss/AutoBot-AI/pull/3927))

- *(agent_loop)* Add default phase_completed to IterationResult — TypeError on every iteration (#3917) ([#3918](https://github.com/mrveiss/AutoBot-AI/pull/3918))

- *(llm)* Cache bypass, empty model_name, unknown session_id, silent adapter errors (#3858 #3860 #3861 #3866) ([#3914](https://github.com/mrveiss/AutoBot-AI/pull/3914))

- *(chat)* ChatHistoryManager.initialize() — implement real async init (#3886) ([#3908](https://github.com/mrveiss/AutoBot-AI/pull/3908))

- *(config)* Settings sync allowlist, depth limit, async file ops + tests (#3881 #3882) ([#3907](https://github.com/mrveiss/AutoBot-AI/pull/3907))

- *(llm)* Fix LLMSettings env parsing SettingsError that blocks test collection (#3843) (#3898) ([#3898](https://github.com/mrveiss/AutoBot-AI/pull/3898))

- *(agent_loop)* Don't add halted tool to executed list; surface error to LLM (#3859 #3862) ([#3903](https://github.com/mrveiss/AutoBot-AI/pull/3903))

- *(config)* Use explicit None checks in startup validation (#3880) (#3897) ([#3897](https://github.com/mrveiss/AutoBot-AI/pull/3897))

- *(agent_loop)* Robust tool-call hash + repetition-halt guard (#3868 #3874 #3877) ([#3899](https://github.com/mrveiss/AutoBot-AI/pull/3899))

- *(ansible)* Deploy permission_rules.yaml to infrastructure config path (#3873) (#3891) ([#3891](https://github.com/mrveiss/AutoBot-AI/pull/3891))

- *(knowledge)* Resolve async Redis client coroutine ping error (#3872) (#3890) ([#3890](https://github.com/mrveiss/AutoBot-AI/pull/3890))

- *(security)* Apply validate_path() to fix path-injection CodeQL alerts (#3164) (#3875) ([#3875](https://github.com/mrveiss/AutoBot-AI/pull/3875))

- *(a2a)* Guard AUTOBOT_A2A_CARD_TTL int() cast against invalid env var (#3824) (#3869) ([#3869](https://github.com/mrveiss/AutoBot-AI/pull/3869))

- *(voice)* Wire VoiceInterface into app.state, guard endpoints with 503 (#3848) (#3867) ([#3867](https://github.com/mrveiss/AutoBot-AI/pull/3867))

- *(chat)* Use ModelConfig.CHAT_NUM_CTX — was referencing wrong class ModelConstants

- *(ansible)* Add notify+flush_handlers to backend role — restart workers on autobot_shared reinstall (#3856)

- *(orchestration)* Guard _save_checkpoint so failures never fail a successful step (#3825) (#3852) ([#3852](https://github.com/mrveiss/AutoBot-AI/pull/3852))

- *(config)* Add alias to AutoBotConfig.path to prevent PATH env var collision (#3851)

- *(chat-workflow)* Remove system_prompt from _build_continuation_prompt to fix double-injection (#3784) (#3791) ([#3791](https://github.com/mrveiss/AutoBot-AI/pull/3791))

- *(ansible)* Inject SLM secrets into standalone deploy extra_vars (#3519) (#3780) ([#3780](https://github.com/mrveiss/AutoBot-AI/pull/3780))

- *(ansible)* Inject SLM secrets into standalone deploy extra_vars (#3773) ([#3773](https://github.com/mrveiss/AutoBot-AI/pull/3773))

- *(backend)* Allow any authenticated user to GET /review/{id} (#3754) (#3772) ([#3772](https://github.com/mrveiss/AutoBot-AI/pull/3772))

- *(chat-workflow)* Route system prompt via Ollama system field; raise num_ctx to 8192 (#3761) (#3765) ([#3765](https://github.com/mrveiss/AutoBot-AI/pull/3765))

- *(frontend)* Clear auto-save interval on ChatController destroy (#3749) (#3766) ([#3766](https://github.com/mrveiss/AutoBot-AI/pull/3766))

- *(config)* Canonicalize browser host env var to AUTOBOT_BROWSER_SERVICE_HOST ([#3764](https://github.com/mrveiss/AutoBot-AI/pull/3764))

- *(monitoring)* Replace hardcoded 172.16.168.25 with $browser_vm_ip variable in Grafana dashboard ([#3763](https://github.com/mrveiss/AutoBot-AI/pull/3763))

- *(config)* Replace hardcoded 172.16.168.* IPs with named placeholders in .env.example ([#3762](https://github.com/mrveiss/AutoBot-AI/pull/3762))

- *(frontend)* Guard loadReview against undefined reviewId (#3755) (#3759) ([#3759](https://github.com/mrveiss/AutoBot-AI/pull/3759))

- *(frontend)* Clear auto-save interval on ChatController destroy ([#3760](https://github.com/mrveiss/AutoBot-AI/pull/3760))

- *(tests)* Handle https→wss protocol upgrade in simple_terminal.e2e_test.py ([#3758](https://github.com/mrveiss/AutoBot-AI/pull/3758))

- *(tests)* Evaluate get_test_backend_url() lazily in TakeoverTestClient (#3747) (#3756) ([#3756](https://github.com/mrveiss/AutoBot-AI/pull/3756))

- *(browser)* Replace hardcoded :3000 with NetworkConstants.BROWSER_SERVICE_PORT in web_crawler.py fallback (#3728) (#3731) ([#3731](https://github.com/mrveiss/AutoBot-AI/pull/3731))

- *(backend)* Remove total timeout from LLM streaming — use connect-only timeout (#3732) (#3737) ([#3737](https://github.com/mrveiss/AutoBot-AI/pull/3737))

- *(tests)* Correct stale src.tool_discovery patch path in tool_discovery_test (#3722) (#3738) ([#3738](https://github.com/mrveiss/AutoBot-AI/pull/3738))

- *(tests)* Update stale src.tool_discovery mock path (#3722) ([#3734](https://github.com/mrveiss/AutoBot-AI/pull/3734))

- *(frontend)* Remove duplicate withSourceId() wrap in Redis health URL (#3714) ([#3715](https://github.com/mrveiss/AutoBot-AI/pull/3715))

- *(ansible)* Idempotent autobot:autobot ownership on Redis dirs (#3396) ([#3721](https://github.com/mrveiss/AutoBot-AI/pull/3721))

- *(backend)* Rate-limit AI Stack connection error logging (#3686) ([#3720](https://github.com/mrveiss/AutoBot-AI/pull/3720))

- *(ansible)* Add post-deploy smoke test to backend role (#3687) ([#3719](https://github.com/mrveiss/AutoBot-AI/pull/3719))

- *(ansible)* AUTOBOT_CHROMADB_HOST fallback uses backend_ai_stack_host (#3541) ([#3717](https://github.com/mrveiss/AutoBot-AI/pull/3717))

- *(frontend)* Remove dead loadReview() — GET /review/{id} has no backend storage (#3701) ([#3713](https://github.com/mrveiss/AutoBot-AI/pull/3713))

- *(frontend)* Use wss:// on HTTPS for CodeQualityDashboard WebSocket connection (#3702) ([#3711](https://github.com/mrveiss/AutoBot-AI/pull/3711))

- *(frontend)* Remove spurious /analytics prefix from code-review pattern preference URLs (#3699) ([#3709](https://github.com/mrveiss/AutoBot-AI/pull/3709))

- *(frontend)* Correct useEvolution base URL from /analytics/evolution to /evolution (#3698) ([#3707](https://github.com/mrveiss/AutoBot-AI/pull/3707))

- *(slm-frontend)* Safe WebSocket URL construction when getBackendUrl() is absolute (#3673) ([#3695](https://github.com/mrveiss/AutoBot-AI/pull/3695))

- *(backend)* Replace bare REDIS_HOST with AUTOBOT_REDIS_HOST in chat_history (no-op — already in #3672) ([#3693](https://github.com/mrveiss/AutoBot-AI/pull/3693))

- *(analytics)* Scope codebase analytics caches and live scans to source_id (#3685) ([#3689](https://github.com/mrveiss/AutoBot-AI/pull/3689))

- *(backend)* Fix REDIS_HOST → AUTOBOT_REDIS_HOST in chat history modules ([#3672](https://github.com/mrveiss/AutoBot-AI/pull/3672))

- *(backend)* Add TTL_24_HOURS to chat_workflow/manager.py import (#3646)

- *(backend)* Default SLM_URL to localhost and deduplicate startup warning (#3655) ([#3667](https://github.com/mrveiss/AutoBot-AI/pull/3667))

- *(ansible)* Guard groups['database'] lookup in deploy-backend-local.yml (#3651) ([#3664](https://github.com/mrveiss/AutoBot-AI/pull/3664))

- *(slm)* Pass auth token to PasswordChangeForm — was always sending empty Bearer

- *(backend)* Guard context_window_manager against list-format llm_models.yaml (#3647)

- *(ansible)* Sync standalone autobot_shared on backend deploy (#3649) ([#3659](https://github.com/mrveiss/AutoBot-AI/pull/3659))

- *(backend)* Normalize naive datetimes from Redis in stats and analytics (#3620) ([#3637](https://github.com/mrveiss/AutoBot-AI/pull/3637))

- *(backend)* Normalize naive datetime from Redis in knowledge_manager (#3618) ([#3636](https://github.com/mrveiss/AutoBot-AI/pull/3636))

- *(backend)* Use local time in is_business_hours and is_weekend (#3619) ([#3635](https://github.com/mrveiss/AutoBot-AI/pull/3635))

- *(backend)* Replace naive datetime.now() with UTC-aware calls (#3613) (#3615) ([#3615](https://github.com/mrveiss/AutoBot-AI/pull/3615))

- *(ansible)* Correct systemd startup ordering for all core services (#3609)

- *(ansible)* Restart backend+celery when code is synced (#3608)

- *(ansible)* Preserve wizard's slm_colocated_frontend in role set_fact; fix include_vars precedence in Phase 4c

- *(ansible)* Fix code_source ownership before git reset to unblock pre-flight sync

- *(ansible)* Use set_fact to override slm_colocated_frontend — include_vars beats task vars

- *(ansible)* Replace fragile group-based SLM detection in Phase 4c with filesystem stat

- *(ansible)* Pass slm_colocated_frontend=true when re-rendering nginx in co-located mode

- *(ansible)* Fix ai-stack source file path — playbooks/ is 3 levels from code_source

- *(ansible)* Add force: yes to pre-flight git sync to handle local modifications

- *(ai-stack)* Remove llama-index-vector-stores-redis from requirements-ai.txt

- *(llm)* Exclude temperature fallback for reasoning models in model_param_registry (#3257)

- *(agents)* Fix health_check call site + deserialize facts in _handle_filter_facts (#3387)

- *(ansible)* Chown frontend dir after rsync to fix npm EACCES on package-lock.json

- *(ansible)* Wait for backend health before VNC credential registration (#3592) ([#3594](https://github.com/mrveiss/AutoBot-AI/pull/3594))

- *(chat-workflow)* Reset loop state per turn + cap fingerprint history (#3583) ([#3587](https://github.com/mrveiss/AutoBot-AI/pull/3587))

- *(ansible)* Extend python312 guard to backend role in deploy.yml (#3584) ([#3585](https://github.com/mrveiss/AutoBot-AI/pull/3585))

- *(llm)* Betas routed via extra_headers + temperature=1 enforced for thinking (#3582) ([#3586](https://github.com/mrveiss/AutoBot-AI/pull/3586))

- *(llm)* Betas routed via extra_headers + temperature=1 enforced for thinking (#3582)

- *(ansible)* AUTOBOT_CHROMADB_HOST uses backend_ai_stack_host on WSL2 (#3541) (#3572) ([#3572](https://github.com/mrveiss/AutoBot-AI/pull/3572))

- *(ansible)* Deploy.yml standalone redeploy now installs python3.12 prerequisite (#3538) (#3568) ([#3568](https://github.com/mrveiss/AutoBot-AI/pull/3568))

- *(multimodal)* Retire multimodal_processor_impl.py — delete dead file (#3579) ([#3581](https://github.com/mrveiss/AutoBot-AI/pull/3581))

- *(ansible)* Add pre-flight git pull to provision-fleet-roles.yml (#3561) (#3567) ([#3567](https://github.com/mrveiss/AutoBot-AI/pull/3567))

- *(multimodal)* Remove shadowed multimodal_processor.py — merge into package (#3554) ([#3558](https://github.com/mrveiss/AutoBot-AI/pull/3558))

- *(media)* Defer VisionProcessor import to break circular dependency (#3551)

- *(ansible)* Ai-stack role uses python3.12 for venv + fix pip cache (#3534) (#3536) ([#3536](https://github.com/mrveiss/AutoBot-AI/pull/3536))

- *(setup_wizard)* Auto-derive backend_chromadb_host from ai_stack_host for fleet deployments (#3523) ([#3524](https://github.com/mrveiss/AutoBot-AI/pull/3524))

- *(setup_wizard)* Propagate injected ai_stack_host into infra_vars (#3515) ([#3522](https://github.com/mrveiss/AutoBot-AI/pull/3522))

- *(slm)* Skip non-path tokens in _check_sensitive_path to fix 3 test failures (#3520)

- *(ansible)* Add backend_chromadb_host/port defaults to backend role (#3514) (#3518) ([#3518](https://github.com/mrveiss/AutoBot-AI/pull/3518))

- *(ansible)* Auto-detect WSL2 and set correct ai_stack_host per deployment (#3503) (#3516) ([#3516](https://github.com/mrveiss/AutoBot-AI/pull/3516))

- *(ansible)* Inject AUTOBOT_INTERNAL_API_KEY into SLM and backend process env (#3512) (#3513) ([#3513](https://github.com/mrveiss/AutoBot-AI/pull/3513))

- *(frontend)* Gate Desktop and CustomDashboard nav links to admins (#3502) (#3517) ([#3517](https://github.com/mrveiss/AutoBot-AI/pull/3517))

- *(ansible)* Set ai_user/ai_group to autobot for co-located ai-stack deployment (#3501) (#3510) ([#3510](https://github.com/mrveiss/AutoBot-AI/pull/3510))

- *(ansible)* Add AUTOBOT_AI_STACK_HOST/PORT to backend env template (#3503) (#3509) ([#3509](https://github.com/mrveiss/AutoBot-AI/pull/3509))

- *(ansible)* Create src/ directory before creating backend module symlinks (#3500) (#3507) ([#3507](https://github.com/mrveiss/AutoBot-AI/pull/3507))

- *(analytics)* Use route.params.sourceId in sub-tab nav links, start polling after sync (#3497, #3498)

- *(agents)* Asyncio.Lock collision causes health check failure in StandardizedAgent (#3491)

- *(ansible)* Ai-stack role missing source deploy, wrong venv, wrong user for co-located (#3491)

- *(chat)* Normalize SSE error key, fix empty exc string, fix status override

- *(slm)* Add sensitive-path denylist for cat/head/tail in nodes_execution.py (#3475) (#3496) ([#3496](https://github.com/mrveiss/AutoBot-AI/pull/3496))

- *(slm)* Block find -delete and file-write actions in argument guard (#3474) (#3495) ([#3495](https://github.com/mrveiss/AutoBot-AI/pull/3495))

- *(slm)* Add admin guard to tools-terminal, files, novnc, voice, mcp routes (#3490) (#3494) ([#3494](https://github.com/mrveiss/AutoBot-AI/pull/3494))

- *(slm)* Require explicit git stash subcommand — bare stash returns HTTP 400 (#3478) (#3486) ([#3486](https://github.com/mrveiss/AutoBot-AI/pull/3486))

- *(ansible)* Update deploy-aiml.yml chromadb_port default from 8000 to 8100 (#3462) (#3483) ([#3483](https://github.com/mrveiss/AutoBot-AI/pull/3483))

- *(slm)* Add admin guard to BrowserTool.vue route (#3470) (#3484) ([#3484](https://github.com/mrveiss/AutoBot-AI/pull/3484))

- *(tts)* Call _check_cache_writable before pocket_tts import, remove redundant mkdir (#3480) (#3482) ([#3482](https://github.com/mrveiss/AutoBot-AI/pull/3482))

- *(frontend)* Extract error/message field from JSON error bodies instead of [object Object] (#3463) (#3481) ([#3481](https://github.com/mrveiss/AutoBot-AI/pull/3481))

- *(tts)* Extend _check_cache_writable to validate hub/xet subdirs (#3471) ([#3473](https://github.com/mrveiss/AutoBot-AI/pull/3473))

- *(tts)* Validate cache directory writability before model load (#3466) ([#3467](https://github.com/mrveiss/AutoBot-AI/pull/3467))

- *(setup)* Auto-inject ai-stack on backend node when no fleet node has it (#3461) ([#3468](https://github.com/mrveiss/AutoBot-AI/pull/3468))

- *(tts)* Change TTS worker port 8082→8083, fix model cache ownership (#3431)

- *(chat)* Resolve 'Error: Error:' double-wrap in SSE error responses (#3458)

- *(wizard)* Co-located backend binds wrong host:port, SLM frontend missing VITE_API_URL (#3426)

- *(slm)* Replace shell denylist with allowlist to prevent command injection (#3421)

- *(ansible)* Rename backend_port to backend_nginx_port in distributed_setup to prevent port conflict (#3431)

- *(backend)* Add authentication to Docker deployment API endpoints (#3423)

- *(slm-agent)* Move get_redis_client to top-level import to fix test patching (#3422)

- *(knowledge-graph)* Remove non-existent _destructor() call — Three.js teardown already complete (#3420)

- Lazy-load KnowledgeGraph3D to defer Three.js loading (#4017) ([#4017](https://github.com/mrveiss/AutoBot-AI/pull/4017))

- Fetch user/group names from API in ShareKnowledgeDialog (#3990) ([#3990](https://github.com/mrveiss/AutoBot-AI/pull/3990))

- *(security)* Harden ALLOWED_EXECUTABLES — dpkg/git-stash/find guards (#3450) ([#3457](https://github.com/mrveiss/AutoBot-AI/pull/3457))

- *(security)* Revert get_current_user on /events/sync — agents have no bearer token (#3452) ([#3472](https://github.com/mrveiss/AutoBot-AI/pull/3472))

- *(security)* Add auth to browser MCP endpoints (#3451) (#3460) ([#3460](https://github.com/mrveiss/AutoBot-AI/pull/3460))

- *(security)* Add auth to /events/sync endpoint (#3452) (#3459) ([#3459](https://github.com/mrveiss/AutoBot-AI/pull/3459))

- *(workflow)* Prevent checkpoint expiry for paused workflows (#3231) (#3448) ([#3448](https://github.com/mrveiss/AutoBot-AI/pull/3448))

- *(analytics)* Pass ComputedRef to useEvolution to prevent stale source_id on project nav (#3436)

- *(security)* Bump vulnerable dependency versions across requirements files

- *(frontend)* PhaseProgressionIndicator calls non-existent project/phase API endpoints (#3413) ([#3413](https://github.com/mrveiss/AutoBot-AI/pull/3413))

- *(knowledge-graph)* Dispose Three.js GPU resources on KnowledgeGraph3D unmount (#3412) ([#3412](https://github.com/mrveiss/AutoBot-AI/pull/3412))

- *(knowledge-graph)* Resize KnowledgeGraph3D canvas when container dimensions change (#3411) ([#3411](https://github.com/mrveiss/AutoBot-AI/pull/3411))

- *(knowledge-graph)* Call cy.resize()/fit() after switching back to 2D view (#3410) ([#3410](https://github.com/mrveiss/AutoBot-AI/pull/3410))

- *(backend)* Fall through on corrupt cache entry; fix cache_function JSONResponse serialisation (#3380) ([#3380](https://github.com/mrveiss/AutoBot-AI/pull/3380))

- *(test)* Align chat_knowledge e2e test path with router registration (#3349) (#3378) ([#3378](https://github.com/mrveiss/AutoBot-AI/pull/3378))

- *(backend)* Log warning instead of silently swallowing exceptions in cache metric helpers (#3350) (#3377) ([#3377](https://github.com/mrveiss/AutoBot-AI/pull/3377))

- *(backend)* Register kb_librarian router in main.py (#3348) (#3379) ([#3379](https://github.com/mrveiss/AutoBot-AI/pull/3379))

- *(backend)* Move empty-prefix router prefixes to registry tuples, eliminate /api/health shadowing (#3355) (#3371) ([#3371](https://github.com/mrveiss/AutoBot-AI/pull/3371))

- *(test)* Correct chat_knowledge underscore paths to chat-knowledge hyphen (#3349) (#3366) ([#3366](https://github.com/mrveiss/AutoBot-AI/pull/3366))

- *(knowledge-graph)* Teardown, i18n, shallowRef typing, nextTick, RAF leak (#3363) (#3369) ([#3369](https://github.com/mrveiss/AutoBot-AI/pull/3369))

- *(chat-workflow)* Wire _inject_mid_conversation_warning into RLM path + move tests (#3260) (#3362) ([#3362](https://github.com/mrveiss/AutoBot-AI/pull/3362))

- *(knowledge)* Doc_indexer stale path, frontmatter parsing, _index.md exclusion (#3299) (#3360) ([#3360](https://github.com/mrveiss/AutoBot-AI/pull/3360))

- *(frontend)* Add missing i18n key auth.login.footer (#3307) (#3358) ([#3358](https://github.com/mrveiss/AutoBot-AI/pull/3358))

- *(chat-workflow)* Add _inject_mid_conversation_warning helper and document Anthropic restriction (#3260) (#3338) ([#3338](https://github.com/mrveiss/AutoBot-AI/pull/3338))

- *(backend)* Re-enable LLM response caching after FastAPI 0.115.9 fix (#3273) (#3341) ([#3341](https://github.com/mrveiss/AutoBot-AI/pull/3341))

- *(install.sh)* Upsert IP/network keys in preserved secrets to prevent stale values (#3194) (#3337) ([#3337](https://github.com/mrveiss/AutoBot-AI/pull/3337))

- *(backend)* Correct .ports -> .port typo in chromadb client modules (#3329) (#3340) ([#3340](https://github.com/mrveiss/AutoBot-AI/pull/3340))

- *(slm-frontend)* Use bg-autobot-bg-tertiary for toggle off-state (#3187) (#3328) ([#3328](https://github.com/mrveiss/AutoBot-AI/pull/3328))

- *(slm-frontend)* Wire i18n keys in WorkflowLiveDashboard status/connection labels (#3188) (#3324) ([#3324](https://github.com/mrveiss/AutoBot-AI/pull/3324))

- *(slm-frontend)* Group wizard role assignment into deployment categories (#3192) (#3323) ([#3323](https://github.com/mrveiss/AutoBot-AI/pull/3323))

- *(ansible)* Align slm_tls_cert/key defaults with actual cert paths (#3191) (#3327) ([#3327](https://github.com/mrveiss/AutoBot-AI/pull/3327))

- *(install.sh)* Pre-create ansible tmp dirs as autobot user (#3298) (#3326) ([#3326](https://github.com/mrveiss/AutoBot-AI/pull/3326))

- *(slm-frontend)* Replace hardcoded colors with design tokens in AgentSettingsPanel (#3187) (#3322) ([#3322](https://github.com/mrveiss/AutoBot-AI/pull/3322))

- *(docs)* Replace hardcoded 172.16.168.x IPs with VM role placeholders (#3315) ([#3315](https://github.com/mrveiss/AutoBot-AI/pull/3315))

- *(ansible)* Fresh-install issues — SLM frontend rebuild, hostname guard, pg_hba default (#3297) ([#3297](https://github.com/mrveiss/AutoBot-AI/pull/3297))

- *(slm-frontend)* Add node summary header to details slide-over panel (#3306) (#3310) ([#3310](https://github.com/mrveiss/AutoBot-AI/pull/3310))

- *(slm-frontend)* Wire dark mode setting to CSS class (#3305) (#3309) ([#3309](https://github.com/mrveiss/AutoBot-AI/pull/3309))

- *(chat-workflow)* Merge context into system prompt instead of appending second system message (#3260) (#3304) ([#3304](https://github.com/mrveiss/AutoBot-AI/pull/3304))

- *(backend)* Replace hardcoded available_providers with real health checks (#3276) (#3303) ([#3303](https://github.com/mrveiss/AutoBot-AI/pull/3303))

- *(ansible)* Add default filter for network_subnet in Ansible playbooks (#3302) ([#3302](https://github.com/mrveiss/AutoBot-AI/pull/3302))

- *(frontend)* Add missing i18n key auth.login.footer (#3307) (#3308) ([#3308](https://github.com/mrveiss/AutoBot-AI/pull/3308))

- *(code)* Normalise deployment paths in code, scripts, and agent configs

- *(docs)* Update Phase 5/9 references and normalise deployment paths

- *(docs)* Rename Phase 5/9 files to remove implementation-era naming

- *(slm-agent)* Heartbeats 502 in co-located mode, wrong /api/ path (#3268)

- *(config)* Close remaining hardcoded IP gaps after #3226 (#3253) (#3264) ([#3264](https://github.com/mrveiss/AutoBot-AI/pull/3264))

- *(slm-agent)* Heartbeats 502 in co-located mode, wrong /api/ path (#3268) ([#3267](https://github.com/mrveiss/AutoBot-AI/pull/3267))

- *(ansible)* Group/host collision, stale secrets IPs, hardcoded networks (#3266)

- *(ansible)* Load slm_manager defaults in Phase 4c before re-rendering nginx (#3226)

- *(ansible)* Guard all infrastructure.hosts.* template expressions against undefined (#3226)

- *(ansible)* Guard infrastructure.hosts.backend against undefined in slm_manager defaults (#3226)

- *(ansible)* Escape inner double quotes in role defaults YAML Jinja2 lookups (#3226)

- *(agent)* Add auth token to SLM agent event sync requests (#3193) (#3249) ([#3249](https://github.com/mrveiss/AutoBot-AI/pull/3249))

- *(config)* Replace deployment-specific IP ranges and paths with portable env vars (#3226)

- *(config)* Remove hardcoded 172.16.168.x IPs from all scripts, Ansible, and shared modules (#3226)

- *(config)* Remove all hardcoded 172.16.168.x IPs from config, env, and test files (#3226)

- *(types)* Type SLM API security function responses instead of unknown (#3190) ([#3248](https://github.com/mrveiss/AutoBot-AI/pull/3248))

- *(orchestration)* Resolve status type mismatch in NodeHealthCard/ServiceActionButtons (#3195) (#3247) ([#3247](https://github.com/mrveiss/AutoBot-AI/pull/3247))

- *(autoResearch)* Align useAutoResearch with composable error handling pattern (#3210) (#3246) ([#3246](https://github.com/mrveiss/AutoBot-AI/pull/3246))

- *(ai)* Use init_empty_weights() in model_inspector + add tests (#3186) (#3244) ([#3244](https://github.com/mrveiss/AutoBot-AI/pull/3244))

- *(voice)* Replace unsafe 'as string' casts with typed voiceSpeak response (#3197) (#3241) ([#3241](https://github.com/mrveiss/AutoBot-AI/pull/3241))

- *(mcp)* Enforce PROJECT_ROOT restriction in executeCommand (#3216) (#3239) ([#3239](https://github.com/mrveiss/AutoBot-AI/pull/3239))

- *(execution)* Inject notification_config into execution_context (#3172) (#3237) ([#3237](https://github.com/mrveiss/AutoBot-AI/pull/3237))

- *(html)* Strip script/style content in _fallback_html_strip (#3214) (#3236) ([#3236](https://github.com/mrveiss/AutoBot-AI/pull/3236))

- *(workflow)* Add trigger_payload field to ActiveWorkflow dataclass (#3178) (#3235) ([#3235](https://github.com/mrveiss/AutoBot-AI/pull/3235))

- *(quantization)* Move load_in_4bit to extra_kwargs (#3179) (#3234) ([#3234](https://github.com/mrveiss/AutoBot-AI/pull/3234))

- *(api)* Add auth guard to DELETE /sessions/{id}/checkpoints (#3173) (#3233) ([#3233](https://github.com/mrveiss/AutoBot-AI/pull/3233))

- *(config)* Replace deployment-specific IP ranges and paths with portable env vars (#3226)

- *(config)* Remove hardcoded 172.16.168.x IPs from all scripts, Ansible, and shared modules (#3226)

- *(config)* Remove all hardcoded 172.16.168.x IPs from config, env, and test files (#3226)

- *(config)* Replace all hardcoded IP fallbacks with empty strings (#3226)

- *(ansible)* Replace all remaining hardcoded IPs and DNS servers with variables (#3226)

- *(ansible)* Remove all hardcoded IPs — derive subnet/hosts from install-time secrets (#3226)

- *(nginx)* Add default for frontend_dist_dir in co-located template (#3226)

- *(install)* Clear IP cache on reinstall + heal stale node IP on startup (#3194)

- *(provision)* Block/rescue VNC registration + colocation by node_id (#3226 #3227)

- *(provision)* VNC registration non-fatal + frontend_backend_host undefined (#3226 #3227)

- *(slm)* Self-register SLM manager node on startup if missing from DB (#3225)

- *(wizard)* Auto-save roles before advancing assign_roles step (#3220)

- *(security)* Resolve Python warning-severity CodeQL alerts (#3164) ([#3204](https://github.com/mrveiss/AutoBot-AI/pull/3204))

- *(security)* Preserve slug lookahead semantics and URL port/query support (#3164)

- *(security)* Resolve Python warning-severity CodeQL alerts (#3164)

- *(security)* Resolve ~14 JavaScript CodeQL alerts (#3164) ([#3183](https://github.com/mrveiss/AutoBot-AI/pull/3183))

- *(security)* Complete sessionStorage migration for auth tokens (#3164)

- *(security)* Resolve ~14 JavaScript CodeQL alerts (#3164)

- *(install)* Redirect detect_local_ip success message to stderr (#3010)

- *(devops)* Fix co-location check for wizard-generated inventories

- *(frontend)* Replace remaining any types across Vue components and TS files (#3167) (#3180) ([#3180](https://github.com/mrveiss/AutoBot-AI/pull/3180))

- *(security)* Apply path validation to ~66 path-injection alerts (#3164) (#3182) ([#3182](https://github.com/mrveiss/AutoBot-AI/pull/3182))

- *(backend)* Persist notification config to Redis across restarts (#3166) (#3175) ([#3175](https://github.com/mrveiss/AutoBot-AI/pull/3175))

- *(backend)* Load workflow notification_config from execution_context (#3168) (#3171) ([#3171](https://github.com/mrveiss/AutoBot-AI/pull/3171))

- *(frontend)* Remove duplicate /agent-registry route (#3163) (#3169) ([#3169](https://github.com/mrveiss/AutoBot-AI/pull/3169))

- *(devops)* Remove /slm prefix from co-located agent admin URL

- *(devops)* Simplify slm_host template to single-line, remove debug

- *(security)* Fix remaining CodeQL alerts - stack-trace-exposure and path-injection (#3151) (#3162) ([#3162](https://github.com/mrveiss/AutoBot-AI/pull/3162))

- *(types)* Replace 103 more any types in ChatController, ChatRepository, and 5 other files (#3152) (#3158) ([#3158](https://github.com/mrveiss/AutoBot-AI/pull/3158))

- *(install)* Make secrets file readable by autobot group

- *(devops)* Derive slm_host from install-time secrets, not hostvars

- *(devops)* Use explicit 172.16.168.19 for slm_host in slm-nodes.yml

- *(devops)* Check venv directory not venv/bin/python for symlink

- *(deps)* Migrate tailwindcss 3→4 CSS-first config (#2636) ([#3146](https://github.com/mrveiss/AutoBot-AI/pull/3146))

- *(types)* Replace 116 any types with concrete types (#2861) ([#3148](https://github.com/mrveiss/AutoBot-AI/pull/3148))

- *(security)* Fix stack-trace-exposure CodeQL alerts (#1733) ([#3149](https://github.com/mrveiss/AutoBot-AI/pull/3149))

- *(backend)* Pass trigger payload to workflow execution (#3138) (#3144) ([#3144](https://github.com/mrveiss/AutoBot-AI/pull/3144))

- *(devops)* Replace hardcoded 172.16.168.20 with configurable variable (#3137) (#3142) ([#3142](https://github.com/mrveiss/AutoBot-AI/pull/3142))

- *(devops)* Add slm_host to slm-nodes.yml inventory

- *(devops)* Fix recursive template loop in VNC slm_admin_password

- *(devops)* Fix backend pip filter and VNC SLM host resolution

- *(backend)* Auto-inject WorkflowMemory findings into step prompts (#3099) (#3135) ([#3135](https://github.com/mrveiss/AutoBot-AI/pull/3135))

- *(backend)* Start TriggerService background loops during app init (#3100) (#3134) ([#3134](https://github.com/mrveiss/AutoBot-AI/pull/3134))

- *(devops)* Move NPU worker models dir to /var/lib/autobot-npu (#3120)

- *(security)* Sanitize git credential tokens from error messages (#3095)

- *(devops)* Resolve /var/lib/autobot ownership conflict between ai-stack and backend (#3097) (#3119) ([#3119](https://github.com/mrveiss/AutoBot-AI/pull/3119))

- *(backend)* Fix Knowledge Base initialization failure (#3094, #3106) (#3118) ([#3118](https://github.com/mrveiss/AutoBot-AI/pull/3118))

- *(devops)* Add /slm prefix to agent admin_url for co-located mode (#3096) (#3117) ([#3117](https://github.com/mrveiss/AutoBot-AI/pull/3117))

- *(frontend,backend)* Add status polling for code source cards (#3092) (#3116) ([#3116](https://github.com/mrveiss/AutoBot-AI/pull/3116))

- *(devops)* Fix nginx WebSocket proxy and template divergence (#3105, #3108, #3109) (#3115) ([#3115](https://github.com/mrveiss/AutoBot-AI/pull/3115))

- *(npu-worker)* Remove hardcoded backend IP fallback (#3084) (#3114) ([#3114](https://github.com/mrveiss/AutoBot-AI/pull/3114))

- *(backend)* Update dead /ws exempt path to /api/ws (#3110) (#3113) ([#3113](https://github.com/mrveiss/AutoBot-AI/pull/3113))

- *(backend)* Add missing websockets dependency to requirements.txt (#3098) (#3112) ([#3112](https://github.com/mrveiss/AutoBot-AI/pull/3112))

- *(backend)* Reorder analytics routes to fix /sources/summary 404 (#3107) (#3111) ([#3111](https://github.com/mrveiss/AutoBot-AI/pull/3111))

- *(lint)* Shorten nosec comment to fit Black line length

- *(lint)* Add nosec B307 for sandboxed eval in dag_executor

- *(lint)* Remove unused imports detected by autoflake

- *(lint)* Resolve 20 pre-existing flake8 F-code violations

- *(ansible)* Remove self-referencing symlink tasks after rename (#2934, #3090)

- *(tts)* Add HuggingFace auth token support for gated models (#3078) (#3086) ([#3086](https://github.com/mrveiss/AutoBot-AI/pull/3086))

- *(infra)* Replace hardcoded IPs in 2 missed test files (#3077) (#3082) ([#3082](https://github.com/mrveiss/AutoBot-AI/pull/3082))

- *(slm-frontend)* Replace hardcoded proxy targets with env var overrides (#3076) (#3081) ([#3081](https://github.com/mrveiss/AutoBot-AI/pull/3081))

- *(security)* Exempt /api/nodes/ from CSRF middleware for agent heartbeats (#3072) ([#3072](https://github.com/mrveiss/AutoBot-AI/pull/3072))

- *(frontend)* Fix all 115 remaining test failures across 5 files (#2641) (#3066) ([#3066](https://github.com/mrveiss/AutoBot-AI/pull/3066))

- *(infra)* Replace hardcoded IPs in utility scripts with env var overrides (#3051) (#3062) ([#3062](https://github.com/mrveiss/AutoBot-AI/pull/3062))

- *(wizard)* Create deployment records during fleet provisioning (#3032) (#3061) ([#3061](https://github.com/mrveiss/AutoBot-AI/pull/3061))

- *(frontend)* Replace hardcoded IPs in vite.config.ts and ServiceDiscovery (#3052) (#3059) ([#3059](https://github.com/mrveiss/AutoBot-AI/pull/3059))

- *(slm-frontend)* Add env var overrides to ssot-config VM IPs and ports (#3049) (#3057) ([#3057](https://github.com/mrveiss/AutoBot-AI/pull/3057))

- *(hooks)* Strip commit message content before pattern checking (#3041) (#3056) ([#3056](https://github.com/mrveiss/AutoBot-AI/pull/3056))

- *(config)* Replace hardcoded IPs in comments to fix SSOT CI check (#3042) (#3054) ([#3054](https://github.com/mrveiss/AutoBot-AI/pull/3054))

- *(vnc)* Handle both access_token and token field names in SLM auth response (#3053) ([#3053](https://github.com/mrveiss/AutoBot-AI/pull/3053))

- *(browser)* Add code sync from code_source — WorkingDirectory was missing (#3044) ([#3044](https://github.com/mrveiss/AutoBot-AI/pull/3044))

- *(redis)* Set User=redis in systemd override (#3031) ([#3031](https://github.com/mrveiss/AutoBot-AI/pull/3031))

- *(tests)* Update redis_optimizer_test.py fixtures to use await pattern (#3029) (#3030) ([#3030](https://github.com/mrveiss/AutoBot-AI/pull/3030))

- *(ansible)* Preserve dpkg conffiles during role removal and decommission (#3011) (#3028) ([#3028](https://github.com/mrveiss/AutoBot-AI/pull/3028))

- *(install)* Use file-based cache for detect_local_ip across subshells (#3010) (#3027) ([#3027](https://github.com/mrveiss/AutoBot-AI/pull/3027))

- *(slm)* Move co-location detection before SLM frontend build (#3013) (#3025) ([#3025](https://github.com/mrveiss/AutoBot-AI/pull/3025))

- *(ansible)* Re-deploy SLM nginx in co-located mode after frontend provision (#3012) (#3024) ([#3024](https://github.com/mrveiss/AutoBot-AI/pull/3024))

- *(ansible)* Add esbuild install step for frontend build + VNC auth assertion (#3006)

- *(frontend)* Fix mock infrastructure for 8 failing test files (#2641) (#3007) ([#3007](https://github.com/mrveiss/AutoBot-AI/pull/3007))

- *(nginx)* Redirect /slm to /slm/ for SLM frontend access without trailing slash

- *(ansible)* Guard VNC deployment to vnc-role nodes only (#2989) (#3002) ([#3002](https://github.com/mrveiss/AutoBot-AI/pull/3002))

- *(ansible)* Audit and fix 5 ignore_errors bypasses in playbooks (#2950) (#3000) ([#3000](https://github.com/mrveiss/AutoBot-AI/pull/3000))

- *(frontend)* Remove orphaned ApprovalGatePanel.vue and useApprovalGates.ts (#2949) (#2997) ([#2997](https://github.com/mrveiss/AutoBot-AI/pull/2997))

- *(config)* Replace hardcoded IPs in standalone script and model schema (#2983) (#2995) ([#2995](https://github.com/mrveiss/AutoBot-AI/pull/2995))

- *(redis)* Await get_async_client() in 12 remaining callers (#2984) (#2991) ([#2991](https://github.com/mrveiss/AutoBot-AI/pull/2991))

- *(npu)* Wire worker manager injection, safe failover, error propagation (#2985) (#2987) ([#2987](https://github.com/mrveiss/AutoBot-AI/pull/2987))

- *(ansible)* Add tts-worker phase to provisioning + verify clean task guards (#2959) (#2980) ([#2980](https://github.com/mrveiss/AutoBot-AI/pull/2980))

- *(deploy)* Single-host deployment gaps — PostgreSQL, auth, SSOT defaults (#2953) (#2981) ([#2981](https://github.com/mrveiss/AutoBot-AI/pull/2981))

- *(npu)* Wire per-worker task tracking callers and add failover fallback (#2944) (#2970) ([#2970](https://github.com/mrveiss/AutoBot-AI/pull/2970))

- *(redis)* Await get_async_client() coroutine in all callers (#2956) (#2969) ([#2969](https://github.com/mrveiss/AutoBot-AI/pull/2969))

- *(backend)* Deploy config files (llm_models.yaml, permission_rules.yaml) (#2957) (#2972) ([#2972](https://github.com/mrveiss/AutoBot-AI/pull/2972))

- *(slm)* Derive heartbeat URL from SSOT config instead of static IP (#2955) (#2966) ([#2966](https://github.com/mrveiss/AutoBot-AI/pull/2966))

- *(chat)* Resolve run_in_chat_io_executor keyword argument mismatch (#2958) (#2964) ([#2964](https://github.com/mrveiss/AutoBot-AI/pull/2964))

- *(redis)* Fix RDB persistence permissions and vm.overcommit (#2954) (#2962) ([#2962](https://github.com/mrveiss/AutoBot-AI/pull/2962))

- *(ansible)* Audit and fix 31 ignore_errors/failed_when bypasses (#2872) (#2952) ([#2952](https://github.com/mrveiss/AutoBot-AI/pull/2952))

- *(security)* Add CSRF mitigation middleware and security headers (#2858) (#2946) ([#2946](https://github.com/mrveiss/AutoBot-AI/pull/2946))

- *(ansible)* Make slm_manager role idempotent and remove silent failures (#2857) (#2943) ([#2943](https://github.com/mrveiss/AutoBot-AI/pull/2943))

- *(ansible)* Redis service file recovery + VNC slm_host resolution

- *(redis)* Use absolute /usr/bin/redis-cli path for Ansible become context

- *(redis)* Use redis-cli from PATH instead of hardcoded /opt/redis-stack path

- *(redis)* Use full path for redis-cli and show logs when no password set

- *(ai-stack)* Change ChromaDB port from 8000 to 8100 to avoid SLM conflict (#2810)

- *(ansible)* Resolve backend/frontend nginx config conflict on single-host (#2829) (#2935) ([#2935](https://github.com/mrveiss/AutoBot-AI/pull/2935))

- *(backend)* Replace hardcoded Redis DB numbers with SSOT env vars (#2806) (#2933) ([#2933](https://github.com/mrveiss/AutoBot-AI/pull/2933))

- *(ansible)* Remove default inventory from ansible.cfg to prevent merge (#2837) (#2931) ([#2931](https://github.com/mrveiss/AutoBot-AI/pull/2931))

- *(frontend)* Use --legacy-peer-deps for npm install (#2835)

- *(frontend)* Add code sync from code_source before build (#2829)

- *(install)* Prompt user to select network interface on multi-interface hosts (#2832)

- *(slm)* Sync NodeRole entries when wizard saves role assignments (#2836)

- *(slm)* Auto-detect co-located frontend instead of relying on external flag (#2829)

- *(slm-frontend)* Only show SLM Services on manager node in wizard (#2900)

- *(ansible)* Add pip timeout to all install tasks to prevent hangs (#2835) (#2927) ([#2927](https://github.com/mrveiss/AutoBot-AI/pull/2927))

- *(ansible)* Deploy backend .env to code_dir matching systemd EnvironmentFile (#2824) (#2925) ([#2925](https://github.com/mrveiss/AutoBot-AI/pull/2925))

- *(ansible)* Protect SLM nginx configs during node decommission (#2918) (#2923) ([#2923](https://github.com/mrveiss/AutoBot-AI/pull/2923))

- *(config)* Replace legacy AUTOBOT_REDIS_DB with named SSOT key (#2813) (#2922) ([#2922](https://github.com/mrveiss/AutoBot-AI/pull/2922))

- *(deps)* Unify langchain upper bounds across all requirements files (#2808) (#2921) ([#2921](https://github.com/mrveiss/AutoBot-AI/pull/2921))

- *(slm)* Stop agent heartbeat from auto-creating unassigned roles (#2900)

- *(deploy)* Activate role status after provisioning and add var defaults (#2836)

- *(slm-frontend)* Remove hardcoded VNC host, use dynamic API only (#2900)

- *(ansible)* Guard all wrong-node clean tasks with node_roles is defined (#2836, #2900)

- *(ansible)* Add SLM service safety guards to co-located role tasks (#2900) (#2912) ([#2912](https://github.com/mrveiss/AutoBot-AI/pull/2912))

- *(backend)* Document bare-except regex false positive on string literals (#2911) (#2917) ([#2917](https://github.com/mrveiss/AutoBot-AI/pull/2917))

- *(backend)* Add noqa markers to demo credentials in analytics_precommit (#2910) (#2916) ([#2916](https://github.com/mrveiss/AutoBot-AI/pull/2916))

- *(docker)* Hardcode HEALTHCHECK port to match exec-form CMD (#2909) (#2915) ([#2915](https://github.com/mrveiss/AutoBot-AI/pull/2915))

- *(devops)* Correct misleading SSH security test description (#2908) (#2914) ([#2914](https://github.com/mrveiss/AutoBot-AI/pull/2914))

- *(frontend)* Remove dead emergency-performance-fix.js (#2907) (#2913) ([#2913](https://github.com/mrveiss/AutoBot-AI/pull/2913))

- *(frontend)* Add backend_host default in configuration summary task

- *(deploy)* Update ssh_user to autobot after enrollment, preserve original for decommission (#2826)

- *(backend)* Centralize DB connection pool sizes via SSOT config (#2860) (#2906) ([#2906](https://github.com/mrveiss/AutoBot-AI/pull/2906))

- *(install)* Wait for HTTPS readiness before Phase 6 node registration (#2830) (#2904) ([#2904](https://github.com/mrveiss/AutoBot-AI/pull/2904))

- *(backend)* Replace silent placeholder implementations with explicit failures (#2869) (#2901) ([#2901](https://github.com/mrveiss/AutoBot-AI/pull/2901))

- *(security)* Make CI security checks blocking — remove continue-on-error (#2874) (#2899) ([#2899](https://github.com/mrveiss/AutoBot-AI/pull/2899))

- *(security)* Replace hardcoded CORS origins and proxy IPs with SSOT (#2862) (#2898) ([#2898](https://github.com/mrveiss/AutoBot-AI/pull/2898))

- *(backend)* Add double-checked locking for singleton/lazy-init globals (#2854) (#2894) ([#2894](https://github.com/mrveiss/AutoBot-AI/pull/2894))

- *(frontend)* Check service exists before stopping legacy Vite dev server

- *(llm)* Add zstd to Ollama install dependencies

- *(backend)* Use backend_code_dir for EnvironmentFile in systemd service (#2824)

- *(deploy)* Single-host nginx conflict, provision log streaming, and installer fixes (#2829, #2824)

- *(frontend)* Add missing event listener cleanup to prevent memory leaks (#2849) (#2888) ([#2888](https://github.com/mrveiss/AutoBot-AI/pull/2888))

- *(backend)* Wrap all SQLAlchemy sessions in context managers (#2851) (#2887) ([#2887](https://github.com/mrveiss/AutoBot-AI/pull/2887))

- *(backend)* Replace hardcoded GPU/NPU benchmark placeholders with real queries (#2871) (#2886) ([#2886](https://github.com/mrveiss/AutoBot-AI/pull/2886))

- *(backend)* Populate empty monitoring stub with Prometheus/Grafana config (#2875) (#2885) ([#2885](https://github.com/mrveiss/AutoBot-AI/pull/2885))

- *(security)* Replace StrictHostKeyChecking=no with accept-new (#2868) (#2884) ([#2884](https://github.com/mrveiss/AutoBot-AI/pull/2884))

- *(frontend)* Remove dead RouterHealthMonitor with disabled recovery (#2870) (#2883) ([#2883](https://github.com/mrveiss/AutoBot-AI/pull/2883))

- *(frontend)* Replace empty catch blocks with logged errors in composables (#2859) (#2882) ([#2882](https://github.com/mrveiss/AutoBot-AI/pull/2882))

- *(security)* Make TLS verification configurable, default to enabled (#2852) (#2881) ([#2881](https://github.com/mrveiss/AutoBot-AI/pull/2881))

- *(security)* Replace f-string SQL queries with parameterized/validated queries (#2845) (#2880) ([#2880](https://github.com/mrveiss/AutoBot-AI/pull/2880))

- *(security)* Prevent path traversal in merge conflict resolution (#2848) (#2879) ([#2879](https://github.com/mrveiss/AutoBot-AI/pull/2879))

- *(security)* Sanitize v-html content to prevent XSS (#2847) (#2878) ([#2878](https://github.com/mrveiss/AutoBot-AI/pull/2878))

- *(security)* Remove hardcoded emergency admin password hash (#2853) (#2877) ([#2877](https://github.com/mrveiss/AutoBot-AI/pull/2877))

- *(security)* Add synchronization for global model state (#2846) (#2876) ([#2876](https://github.com/mrveiss/AutoBot-AI/pull/2876))

- *(backend)* Add logging to silent exception handler in database session (#2850) (#2873) ([#2873](https://github.com/mrveiss/AutoBot-AI/pull/2873))

- *(backend)* Enforce TTL for lpush/rpush/xadd and fix ttl=0 override in redis_mcp (#2793) (#2866) ([#2866](https://github.com/mrveiss/AutoBot-AI/pull/2866))

- *(deps)* Unify redis client pin to >=7.4.0, remove deprecated aioredis (#2807) (#2865) ([#2865](https://github.com/mrveiss/AutoBot-AI/pull/2865))

- *(devops)* Improve IP detection for multi-interface hosts in install.sh (#2832) (#2864) ([#2864](https://github.com/mrveiss/AutoBot-AI/pull/2864))

- *(ansible)* Add apply blocks for tag propagation in include_role tasks (#2827) (#2863) ([#2863](https://github.com/mrveiss/AutoBot-AI/pull/2863))

- *(backend)* Update agent admin_url when node IP changes in wizard (#2833) (#2856) ([#2856](https://github.com/mrveiss/AutoBot-AI/pull/2856))

- *(database)* Remove unused Redis DB duplicate allocations for DB 7 and DB 11 (#2810) (#2855) ([#2855](https://github.com/mrveiss/AutoBot-AI/pull/2855))

- *(deps)* Add upper version bounds to llama-index dependencies (#2822) (#2844) ([#2844](https://github.com/mrveiss/AutoBot-AI/pull/2844))

- *(ansible)* Update stale llama3.2:3b references to llama3.2:1b in config templates (#2809) (#2843) ([#2843](https://github.com/mrveiss/AutoBot-AI/pull/2843))

- *(frontend)* Remove dead save-workflow/update-workflow emits (#2820) (#2842) ([#2842](https://github.com/mrveiss/AutoBot-AI/pull/2842))

- *(backend)* Update stale model fallbacks in optimize_llm_models (#2814) (#2841) ([#2841](https://github.com/mrveiss/AutoBot-AI/pull/2841))

- *(docker)* Use exec form in Dockerfile CMD for graceful shutdown (#2821) (#2840) ([#2840](https://github.com/mrveiss/AutoBot-AI/pull/2840))

- *(frontend)* Replace hardcoded English plural with i18n in MessageAttachments (#2805) (#2839) ([#2839](https://github.com/mrveiss/AutoBot-AI/pull/2839))

- *(backend)* Remove unused DEFAULT_ROLES import (#2817) (#2838) ([#2838](https://github.com/mrveiss/AutoBot-AI/pull/2838))

- *(ansible)* Override ansible.cfg default inventory to prevent production.yml merge (#2836)

- Runtime validation of major npm upgrades (vue-router 5, pinia 3, vitest 4) (#2801) ([#2801](https://github.com/mrveiss/AutoBot-AI/pull/2801))

- *(deps)* Upgrade llama-index to 0.14.x to resolve openai>=2 conflict (#2747)

- *(docker)* Align nginx conf var name and harden worker service (#1809)

- *(deps)* Resolve port collision and bcrypt conflict (#2669) (#2799) ([#2799](https://github.com/mrveiss/AutoBot-AI/pull/2799))

- *(devops)* Remove stale autobot-shared copies (#2796) ([#2803](https://github.com/mrveiss/AutoBot-AI/pull/2803))

- *(devops)* Remove stale autobot-shared copies from ansible node dirs (#2796)

- *(devops)* Add missing tier models to nested settings.json (#2794) ([#2802](https://github.com/mrveiss/AutoBot-AI/pull/2802))

- *(devops)* Add missing tier models to nested settings.json defaults (#2794)

- *(frontend)* Fix useErrorHandler + useKnowledgeVectorization tests (#2641) (#2795) ([#2795](https://github.com/mrveiss/AutoBot-AI/pull/2795))

- *(ansible)* Run provisioning from code_source for latest roles (#2747)

- *(ansible)* Remove duplicate unfiltered requirements install that fails on relative path (#2747)

- *(devops)* Use dynamic inventory from DB (#2700) ([#2789](https://github.com/mrveiss/AutoBot-AI/pull/2789))

- *(devops)* Use dynamic inventory from DB instead of static file (#2700)

- *(frontend)* Fix 3 test files with stale assertions (#2641) (#2787) ([#2787](https://github.com/mrveiss/AutoBot-AI/pull/2787))

- *(frontend)* Align type-check script with CI command (#2643) (#2785) ([#2785](https://github.com/mrveiss/AutoBot-AI/pull/2785))

- *(slm)* Use correct admin URL for single-host installs (#2747) (#2782) ([#2782](https://github.com/mrveiss/AutoBot-AI/pull/2782))

- *(backend)* Use shared get_local_ips() for single-host detection (#2722) (#2780) ([#2780](https://github.com/mrveiss/AutoBot-AI/pull/2780))

- *(ansible)* Add SLM backend code sync from code_source to slm_manager role (#2747)

- *(api)* Create NodeRole entries when registering node via POST /api/nodes (#2747)

- *(devops)* Remove stale ssot_config.py copies (#2580) ([#2779](https://github.com/mrveiss/AutoBot-AI/pull/2779))

- *(devops)* Remove stale ssot_config.py copies from ansible node dirs (#2580)

- *(setup)* Health check validates assigned roles only, not all default roles (#2747)

- *(install)* Register only SLM + monitoring roles, user assigns service roles via wizard (#2717)

- *(install)* Only register SLM roles on install, service roles assigned via wizard (#2717)

- *(devops)* Restore docker-compose.override.example.yml (#2688) ([#2776](https://github.com/mrveiss/AutoBot-AI/pull/2776))

- *(devops)* Restore docker-compose.override.example.yml (#2688)

- *(devops)* Replace obsolete model names (#2585) ([#2775](https://github.com/mrveiss/AutoBot-AI/pull/2775))

- *(devops)* Replace obsolete model names with 3-tier mapping (#2585)

- *(devops)* Use fixed+percentage threshold for small commit contamination (#2761) (#2773) ([#2773](https://github.com/mrveiss/AutoBot-AI/pull/2773))

- *(frontend)* Implement AdvancedStepConfirmationModal (#2674) (#2770) ([#2770](https://github.com/mrveiss/AutoBot-AI/pull/2770))

- *(ci)* Prevent stale CodeQL check status on PRs (#2699) (#2769) ([#2769](https://github.com/mrveiss/AutoBot-AI/pull/2769))

- *(devops)* Restore docker-compose.override.example.yml deleted by pre-commit (#2688) (#2768) ([#2768](https://github.com/mrveiss/AutoBot-AI/pull/2768))

- *(slm)* Remove hardcoded external_url default, write SLM_EXTERNAL_URL at deploy (#2758) (#2767) ([#2767](https://github.com/mrveiss/AutoBot-AI/pull/2767))

- *(frontend)* Align DatabaseConstants with ssot_config.py (#2762) (#2765) ([#2765](https://github.com/mrveiss/AutoBot-AI/pull/2765))

- *(install)* Use correct role names matching role_registry for node registration (#2717)

- *(ansible)* Use code_source_dir for backend code sync instead of playbook_dir (#2747)

- *(ansible)* Skip git clone when code already synced from code_source (#2747)

- *(ansible)* Add code sync tasks to backend role for provisioning (#2747)

- *(ansible)* Guard all role clean tasks to not delete SLM dirs on single-host (#2747)

- *(devops)* Make Claude settings portable and reduce permission prompts (#2764)

- *(ansible)* Use 127.0.0.1 for redis wait_for and connectivity check (#2747)

- *(ansible)* Create redis user/group before redis-stack data dir (#2747)

- *(devops)* Batch pre-commit --files for large staged sets (#2697) (#2750) ([#2750](https://github.com/mrveiss/AutoBot-AI/pull/2750))

- *(backend)* Suppress false positive db.execute in blocking detection (#2656) ([#2757](https://github.com/mrveiss/AutoBot-AI/pull/2757))

- *(devops)* Scope PostToolUse auto-format to already-staged files (#2698) (#2748) ([#2748](https://github.com/mrveiss/AutoBot-AI/pull/2748))

- *(backend)* Validate file paths in analytics problems scanner (#2724) (#2753) ([#2753](https://github.com/mrveiss/AutoBot-AI/pull/2753))

- *(backend)* Fix sync for newly added repos in analytics (#2654) ([#2756](https://github.com/mrveiss/AutoBot-AI/pull/2756))

- *(ansible)* Remove hardcoded backend_port, derive all from infra_vars (#2747)

- *(ansible)* Derive backend_host from ansible facts instead of hardcoding (#2747)

- *(ansible)* Replace hardcoded backend_host with 127.0.0.1 fallback (#2747)

- *(setup)* Include inactive roles in provisioning inventory (#2747)

- *(backend)* Harden local node detection in code source (#2721) ([#2752](https://github.com/mrveiss/AutoBot-AI/pull/2752))

- *(setup)* Fix duplicate host in inventory and guard frontend clean task (#2747)

- *(backend)* Revert_prompt returns 404 instead of 500 (#2745) ([#2749](https://github.com/mrveiss/AutoBot-AI/pull/2749))

- *(setup)* Pass node_roles to dynamic inventory for provisioning (#2747)

- *(ansible)* Allow localhost traffic through UFW for service communication (#2722)

- *(backend)* Populate empty codebase analytics sections (#2655) ([#2744](https://github.com/mrveiss/AutoBot-AI/pull/2744))

- *(backend)* Scope analytics to active source by default (#2653) ([#2738](https://github.com/mrveiss/AutoBot-AI/pull/2738))

- *(backend)* Convert sync __init__ Redis calls to lazy async init (#2725) ([#2737](https://github.com/mrveiss/AutoBot-AI/pull/2737))

- *(setup)* Also remove ProtectHome for user creation during provisioning (#2722)

- *(setup)* Remove ProtectSystem=strict to allow Ansible provisioning (#2722)

- *(setup)* Escape systemd namespace for provisioning ansible (#2722)

- *(setup)* Use local connection for self-node provisioning (#2722)

- *(backend)* Resolve undefined file paths in endpoint scanner (#2652) ([#2733](https://github.com/mrveiss/AutoBot-AI/pull/2733))

- *(frontend)* Add missing analytics i18n sections to fa/he/ur (#2625) ([#2732](https://github.com/mrveiss/AutoBot-AI/pull/2732))

- *(backend)* Align DatabaseConstants with ssot_config.py (#2723) ([#2731](https://github.com/mrveiss/AutoBot-AI/pull/2731))

- *(backend)* Move testing DB from 15 to 13 (#2720) ([#2730](https://github.com/mrveiss/AutoBot-AI/pull/2730))

- *(devops)* Preserve existing secret key in deploy-backend-env.yml (#2726) ([#2728](https://github.com/mrveiss/AutoBot-AI/pull/2728))

- *(install)* Fix deployment failures and add uninstall, /slm subroute, node self-registration (#2705, #2706, #2716, #2717)

- *(devops)* Preserve secret key and add SLM CORS on .env regen (#2649)

- *(devops)* Regenerate backend .env from template during fleet code sync (#2649) ([#2709](https://github.com/mrveiss/AutoBot-AI/pull/2709))

- *(devops)* Add autobot_shared symlink inside backend dir after fleet sync (#2651) ([#2708](https://github.com/mrveiss/AutoBot-AI/pull/2708))

- *(backend)* Restore await on async Redis call sites (#2707) ([#2711](https://github.com/mrveiss/AutoBot-AI/pull/2711))

- *(backend)* Align knowledge DB allocation across config files (#2673) ([#2704](https://github.com/mrveiss/AutoBot-AI/pull/2704))

- *(backend)* Remove hardcoded Redis IP from .env.example Celery URLs (#2677) ([#2702](https://github.com/mrveiss/AutoBot-AI/pull/2702))

- *(backend)* Add missing Celery DB entries to redis-databases.yaml (#2675) ([#2701](https://github.com/mrveiss/AutoBot-AI/pull/2701))

- Remove stale pyvenv.cfg from tracking (Python 3.10 artifact)

- *(devops)* Replace grep -P with bash regex in detection script (#2695)

- *(npu)* Align Windows NPU worker resources to Python 3.12 (#2692)

- *(devops)* Restore docker-compose.override.example.yml (#2688)

- *(devops)* Restore docker-compose.override.example.yml (#2688)

- *(devops)* Restore docker-compose.override.example.yml (#2688)

- Detection script false positives, TLS ports in SSOT (#2687, #2689)

- *(devops)* Restore docker-compose.override.example.yml (#2688)

- *(backend)* Correct ssot_config attribute paths in npu_workers.py (#2686)

- *(ci)* Align knowledge-base Dockerfile to Python 3.12 (#2683)

- *(ci)* Align remaining setup.py and Dockerfiles to Python 3.12 (#2683)

- *(ci)* Align .python-version and setup.py to Python 3.12 (#2683)

- *(provisioning)* Use temp inventory by IP for node provisioning, make fleet playbook dynamic (#2678)

- *(ci)* Bulk isort re-sort with src_paths config (#2679) ([#2691](https://github.com/mrveiss/AutoBot-AI/pull/2691))

- *(ci)* Add known_first_party config and fix celery_app isort (#2679) ([#2690](https://github.com/mrveiss/AutoBot-AI/pull/2690))

- *(ci)* Add pyproject.toml isort config and fix celery_app imports (#2667) (#2680) ([#2680](https://github.com/mrveiss/AutoBot-AI/pull/2680))

- *(decommission)* Use temp inventory by IP, add full VM cleanup phases (#2678)

- *(redis)* Reassign Celery from DB 1/2 to DB 14/15 (#2669)

- *(backend)* Remove erroneous await on sync get_redis_client() (#2628) ([#2633](https://github.com/mrveiss/AutoBot-AI/pull/2633))

- *(slm-frontend)* Migrate eslint to flat config for v9 compat (#2561)

- *(frontend)* Compat fixes for npm major version upgrades (#2559)

- *(ci)* Upgrade typing to 3.10+ style, fix isort CI failures (#2608) ([#2662](https://github.com/mrveiss/AutoBot-AI/pull/2662))

- *(mcp)* Forward RBAC role and move tool injection to base agent (#2629, #2631) ([#2647](https://github.com/mrveiss/AutoBot-AI/pull/2647))

- *(agents)* Remove stale INSTRUCTION/LIGHT/SYSTEM_MODEL imports (#2553)

- *(workflow)* Extend step refs to all types + multi-ref support (#2632) ([#2634](https://github.com/mrveiss/AutoBot-AI/pull/2634))

- *(ansible)* Backend.env.j2 template uses per-tier models instead of flat (#2553)

- *(frontend)* Make createLogger variadic to support %s and multi-arg calls (#2607)

- *(frontend)* Accumulate errors in useCodeIntelligence for parallel calls (#2588) ([#2617](https://github.com/mrveiss/AutoBot-AI/pull/2617))

- *(ansible)* Add llm/reserved hosts to production.yml slm_nodes (#2586) ([#2611](https://github.com/mrveiss/AutoBot-AI/pull/2611))

- *(i18n)* Add noPreviousScan key to all locale files (#2572) ([#2605](https://github.com/mrveiss/AutoBot-AI/pull/2605))

- *(deps)* Tighten Node engine constraint to >=20.19.0 (#2583) ([#2604](https://github.com/mrveiss/AutoBot-AI/pull/2604))

- *(frontend)* Also update @vue/runtime-core in plugins/api.ts (#2579)

- *(frontend)* Resolve TypeScript errors breaking CI on Dev_new_gui (#2579)

- *(llm)* Add thread safety to TokenOptimizer for concurrent access (#2577) ([#2595](https://github.com/mrveiss/AutoBot-AI/pull/2595))

- *(docker)* Target specific worker in celery healthcheck (#2565)

- *(models)* Replace postgresql.UUID with Uuid in 9 more model files (#2563)

- *(ansible)* Add autobot_shared symlink to fleet deployment (#2517)

- *(infra)* Restore full secret_id in diagnostic JSON output (#2555) (#2560) ([#2560](https://github.com/mrveiss/AutoBot-AI/pull/2560))

- *(models)* Split JSONB/UUID imports, replace postgresql.UUID in 6 more files (#2533)

- *(frontend)* Add router-view to WorkflowBuilderView for child routes (#2368) ([#2542](https://github.com/mrveiss/AutoBot-AI/pull/2542))

- *(frontend)* Auto-load Code Intelligence scores on dashboard open (#2115) ([#2544](https://github.com/mrveiss/AutoBot-AI/pull/2544))

- *(models)* Split JSONB/UUID imports, replace postgresql.UUID in 6 more files (#2533) ([#2540](https://github.com/mrveiss/AutoBot-AI/pull/2540))

- *(ansible)* Add cross-inventory group aliases (#2515) ([#2534](https://github.com/mrveiss/AutoBot-AI/pull/2534))

- *(nginx)* Add /slm/api/ws/ WebSocket proxy location (#2489) ([#2535](https://github.com/mrveiss/AutoBot-AI/pull/2535))

- *(deps)* Align oxlint version with eslint-plugin-oxlint peer dep (#2518) ([#2524](https://github.com/mrveiss/AutoBot-AI/pull/2524))

- *(models)* Replace postgresql.UUID with sqlalchemy.types.Uuid (#2495) ([#2532](https://github.com/mrveiss/AutoBot-AI/pull/2532))

- *(frontend)* Replace hardcoded model ref with SSOT config (#2480) ([#2530](https://github.com/mrveiss/AutoBot-AI/pull/2530))

- *(docker)* Replace inherited HTTP healthcheck with Celery ping for worker (#2488) ([#2527](https://github.com/mrveiss/AutoBot-AI/pull/2527))

- *(devops)* Remove stale run_autobot.sh references (#2493)

- *(hooks)* Auto-update stale pre-commit wrapper on checkout (#2519)

- *(hooks)* Bypass pre-commit stash cycle with --files flag (#2512)

- *(ansible)* SLM PYTHONPATH + health-check/manage_services group alignment (#2514)

- *(devops)* Restore CLAUDE.md cleanup rules + enhance cleanup script (#2507, #2508)

- *(ci)* Make sync workflow manual-only to prevent untested code on main (#2445)

- *(ci)* Reverse sync direction to Dev_new_gui → main (#2445)

- *(backend)* Add failover monitor for dead worker task migration (#1769) (#2487) ([#2487](https://github.com/mrveiss/AutoBot-AI/pull/2487))

- *(devops)* Add post-commit hook to auto-heal stash-pop conflicts (#2416) (#2486) ([#2486](https://github.com/mrveiss/AutoBot-AI/pull/2486))

- *(backend)* Remove BrowserAutomationSkill stub — browser_mcp.py is canonical (#1973) (#2484) ([#2484](https://github.com/mrveiss/AutoBot-AI/pull/2484))

- *(ci)* Add main→Dev_new_gui sync workflow (#2445) (#2482) ([#2482](https://github.com/mrveiss/AutoBot-AI/pull/2482))

- *(infra)* Sync 6 Ansible node ssot_config.py copies to canonical (#2415)

- *(docker)* Hardcode cert path to avoid fleet .env conflict (#2458)

- *(shared)* Guard _get_config_manager() null dereference (#2477)

- *(devops)* Add Docker TLS cert path override to docker/.env.docker (#2458) (#2476) ([#2476](https://github.com/mrveiss/AutoBot-AI/pull/2476))

- *(devops)* Restore 0.0.0.0 bind for x11vnc in Docker compose (#2409) (#2475) ([#2475](https://github.com/mrveiss/AutoBot-AI/pull/2475))

- *(devops)* Target Dev_new_gui for Dependabot PRs (#2449) (#2473) ([#2473](https://github.com/mrveiss/AutoBot-AI/pull/2473))


### CI/CD

- Auto-update PR branches when Dev_new_gui advances (#9323) ([#9323](https://github.com/mrveiss/AutoBot-AI/pull/9323))

- *(visual-regression)* Increase job timeout-minutes 180 → 360 (MVA-1504) (#8930) ([#8930](https://github.com/mrveiss/AutoBot-AI/pull/8930))

- Fix visual-regression baselines + remove dead redis.conf.j2 (#7033, #6954) ([#8078](https://github.com/mrveiss/AutoBot-AI/pull/8078))

- Re-trigger workflows on rebased branch (#7522) (#8065) ([#8065](https://github.com/mrveiss/AutoBot-AI/pull/8065))

- *(hooks,actions)* Complete lib/_common.sh migration + composite setup-python action (GH#7086, GH#7203) (#8052) ([#8052](https://github.com/mrveiss/AutoBot-AI/pull/8052))

- *(phase-validation)* Re-enable blocking gate now that PHASE_CRITERIA is fixed (closes #7496) (#7851) ([#7851](https://github.com/mrveiss/AutoBot-AI/pull/7851))

- Route code-quality and frontend-test to self-hosted runner (MVA-454) (#7811) ([#7811](https://github.com/mrveiss/AutoBot-AI/pull/7811))

- Add cache-dependency-path to setup-python/node; add no-literal-ttl-seconds pre-commit hook (GH#7073, GH#7080) ([#7776](https://github.com/mrveiss/AutoBot-AI/pull/7776))

- *(hardening)* Pipefail + concurrency + actionlint (GH#7071, GH#7074, GH#7083)

- *(hooks,actions)* Complete lib/_common.sh migration + composite setup-python action (GH#7086, GH#7203) (#7734) ([#7734](https://github.com/mrveiss/AutoBot-AI/pull/7734))

- *(mypy)* Wire mypy into code-quality pipeline — enforce on autobot_shared (GH#7105) (#7641) ([#7641](https://github.com/mrveiss/AutoBot-AI/pull/7641))

- Enable pip and npm caching across all CI workflows (GH#7073) (#7628) ([#7628](https://github.com/mrveiss/AutoBot-AI/pull/7628))

- Speed up Docker Smoke Test with buildx layer cache + 15-min health wait (closes #7034) (#7598) ([#7598](https://github.com/mrveiss/AutoBot-AI/pull/7598))

- *(code-quality)* Fix isort import ordering on 7 backend files (#7522) (#7596) ([#7596](https://github.com/mrveiss/AutoBot-AI/pull/7596))

- Extend ansible-role-facts-test trigger paths (closes #7223 partial) (#7242) ([#7242](https://github.com/mrveiss/AutoBot-AI/pull/7242))

- *(lint)* Pre-commit hook for git safe.directory + fix 7 missed sites (closes #7219) (#7240) ([#7240](https://github.com/mrveiss/AutoBot-AI/pull/7240))

- *(lint)* Pre-commit hook to block deprecated ansible_X facts (closes #7221) (#7229) ([#7229](https://github.com/mrveiss/AutoBot-AI/pull/7229))

- *(deps)* Comprehensive pip ignore audit — 14 missing entries across 7 dirs (closes #7210) (#7211) ([#7211](https://github.com/mrveiss/AutoBot-AI/pull/7211))

- *(deps)* Add semver-major ignores to autobot_shared + autobot-slm-backend pip (closes #7200) (#7201) ([#7201](https://github.com/mrveiss/AutoBot-AI/pull/7201))

- *(deps)* Add semver-major ignore rules to worker pip ecosystems (closes #7192) (#7194) ([#7194](https://github.com/mrveiss/AutoBot-AI/pull/7194))

- *(hooks)* Extract lib/_common.sh — DRY proof-of-concept (#7185) (#7188) ([#7188](https://github.com/mrveiss/AutoBot-AI/pull/7188))

- *(security)* Expand Dependabot to cover production worker dirs + root manifests (closes #7182 P1+P2) (#7187) ([#7187](https://github.com/mrveiss/AutoBot-AI/pull/7187))

- *(security)* Add npm ecosystem for context7 MCP tool (#7170 self-review) (#7174) ([#7174](https://github.com/mrveiss/AutoBot-AI/pull/7174))

- *(security)* Add 2 missed Dockerfiles + semver-major ignore rules to docker Dependabot (#7157 self-review) (#7170) ([#7170](https://github.com/mrveiss/AutoBot-AI/pull/7170))

- *(security)* Enable Dependabot for docker ecosystem (closes #7157) (#7163) ([#7163](https://github.com/mrveiss/AutoBot-AI/pull/7163))

- *(security)* Add pre-commit-no-tag-pinned-action hook (closes #7120) (#7142) ([#7142](https://github.com/mrveiss/AutoBot-AI/pull/7142))

- *(security)* Pin all 3rd-party actions to commit SHAs (closes #7091) (#7102) ([#7102](https://github.com/mrveiss/AutoBot-AI/pull/7102))

- Add `requirements-ci/**` to path filters (closes #7089) (#7099) ([#7099](https://github.com/mrveiss/AutoBot-AI/pull/7099))

- Dedupe path-filter lists via YAML anchors (closes #7038) (#7039) ([#7039](https://github.com/mrveiss/AutoBot-AI/pull/7039))

- Per-job path filters for ci.yml + security.yml (closes #7006) (#7027) ([#7027](https://github.com/mrveiss/AutoBot-AI/pull/7027))

- Workflow polish — stale comments, action version drift, missing concurrency (#7017 A-C) (#7020) ([#7020](https://github.com/mrveiss/AutoBot-AI/pull/7020))

- Add `set -euo pipefail` to all piped run blocks (closes #7015) (#7019) ([#7019](https://github.com/mrveiss/AutoBot-AI/pull/7019))

- Broaden path filters added in #6998 to cover all workflow inputs (#6992) (#7002) ([#7002](https://github.com/mrveiss/AutoBot-AI/pull/7002))

- Add path filters to 3 expensive workflows (partial #6992) (#6998) ([#6998](https://github.com/mrveiss/AutoBot-AI/pull/6998))

- Replace deadsnakes-PPA Python install with setup-python@v5 (closes #6990) (#6997) ([#6997](https://github.com/mrveiss/AutoBot-AI/pull/6997))

- Migrate Bucket B workflows to ubuntu-latest (#6982 final slice, eliminates self-hosted SPOF) (#6986) ([#6986](https://github.com/mrveiss/AutoBot-AI/pull/6986))

- Migrate Bucket A workflows to ubuntu-latest (#6982 follow-up to #6721) (#6984) ([#6984](https://github.com/mrveiss/AutoBot-AI/pull/6984))

- Migrate 4 lint/security workflows from self-hosted → ubuntu-latest (partial #6721) (#6981) ([#6981](https://github.com/mrveiss/AutoBot-AI/pull/6981))

- *(frontend)* Wire check-ts-delta.sh into package.json and CI pipeline (#5830) (#5835) ([#5835](https://github.com/mrveiss/AutoBot-AI/pull/5835))

- *(workflows)* Block datetime.utcnow().isoformat() regressions in CI (#5268) (#5280) ([#5280](https://github.com/mrveiss/AutoBot-AI/pull/5280))

- *(lint)* Add datetime.utcnow().isoformat() regression-prevention hook (#5178 part C) (#5264) ([#5264](https://github.com/mrveiss/AutoBot-AI/pull/5264))

- *(workflows)* Add visual regression workflow for Storybook stories (#5226) (#5244) ([#5244](https://github.com/mrveiss/AutoBot-AI/pull/5244))

- Add automated issue triage workflow for Phase 2.5 (#4196) ([#4196](https://github.com/mrveiss/AutoBot-AI/pull/4196))

- Add Docker smoke test workflow for automated validation (#4032) ([#4032](https://github.com/mrveiss/AutoBot-AI/pull/4032))


### Documentation

- Remove all bounty references (MVA-2591) (#9314) ([#9314](https://github.com/mrveiss/AutoBot-AI/pull/9314))

- Create Obsidian index files for 21 docs/ subdirectories (MVA-2596) ([#9315](https://github.com/mrveiss/AutoBot-AI/pull/9315))

- *(contributing)* Rewrite CONTRIBUTING.md with two-path workflow and PR guidelines

- *(frontend)* Clarify host composables scope and separation (#9063) ([#9184](https://github.com/mrveiss/AutoBot-AI/pull/9184))

- *(code-sync)* Fix stale resolve_drift docstring — no longer references SLM self-sync (#9073)

- *(transcriber)* Add design spec and 4-part implementation plan

- *(claude)* Add hook test requirement — bash vs ugrep grep distinction (#8262)

- *(resource-policy)* Add implementation plan for resource governance role

- *(resource-policy)* Add system-wide resource governance design spec

- *(arch)* Add agent belief-state architecture design (MVA-1426) ([#8869](https://github.com/mrveiss/AutoBot-AI/pull/8869))

- *(llc)* AutoBot LLC Module PRD — 6-phase autonomous company OS design (#8204)

- *(agent-patterns)* Replace PR-wait polling with Monitor/ScheduleWakeup guidance (MVA-315) (#8047) ([#8047](https://github.com/mrveiss/AutoBot-AI/pull/8047))

- *(arch)* Add chat state SSOT design document (#6746) (#7944) ([#7944](https://github.com/mrveiss/AutoBot-AI/pull/7944))

- *(frontend/composables)* Add canonical composable pattern guide (GH#7452) ([#7863](https://github.com/mrveiss/AutoBot-AI/pull/7863))

- *(storybook)* Add stories for singleton components (#6869) (#7814) ([#7814](https://github.com/mrveiss/AutoBot-AI/pull/7814))

- *(rules)* Document AUTOBOT_CHAT_SESSION_CACHE_TTL env var (#7026) (#7813) ([#7813](https://github.com/mrveiss/AutoBot-AI/pull/7813))

- *(ansible)* Mark redis.conf.j2 as non-deployed reference template (#7257) (#7783) ([#7783](https://github.com/mrveiss/AutoBot-AI/pull/7783))

- *(adr)* Add ADR-006 Skill-Bound Planning (GH#7268, MVA-416)

- *(agent-patterns)* Replace PR-wait polling with Monitor/ScheduleWakeup guidance (MVA-315) (#7710) ([#7710](https://github.com/mrveiss/AutoBot-AI/pull/7710))

- *(ci/visual-regression)* Document CI-only baseline policy + add workflow_dispatch regeneration (MVA-270) (#7698) ([#7698](https://github.com/mrveiss/AutoBot-AI/pull/7698))

- *(ci)* Record code-quality as required check on Dev_new_gui (MVA-283) ([#7700](https://github.com/mrveiss/AutoBot-AI/pull/7700))

- *(arch)* Add chat state SSOT design document (#6746) (#7592) ([#7592](https://github.com/mrveiss/AutoBot-AI/pull/7592))

- *(canonical-check)* Design spec + Wave 0 foundation plan for #7458 (#7499) ([#7499](https://github.com/mrveiss/AutoBot-AI/pull/7499))

- Refresh stale status/changelog and canonical TaskStatus examples (#7498) ([#7498](https://github.com/mrveiss/AutoBot-AI/pull/7498))

- *(docker)* Document healthcheck CMD vs CMD-SHELL convention (closes #7456) (#7489) ([#7489](https://github.com/mrveiss/AutoBot-AI/pull/7489))

- *(schemas/sandbox-files)* Annotate 7 FileSandbox* classes as deferred wire-in to #7409 (#6676) (#7411) ([#7411](https://github.com/mrveiss/AutoBot-AI/pull/7411))

- *(autobot_shared)* Document local pytest invocation pattern (closes #7175) (#7177) ([#7177](https://github.com/mrveiss/AutoBot-AI/pull/7177))

- *(deps)* Point Backend Common section to pyproject.toml (post-#7113) (#7126) ([#7126](https://github.com/mrveiss/AutoBot-AI/pull/7126))

- *(specs)* Add ARC Prize plugin Phase 1 design spec

- *(api/health)* Record parallel-surface decision for /monitoring/services/health (#6922) (#7005) ([#7005](https://github.com/mrveiss/AutoBot-AI/pull/7005))

- *(frontend)* Add Storybook stories for design-system core (#4201) (#6880) ([#6880](https://github.com/mrveiss/AutoBot-AI/pull/6880))

- *(frontend)* Correct FeatureConnectivity tier docs — backend features are not gated by browser→backend connectivity (#6566) (#6599) ([#6599](https://github.com/mrveiss/AutoBot-AI/pull/6599))

- *(pki)* Add CA rotation runbook; update renew() error message to reference it (#6338) (#6354) ([#6354](https://github.com/mrveiss/AutoBot-AI/pull/6354))

- *(composables)* Document useVoiceConversation fetchWithAuth FormData exemption (#6031) (#6166) ([#6166](https://github.com/mrveiss/AutoBot-AI/pull/6166))

- *(composables)* Document useVoiceOutput fetchWithAuth binary exemption (#6030) (#6160) ([#6160](https://github.com/mrveiss/AutoBot-AI/pull/6160))

- *(composables)* Document useIndexingJob fetchWithAuth intentional exemption (#6024) (#6134) ([#6134](https://github.com/mrveiss/AutoBot-AI/pull/6134))

- *(plans)* Composable weakness remediation — 4 wave implementation plans (#6006)

- *(specs)* Fix Wave 2 count to 12 (add useBackgroundTask), master tracker #6006

- *(specs)* Composable weakness remediation design — 67 issues, 4 waves

- *(composables)* Document Pattern A2, B2, C in COMPOSABLE_HTTP_PATTERNS.md (#5927) (#5940) ([#5940](https://github.com/mrveiss/AutoBot-AI/pull/5940))

- *(claude)* Update schemas_common.py constraint note — #5799 resolved, domain files now in use

- *(api)* Add response schema selection guide to API_RESPONSE_MIGRATION.md (#5914) (#5919) ([#5919](https://github.com/mrveiss/AutoBot-AI/pull/5919))

- *(composables)* Document ApiClient vs fetchWithAuth patterns and when to use each (#5884) (#5898) ([#5898](https://github.com/mrveiss/AutoBot-AI/pull/5898))

- *(workflow)* Document schemas_common.py serialization requirement (#5842) ([#5889](https://github.com/mrveiss/AutoBot-AI/pull/5889))

- *(workflow)* Add squash-duplicate detection gate to pre-merge-validate (#5841) ([#5888](https://github.com/mrveiss/AutoBot-AI/pull/5888))

- *(composables)* Document counter-based loading in useCodeIntelligence (#5880) ([#5887](https://github.com/mrveiss/AutoBot-AI/pull/5887))

- *(frontend)* Correct TypeScript error baseline from 2005 to 188 (#5096) (#5860) ([#5860](https://github.com/mrveiss/AutoBot-AI/pull/5860))

- *(architecture)* Move ARCHITECTURE_EXCEPTIONS.md to docs/developer/ + add missing entries (#5802 #5805) (#5855) ([#5855](https://github.com/mrveiss/AutoBot-AI/pull/5855))

- *(architecture)* Move ARCHITECTURE_EXCEPTIONS.md + add skills exception entries (#5802) (#5852) ([#5852](https://github.com/mrveiss/AutoBot-AI/pull/5852))

- *(architecture)* Move ARCHITECTURE_EXCEPTIONS.md to docs/developer/, add 3 skills exception entries (#5802) (#5848) ([#5848](https://github.com/mrveiss/AutoBot-AI/pull/5848))

- *(frontend)* Add TypeScript error baseline and delta-check script (#5096) (#5825) ([#5825](https://github.com/mrveiss/AutoBot-AI/pull/5825))

- *(config)* Complete VNC dormant comments in ssot-config, AppConfig, ServiceDiscovery, stores, slm-frontend, docs (#5138) (#5819) ([#5819](https://github.com/mrveiss/AutoBot-AI/pull/5819))

- *(audit)* Poller composables comparison + consolidation proposal (#5250) (#5815) ([#5815](https://github.com/mrveiss/AutoBot-AI/pull/5815))

- *(config)* Mark VNC browser-path env vars as dormant in .env.example (#5138) (#5814) ([#5814](https://github.com/mrveiss/AutoBot-AI/pull/5814))

- *(audit)* Poller composables comparison + consolidation proposal (#5250) (#5809) ([#5809](https://github.com/mrveiss/AutoBot-AI/pull/5809))

- *(config)* Mark VNC browser-path env vars as dormant in .env.example (#5138) (#5807) ([#5807](https://github.com/mrveiss/AutoBot-AI/pull/5807))

- *(audit)* Add openai_compat.py /v1/ endpoints to response_model coverage audit (#5413) (#5794) ([#5794](https://github.com/mrveiss/AutoBot-AI/pull/5794))

- *(orchestrator)* Annotate why _execute_agents_in_parallel is intentionally unbounded (#5114) (#5786) ([#5786](https://github.com/mrveiss/AutoBot-AI/pull/5786))

- *(standards)* Add latency SLO budgets for hot paths to CLAUDE_RULES (#5075) (#5748) ([#5748](https://github.com/mrveiss/AutoBot-AI/pull/5748))

- *(ops)* Add KB Redis-unreachable degradation runbook + Prometheus alert routing (#5408) (#5639) ([#5639](https://github.com/mrveiss/AutoBot-AI/pull/5639))

- *(primitives)* Document lazy_singleton arg-guard behavior in PRIMITIVES.md (#5445)

- *(architecture)* Add ARCHITECTURE_EXCEPTIONS.md for Windows NPU standalone redis_client (#5438) (#5498) ([#5498](https://github.com/mrveiss/AutoBot-AI/pull/5498))

- *(skills)* Consolidate team-implement into batch-implement + fix worktree path (closes #5447 #5454) (#5458) ([#5458](https://github.com/mrveiss/AutoBot-AI/pull/5458))

- *(methodology)* Codify Phase 0d Behavioral Grep rule (closes #5372) (#5444) ([#5444](https://github.com/mrveiss/AutoBot-AI/pull/5444))

- *(audit)* Response_model coverage audit — 14% baseline, recommended batches (#5317) (#5401) ([#5401](https://github.com/mrveiss/AutoBot-AI/pull/5401))

- *(analytics)* Manual E2E verification checklist for /analytics/codebase (#5370) (#5379) ([#5379](https://github.com/mrveiss/AutoBot-AI/pull/5379))

- *(database)* SQLAlchemy DateTime column audit — naive vs aware classification (#5270) (#5281) ([#5281](https://github.com/mrveiss/AutoBot-AI/pull/5281))

- *(backend)* Datetime utcnow non-isoformat audit — 248 sites, 84 files (#5211 part A) (#5267) ([#5267](https://github.com/mrveiss/AutoBot-AI/pull/5267))

- *(backend)* Datetime producer audit — 57 files, 139 sites bypass time_utils (#5178 part A) (#5189) ([#5189](https://github.com/mrveiss/AutoBot-AI/pull/5189))

- *(shared)* Datetime parsing audit + canonicalization decision (#5169 parts B + C) (#5186) ([#5186](https://github.com/mrveiss/AutoBot-AI/pull/5186))

- *(shared)* Document UTC-format selection rule in autobot_shared.time_utils (#5169 part A) (#5176) ([#5176](https://github.com/mrveiss/AutoBot-AI/pull/5176))

- Add historical banners to superseded orchestrator planning docs (#5097)

- Update class names and import paths after orchestrator rename (#5097)

- *(process)* Also update Pre-Implementation Validation section (#4969)

- *(process)* Add commit-before-subagents rule to pre-flight checklists (#4969)

- *(plans)* Add session plan files for graphify-gaps, gui-audit, and responsive-nav

- *(rag)* Update get_weights() docstring to reflect 60s eviction throttle (#4833)

- Rewrite README hero with brand narrative — Your data. Your AI. ([#4746](https://github.com/mrveiss/AutoBot-AI/pull/4746))

- Rewrite README hero with brand narrative — Your data. Your AI.

- *(claude)* Add batch-execution, branch-safety, discovery-filing, and pre-flight rules from session (#4660)

- Add system diagrams, demo guide, and architecture reference (#4509) ([#4509](https://github.com/mrveiss/AutoBot-AI/pull/4509))

- Heartbeat system reference and responsive design guide (#4500) ([#4500](https://github.com/mrveiss/AutoBot-AI/pull/4500))

- *(users)* Admin user management guide and signup documentation (#4499) ([#4499](https://github.com/mrveiss/AutoBot-AI/pull/4499))

- *(marketplace)* API reference and plugin publishing guide (#4498) ([#4498](https://github.com/mrveiss/AutoBot-AI/pull/4498))

- Add AutoResearch user guide and update developer index (#4489) ([#4489](https://github.com/mrveiss/AutoBot-AI/pull/4489))

- *(api)* Add usage metering API reference and admin guide (#4488) ([#4488](https://github.com/mrveiss/AutoBot-AI/pull/4488))

- *(developer)* Add comprehensive hook system guide (#4487) ([#4487](https://github.com/mrveiss/AutoBot-AI/pull/4487))

- *(claude.md)* Add codebase-as-source-of-truth rule

- Remove .19 node references from deployment documentation

- Add Issue Closure Verification Gate to CLAUDE.md

- *(claude)* Add insights implementation tweaks - pre-impl validation, permission enforcement, post-merge audit, enhanced validation, CI integration

- *(i18n)* Document RTL translation requirements and status (#4225)

- *(testing)* Add advanced Vue testing patterns (#4200) (#4227) ([#4227](https://github.com/mrveiss/AutoBot-AI/pull/4227))

- *(deploy)* Create single-host deployment runbook at developer path (#2961) (#4187) ([#4187](https://github.com/mrveiss/AutoBot-AI/pull/4187))

- *(testing)* Document Pinia setup pattern for Vue component tests (#4188) (#4193) ([#4193](https://github.com/mrveiss/AutoBot-AI/pull/4193))

- Add comprehensive CONTRIBUTORS.md guide for Phase 2.5 (#4195) ([#4195](https://github.com/mrveiss/AutoBot-AI/pull/4195))

- Enhance README with comprehensive issue discovery links for Phase 2.5 (#4197) ([#4197](https://github.com/mrveiss/AutoBot-AI/pull/4197))

- *(workflow)* Add parallel work isolation rules and pre-flight/review checklists

- Document populate_autobot_docs fix via background task (#4102, #4103)

- *(dev)* Expand gh pr edit workaround and add helper script (#3753) (#4080) ([#4080](https://github.com/mrveiss/AutoBot-AI/pull/4080))

- *(causal)* Add causal reasoning framework documentation and integration tests

- *(runbook)* Add single-host deployment runbook (#2961)

- Rewrite README with hero section and Docker quickstart (#4030) ([#4030](https://github.com/mrveiss/AutoBot-AI/pull/4030))

- *(security)* Monitor unpatched diskcache CVE with 90-day escalation path (#3446)

- Document gh pr edit --body workaround for classic Projects issue (#3753) (#3952) ([#3952](https://github.com/mrveiss/AutoBot-AI/pull/3952))

- *(plans)* Add language switcher implementation plan

- *(specs)* Add language switcher design spec

- *(how-to)* Add 6 query-matching how-to guides targeting remaining Context7 gaps

- Deepen prompt middleware guide and how-to docs to improve Context7 scores

- *(how-to)* Add 4 query-matching how-to guides to improve Context7 scores

- *(nginx)* Mark slm-site.conf as reference-only, not deployed (#3174) (#3325) ([#3325](https://github.com/mrveiss/AutoBot-AI/pull/3325))

- *(arch)* Add VM roles reference and consolidate task tracking

- *(structure)* Move docs/plans/ to docs/archives/plans/

- *(index)* Rewrite INDEX.md as Obsidian vault home with full directory links

- *(nav)* Add _index.md navigation hubs for all docs directories

- Add AutoResearch M3 implementation plan (#2600)

- Add AutoResearch M3 design spec (#2600)

- *(frontend)* Document mockReset gotcha in vitest config (#3070) (#3147) ([#3147](https://github.com/mrveiss/AutoBot-AI/pull/3147))

- Add platform hardening plan and design spec (#3009)

- *(llm)* Document 6-tier model stack and remove redundant GPU models

- Remove stale passlib references after bcrypt 5.x migration (#2811) (#2930) ([#2930](https://github.com/mrveiss/AutoBot-AI/pull/2930))

- *(cleanup)* Update stale deepseek-r1:14b and llama3.2:3b refs (#2816) (#2924) ([#2924](https://github.com/mrveiss/AutoBot-AI/pull/2924))

- Shared dependency roles implementation plan (#2747)

- Shared dependency roles design spec (#2747)

- Fix remaining stale model names and broken links (#2734, #2736) (#2751) ([#2751](https://github.com/mrveiss/AutoBot-AI/pull/2751))

- Add public API reference and SDK quickstart (#1802) (#2714) ([#2714](https://github.com/mrveiss/AutoBot-AI/pull/2714))

- Add Quick Answer sections for Context7 benchmark (#1925) (#2719) ([#2719](https://github.com/mrveiss/AutoBot-AI/pull/2719))

- Update stale model names to 6-tier architecture (#2587) (#2729) ([#2729](https://github.com/mrveiss/AutoBot-AI/pull/2729))

- Update installation guide to match current install.sh (#2672) (#2712) ([#2712](https://github.com/mrveiss/AutoBot-AI/pull/2712))

- Update stale model names to 6-tier architecture (#2587)

- Final Python 3.12 alignment in test docs and guides (#2683)

- Align remaining docs to Python 3.12 (#2683)

- *(config)* Align remaining docs, agents, and scripts to Python 3.12 (#2683)

- *(install)* Update installation guide and add systemd check (#2672)

- Redis MCP bridge design (#2511)

- Remove stale run_autobot.sh references (#2468) ([#2485](https://github.com/mrveiss/AutoBot-AI/pull/2485))


### Features

- *(api)* Implement ChromaDB REST API endpoints (MVA-2046) (#9235) ([#9235](https://github.com/mrveiss/AutoBot-AI/pull/9235))

- *(transcriber)* Add transcript export formats (DOCX, PDF, SRT, VTT) [MVA-2211] (#9348) ([#9348](https://github.com/mrveiss/AutoBot-AI/pull/9348))

- *(mcp)* Build MCP resource browser and prompt template library UI (MVA-2167) (#9343) ([#9343](https://github.com/mrveiss/AutoBot-AI/pull/9343))

- *(claims-audit)* Implement report generator (MVA-2722) (#9335) ([#9335](https://github.com/mrveiss/AutoBot-AI/pull/9335))

- *(observability)* Add LangFuse and LangSmith tracing observers (#9012) (#9353) ([#9353](https://github.com/mrveiss/AutoBot-AI/pull/9353))

- *(transcriber/frontend)* Views & Integration (MVA-2051) (#9303) ([#9303](https://github.com/mrveiss/AutoBot-AI/pull/9303))

- *(connectors)* Add Nextcloud Documents connector via WebDAV (MVA-2039) (#9291) ([#9291](https://github.com/mrveiss/AutoBot-AI/pull/9291))

- *(landing)* Operator-focused copy, outcome-based cards, concrete deploy proof (#9298)

- *(landing)* Force-directed cluster graph background (#9298)

- *(landing)* Add particle mesh background animation to hero (#9298)

- *(transcriber/frontend)* Utility Components (MVA-2056) ([#9302](https://github.com/mrveiss/AutoBot-AI/pull/9302))

- *(transcriber/frontend)* Waveform & Core UI (MVA-2055) ([#9301](https://github.com/mrveiss/AutoBot-AI/pull/9301))

- *(analytics)* Consent Mode v2 banner + GDPR consent flow (#9298)

- *(docs)* Add Jekyll + just-the-docs with Ember color scheme (#9298)

- *(landing)* Geometric logo mark, GTM, scale/knowledge sections (#9298)

- *(landing)* Add scale, knowledge base, contribute, donate sections (#9298)

- *(landing)* Animated AutoBot landing page with Ember theme (#9298)

- *(mcp)* Implement resource subscriptions for real-time updates (MVA-2166) (#9275) ([#9275](https://github.com/mrveiss/AutoBot-AI/pull/9275))

- *(ansible)* Include AUTOBOT_BACKEND_HOST in backend deployment config (MVA-2418) ([#9280](https://github.com/mrveiss/AutoBot-AI/pull/9280))

- *(mcp)* Implement resources/prompts in git and knowledge bridges (MVA-2165)

- *(telegram)* Implement advanced Telegram bot features (MVA-2075) (#9273) ([#9273](https://github.com/mrveiss/AutoBot-AI/pull/9273))

- *(execution)* Snapshot API endpoints (MVA-2227, GH#4458) ([#9240](https://github.com/mrveiss/AutoBot-AI/pull/9240))

- *(execution)* Add snapshot interface to ExecutionBackend base class (MVA-2226, GH#4458) ([#9239](https://github.com/mrveiss/AutoBot-AI/pull/9239))

- *(tasks)* Implement snapshot cleanup Celery task (#4458)

- *(embed)* Implement missing /api/chats/embed/message backend endpoint (MVA-1759) ([#9234](https://github.com/mrveiss/AutoBot-AI/pull/9234))

- *(integrations)* Complete mobile device pairing with encryption and push (#4463) ([#9227](https://github.com/mrveiss/AutoBot-AI/pull/9227))

- *(integrations/microsoft365)* Wire now_utc for datetime normalisation (#MVA-2203) (#9217) ([#9217](https://github.com/mrveiss/AutoBot-AI/pull/9217))

- *(chat)* Add org-wide preset support (GH#4449) (#9222) ([#9222](https://github.com/mrveiss/AutoBot-AI/pull/9222))

- *(transcriber)* Add pipeline orchestration and merge logic (MVA-2186)

- *(mcp)* Implement resource/prompt infrastructure in filesystem bridge (#9213) ([#9213](https://github.com/mrveiss/AutoBot-AI/pull/9213))

- *(api)* Transcript AI Analysis & KB Integration (MVA-2176) ([#9212](https://github.com/mrveiss/AutoBot-AI/pull/9212))

- *(voice)* Language-keyed speech provider system (#9044)

- *(llm)* Per-run dynamic API key injection (GH#9037) (#9187) ([#9187](https://github.com/mrveiss/AutoBot-AI/pull/9187))

- *(llc-frontend)* Template browser UI for company creation wizard (#9164) (#9178) ([#9178](https://github.com/mrveiss/AutoBot-AI/pull/9178))

- *(integrations)* Telegram bot core integration (MVA-2074) (#9174) ([#9174](https://github.com/mrveiss/AutoBot-AI/pull/9174))

- *(sso)* Add OKTA provider type and endpoint templates (#9177) ([#9177](https://github.com/mrveiss/AutoBot-AI/pull/9177))

- *(chat)* Thinking mode toggle — per-conversation control for reasoning models (#8993) (#9172) ([#9172](https://github.com/mrveiss/AutoBot-AI/pull/9172))

- *(chat)* Thinking mode toggle, budget slider, and response indicator (#8993)

- *(llm)* Configure llama3.2:1b as trivial tier model (#9175) ([#9175](https://github.com/mrveiss/AutoBot-AI/pull/9175))

- *(frontend)* Add UI for agent abstention status (GH#6626) (#9171) ([#9171](https://github.com/mrveiss/AutoBot-AI/pull/9171))

- *(transcriber/frontend)* Add API composable, SSE progress, and Pinia store (#MVA-2054) (#9170) ([#9170](https://github.com/mrveiss/AutoBot-AI/pull/9170))

- *(ui)* Add user-selectable theme system with custom accent colors (#8988) (#9168) ([#9168](https://github.com/mrveiss/AutoBot-AI/pull/9168))

- *(llm)* Add lightweight mode cost indicator (MVA-1993) (#9176) ([#9176](https://github.com/mrveiss/AutoBot-AI/pull/9176))

- *(llm)* Register BedrockProvider in provider registry (#9010)

- *(llm)* AWS Bedrock provider with Claude, Llama, Mistral, Titan, Nova (#9010)

- *(integrations)* WhatsApp Business API channel adapter (#9007)

- *(llm)* Quota-triggered model fallback (#8998) (#9173) ([#9173](https://github.com/mrveiss/AutoBot-AI/pull/9173))

- *(plugins)* Plugin capability manifest — declare permissions and sandbox boundaries per plugin (#9049) (#9151) ([#9151](https://github.com/mrveiss/AutoBot-AI/pull/9151))

- *(llm)* Add trivial complexity tier for lightweight inference (#9050) (#9158) ([#9158](https://github.com/mrveiss/AutoBot-AI/pull/9158))

- *(llc)* Add built-in company templates (#9042) (#9163) ([#9163](https://github.com/mrveiss/AutoBot-AI/pull/9163))

- *(frontend)* Add context overflow warning UI and preference settings (MVA-2006) (#9162) ([#9162](https://github.com/mrveiss/AutoBot-AI/pull/9162))

- *(integrations)* Microsoft 365 Calendar, Outlook, and Teams connector (#9041)

- *(chat)* Context overflow protection — auto-summarize when approaching model context limit (#9043) (#9161) ([#9161](https://github.com/mrveiss/AutoBot-AI/pull/9161))

- *(plugins)* Add trust tier badges and capability API methods (#9165) ([#9165](https://github.com/mrveiss/AutoBot-AI/pull/9165))

- *(backend)* Lightweight inference mode — bypass RAG/memory for trivial tier (MVA-1992) (#9160) ([#9160](https://github.com/mrveiss/AutoBot-AI/pull/9160))

- *(plugins)* Add capability approval dialog and audit log UI (MVA-1989) (#9159) ([#9159](https://github.com/mrveiss/AutoBot-AI/pull/9159))

- *(connectors)* GitLab/Gitea/Forgejo KB connector — index repos and issues (#9011) (#9138) ([#9138](https://github.com/mrveiss/AutoBot-AI/pull/9138))

- *(frontend/css)* Migrate color tokens to OKLCH with hex fallbacks (GH#9014) ([#9139](https://github.com/mrveiss/AutoBot-AI/pull/9139))

- *(integrations)* Frontend for web push notifications (service worker + permission UI) (GH#4459) (#9135) ([#9135](https://github.com/mrveiss/AutoBot-AI/pull/9135))

- *(llc)* Per-agent memory wiki — knowledge vault scoped to agent role (#9021) ([#9130](https://github.com/mrveiss/AutoBot-AI/pull/9130))

- *(ui)* Global keyboard shortcut system for power-user navigation (#8989) (#9124) ([#9124](https://github.com/mrveiss/AutoBot-AI/pull/9124))

- *(chat)* Context window usage indicator (#8990) (#9126) ([#9126](https://github.com/mrveiss/AutoBot-AI/pull/9126))

- *(providers)* Add Google Cloud Vertex AI LLM provider (GH#9009) (#9125) ([#9125](https://github.com/mrveiss/AutoBot-AI/pull/9125))

- *(auth)* Shared chat link access control — password-protect shared conversations (#8996) (#9122) ([#9122](https://github.com/mrveiss/AutoBot-AI/pull/9122))

- *(media)* Image generation — DALL-E 3, Flux, Stable Diffusion (#9015) (#9120) ([#9120](https://github.com/mrveiss/AutoBot-AI/pull/9120))

- *(llc)* Persistent agent session state — checkpoint and recovery (GH#9026) ([#9083](https://github.com/mrveiss/AutoBot-AI/pull/9083))

- *(connectors)* ConnectorCredentialStore scaffolding per ADR-007 (#9019) (#9079) ([#9079](https://github.com/mrveiss/AutoBot-AI/pull/9079))

- *(llc/adapters)* Add CopilotLocalAdapter for gh copilot CLI sessions (#9008) (#9078) ([#9078](https://github.com/mrveiss/AutoBot-AI/pull/9078))

- *(integrations)* Backend for web push notifications (DB + VAPID + pywebpush) (GH#4459) (#8945) ([#8945](https://github.com/mrveiss/AutoBot-AI/pull/8945))

- *(code-sync)* Add Update This Server button to trigger SLM self-update from GUI (#9073)

- *(chat)* Add conversation folders and collections (#8987) (#9051) ([#9051](https://github.com/mrveiss/AutoBot-AI/pull/9051))

- *(agent-loop)* Assertion-based belief state on TaskContext (GH#6629) (#8956) ([#8956](https://github.com/mrveiss/AutoBot-AI/pull/8956))

- *(chat)* Add Presets settings tab for slash command preset management (GH#4449-2) (#8948) ([#8948](https://github.com/mrveiss/AutoBot-AI/pull/8948))

- *(frontend)* Embeddable chat widget for external websites (GH#4457) (#8943) ([#8943](https://github.com/mrveiss/AutoBot-AI/pull/8943))

- *(execution)* Sandbox state snapshot and restore for resumable agent sessions (GH#4458) (#8991) ([#8991](https://github.com/mrveiss/AutoBot-AI/pull/8991))

- *(voice)* Register voice_bundle_user router and add comprehensive tests (GH#8605)

- *(core)* Idempotent Paperclip API wrappers in autobot_shared (GH#8944) (#8946) ([#8946](https://github.com/mrveiss/AutoBot-AI/pull/8946))

- *(integrations)* Mobile device pairing for push and offline sync (GH#4463) (#8940) ([#8940](https://github.com/mrveiss/AutoBot-AI/pull/8940))

- *(execution)* Add env var configuration for Docker container pool (GH#4452)

- *(chat)* Add SlashCommandDropdown story and managePresets i18n key (GH#4449-2) ([#8937](https://github.com/mrveiss/AutoBot-AI/pull/8937))

- *(llc/kb)* Implement write guard — sub-company agents must not write to parent KB collections (#8598)

- *(npu)* Add heartbeat reachability check to pulse-probe (MVA-1399) (#8892) ([#8892](https://github.com/mrveiss/AutoBot-AI/pull/8892))

- *(belief-state)* Suppress re-queries when high-confidence assertion exists (MVA-1434) ([#8878](https://github.com/mrveiss/AutoBot-AI/pull/8878))

- *(belief-state)* Add ConfigFileExtractor for YAML/TOML/JSON (MVA-1433) ([#8877](https://github.com/mrveiss/AutoBot-AI/pull/8877))

- *(npu)* Architecture-aware SSM kernel path with NPU_SSM_ENABLED flag (MVA-1383) ([#8873](https://github.com/mrveiss/AutoBot-AI/pull/8873))

- *(backend)* Architecture-family dispatch table in attention_backend.py (MVA-1385, GH#7350) ([#8872](https://github.com/mrveiss/AutoBot-AI/pull/8872))

- *(backend)* Bypass 4K/8K context cap for non-transformer models (MVA-1387, GH#7351) ([#8871](https://github.com/mrveiss/AutoBot-AI/pull/8871))

- *(routing)* Add long_context tier to tiered_routing (MVA-1386, GH#7349) ([#8870](https://github.com/mrveiss/AutoBot-AI/pull/8870))

- *(router)* Add expected_output_tokens SSM routing factor (GH#7353) ([#8868](https://github.com/mrveiss/AutoBot-AI/pull/8868))

- *(slm-api)* Add rdp-credentials endpoint for xrdp nodes (MVA-1371) ([#8867](https://github.com/mrveiss/AutoBot-AI/pull/8867))

- *(heartbeat)* Add ERROR status to AgentRuntimeState (MVA-1411) ([#8866](https://github.com/mrveiss/AutoBot-AI/pull/8866))

- *(registry)* Add architecture_family field to model metadata (GH#7347) ([#8864](https://github.com/mrveiss/AutoBot-AI/pull/8864))

- *(rbac)* Per-user voice bundle assignment backend (MVA-1365) ([#8862](https://github.com/mrveiss/AutoBot-AI/pull/8862))

- *(npu-worker)* Add get_inference_engine() and wire into handle_partial_forward (MVA-1354) ([#8861](https://github.com/mrveiss/AutoBot-AI/pull/8861))

- *(npu)* Cross-host pipeline parallelism for 70B+ model sharding (GH#6737) ([#8859](https://github.com/mrveiss/AutoBot-AI/pull/8859))

- *(belief-state)* Prototype Assertion dataclasses + rule-based extractors + loop integration (MVA-1407) ([#8858](https://github.com/mrveiss/AutoBot-AI/pull/8858))

- *(browser)* Scrape template management UI panel (GH#5136 Phase 5) ([#8846](https://github.com/mrveiss/AutoBot-AI/pull/8846))

- *(llc/kb)* Implement write guard — sub-company agents must not write to parent KB (GH#8598) ([#8857](https://github.com/mrveiss/AutoBot-AI/pull/8857))

- *(orchestration)* Per-task git worktree workspace — Celery cleanup, API endpoint, base_agent cwd, tests (GH#6471) ([#8854](https://github.com/mrveiss/AutoBot-AI/pull/8854))

- *(browser)* AI-assisted region proposal endpoint + frontend magic-wand (MVA-1372) ([#8840](https://github.com/mrveiss/AutoBot-AI/pull/8840))

- *(a2a)* Continuous behavioural trust scoring for federated peers (MVA-1368) ([#8838](https://github.com/mrveiss/AutoBot-AI/pull/8838))

- *(browser)* ScrapeTemplate Redis model, CRUD endpoints & template runner (GH#5136 Phase 4) (#8837) ([#8837](https://github.com/mrveiss/AutoBot-AI/pull/8837))

- *(browser)* Wire AccessibilitySnapshot + add page_snapshot/intercept_api MCP tools (#5136 Phase 1, closes #5138) (#8834) ([#8834](https://github.com/mrveiss/AutoBot-AI/pull/8834))

- *(rdp)* Provision .26 (26-VNC) as RDP node — deploy xrdp on port 3389 (GH#1525) ([#8831](https://github.com/mrveiss/AutoBot-AI/pull/8831))

- *(heartbeat)* Add AgentStatus badge and Pause/Resume controls to HeartbeatPanel (GH#8732) (#8825) ([#8825](https://github.com/mrveiss/AutoBot-AI/pull/8825))

- *(execution)* Pre-warmed Docker container pool for fast sandbox cold start (GH#4452) (#8824) ([#8824](https://github.com/mrveiss/AutoBot-AI/pull/8824))

- *(api)* Add typed Python and TypeScript SDK packages for AutoBot API (GH#4454) (#8827) ([#8827](https://github.com/mrveiss/AutoBot-AI/pull/8827))

- *(ux)* Convert WorkflowBuilderView to URL-routed sections (GH#8750) (#8813) ([#8813](https://github.com/mrveiss/AutoBot-AI/pull/8813))

- *(heartbeat)* Wire SkillApproval into system-pause resume workflow (GH#8734)

- *(llc)* Wire GoalService.get_goal_ancestry_for_work_item() into production paths ([#8796](https://github.com/mrveiss/AutoBot-AI/pull/8796))

- *(a2a)* Behavioural trust score for federated peers (GH#7358) (#8736) ([#8736](https://github.com/mrveiss/AutoBot-AI/pull/8736))

- *(orchestration)* Goal ancestry as schema on Task model (GH#6469) (#8735) ([#8735](https://github.com/mrveiss/AutoBot-AI/pull/8735))

- *(agent-loop)* Semantic stagnation detector (GH#6627) (#8723) ([#8723](https://github.com/mrveiss/AutoBot-AI/pull/8723))

- *(mcp)* Plugin discovery for zero-downtime MCP bridge registration (GH#4462) (#8719) ([#8719](https://github.com/mrveiss/AutoBot-AI/pull/8719))

- *(heartbeat)* Add AgentStatus enum and status transition endpoints (GH#6476) ([#8724](https://github.com/mrveiss/AutoBot-AI/pull/8724))

- *(voice)* Cost + duration telemetry for Realtime WebRTC (GH#7421) ([#8720](https://github.com/mrveiss/AutoBot-AI/pull/8720))

- *(memory)* Trajectory learning store (GH#7357) ([#8717](https://github.com/mrveiss/AutoBot-AI/pull/8717))

- *(design-tokens)* Phase 4 ESLint rule — block deprecated size/color tokens in Vue templates (MVA-356) (#8714) ([#8714](https://github.com/mrveiss/AutoBot-AI/pull/8714))

- *(cost)* Auto-refresh MODEL_PRICING from provider APIs (GH#6480) ([#8692](https://github.com/mrveiss/AutoBot-AI/pull/8692))

- *(voice)* MCP tools as Realtime function tools (GH#7343) ([#8711](https://github.com/mrveiss/AutoBot-AI/pull/8711))

- *(coordination)* SharedRuntimeBag follow-up — integration test, AgentBudgetTracker, lint rule (GH#6630) ([#8693](https://github.com/mrveiss/AutoBot-AI/pull/8693))

- *(channels)* Expand gateway to 9+ platforms — Telegram, Signal, Matrix, iMessage (#8703) ([#8703](https://github.com/mrveiss/AutoBot-AI/pull/8703))

- *(rbac)* Per-user voice toolset bundle + settings UI (GH#7422) ([#8694](https://github.com/mrveiss/AutoBot-AI/pull/8694))

- *(design-tokens)* Add DEV prop validators for Size and Intent to base components (MVA-353) ([#8691](https://github.com/mrveiss/AutoBot-AI/pull/8691))

- *(llm)* Anthropic-format passthrough endpoint /v1/messages (GH#6591) ([#8689](https://github.com/mrveiss/AutoBot-AI/pull/8689))

- *(npu-worker)* Architecture-aware model loading — OpenVINO dispatch by architecture_family (GH#7352) ([#8682](https://github.com/mrveiss/AutoBot-AI/pull/8682))

- *(chat)* Preset management modal UI (GH#8596) ([#8688](https://github.com/mrveiss/AutoBot-AI/pull/8688))

- *(orchestration)* Per-task git worktree workspace for code-writing agents (GH#6471) (#8676) ([#8676](https://github.com/mrveiss/AutoBot-AI/pull/8676))

- *(design-tokens)* Codemod small→sm, medium→md, large→lg, danger→error (Phase 1) (#8680) ([#8680](https://github.com/mrveiss/AutoBot-AI/pull/8680))

- *(chat)* Slash command presets backend API endpoints (GH#8595) (#8678) ([#8678](https://github.com/mrveiss/AutoBot-AI/pull/8678))

- *(agent-loop)* Consult error_boundaries severity before retry (GH#6628) ([#8648](https://github.com/mrveiss/AutoBot-AI/pull/8648))

- *(voice)* Backend SDP proxy for OpenAI Realtime WebRTC (GH#7342) ([#8658](https://github.com/mrveiss/AutoBot-AI/pull/8658))

- *(docs)* Verification artifact — wired endpoint/test proof (GH#7359) ([#8677](https://github.com/mrveiss/AutoBot-AI/pull/8677))

- *(cost)* Budget Policies UI — BudgetPolicies.vue (GH#6470) ([#8672](https://github.com/mrveiss/AutoBot-AI/pull/8672))

- *(npu)* Auto-suggest profile from worker capabilities (GH#6738, MVA-1081) ([#8673](https://github.com/mrveiss/AutoBot-AI/pull/8673))

- *(npu)* Pre-fill pair-confirm dialog with recommended_profile + capabilities_summary (GH#6738, MVA-1138) ([#8671](https://github.com/mrveiss/AutoBot-AI/pull/8671))

- *(workers)* Background audit daemon on Celery Beat schedule (GH#7356) ([#8659](https://github.com/mrveiss/AutoBot-AI/pull/8659))

- *(llm/tiered-routing)* Add long_context tier alongside simple/complex (GH#7349) ([#8661](https://github.com/mrveiss/AutoBot-AI/pull/8661))

- *(npu-pipeline)* Provider_registry hook + latency guard (MVA-1099) (#8644) ([#8644](https://github.com/mrveiss/AutoBot-AI/pull/8644))

- *(npu)* Pulse-probe correctness check (GH#6739) (#8660) ([#8660](https://github.com/mrveiss/AutoBot-AI/pull/8660))

- *(agent-loop)* Wire ThinkResult.confidence into halt path — abstention (GH#6626) (#8665) ([#8665](https://github.com/mrveiss/AutoBot-AI/pull/8665))

- *(npu-pipeline)* ShardPlanner + PipelineDispatcher + peer failover (MVA-1096/1097) (#8662) ([#8662](https://github.com/mrveiss/AutoBot-AI/pull/8662))

- *(npu)* Cross-host pipeline dispatcher and integration tests (GH#6737) ([#8643](https://github.com/mrveiss/AutoBot-AI/pull/8643))

- *(npu-pipeline)* Worker partial-forward handler (MVA-1098) ([#8645](https://github.com/mrveiss/AutoBot-AI/pull/8645))

- *(orchestration)* GOAP-style state-space planner for WorkflowPlan (GH#7354) ([#8608](https://github.com/mrveiss/AutoBot-AI/pull/8608))

- *(cost)* Budget policy CRUD API + integration test (GH#6470) ([#8603](https://github.com/mrveiss/AutoBot-AI/pull/8603))

- *(llc)* Provider rate-limit recovery — exponential backoff + auto-resume on quota reset (GH#8502) ([#8607](https://github.com/mrveiss/AutoBot-AI/pull/8607))

- *(voice)* WebRTC Realtime mode in voice conversation UI (#7345) ([#8602](https://github.com/mrveiss/AutoBot-AI/pull/8602))

- *(ui)* Live Canvas — agent-driven visual canvas workspace (GH#7425) ([#8606](https://github.com/mrveiss/AutoBot-AI/pull/8606))

- *(orchestration)* Atomic task checkout via Redis lock (GH#6468) ([#8604](https://github.com/mrveiss/AutoBot-AI/pull/8604))

- *(chat)* Slash command presets — user-defined shortcut prompts (GH#4449) ([#8594](https://github.com/mrveiss/AutoBot-AI/pull/8594))

- *(llc/agents)* Haiku assistant tier — token efficiency (#8486) (#8590) ([#8590](https://github.com/mrveiss/AutoBot-AI/pull/8590))

- *(llc/agents)* Provider-agnostic cheap/senior model tier (#8487) (#8589) ([#8589](https://github.com/mrveiss/AutoBot-AI/pull/8589))

- *(scripts)* Test-first remediation loop + review agent guardrails (#8579) ([#8579](https://github.com/mrveiss/AutoBot-AI/pull/8579))

- *(llc/kb)* Agent capability indexing into company KB on hire/update (#8244)

- *(llc/kb)* Sub-company KB inheritance with parent read-through and weight decay (#8241)

- *(llc/kb)* HandoffBriefGenerator — AI→Human and Human→AI KB briefs (#8239)

- *(llc)* LLC system health probe — scheduler uptime, lag, budget metrics (#8259)

- *(llc/kb)* Sprint KB summarizer — LLM-summarize and merge into project KB on close (GH#8238)

- *(llc)* Board instant pause/resume/terminate controls — FR-GOV-05 (#8256)

- *(llc/frontend)* Company Portability UI — export, import preview, import execute (GH#8250) ([#8537](https://github.com/mrveiss/AutoBot-AI/pull/8537))

- *(llc/frontend)* Company Portability UI — export, import preview, import execute (GH#8250)

- *(llc/kb)* Board decision log writer — approvals indexed to company decisions KB (#8243) ([#8548](https://github.com/mrveiss/AutoBot-AI/pull/8548))

- *(llc)* Company template & snapshot export with secret scrubbing (#8245)

- *(llc/frontend)* Approvals Inbox + Cost Dashboard + Heartbeat Monitor + CEO Chat (#8249)

- *(llc/frontend)* Company Dashboard, Org Chart, Goal Tree, Sub-Company Tree (#8247)

- *(llc)* Work item file attachments — upload, storage, text extraction (#8253)

- *(llc)* Claude_code adapter — ClaudeCodeAdapter for heartbeat sessions (#8258)

- *(llc)* Cross-company template KB — platform-level template index (#8260)

- *(llc)* Notification routing service — relay llc:* Redis events to WebSocket (#8255)

- *(llc)* Work item relations — blocking, blocked-by, duplicate, relates-to (#8252)

- *(llc)* Work item label management — llc_labels table, CRUD API, assignment (#8254)

- *(llc)* Company import — collision detection, preview, namespace remapping (#8246)

- *(llc/kb)* Artifact ingestor — work products indexed into project KB on done (#8242)

- *(llc)* Outbound project management sync — wire LLC work item completion (#8257)

- *(llc/kb)* Agent diary KB writer — post-heartbeat hook on agent_diary.py (#8237)

- *(llc/kb)* KB collection lifecycle manager — create/archive per entity (GH#8235)

- *(llc)* Heartbeat context builder — parallel RAG assembly, fat payload (#8236)

- *(llc/frontend)* Backlog + Sprint Board + Kanban Board + Work Item Detail views (GH#8248) (#8525) ([#8525](https://github.com/mrveiss/AutoBot-AI/pull/8525))

- *(llc/kb)* AC suggester — RAG over company policies + past PBIs (GH#8240) ([#8522](https://github.com/mrveiss/AutoBot-AI/pull/8522))

- *(llc)* Union assignment model — human|agent co-assignees, co-working mode (#8230) (#8514) ([#8514](https://github.com/mrveiss/AutoBot-AI/pull/8514))

- *(llc)* Human review gate — mid-work-item approval step, configurable (#8234) (#8510) ([#8510](https://github.com/mrveiss/AutoBot-AI/pull/8510))

- *(llc)* Agent-to-human handoff — KB brief, reviewer notification (#8231) (#8511) ([#8511](https://github.com/mrveiss/AutoBot-AI/pull/8511))

- *(llc)* Human→Agent handoff — notes ingestion into work item KB, pickup (#8232) (#8509) ([#8509](https://github.com/mrveiss/AutoBot-AI/pull/8509))

- *(llc)* CEO Chat — company-scoped chat resolving to work objects via LLM+KB (#8233) ([#8507](https://github.com/mrveiss/AutoBot-AI/pull/8507))

- *(llm-routing)* Wire Claude as top-tier escalation provider with prompt caching (#8171) ([#8508](https://github.com/mrveiss/AutoBot-AI/pull/8508))

- *(llc)* Provider rate-limit recovery — exponential backoff + auto-resume (GH#8502) ([#8503](https://github.com/mrveiss/AutoBot-AI/pull/8503))

- *(llc)* Heartbeat scheduler — Redis sorted set, cron dispatch, restart-safe (#8225)

- *(llc)* LLC Routines API routes — CRUD, run history, manual trigger (GH#8229)

- *(llc)* RoutineService CRUD + env overlay + secret resolution (GH#8229)

- *(llc)* DB migration + SQLAlchemy models + enums for LLC Routines (#8229)

- *(llc)* LLC Routines — model, service, API, HeartbeatScheduler, pytest suite (GH#8229)

- *(llc)* Adapter protocol — process + http adapters (GH#8226) ([#8484](https://github.com/mrveiss/AutoBot-AI/pull/8484))

- *(llc)* AutoBot agent adapter — GH#8227 (PR #8480)

- *(llc)* AutoBot agent adapter — wraps base_agent.py for heartbeat dispatch (#8227)

- *(llc)* Liveness monitor + budget watchdog — stuck run detection, recovery action (GH#8228) ([#8481](https://github.com/mrveiss/AutoBot-AI/pull/8481))

- *(llc)* AutoBot agent adapter — wraps base_agent.py for heartbeat dispatch (#8227) ([#8480](https://github.com/mrveiss/AutoBot-AI/pull/8480))

- *(llc)* Kanban and Sprint board infrastructure (#8221) ([#8477](https://github.com/mrveiss/AutoBot-AI/pull/8477))

- *(llc)* Human workers as first-class assignees — membership + claim protocol (#8223) (#8475) ([#8475](https://github.com/mrveiss/AutoBot-AI/pull/8475))

- *(llc)* Sprint planning — capacity, velocity history, burndown (GH#8220) ([#8470](https://github.com/mrveiss/AutoBot-AI/pull/8470))

- *(llc)* Sprint auto-close — board approval gate, KB stub, rollover (GH#8224) ([#8471](https://github.com/mrveiss/AutoBot-AI/pull/8471))

- *(llc)* Backlog view API — priority ordering, bulk sprint assign, type/status filter (GH#8222) (#8469) ([#8469](https://github.com/mrveiss/AutoBot-AI/pull/8469))

- *(llc)* LLC API route group + agent-facing API keys (GH#8218) ([#8468](https://github.com/mrveiss/AutoBot-AI/pull/8468))

- *(llc)* Company-scoped secrets — versioned, encrypted, RBAC (GH#8217) (#8467) ([#8467](https://github.com/mrveiss/AutoBot-AI/pull/8467))

- *(llc)* Board approval gates — GH#8214 (#8458) ([#8458](https://github.com/mrveiss/AutoBot-AI/pull/8458))

- *(llc)* Immutable activity log — model, service, API, migration (GH#8216) ([#8457](https://github.com/mrveiss/AutoBot-AI/pull/8457))

- *(llc)* Per-agent budget enforcement — hard stop, soft alert, cost ingest (#8215) ([#8459](https://github.com/mrveiss/AutoBot-AI/pull/8459))

- *(llc)* GH#8212 4-level goal hierarchy — CRUD, ancestry, KB indexing ([#8451](https://github.com/mrveiss/AutoBot-AI/pull/8451))

- *(llc)* Company model extension — sub-companies, budget, issue prefix, status (#8211) ([#8452](https://github.com/mrveiss/AutoBot-AI/pull/8452))

- *(llc)* Work item hierarchy with atomic checkout (GH#8213) ([#8453](https://github.com/mrveiss/AutoBot-AI/pull/8453))

- *(canvas)* Phase 2C — CSP header + integration tests (MVA-486) ([#8450](https://github.com/mrveiss/AutoBot-AI/pull/8450))

- *(skills)* Community skill hub — install external MCP skills from registry (GH#4412) (#8430) ([#8430](https://github.com/mrveiss/AutoBot-AI/pull/8430))

- *(orchestration)* Extract retry_with_backoff + publish_event primitives, shrink Orchestrator to 779 lines (#5060) (#8394) ([#8394](https://github.com/mrveiss/AutoBot-AI/pull/8394))

- *(plugins)* Autobot-plugins/ monorepo + @autobot/terminal + @autobot/vnc (#4984 #4983 #4985) ([#8403](https://github.com/mrveiss/AutoBot-AI/pull/8403))

- *(vector-store,llm)* Batch K — LSM write buffer, tiering, HNSW prefetch, shared LLM rate limiter (#8377) ([#8377](https://github.com/mrveiss/AutoBot-AI/pull/8377))

- *(ui)* P1 migration — convert onMounted data-fetch showToast(error) to BaseAlert (MVA-357) ([#8375](https://github.com/mrveiss/AutoBot-AI/pull/8375))

- *(connectors)* Standardized acceptance test harness for AbstractConnector (#8151) ([#8368](https://github.com/mrveiss/AutoBot-AI/pull/8368))

- *(connectors)* Add config schema versioning and migration support (#8152) (#8367) ([#8367](https://github.com/mrveiss/AutoBot-AI/pull/8367))

- *(connectors)* ExternalConnectorAdapter subprocess adapter (#8150) (#8369) ([#8369](https://github.com/mrveiss/AutoBot-AI/pull/8369))

- *(ui)* P1 migration — convert form-submit showToast(error) to BaseAlert (MVA-355 spec §3/7) ([#8374](https://github.com/mrveiss/AutoBot-AI/pull/8374))

- *(tools/lint)* Add --fix mode to check_decorator_order.py (#6787) ([#8365](https://github.com/mrveiss/AutoBot-AI/pull/8365))

- *(code-analysis)* Add COMPOSABLE_OPPORTUNITY Vue detector (#6748) ([#8371](https://github.com/mrveiss/AutoBot-AI/pull/8371))

- *(orchestration/planner)* Async gap-fill resume path (#7431, ADR-006 Phase 3) (#8370) ([#8370](https://github.com/mrveiss/AutoBot-AI/pull/8370))

- *(ci)* Add smoke-test for docker-compose.hardened.yml (#8094) ([#8351](https://github.com/mrveiss/AutoBot-AI/pull/8351))

- *(llm)* Context_window_manager bypasses 4K/8K cap for non-transformer families (#7351) ([#8348](https://github.com/mrveiss/AutoBot-AI/pull/8348))

- *(llm)* Add ArchitectureFamily enum + attention_backend dispatch (#7347,#7350) ([#8345](https://github.com/mrveiss/AutoBot-AI/pull/8345))

- *(frontend)* Add TypeScript to KnowledgePersistenceDialog (#8329) ([#8336](https://github.com/mrveiss/AutoBot-AI/pull/8336))

- *(security)* Add GitHub security vulnerability reporting policy ([#8334](https://github.com/mrveiss/AutoBot-AI/pull/8334))

- *(rbac)* Named voice-context toolset bundles for MCP exposure (#7344) ([#8321](https://github.com/mrveiss/AutoBot-AI/pull/8321))

- *(llm/tiered-routing)* Add expected_output_tokens factor (#7353) ([#8320](https://github.com/mrveiss/AutoBot-AI/pull/8320))

- *(mcp)* Admin endpoints to generate/revoke scoped tokens (#6453) ([#8319](https://github.com/mrveiss/AutoBot-AI/pull/8319))

- *(frontend/icons)* Migrate 48 component files from FA to canonical Icon.vue (#6442, #4805) ([#8310](https://github.com/mrveiss/AutoBot-AI/pull/8310))

- *(llm)* Wire MCP tools into Ollama provider native function calling (#7911) ([#8305](https://github.com/mrveiss/AutoBot-AI/pull/8305))

- *(orchestration,schemas)* Redis-persist task-assignment state + typed result/AI-stack schemas (#6479, #6407, #6387) (#8309) ([#8309](https://github.com/mrveiss/AutoBot-AI/pull/8309))

- *(frontend)* Wire useFileSandbox() + host inventory UI (#7773, #7513) (#8293) ([#8293](https://github.com/mrveiss/AutoBot-AI/pull/8293))

- *(connectors)* Output schema validation, parallel sync, event hooks (#8147, #8148, #8149) ([#8289](https://github.com/mrveiss/AutoBot-AI/pull/8289))

- *(llm)* Wire MCP tools into Anthropic/OpenAI/Groq/CustomOpenAI providers (#7910) ([#8278](https://github.com/mrveiss/AutoBot-AI/pull/8278))

- *(connectors)* HTTP retry, typed auth, mid-sync checkpoint (#8144, #8145, #8146) ([#8277](https://github.com/mrveiss/AutoBot-AI/pull/8277))

- *(orchestration)* Wire-in orphaned modules + rename AgentRouter → TaskAgentScorer (GH #6820, #6819, #6816) ([#8101](https://github.com/mrveiss/AutoBot-AI/pull/8101))

- *(llm_shared)* Pluggable LLMObserver protocol — GH#6593 (#8100) ([#8100](https://github.com/mrveiss/AutoBot-AI/pull/8100))

- *(api)* Add x-llm-routed-from header + x-llm-cost test (GH#6589, GH#6592) (#8098) ([#8098](https://github.com/mrveiss/AutoBot-AI/pull/8098))

- *(system-health)* Data_callback extension for probe helpers — probe_batch_jobs re-migrated (#6914) (#8086) ([#8086](https://github.com/mrveiss/AutoBot-AI/pull/8086))

- *(security)* Semgrep rules, cosign signing, hardened compose, LLM routing strategies (#6595 #6596 #6597) (#8093) ([#8093](https://github.com/mrveiss/AutoBot-AI/pull/8093))

- *(orchestration)* Wire SuccessCriteriaEvaluator into DAGExecutor + WorkflowExecutor (#7887/#7888) ([#8087](https://github.com/mrveiss/AutoBot-AI/pull/8087))

- *(tls)* Canonical SSL context factory in autobot_shared/tls.py (#6702) ([#8089](https://github.com/mrveiss/AutoBot-AI/pull/8089))

- *(browser)* Wire snapshot-with-regions endpoint to PopoutChromiumBrowser (#6446) (#8081) ([#8081](https://github.com/mrveiss/AutoBot-AI/pull/8081))

- *(artifact-cells)* Implement ChartCell and CodeCell components (MVA-485) ([#8079](https://github.com/mrveiss/AutoBot-AI/pull/8079))

- *(canvas)* MSW mock layer for Live Canvas API (MVA-399) ([#8080](https://github.com/mrveiss/AutoBot-AI/pull/8080))

- *(a11y)* BaseAlert compact size variant + document role=alert (MVA-349) ([#8077](https://github.com/mrveiss/AutoBot-AI/pull/8077))

- *(canvas)* Live Canvas backend — MVA-359/362/370 (#8074) ([#8074](https://github.com/mrveiss/AutoBot-AI/pull/8074))

- *(toast)* Reduce max stack 5→3 with Tier C eviction protection (MVA-347) (#8049) ([#8049](https://github.com/mrveiss/AutoBot-AI/pull/8049))

- *(design-tokens)* Add canonical Size and Intent types (MVA-346) (#8039) ([#8039](https://github.com/mrveiss/AutoBot-AI/pull/8039))

- *(frontend)* Wire AutomationWorkflowStep into useWorkflowBuilder.WorkflowStep (closes #7123) (#7988) ([#7988](https://github.com/mrveiss/AutoBot-AI/pull/7988))

- *(system-health)* Add KnownProbes SSOT enum, use in batch_jobs and long_running probes (#6917) (#7915) ([#7915](https://github.com/mrveiss/AutoBot-AI/pull/7915))

- *(backend)* Centralize background scheduler registry (GH#6594) ([#7914](https://github.com/mrveiss/AutoBot-AI/pull/7914))

- *(voice)* Env_int_clamped helper + AUTOBOT_TTS_MAX_CHUNK_CHARS env var (GH #6824) (#7909) ([#7909](https://github.com/mrveiss/AutoBot-AI/pull/7909))

- *(dashboard)* Surface unwired-tracker modules metric in Code Quality Dashboard (#6871) (#7906) ([#7906](https://github.com/mrveiss/AutoBot-AI/pull/7906))

- *(routing)* Wire TopologyAwareRouter into AgentRouter as topology strategy (#6821) (#7904) ([#7904](https://github.com/mrveiss/AutoBot-AI/pull/7904))

- *(tools/lint)* Broaden check_no_src_mock_path with runtime resolution + caching (#7901) ([#7901](https://github.com/mrveiss/AutoBot-AI/pull/7901))

- *(agents)* Add LEDGER_VS_EXECUTOR rule to base agent prompts (#7380) (#7897) ([#7897](https://github.com/mrveiss/AutoBot-AI/pull/7897))

- *(canvas)* MVA-485 Phase 2B — ChartCell and CodeCell components with a11y (#485) (#7893) ([#7893](https://github.com/mrveiss/AutoBot-AI/pull/7893))

- *(canvas)* MVA-484 Phase 2A — Vega-Lite validation, rich_payload schema, headless SVG export (#7837) ([#7837](https://github.com/mrveiss/AutoBot-AI/pull/7837))

- *(components)* Add ErrorBanner base component (#7462 Phase A) (#7866) ([#7866](https://github.com/mrveiss/AutoBot-AI/pull/7866))

- *(canvas)* MVA-360 Phase 1 — Live Canvas frontend (#7823) ([#7823](https://github.com/mrveiss/AutoBot-AI/pull/7823))

- *(plugin-sdk)* Hooks registry + PluginLoadError + frontend mount registry (#6970, #6971, #6972) (#7792) ([#7792](https://github.com/mrveiss/AutoBot-AI/pull/7792))

- *(api/analytics)* Wire-in EngagementMetricsResponse — backend endpoint + frontend composable (#7111) (#7790) ([#7790](https://github.com/mrveiss/AutoBot-AI/pull/7790))

- *(plugin_sdk)* ManifestContract Protocol + UnifiedRegistry (GH#7369) (#7769) ([#7769](https://github.com/mrveiss/AutoBot-AI/pull/7769))

- *(frontend)* Implement useFileSandbox() composable (GH#7409) (#7772) ([#7772](https://github.com/mrveiss/AutoBot-AI/pull/7772))

- *(frontend)* Implement useFileSandbox() composable (GH#7409)

- *(frontend/a11y)* SLM canonical alignment + icon-only button aria-label audit (GH#7449, GH#7391)

- *(sandbox)* Implement api/sandbox_files.py + register in feature_routers.py (#7409)

- *(slm-frontend)* Storybook 10.x + vue-i18n setup (GH#7390, GH#7392) ([#7763](https://github.com/mrveiss/AutoBot-AI/pull/7763))

- *(frontend)* Add useNotificationBus composable + wire into 17 components (GH#7741) (#7759) ([#7759](https://github.com/mrveiss/AutoBot-AI/pull/7759))

- *(chromadb,tests)* Tag ChromaDB collections with provenance metadata + Redis fixture migration (GH#7427, GH#7280) ([#7756](https://github.com/mrveiss/AutoBot-AI/pull/7756))

- *(canvas)* Phase 1 Live Canvas backend — schema, API, state machine, export (MVA-359) (#7730) ([#7730](https://github.com/mrveiss/AutoBot-AI/pull/7730))

- *(knowledge)* WebResearchPanel 4-tab UI — Fetch Page / Crawl Site / Find Pages / Get Data (MVA-344) (#7726) ([#7726](https://github.com/mrveiss/AutoBot-AI/pull/7726))

- *(toast)* Reduce max stack 5→3 with Tier C eviction protection (MVA-347) (#7731) ([#7731](https://github.com/mrveiss/AutoBot-AI/pull/7731))

- *(a2a)* Outbound PII redaction pipeline — 14 detectors (#7355) ([#7744](https://github.com/mrveiss/AutoBot-AI/pull/7744))

- *(a2a)* Outbound PII redaction pipeline — 14 detectors + task_executor wire-in (#7355)

- *(design-tokens)* Add canonical Size and Intent types (MVA-346) ([#7725](https://github.com/mrveiss/AutoBot-AI/pull/7725))

- *(enums)* Consolidate TaskPriority and AgentStatus to canonical status_enums (#7504)

- *(security)* SEC-2 Phase 2 — wire run-JWT scope validation into MCP bridges (MVA-90) ([#7646](https://github.com/mrveiss/AutoBot-AI/pull/7646))

- *(security)* Mint run-scoped JWTs for heartbeat agents (SEC-2 #6473) (#7534) ([#7534](https://github.com/mrveiss/AutoBot-AI/pull/7534))

- *(llm-keys)* Virtual LLM API keys with per-key budgets (#6590) (#7617) ([#7617](https://github.com/mrveiss/AutoBot-AI/pull/7617))

- *(security)* Run-scoped short-lived JWTs to limit blast radius (#6473) (#7535) ([#7535](https://github.com/mrveiss/AutoBot-AI/pull/7535))

- *(slm/redis)* Wire TLS variables into redis-stack.conf.j2 (#6955)

- *(workflow)* #7431 Phase 3 — async gap-fill resume path for blocked plans (#7268) (#7517) ([#7517](https://github.com/mrveiss/AutoBot-AI/pull/7517))

- *(agent-tools)* Register web-research tools across chat + orchestration + MCP (#7509) (#7514) ([#7514](https://github.com/mrveiss/AutoBot-AI/pull/7514))

- *(knowledge/crawl)* Thin POST /knowledge/crawl endpoint (#7508) (#7512) ([#7512](https://github.com/mrveiss/AutoBot-AI/pull/7512))

- *(web_fetch)* Add WebFetcher.fetch_raw_html public API (closes #7476) (#7497) ([#7497](https://github.com/mrveiss/AutoBot-AI/pull/7497))

- *(web_fetch)* Add POST /knowledge/extract schema-driven structured data extraction (#7405) (#7482) ([#7482](https://github.com/mrveiss/AutoBot-AI/pull/7482))

- *(web_fetch)* Add POST /knowledge/site-map endpoint (#7403) (#7481) ([#7481](https://github.com/mrveiss/AutoBot-AI/pull/7481))

- *(orchestration/executor)* Wire skill_name dispatch into WorkflowExecutor (#7430 / #7268 Phase 2) (#7468) ([#7468](https://github.com/mrveiss/AutoBot-AI/pull/7468))

- *(web_search)* Add fetch_full mode to search_web tool (#7404) (#7465) ([#7465](https://github.com/mrveiss/AutoBot-AI/pull/7465))

- *(knowledge/crawl)* Wire max_depth + frontier + robots in WebCrawlerConnector (#7402) (#7464) ([#7464](https://github.com/mrveiss/AutoBot-AI/pull/7464))

- *(knowledge/scrape)* Consolidate scrape paths + new endpoint (#7401) (#7463) ([#7463](https://github.com/mrveiss/AutoBot-AI/pull/7463))

- *(orchestration/planner)* Wire StrategyPlanner → skill_router for plan-time skill resolution (#7268 Phase 1) (#7432) ([#7432](https://github.com/mrveiss/AutoBot-AI/pull/7432))

- *(web_fetch)* Foundation package with auto-detect render (#7400) (#7428) ([#7428](https://github.com/mrveiss/AutoBot-AI/pull/7428))

- *(test/fixtures)* Extend make_async_redis with pipeline + scan_iter support (closes #7339) (#7397) ([#7397](https://github.com/mrveiss/AutoBot-AI/pull/7397))

- *(tools/lint)* Pre-commit hook flagging patch("src.*") mock paths (closes #7165, closes #7173) (#7333) ([#7333](https://github.com/mrveiss/AutoBot-AI/pull/7333))

- *(codegen)* Extend MANIFEST to cover WorkflowStepStatus + RiskLevel (closes #7226) (#7269) ([#7269](https://github.com/mrveiss/AutoBot-AI/pull/7269))

- *(tests)* Canonical make_async_redis() + patch_async_redis() fixtures (#7264) (#7267) ([#7267](https://github.com/mrveiss/AutoBot-AI/pull/7267))

- *(plugin-sdk)* Declarative required_env field on PluginManifest (#6971) (#7256) ([#7256](https://github.com/mrveiss/AutoBot-AI/pull/7256))

- *(api/analytics)* Wire DateRangeParams as Depends() helper, migrate /timeline (#7110) (#7254) ([#7254](https://github.com/mrveiss/AutoBot-AI/pull/7254))

- *(tooling)* Minimal frontend codegen pipeline + drift CI guard (closes #7122) (#7222) ([#7222](https://github.com/mrveiss/AutoBot-AI/pull/7222))

- *(frontend)* Wire AutomationWorkflowStep into useWorkflowBuilder.WorkflowStep (closes #7123) (#7217) ([#7217](https://github.com/mrveiss/AutoBot-AI/pull/7217))

- *(orchestration)* Wire DEBUG mode + DebugController into workflow executor (closes #7206) (#7213) ([#7213](https://github.com/mrveiss/AutoBot-AI/pull/7213))

- *(workflow)* Lifecycle methods on canonical WorkflowTask + TaskStatus to autobot_shared (closes #7121, partial #6520) (#7212) ([#7212](https://github.com/mrveiss/AutoBot-AI/pull/7212))

- *(code-sync)* Add 'Resync from Source' button to drift report (closes #7149) (#7189) ([#7189](https://github.com/mrveiss/AutoBot-AI/pull/7189))

- *(workflow)* Canonical to_dict()/from_dict() helpers (closes #7124) (#7148) ([#7148](https://github.com/mrveiss/AutoBot-AI/pull/7148))

- *(frontend/health)* Wire /api/system/health/probes into probe-name lookups (#7008) (#7135) ([#7135](https://github.com/mrveiss/AutoBot-AI/pull/7135))

- *(workflow)* Phase 2F + #7044 — split TemplateStep, drop _legacy_step_dict, frontend codegen onto canonical (#6951) (#7112) ([#7112](https://github.com/mrveiss/AutoBot-AI/pull/7112))

- *(frontend/settings)* Wire 'Test backend connection' button (#6964, resolves #6845) (#7077) ([#7077](https://github.com/mrveiss/AutoBot-AI/pull/7077))

- *(intelligence)* Wire MockLLMService — fix broken demo __main__ blocks (#6994) (#7076) ([#7076](https://github.com/mrveiss/AutoBot-AI/pull/7076))

- *(install)* Env-var overrides for interactive prompts (#7057) (#7060) ([#7060](https://github.com/mrveiss/AutoBot-AI/pull/7060))

- *(hooks)* No-new-workflow-step pre-commit guard (#7014, closes #6951 Phase 4) (#7037) ([#7037](https://github.com/mrveiss/AutoBot-AI/pull/7037))

- *(workflow)* Phase 3 — orchestration.types WorkflowStep/Plan aliased to canonical (#6951) (#7011) ([#7011](https://github.com/mrveiss/AutoBot-AI/pull/7011))

- *(system-health)* Expose GET /api/system/health/probes (#6917) (#7003) ([#7003](https://github.com/mrveiss/AutoBot-AI/pull/7003))

- *(autobot_shared)* Add optional_import() helper to MissingDep (#6691) (#6999) ([#6999](https://github.com/mrveiss/AutoBot-AI/pull/6999))

- *(tools/lint)* Block dict-style access on LLMResponse (#6940) (#6996) ([#6996](https://github.com/mrveiss/AutoBot-AI/pull/6996))

- *(workflow)* Phase 2B — migrate enhanced_orchestration onto canonical WorkflowTask (#6951) (#6993) ([#6993](https://github.com/mrveiss/AutoBot-AI/pull/6993))

- *(workflow)* Phase 2A — migrate workflow_templates to canonical WorkflowTask (#6951) (#6985) ([#6985](https://github.com/mrveiss/AutoBot-AI/pull/6985))

- *(workflow)* Canonical WorkflowTask + WorkflowPlan in autobot_shared (#6951) (#6965) ([#6965](https://github.com/mrveiss/AutoBot-AI/pull/6965))

- *(ci)* Generalize hook→CI wrapper to no-direct-redis + no-print-console (closes #6785) (#6956) ([#6956](https://github.com/mrveiss/AutoBot-AI/pull/6956))

- *(frontend)* ESLint no-restricted-syntax rule blocking literal VM-IP fallbacks (closes #6784) (#6949) ([#6949](https://github.com/mrveiss/AutoBot-AI/pull/6949))

- *(closure-gate)* Layered defense against premature feature-issue closure (#6836) (#6875) ([#6875](https://github.com/mrveiss/AutoBot-AI/pull/6875))

- *(system-health)* Probe data enrichment + frontend caller migration (#6902 partial) (#6913) ([#6913](https://github.com/mrveiss/AutoBot-AI/pull/6913))

- *(system-health)* Sunset/Deprecation headers on legacy /api/<module>/health (#6902) (#6912) ([#6912](https://github.com/mrveiss/AutoBot-AI/pull/6912))

- *(system-health)* Post-#3333 follow-ups — boilerplate cleanup, KB metric, cache removal, breaker visibility, feature-routers probe (#6903 #6905 #6906 #6907 #6908) (#6910) ([#6910](https://github.com/mrveiss/AutoBot-AI/pull/6910))

- *(observability)* RAG per-stage timing + iconMappings non-string telemetry (#6791 #6796) (#6805) ([#6805](https://github.com/mrveiss/AutoBot-AI/pull/6805))

- *(observability)* Surface feature-router load status — escalate partial-boot to ERROR + new /api/health/feature-routers (#6797) (#6802) ([#6802](https://github.com/mrveiss/AutoBot-AI/pull/6802))

- *(code-analysis)* Wire LSP + consolidation rules through scanner finalize step (#6747) (#6754) ([#6754](https://github.com/mrveiss/AutoBot-AI/pull/6754))

- *(code-analysis)* Add enum/class consolidation detector to AntiPatternDetector (#6684) (#6736) ([#6736](https://github.com/mrveiss/AutoBot-AI/pull/6736))

- *(code-analysis)* Add LSP-violation detector to AntiPatternDetector (#6661) (#6735) ([#6735](https://github.com/mrveiss/AutoBot-AI/pull/6735))

- *(ci)* Add pre-commit lint check for @with_error_handling/@router decorator order (#6638) (#6714) ([#6714](https://github.com/mrveiss/AutoBot-AI/pull/6714))

- *(audit)* Add SESSION_EXPORT enum value and use it in chat_sessions export endpoint (#6639) (#6712) ([#6712](https://github.com/mrveiss/AutoBot-AI/pull/6712))

- *(frontend)* Unify /agents/* under tabbed AgentsLayout — each tab keeps its own URL (#6634) (#6635) ([#6635](https://github.com/mrveiss/AutoBot-AI/pull/6635))

- *(security)* Wire audit_record into chat_sessions.py session endpoints (#6559) (#6579) ([#6579](https://github.com/mrveiss/AutoBot-AI/pull/6579))

- *(deploy)* Add Celery Beat systemd service so periodic schedules fire (#6555) (#6560) ([#6560](https://github.com/mrveiss/AutoBot-AI/pull/6560))

- *(onboarding)* First-login redirect when no preset applied (#6452) (#6563) ([#6563](https://github.com/mrveiss/AutoBot-AI/pull/6563))

- *(hooks)* Block git checkout main and reset-to-protected to enforce worktree isolation (#6549) (#6550) ([#6550](https://github.com/mrveiss/AutoBot-AI/pull/6550))

- *(plugins)* User-extensible marketplace sources (#6481) (#6500) ([#6500](https://github.com/mrveiss/AutoBot-AI/pull/6500))

- *(nav)* Wire AgentActivity into App.vue navigation (#6451) (#6478) ([#6478](https://github.com/mrveiss/AutoBot-AI/pull/6478))

- *(plugins)* Add ZIP upload + Git URL install for 3rd-party plugins (#6464) (#6466) ([#6466](https://github.com/mrveiss/AutoBot-AI/pull/6466))

- *(security)* Wire audit_record into knowledge and API key mutation endpoints (#6386) (#6444) ([#6444](https://github.com/mrveiss/AutoBot-AI/pull/6444))

- *(ui)* Migrate Font Awesome icons to inline SVG in views + components (#4805) ([#6432](https://github.com/mrveiss/AutoBot-AI/pull/6432))

- *(browser)* Snapshot-with-regions endpoint + region overlay (#5136) ([#6424](https://github.com/mrveiss/AutoBot-AI/pull/6424))

- *(perf)* Move memory write-path off chat hot path via stop/pre-compact hooks (#5073) (#6441) ([#6441](https://github.com/mrveiss/AutoBot-AI/pull/6441))

- *(chat)* Tiered L0-L3 context wake-up to replace unconditional prompt injection (#5066) (#6436) ([#6436](https://github.com/mrveiss/AutoBot-AI/pull/6436))

- *(mcp)* Expose AutoBot memory/KB/graph as MCP server for external clients (#5072) (#6435) ([#6435](https://github.com/mrveiss/AutoBot-AI/pull/6435))

- *(agents)* Per-agent diary with background append and runtime discovery (#5071) (#6434) ([#6434](https://github.com/mrveiss/AutoBot-AI/pull/6434))

- *(skills)* Open skill-manifest standard + external repo import (#5063) (#6427) ([#6427](https://github.com/mrveiss/AutoBot-AI/pull/6427))

- *(onboarding)* Starter presets + system-health doctor for first-run UX (#5061) (#6426) ([#6426](https://github.com/mrveiss/AutoBot-AI/pull/6426))

- *(memory)* Verbatim conversational-memory lane alongside summarized store (#5070) (#6425) ([#6425](https://github.com/mrveiss/AutoBot-AI/pull/6425))

- *(schemas_chat)* Type chat_sessions DataResponse endpoints (#6405) (#6408) ([#6408](https://github.com/mrveiss/AutoBot-AI/pull/6408))

- *(security)* Add structured audit log service with Redis storage and admin query API (#4456) (#6385) ([#6385](https://github.com/mrveiss/AutoBot-AI/pull/6385))

- *(backend)* Add append-only compliance event log with Redis storage and admin query API (#4461) (#6365) ([#6365](https://github.com/mrveiss/AutoBot-AI/pull/6365))

- *(frontend)* Add 'Open in new window' button to DesktopInterface toolbar (#6362) (#6364) ([#6364](https://github.com/mrveiss/AutoBot-AI/pull/6364))

- *(frontend)* Wire DesktopInterface VNC into /slm/tools/novnc view and chat tab (#4977) (#6359) ([#6359](https://github.com/mrveiss/AutoBot-AI/pull/6359))

- *(frontend)* Wire useRequestQueue into ChatController.sendMessage for concurrency control (#6313) (#6355) ([#6355](https://github.com/mrveiss/AutoBot-AI/pull/6355))

- *(plugins)* Add Marketplace tab to PluginsView — merged from standalone /marketplace (#6347)

- *(chat)* Add sources field to chat messages for RAG citation tracking (#4448) (#6310) ([#6310](https://github.com/mrveiss/AutoBot-AI/pull/6310))

- *(skills)* Add MCPSpan tracing per tool call with Redis storage and traces API (#4413) (#6308) ([#6308](https://github.com/mrveiss/AutoBot-AI/pull/6308))

- *(skills)* Add builtin web_fetch, youtube_transcript, github_search, rss_reader skill entries (#4422) (#6296) ([#6296](https://github.com/mrveiss/AutoBot-AI/pull/6296))

- *(frontend)* Add useRequestQueue composable with priority queue and deduplication (#4415) (#6295) ([#6295](https://github.com/mrveiss/AutoBot-AI/pull/6295))

- *(frontend)* Add signal?: AbortSignal to RequestOptions in ApiClient (#6257) (#6267) ([#6267](https://github.com/mrveiss/AutoBot-AI/pull/6267))

- *(frontend)* Migrate multi-value spacing shorthands to design tokens (#4947) (#6239) ([#6239](https://github.com/mrveiss/AutoBot-AI/pull/6239))

- *(tooling)* Add resolve_schema_conflicts.py with AST validation (#6113) (#6208) ([#6208](https://github.com/mrveiss/AutoBot-AI/pull/6208))

- *(composables)* Add useConfirmDialog + ConfirmDialog.vue; register in App.vue (#6092) (#6172) ([#6172](https://github.com/mrveiss/AutoBot-AI/pull/6172))

- *(lint)* Add no-local-schemas pre-commit hook to enforce domain schema separation (#6056) (#6124) ([#6124](https://github.com/mrveiss/AutoBot-AI/pull/6124))

- *(types)* Eliminate any types in composables and stores (#5950) (#6121) ([#6121](https://github.com/mrveiss/AutoBot-AI/pull/6121))

- *(api)* Add @with_error_handling to all remaining API routes — full coverage (#5999) (#6067) ([#6067](https://github.com/mrveiss/AutoBot-AI/pull/6067))

- *(composables)* Add AbortController race protection to 7 fetchWithAuth composables (#5944) (#6065) ([#6065](https://github.com/mrveiss/AutoBot-AI/pull/6065))

- *(composables)* Add AbortController race protection to 7 fetchWithAuth composables (#5944) (#6063) ([#6063](https://github.com/mrveiss/AutoBot-AI/pull/6063))

- *(api)* Add @with_error_handling to all remaining API routes — full coverage (#5999) (#6062) ([#6062](https://github.com/mrveiss/AutoBot-AI/pull/6062))

- *(tools)* Add schema-split scripts for future domain re-splits (#5932) (#5972) ([#5972](https://github.com/mrveiss/AutoBot-AI/pull/5972))

- *(lint)* Add single-assignment variable tracking to check_response_models (#5926) (#5941) ([#5941](https://github.com/mrveiss/AutoBot-AI/pull/5941))

- *(lint)* Add check_response_models pre-commit hook for DataResponse safety (#5913) (#5918) ([#5918](https://github.com/mrveiss/AutoBot-AI/pull/5918))

- *(tools)* Add ToolOutputFilter 15-method pipeline (#5862) ([#5886](https://github.com/mrveiss/AutoBot-AI/pull/5886))

- *(tools)* Add ToolOutputFilter service with YAML config and 3 integration points (#5862) (#5882) ([#5882](https://github.com/mrveiss/AutoBot-AI/pull/5882))

- *(planner)* Wire compress_description into chat_completion_optimized (#5827) (#5858) ([#5858](https://github.com/mrveiss/AutoBot-AI/pull/5858))

- *(api)* Add response_model= to wake_word, analytics_cost, conversation_files, files (#5317) (#5833) ([#5833](https://github.com/mrveiss/AutoBot-AI/pull/5833))

- *(api)* Add response_model= to advanced_control, analytics, integration_github, npu_workers (#5317) (#5832) ([#5832](https://github.com/mrveiss/AutoBot-AI/pull/5832))

- *(api)* Add response_model= to remaining analytics endpoints (#5317) (#5821) ([#5821](https://github.com/mrveiss/AutoBot-AI/pull/5821))

- *(api)* Add response_model= to analytics_architecture, cfg, code, export, pattern_learning, quality (#5317) (#5818) ([#5818](https://github.com/mrveiss/AutoBot-AI/pull/5818))

- *(api)* Add response_model= to remaining knowledge endpoints (#5317) (#5813) ([#5813](https://github.com/mrveiss/AutoBot-AI/pull/5813))

- *(api)* Add response_model= to remaining knowledge endpoints (#5317) (#5811) ([#5811](https://github.com/mrveiss/AutoBot-AI/pull/5811))

- *(api)* Add response_model= to cache_management, monitoring, settings (#5317) (#5810) ([#5810](https://github.com/mrveiss/AutoBot-AI/pull/5810))

- *(api)* Add response_model= to mcp_registry, knowledge_ai_stack, http_client_mcp, feature_flags, database_mcp (#5317) ([#5793](https://github.com/mrveiss/AutoBot-AI/pull/5793))

- *(api)* Add response_model= to logs, git_mcp, analytics_llm_patterns, voice, skills_governance (#5317) ([#5792](https://github.com/mrveiss/AutoBot-AI/pull/5792))

- *(api)* Add response_model= to research_browser, metrics, enterprise_features, web_research_settings, orchestration (#5317) ([#5791](https://github.com/mrveiss/AutoBot-AI/pull/5791))

- *(api)* Add response_model= to analytics_bug_prediction, continuous_learning, maintenance, precommit (#5317) (#5789) ([#5789](https://github.com/mrveiss/AutoBot-AI/pull/5789))

- *(api)* Add response_model= to templates, state_tracking, secrets, development_speedup, analytics_code_review (#5317) ([#5785](https://github.com/mrveiss/AutoBot-AI/pull/5785))

- *(api)* Add response_model= to knowledge_metadata, knowledge_collections, knowledge_categories, validation_dashboard (#5317) ([#5784](https://github.com/mrveiss/AutoBot-AI/pull/5784))

- *(api)* Add response_model= to analytics precommit, maintenance, continuous_learning, bug_prediction (#5317) ([#5783](https://github.com/mrveiss/AutoBot-AI/pull/5783))

- *(api)* Add response_model= to filesystem_mcp, knowledge_tags, scheduler, error_monitoring (#5317) ([#5782](https://github.com/mrveiss/AutoBot-AI/pull/5782))

- *(api)* Add response_model= to playwright, skills, log_forwarding, ide_integration (#5317) ([#5781](https://github.com/mrveiss/AutoBot-AI/pull/5781))

- *(api)* Add response_model= to system, security_assessment, memory, agent_terminal (#5317) ([#5780](https://github.com/mrveiss/AutoBot-AI/pull/5780))

- *(api)* Add response_model= to llm endpoints (#5317) ([#5765](https://github.com/mrveiss/AutoBot-AI/pull/5765))

- *(api)* Add response_model= to chat endpoints (#5317) ([#5764](https://github.com/mrveiss/AutoBot-AI/pull/5764))

- *(api)* Add response_model= to agent and ai_stack endpoints (#5317) (#5763) ([#5763](https://github.com/mrveiss/AutoBot-AI/pull/5763))

- *(api)* Add response_model= to chat endpoints (#5317) (#5762) ([#5762](https://github.com/mrveiss/AutoBot-AI/pull/5762))

- *(api)* Add response_model= to vnc_manager, vnc_mcp, vnc_proxy, browser_mcp endpoints (#5317) (#5759) ([#5759](https://github.com/mrveiss/AutoBot-AI/pull/5759))

- *(api)* Add response_model= to code_intelligence, code_search endpoints (#5317) (#5757) ([#5757](https://github.com/mrveiss/AutoBot-AI/pull/5757))

- *(api)* Add schemas_common.py and wire response_model into terminal endpoints (#5739) (#5755) ([#5755](https://github.com/mrveiss/AutoBot-AI/pull/5755))

- *(redis)* Add AsyncRedisClientLockedMixin; fix unawaited bug + migrate analytics_embedding_patterns (#5710) (#5719) ([#5719](https://github.com/mrveiss/AutoBot-AI/pull/5719))

- *(utils)* Add async_lazy_singleton primitive + migrate 7 async singleton patterns (#5632) (#5658) ([#5658](https://github.com/mrveiss/AutoBot-AI/pull/5658))

- *(composables)* UsePollingJob accepts Ref<number> | number for intervalMs (#5586) (#5635) ([#5635](https://github.com/mrveiss/AutoBot-AI/pull/5635))

- *(provision)* Clean task names, phase chips, heartbeat indicator (#5610)

- *(provision)* Add slow-task hints for pip filtering, package installs, rsync

- *(install)* Stream Ansible output live during deployment

- *(backend)* Add response_model= audit report + first batch of 7 endpoints (#5317) (#5599) ([#5599](https://github.com/mrveiss/AutoBot-AI/pull/5599))

- *(frontend)* Generate api.ts from live OpenAPI spec (898 schemas, #5317)

- *(api-contract)* Add 85 frontend type aliases for all #5317 KB response/request schemas (#5488) (#5555) ([#5555](https://github.com/mrveiss/AutoBot-AI/pull/5555))

- *(useFetchEndpoint)* Per-request context hook threaded through callbacks (#5457) (#5523) ([#5523](https://github.com/mrveiss/AutoBot-AI/pull/5523))

- *(backend)* Add response_model= to knowledge_mcp.py and knowledge_rag_feedback.py (#5317 batch 4c) (#5501) ([#5501](https://github.com/mrveiss/AutoBot-AI/pull/5501))

- *(backend)* Add response_model= to knowledge_mcp.py and knowledge_rag_feedback.py (#5317 batch 4c) (#5500) ([#5500](https://github.com/mrveiss/AutoBot-AI/pull/5500))

- *(backend)* Add response_model= to api/knowledge_vectorization.py endpoints (#5317 batch 4a) (#5499) ([#5499](https://github.com/mrveiss/AutoBot-AI/pull/5499))

- *(backend)* Add response_model= to api/knowledge_maintenance.py endpoints (#5317 batch 3a) (#5497) ([#5497](https://github.com/mrveiss/AutoBot-AI/pull/5497))

- *(backend)* Add response_model= to api/knowledge_population.py endpoints (#5317 batch 3b) (#5496) ([#5496](https://github.com/mrveiss/AutoBot-AI/pull/5496))

- *(backend)* Add response_model= to api/knowledge_rag.py endpoints (#5317 batch 3c) (#5495) ([#5495](https://github.com/mrveiss/AutoBot-AI/pull/5495))

- *(backend)* Add response_model= to api/knowledge_search.py endpoints (#5317 batch 2) (#5492) ([#5492](https://github.com/mrveiss/AutoBot-AI/pull/5492))

- *(backend)* Add response_model= to remaining 20 api/knowledge.py endpoints (#5317 batch 1b) (#5483) ([#5483](https://github.com/mrveiss/AutoBot-AI/pull/5483))

- *(backend)* Add response_model= to 13 api/knowledge.py endpoints (#5317 batch 1a) (#5480) ([#5480](https://github.com/mrveiss/AutoBot-AI/pull/5480))

- *(useFocusTrap)* IsTabbable filter for aria-hidden + inert + display:none (closes #5373) (#5481) ([#5481](https://github.com/mrveiss/AutoBot-AI/pull/5481))

- *(observability)* Wire 10+ KB degradation sites with differentiated reason labels (#5407) (#5451) ([#5451](https://github.com/mrveiss/AutoBot-AI/pull/5451))

- *(composables)* Extract useInitialFocus + full-kit 2 missed dialogs (closes #5410 #5411) (#5417) ([#5417](https://github.com/mrveiss/AutoBot-AI/pull/5417))

- *(utils)* Wire in semantic_chunker_gpu_optimized module (#5395 follow-up) (#5415) ([#5415](https://github.com/mrveiss/AutoBot-AI/pull/5415))

- *(useFetchEndpoint)* FallbackData option + migrate _fetchEnvironmentExportData (#5389) (#5409) ([#5409](https://github.com/mrveiss/AutoBot-AI/pull/5409))

- *(knowledge)* Add AsyncBaseCollection + AsyncBaseClient ABCs + ChromaDB/InMemory adapters (#5316) (#5400) ([#5400](https://github.com/mrveiss/AutoBot-AI/pull/5400))

- *(composables)* Extract useFocusRestore + migrate 3 dialogs (#5356) (#5382) ([#5382](https://github.com/mrveiss/AutoBot-AI/pull/5382))

- *(analytics)* Per-section loading spinners in Hardcodes/Duplicates/Declarations (#5368) (#5376) ([#5376](https://github.com/mrveiss/AutoBot-AI/pull/5376))

- *(composables)* Extract useFocusTrap + migrate BaseModal + HostSelectionDialog (#5130) (#5343) ([#5343](https://github.com/mrveiss/AutoBot-AI/pull/5343))

- *(observability)* Add Prometheus counter + warning log on kb_connected=false (#5319) (#5346) ([#5346](https://github.com/mrveiss/AutoBot-AI/pull/5346))

- *(composables)* Add selectByKey/toggleByKey to useBatchSelection + migrate 4 consumers (#5328) (#5329) ([#5329](https://github.com/mrveiss/AutoBot-AI/pull/5329))

- *(composables)* Extract useExpansion<Key> primitive + migrate 8 sites (#5306) (#5308) ([#5308](https://github.com/mrveiss/AutoBot-AI/pull/5308))

- *(knowledge)* Distinguish empty-KB vs broken-KB with clear CTA panels (#5201) (#5287) ([#5287](https://github.com/mrveiss/AutoBot-AI/pull/5287))

- *(shared)* Add now_utc() helper + migrate 23 dataclass default_factory sites (#5211 phases B1+B2) (#5289) ([#5289](https://github.com/mrveiss/AutoBot-AI/pull/5289))

- *(composables)* Extract useDebouncedSearch primitive (#5198) (#5285) ([#5285](https://github.com/mrveiss/AutoBot-AI/pull/5285))

- *(composables)* Extract useFakeProgress + migrate KnowledgeAdvanced sites (#5237) (#5275) ([#5275](https://github.com/mrveiss/AutoBot-AI/pull/5275))

- *(backend)* Expose KB stats as Pydantic response_models for OpenAPI type-gen (#5248) (#5274) ([#5274](https://github.com/mrveiss/AutoBot-AI/pull/5274))

- *(ui)* Migrate Font Awesome to Icon component in 4 ui files (#5025) (#5255) ([#5255](https://github.com/mrveiss/AutoBot-AI/pull/5255))

- *(composables)* Extract useBatchSelection + refactor useKnowledgeVectorization to use it (#5192) (#5242) ([#5242](https://github.com/mrveiss/AutoBot-AI/pull/5242))

- *(composables)* Extract usePollingJob<T> + migrate KB job-status pollers (#5191) (#5241) ([#5241](https://github.com/mrveiss/AutoBot-AI/pull/5241))

- *(platform)* Add OpenAPI-driven frontend type generation (#5209) (#5229) ([#5229](https://github.com/mrveiss/AutoBot-AI/pull/5229))

- *(visual)* Visual regression tests for Storybook stories (#5077) (#5221) ([#5221](https://github.com/mrveiss/AutoBot-AI/pull/5221))

- *(tools)* Add pre-push git hook enforcing Phase 0c + Phase 6 (#5142 #5143) (#5205) ([#5205](https://github.com/mrveiss/AutoBot-AI/pull/5205))

- *(docs)* Mirror team-implement skill into repo (#5094) (#5188) ([#5188](https://github.com/mrveiss/AutoBot-AI/pull/5188))

- *(tools)* Add tools/codemods/ with proven Vue parseApiResponse codemod (#5150) (#5185) ([#5185](https://github.com/mrveiss/AutoBot-AI/pull/5185))

- *(composables)* Add useApiResource<T> reactive primitive (#5149) (#5161) ([#5161](https://github.com/mrveiss/AutoBot-AI/pull/5161))

- *(benchmarks)* Enforce held-out dev/test split for RAG benchmarks (#5074) (#5146) ([#5146](https://github.com/mrveiss/AutoBot-AI/pull/5146))

- *(rag)* Introduce BaseCollection + BaseClient ABCs for pluggable vector backends (#5062) (#5129) ([#5129](https://github.com/mrveiss/AutoBot-AI/pull/5129))

- *(events)* Add canonical event_type constants module to prevent casing drift (#5014)

- *(security)* Prompt-injection sanitizer for KB queries and documents (#5064) (#5117) ([#5117](https://github.com/mrveiss/AutoBot-AI/pull/5117))

- *(primitives)* Add bounded_gather helper + unit tests (#5059)

- *(knowledge)* Per-org LLM and embedding model config with ssot fallback (#4451)

- *(knowledge)* Add document_sync_queues model with priority-ordered re-indexing (#4453)

- *(knowledge)* Cleanup_orphan_documents + cleanup_generated_files scheduled tasks (#4455)

- *(knowledge)* Add tier attribute to connectors and KnowledgeBrowser readiness badge (#4421)

- *(knowledge)* Add /connectors/health endpoint aggregating test_connection() across registry (#4420)

- *(testing)* Report missing requirements.txt deps in pytest session header (#5032)

- *(ui)* Migrate Font Awesome icons to inline SVG via shared Icon component (#4805)

- *(chat)* Add multi-model comparison fan-out with concurrent SSE streaming (#4414)

- *(api)* Add OpenAI-compatible /v1/chat/completions and /v1/models endpoints (#4447)

- *(usage)* Add personal tab, period selector, and admin tab to UsageView (#4442)

- *(nav)* Wire useNavOverflow into desktop nav — overflow items collapse to More dropdown

- *(nav)* Add NavOverflowMenu component with teleported dropdown and active-route highlight

- *(nav)* Add useNavOverflow composable with ResizeObserver-based overflow detection

- *(media)* Add Jina Reader fast-path to LinkPipeline with BeautifulSoup fallback (#4419)

- *(i18n)* Add CI check script for missing i18n keys (#4826)

- *(rag)* Wire rag_benchmarks into RetrievalLearner feedback loop (#4676)

- *(agent_terminal)* Add countdown timer to tool approval dialog (#4960)

- *(kb)* Search() on DocIndexerService merges autobot_docs into RAGService results (#4953)

- *(about)* Replace placeholder with real About page content

- *(rag)* Consume source_provenance in reranking/response (#4836)

- *(knowledge)* Wire CodeIndexer into DocIndexer pipeline (#4835)

- *(mesh)* Wire CommunityClusterer into production scheduler (#4834)

- *(knowledge)* Add tree-sitter AST code indexer with SHA-256 cache (#4820)

- *(mesh)* Add CommunityCluserer with Leiden anchor seeding (#4819)

- *(mesh)* Add get_anchor_neighbors() to MeshDB + MeshDBAdapter (#4819)

- *(mesh)* Add source_provenance field to GraphRAGService relation metadata (#4818)

- *(knowledge)* Autonomous improvement loop — self-directed RAG/synthesis optimization (#4680) (#4782) ([#4782](https://github.com/mrveiss/AutoBot-AI/pull/4782))

- *(knowledge)* Autonomous synthesis prompt evolution — UCB1 variant selection with provenance-based scoring (#4675) (#4777) ([#4777](https://github.com/mrveiss/AutoBot-AI/pull/4777))

- *(frontend)* Wire DesktopContextPanel into DesktopInterface as collapsible context panel (#4771) (#4776) ([#4776](https://github.com/mrveiss/AutoBot-AI/pull/4776))

- *(frontend)* Wire DesktopView.vue as /desktop route — re-enables direct desktop access (#4704) (#4773) ([#4773](https://github.com/mrveiss/AutoBot-AI/pull/4773))

- *(slm-frontend)* Wire ServicesView.vue as direct /services route (#4762) (#4772) ([#4772](https://github.com/mrveiss/AutoBot-AI/pull/4772))

- *(rag)* Session-adaptive reranking — close feedback loop into live weights (#4690) (#4768) ([#4768](https://github.com/mrveiss/AutoBot-AI/pull/4768))

- *(knowledge)* Evolutionary lineage tracking — parent→child chain for synthesis outputs and KB entities (#4681) (#4767) ([#4767](https://github.com/mrveiss/AutoBot-AI/pull/4767))

- *(frontend)* Wire AgentRegistryView into router at /agents/registry (#4703)

- *(agents)* Add circuit breaker unit tests for issue #4694

- *(agents)* Add circuit breaker for unhealthy distributed agents (#4694)

- *(slm-frontend)* Wire RolesView.vue into router (#4706) (#4752) ([#4752](https://github.com/mrveiss/AutoBot-AI/pull/4752))

- *(slm-frontend)* Wire InfrastructureSettings.vue into router (#4705) (#4751) ([#4751](https://github.com/mrveiss/AutoBot-AI/pull/4751))

- *(frontend)* Wire AgentRegistryView into router at /agents/registry (#4703) (#4750) ([#4750](https://github.com/mrveiss/AutoBot-AI/pull/4750))

- *(agents)* Add circuit breaker for unhealthy distributed agents (#4694) (#4747) ([#4747](https://github.com/mrveiss/AutoBot-AI/pull/4747))

- *(agents)* Add self-critique reflection pass in subagent orchestrator (#4691)

- *(a2a)* Add self-evaluation quality gate before COMPLETED state (#4687)

- *(knowledge)* Add Cognition Store seeding layer to prevent cold-start (#4679)

- *(knowledge)* Per-collection synthesis_model override in synthesis_schema.yaml (#4688)

- *(rag)* Add UCB1 sampling to RetrievalLearner for exploration/exploitation balance (#4674)

- *(rag)* Add RealKBBenchmarks with real ChromaDB precision@k tests (#4697)

- *(knowledge)* Route synthesis output to schema-defined synthesis_target collections (#4635) (#4642) ([#4642](https://github.com/mrveiss/AutoBot-AI/pull/4642))

- *(knowledge)* Wire synthesis_schema into KBSynthesizer prompt selection (#4614) (#4629) ([#4629](https://github.com/mrveiss/AutoBot-AI/pull/4629))

- *(knowledge)* Wire synthesis_schema into KBSynthesizer prompt selection (#4614) (#4623) ([#4623](https://github.com/mrveiss/AutoBot-AI/pull/4623))

- *(knowledge)* Add synthesis provenance log to Redis stream (#4567) (#4588) ([#4588](https://github.com/mrveiss/AutoBot-AI/pull/4588))

- *(knowledge)* Add schema-driven synthesis config to DocIndexer (#4565) (#4586) ([#4586](https://github.com/mrveiss/AutoBot-AI/pull/4586))

- *(knowledge)* Add semantic contradiction detection + /knowledge/lint endpoint (#4566) (#4587) ([#4587](https://github.com/mrveiss/AutoBot-AI/pull/4587))

- *(knowledge)* Add LLM synthesis layer for KB wiki pages (#4564) (#4585) ([#4585](https://github.com/mrveiss/AutoBot-AI/pull/4585))

- *(a2a)* SSE streaming + sliding TTL for A2A task polling (#4554) (#4558) ([#4558](https://github.com/mrveiss/AutoBot-AI/pull/4558))

- *(llm)* Multi-format chat templates (ChatML, Zephyr, Vicuna) for local providers (#4486) (#4516) ([#4516](https://github.com/mrveiss/AutoBot-AI/pull/4516))

- *(execution)* Code_interpreter tool — model-callable Python sandbox (#4485) (#4515) ([#4515](https://github.com/mrveiss/AutoBot-AI/pull/4515))

- *(prompts)* YAML-sectioned system prompt format with per-section overrides (#4484) (#4514) ([#4514](https://github.com/mrveiss/AutoBot-AI/pull/4514))

- *(tools)* Pydantic schema self-correction retry loop for tool validation (#4482) (#4496) ([#4496](https://github.com/mrveiss/AutoBot-AI/pull/4496))

- *(agent)* Inject first-turn context hint on iteration 0 (#4481) (#4495) ([#4495](https://github.com/mrveiss/AutoBot-AI/pull/4495))

- *(auth)* Wire user-management router and add AdminUsersView (#1801) (#4476) ([#4476](https://github.com/mrveiss/AutoBot-AI/pull/4476))

- *(marketplace)* Install/uninstall endpoints and MarketplaceView UI (#1803) (#4473) ([#4473](https://github.com/mrveiss/AutoBot-AI/pull/4473))

- *(research)* AutoResearch integration with experiment loop and nav link (#1440) (#4472) ([#4472](https://github.com/mrveiss/AutoBot-AI/pull/4472))

- *(marketplace)* Plugin and agent marketplace catalog API (#1803) (#4470) ([#4470](https://github.com/mrveiss/AutoBot-AI/pull/4470))

- *(auth)* Add self-signup and user role management endpoints (#1801) (#4469) ([#4469](https://github.com/mrveiss/AutoBot-AI/pull/4469))

- *(usage)* Add POST /record endpoint and UsageView frontend (#1807)

- *(usage)* Add POST /usage/record endpoint for LLM event ingestion (#1807)

- *(ui)* Mobile-responsive layout and navigation (#1804)

- *(agents)* Integrate HeartbeatPanel with live events (#1522) ([#4440](https://github.com/mrveiss/AutoBot-AI/pull/4440))

- *(usage)* Add usage metering and cost tracking API (#1807) ([#4439](https://github.com/mrveiss/AutoBot-AI/pull/4439))

- *(chat)* Implement bidirectional session sync between local store and backend (#4352) (#4417) ([#4417](https://github.com/mrveiss/AutoBot-AI/pull/4417))

- *(views)* Wire orphaned AboutView (#4267) (#4410) ([#4410](https://github.com/mrveiss/AutoBot-AI/pull/4410))

- *(views)* Wire orphaned HomeView (#4266) (#4402) ([#4402](https://github.com/mrveiss/AutoBot-AI/pull/4402))

- *(hooks)* Wire prompt building hooks (#4265) (#4401) ([#4401](https://github.com/mrveiss/AutoBot-AI/pull/4401))

- *(router)* Register error_resilience and user_management routers (#4400) ([#4400](https://github.com/mrveiss/AutoBot-AI/pull/4400))

- *(orchestration)* Autonomous subagent spawning for parallel workstreams (#4348)

- *(hooks)* Wire remaining error/loop hooks (#4262) (#4384) ([#4384](https://github.com/mrveiss/AutoBot-AI/pull/4384))

- Add funding infrastructure for Phase 1.4 (#4393) ([#4393](https://github.com/mrveiss/AutoBot-AI/pull/4393))

- *(scheduler)* Cron-scheduled automation tasks (#4347) (#4388) ([#4388](https://github.com/mrveiss/AutoBot-AI/pull/4388))

- *(orchestration)* Autonomous subagent spawning for parallel workstreams (#4348) (#4387) ([#4387](https://github.com/mrveiss/AutoBot-AI/pull/4387))

- *(hooks)* Wire RAG and response hooks (#4263) (#4385) ([#4385](https://github.com/mrveiss/AutoBot-AI/pull/4385))

- *(hooks)* Wire continuation and approval hooks (#4264) (#4386) ([#4386](https://github.com/mrveiss/AutoBot-AI/pull/4386))

- *(memory)* Provider-based memory architecture (#4344)

- *(memory)* Provider-based memory architecture (#4344) (#4381) ([#4381](https://github.com/mrveiss/AutoBot-AI/pull/4381))

- *(execution)* Pluggable execution backends (Modal, Docker, SSH) (#4343) (#4378) ([#4378](https://github.com/mrveiss/AutoBot-AI/pull/4378))

- *(security)* Prompt injection detection in context files (#4345) (#4379) ([#4379](https://github.com/mrveiss/AutoBot-AI/pull/4379))

- *(execution)* Pluggable execution backends (#4343)

- *(security)* Prompt injection detection in context files (#4345)

- *(skills)* Skill relevance ranking at prompt time (#4337) (#4364) ([#4364](https://github.com/mrveiss/AutoBot-AI/pull/4364))

- *(skills)* Skill relevance ranking at prompt time (#4337)

- *(skills)* Autonomous skill extraction from conversations (#4338)

- *(hooks)* Wire core LLM hooks (#4259) (#4370) ([#4370](https://github.com/mrveiss/AutoBot-AI/pull/4370))

- *(hooks)* Wire session lifecycle hooks (#4260) (#4371) ([#4371](https://github.com/mrveiss/AutoBot-AI/pull/4371))

- *(hooks)* Wire tool execution hooks (#4261) (#4372) ([#4372](https://github.com/mrveiss/AutoBot-AI/pull/4372))

- *(gateway)* Unified multi-platform message gateway (#4340) (#4373) ([#4373](https://github.com/mrveiss/AutoBot-AI/pull/4373))

- *(llm)* Model provider flexibility and vendor-agnostic switching (#4341) (#4374) ([#4374](https://github.com/mrveiss/AutoBot-AI/pull/4374))

- *(resilience)* Error isolation and graceful degradation (#4342) (#4375) ([#4375](https://github.com/mrveiss/AutoBot-AI/pull/4375))

- *(skills)* Skill relevance ranking at prompt time (#4337)

- *(skills)* Autonomous skill extraction from conversations (#4338)

- *(hooks)* Wire core LLM hooks (#4259)

- *(hooks)* Wire tool execution hooks (#4261)

- *(gateway)* Unified multi-platform message gateway (#4340)

- *(llm)* Model provider flexibility and vendor-agnostic switching (#4341)

- *(resilience)* Error isolation and graceful degradation (#4342)

- *(skills)* Skill relevance ranking at prompt time (#4337)

- *(skills)* Autonomous skill extraction from conversations (#4338)

- *(skills)* Usage metrics and health tracking (#4339) (#4366) ([#4366](https://github.com/mrveiss/AutoBot-AI/pull/4366))

- *(integrations)* Add rate limiting to GitHub and Slack (#4162) (#4249) ([#4249](https://github.com/mrveiss/AutoBot-AI/pull/4249))

- *(integrations)* Add rate limiting to GitHub and Slack (#4162)

- *(kb)* Add persistent editable AI output documents (#3245)

- *(integration)* Slack integration for notifications and approvals (#4098)

- *(integration)* GitHub API integration for code context and reviews (#4097)

- *(frontend)* Integrate ThemeToggle into PreferencesPanel (#3286)

- *(frontend)* I18n - multi-language support (#3272)

- Service-to-service auth enforcement (#3394) (#4223) ([#4223](https://github.com/mrveiss/AutoBot-AI/pull/4223))

- *(fullstack)* Model manager - dynamic LLM model list (#3280) (#4164) ([#4164](https://github.com/mrveiss/AutoBot-AI/pull/4164))

- *(fullstack)* Plugin/extension system (#4165) ([#4165](https://github.com/mrveiss/AutoBot-AI/pull/4165))

- *(backend)* Centralized input validation middleware (#3274) (#4169) ([#4169](https://github.com/mrveiss/AutoBot-AI/pull/4169))

- *(fullstack)* Offline mode - core functionality (#3275) (#4170) ([#4170](https://github.com/mrveiss/AutoBot-AI/pull/4170))

- *(autoresearch)* Resume + retry-failures for experiment runner (#3261) (#4209) ([#4209](https://github.com/mrveiss/AutoBot-AI/pull/4209))

- *(frontend)* Complete Knowledge Manager UI (#3270) (#4168) ([#4168](https://github.com/mrveiss/AutoBot-AI/pull/4168))

- *(backend)* Implement circuit breaker pattern (#3271) (#4171) ([#4171](https://github.com/mrveiss/AutoBot-AI/pull/4171))

- Capture deployment/playbook outputs (#4175) (#4198) ([#4198](https://github.com/mrveiss/AutoBot-AI/pull/4198))

- *(chat)* Stream agent chain-of-thought to frontend in real time (#3232) (#4207) ([#4207](https://github.com/mrveiss/AutoBot-AI/pull/4207))

- *(llm)* Prompt_prefix per model in YAML registry (#3263) (#4208) ([#4208](https://github.com/mrveiss/AutoBot-AI/pull/4208))

- *(autoresearch)* Enriched store indexing with missing spec fields (#3212) (#4210) ([#4210](https://github.com/mrveiss/AutoBot-AI/pull/4210))

- *(llm)* Persist provider_metadata on LLMResponse (#3262) (#4211) ([#4211](https://github.com/mrveiss/AutoBot-AI/pull/4211))

- *(knowledge)* Audio/video/YouTube ingestion via Whisper (#3243) (#4212) ([#4212](https://github.com/mrveiss/AutoBot-AI/pull/4212))

- *(autoresearch)* Required_temperature and system_prompt per experiment task (#3259) (#4213) ([#4213](https://github.com/mrveiss/AutoBot-AI/pull/4213))

- *(chat-workflow)* Content-aware tool-call loop detection (#3254) (#4214) ([#4214](https://github.com/mrveiss/AutoBot-AI/pull/4214))

- *(knowledge)* Project-scoped boards for namespaced isolation (#3242) (#4215) ([#4215](https://github.com/mrveiss/AutoBot-AI/pull/4215))

- *(knowledge)* Persistent editable AI output documents (#3245) (#4216) ([#4216](https://github.com/mrveiss/AutoBot-AI/pull/4216))

- *(notifications)* Implement automated CI notification suppression (#4167) (#4222) ([#4222](https://github.com/mrveiss/AutoBot-AI/pull/4222))

- *(slack)* Approval workflow integration (#4163) (#4221) ([#4221](https://github.com/mrveiss/AutoBot-AI/pull/4221))

- *(branch-health)* Implement branch divergence monitoring (#4112) (#4219) ([#4219](https://github.com/mrveiss/AutoBot-AI/pull/4219))

- *(automation)* Implement automated branch cleanup workflows (#4110) (#4218) ([#4218](https://github.com/mrveiss/AutoBot-AI/pull/4218))

- *(monitoring)* Add MCP worker restart budget tracking (#4109) (#4217) ([#4217](https://github.com/mrveiss/AutoBot-AI/pull/4217))

- *(perf)* Memoize expensive computed properties in analytics dashboards (#4036)

- *(ui)* Hotkey command palette with agent personalities (#4095)

- *(chat)* Add ON_PROMPT_READY plugin hooks + telemetry middleware (#3405)

- *(slm)* Add remote shell execution API and distributed_shell workflow step (#3406)

- *(integration)* Notion integration for knowledge base and task tracking (#4099)

- *(events)* Capture and publish task artifacts as evidence (#4094)

- *(agent)* Approval workflow for sensitive operations (#4092)

- *(slm)* Implement autobot-backend Docker deployment API bridge (#3407)

- *(backend)* Dynamic FastAPI endpoint discovery for LLM self-awareness (#3295)

- *(backend)* Complete MCP manual integration (#3287)

- *(testing)* Establish comprehensive automated test coverage framework (#3285)

- *(backend)* Implement knowledge base suggestion logic (#3284)

- *(frontend)* Implement toast notification system (#3283)

- *(fullstack)* Collaborative multi-user support (#3282)

- *(llm)* Add Anthropic and Groq provider adapters (#4096)

- Update issue templates with streamlined bug and feature request forms

- *(backend)* Implement audit logging system (#3277)

- *(frontend)* Implement terminal tab completion (#3279)

- *(knowledge)* Implement Redis-backed task status tracking for async populate (#4103)

- *(agents)* Distribute MCP tool capabilities across agent roster (#3386) (#4104) ([#4104](https://github.com/mrveiss/AutoBot-AI/pull/4104))

- *(rag)* Semantic chunking, fact extraction, entity resolution (#3395) (#4093) ([#4093](https://github.com/mrveiss/AutoBot-AI/pull/4093))

- *(causality-tier4)* Knowledge-grounded agent reasoning - prevent hallucinations via KB grounding

- *(perf)* Memoize analytics computations (#4036) (#4079) ([#4079](https://github.com/mrveiss/AutoBot-AI/pull/4079))

- *(perf)* Optimize base64 thumbnail generation (#4038)

- *(perf)* Debounce search and filter inputs (#4035) (#4075) ([#4075](https://github.com/mrveiss/AutoBot-AI/pull/4075))

- *(perf)* Fix fixed-height containers causing layout thrashing (#4034) (#4074) ([#4074](https://github.com/mrveiss/AutoBot-AI/pull/4074))

- *(perf)* Add loading='lazy' to images for deferred loading (#4033) (#4073) ([#4073](https://github.com/mrveiss/AutoBot-AI/pull/4073))

- *(causality)* Tier 3 architectural - CausalInferenceEngine, DAG validation, error recovery

- *(causality)* Tier 2 medium impact - RAG extraction, counterfactual, analytics

- *(causality)* Tier 1 quick wins - CoT annotations, root-cause API, causal reasoning

- *(knowledge)* Memory graph semantic search — query processor and hybrid scoring (#3384)

- *(perf)* Virtual scrolling for large lists (#4037) (#4071) ([#4071](https://github.com/mrveiss/AutoBot-AI/pull/4071))

- Add contribution section to README

- Add CONTRIBUTORS.md guide for community

- Add GitHub Actions workflow for auto-triage

- Add general issue template

- *(ansible)* Add single-host deployment inventory configuration (#2961)

- *(perf)* Add virtual scrolling composable and integration guide (#4037)

- *(perf)* Add Web Worker for video thumbnail generation (#4038)

- *(pwa)* Add Service Worker and manifest for offline support (#4041)

- Phase-2.3-github-seo-optimize-for-self-hosted-keyword

- *(perf)* Add debounce to search/filter handlers (#4035) (#4049) ([#4049](https://github.com/mrveiss/AutoBot-AI/pull/4049))

- Add issue templates, PR template, contributing guidelines, and funding config (#4031) ([#4031](https://github.com/mrveiss/AutoBot-AI/pull/4031))

- *(frontend)* Add KB full-text search result viewer (#3296) (#3920) ([#3920](https://github.com/mrveiss/AutoBot-AI/pull/3920))

- *(backend)* Implement agent usage tracking (#3921) ([#3921](https://github.com/mrveiss/AutoBot-AI/pull/3921))

- *(backend)* Custom success criteria for workflow orchestrator (#3919) ([#3919](https://github.com/mrveiss/AutoBot-AI/pull/3919))

- *(dev)* Extend hardcoding prevention hook — DB DSNs + timeouts (#3397) ([#3929](https://github.com/mrveiss/AutoBot-AI/pull/3929))

- *(frontend)* Web research settings UI (#3850) ([#3924](https://github.com/mrveiss/AutoBot-AI/pull/3924))

- *(i18n)* Language switcher — globe icon in nav with cross-device sync (#3901) ([#3915](https://github.com/mrveiss/AutoBot-AI/pull/3915))

- *(frontend)* Wire up step editor in AdvancedStepConfirmationModal (#3894) ([#3894](https://github.com/mrveiss/AutoBot-AI/pull/3894))

- *(frontend)* Add web research settings UI (#3896) ([#3896](https://github.com/mrveiss/AutoBot-AI/pull/3896))

- *(backend)* Add hardware priority updates API endpoint (#3895) ([#3895](https://github.com/mrveiss/AutoBot-AI/pull/3895))

- *(agents)* Stream chain-of-thought events to frontend in real time (#3889) ([#3889](https://github.com/mrveiss/AutoBot-AI/pull/3889))

- *(autoresearch)* Wire real scorers + benchmark, add agent registration path (#3208) (#3876) ([#3876](https://github.com/mrveiss/AutoBot-AI/pull/3876))

- *(config)* Config management enhancements — startup validation and sync API (#3398) (#3834) ([#3834](https://github.com/mrveiss/AutoBot-AI/pull/3834))

- *(agent-loop)* Content-aware repetitive tool-call detection (#3255) (#3832) ([#3832](https://github.com/mrveiss/AutoBot-AI/pull/3832))

- *(llm)* Migrate chat completion calls to vLLM optimised API (#3389) (#3835) ([#3835](https://github.com/mrveiss/AutoBot-AI/pull/3835))

- *(hardening)* WebSocket auth, shared WorkflowMemory, register PermissionExtension in lifespan (#3009, tasks 10-12) (#3857) ([#3857](https://github.com/mrveiss/AutoBot-AI/pull/3857))

- *(hardening)* Tool SDK Registry + ToolRegistry SDK dispatch + PermissionEnforcementExtension (#3009, tasks 7-9) (#3853) ([#3853](https://github.com/mrveiss/AutoBot-AI/pull/3853))

- *(memory-graph)* REST endpoints for invalidate_entity and invalidate_relation (#3810) (#3854) ([#3854](https://github.com/mrveiss/AutoBot-AI/pull/3854))

- *(hardening)* Tasks 3-6 + perf(memory): fix O(n) get_all_facts scan (#3009, #3808) (#3846) ([#3846](https://github.com/mrveiss/AutoBot-AI/pull/3846))

- *(memory)* Wire WorkingMemory/EssentialStory/AgentDiary into UnifiedMemoryManager (#3822) ([#3822](https://github.com/mrveiss/AutoBot-AI/pull/3822))

- *(memory)* Temporal fact validity — valid_from/valid_to on memory graph (#3790) (#3807) ([#3807](https://github.com/mrveiss/AutoBot-AI/pull/3807))

- *(memory)* Essential story layer — always-loaded compact memory summary (#3787) (#3804) ([#3804](https://github.com/mrveiss/AutoBot-AI/pull/3804))

- *(knowledge)* Semantic duplicate guard on individual fact writes (#3788) (#3805) ([#3805](https://github.com/mrveiss/AutoBot-AI/pull/3805))

- *(memory)* Essential story layer — always-loaded compact memory summary (#3793) ([#3793](https://github.com/mrveiss/AutoBot-AI/pull/3793))

- *(memory)* Temporal fact validity — valid_from/valid_to on memory graph entities and relations (#3798) ([#3798](https://github.com/mrveiss/AutoBot-AI/pull/3798))

- *(agents)* Per-agent cross-session diary — persistent agent journal in KB (#3792) ([#3792](https://github.com/mrveiss/AutoBot-AI/pull/3792))

- *(knowledge)* Semantic duplicate guard on individual fact writes (#3788) (#3800) ([#3800](https://github.com/mrveiss/AutoBot-AI/pull/3800))

- *(ansible)* Add deploy-hybrid-docker.yml and docker Ansible role (#3424) (#3786) ([#3786](https://github.com/mrveiss/AutoBot-AI/pull/3786))

- *(agents)* Enforce memory read/write via pipeline lifecycle hooks (#3777) ([#3777](https://github.com/mrveiss/AutoBot-AI/pull/3777))

- *(memory)* Context-adaptive memory compression for small-context models (#3776) ([#3776](https://github.com/mrveiss/AutoBot-AI/pull/3776))

- *(memory)* Redis-backed session-scoped working memory with TTL (#3775) ([#3775](https://github.com/mrveiss/AutoBot-AI/pull/3775))

- *(frontend)* Add KB vectorization status badge, action button, batch toolbar, progress modal (#3388) (#3774) ([#3774](https://github.com/mrveiss/AutoBot-AI/pull/3774))

- *(slm)* Redis service management UI — start/stop/restart controls (#3381) ([#3740](https://github.com/mrveiss/AutoBot-AI/pull/3740))

- *(backend)* Persist code-review results in Redis + GET /review/{id} endpoint (#3716) ([#3735](https://github.com/mrveiss/AutoBot-AI/pull/3735))

- *(frontend)* Wrap router-view with ErrorBoundary in App.vue (#3375) ([#3739](https://github.com/mrveiss/AutoBot-AI/pull/3739))

- *(slm)* Implement autobot-admin CLI with reset-password subcommand (#3691) ([#3718](https://github.com/mrveiss/AutoBot-AI/pull/3718))

- *(analytics)* Scope quality/review/evolution/generation to project source_root (#3441) ([#3705](https://github.com/mrveiss/AutoBot-AI/pull/3705))

- *(slm)* Add component selector to File Drift Check UI (#3433) ([#3679](https://github.com/mrveiss/AutoBot-AI/pull/3679))

- *(ansible)* Add pre-flight code_source sync to deploy playbooks (#3604) ([#3677](https://github.com/mrveiss/AutoBot-AI/pull/3677))

- *(slm)* Add admin password reset to user management UI (#3625) ([#3626](https://github.com/mrveiss/AutoBot-AI/pull/3626))

- *(memory-graph)* Consolidate into single autobot_memory_graph with semantic search (#3612) (#3616) ([#3616](https://github.com/mrveiss/AutoBot-AI/pull/3616))

- *(rag)* Per-user annotation signals for personalized RAG retrieval (#3240) (#3610) ([#3610](https://github.com/mrveiss/AutoBot-AI/pull/3610))

- *(ansible)* Add sync-code-source.yml to push code from controller to SLM (#3604)

- *(llm)* YAML-driven per-model parameter registry (#3257)

- *(ansible)* Display code_source staleness metrics in pre-flight sync (#3593) ([#3595](https://github.com/mrveiss/AutoBot-AI/pull/3595))

- *(chat-workflow)* Content-aware tool-call loop detection in LangGraph chat graph (#3254) (#3577) ([#3577](https://github.com/mrveiss/AutoBot-AI/pull/3577))

- *(llm)* Anthropic extended thinking / reasoning budget support (#3258) (#3575) ([#3575](https://github.com/mrveiss/AutoBot-AI/pull/3575))

- *(frontend)* Wire DesktopView and CustomDashboard into router and nav (#3502) ([#3506](https://github.com/mrveiss/AutoBot-AI/pull/3506))

- *(analytics)* Merge quality/review/evolution/generation into per-project codebase analytics (#3436)

- *(slm)* Deployed-vs-source file drift detection (#2834) (#3430) ([#3430](https://github.com/mrveiss/AutoBot-AI/pull/3430))

- *(e2e)* Restore kb-librarian-api.spec.ts for /api/kb-librarian endpoints (#3402) (#3418) ([#3418](https://github.com/mrveiss/AutoBot-AI/pull/3418))

- *(autoresearch)* Quality-diversity archive replacing top-K in PromptOptimizer (#3222) (#3419) ([#3419](https://github.com/mrveiss/AutoBot-AI/pull/3419))

- *(slm)* Implement autobot-backend Docker deployment API bridge (SLM → Ansible → Docker) (#3416) ([#3416](https://github.com/mrveiss/AutoBot-AI/pull/3416))

- *(slm)* Add remote shell execution API + distributed_shell workflow step type for fleet parallelism (#3417) ([#3417](https://github.com/mrveiss/AutoBot-AI/pull/3417))

- *(chat)* Add ON_PROMPT_READY plugin hooks + telemetry-based prompt middleware example (#3414) ([#3414](https://github.com/mrveiss/AutoBot-AI/pull/3414))

- *(monitoring)* Wire HealthCollector state-change events to workflow trigger + notification pipeline (#3415) ([#3415](https://github.com/mrveiss/AutoBot-AI/pull/3415))

- *(backend)* Register kb_librarian router at /api/kb-librarian, add auth guards (#3402) (#3403) ([#3403](https://github.com/mrveiss/AutoBot-AI/pull/3403))

- *(knowledge-graph)* Add 3D force-graph view toggle (#3330) (#3365) ([#3365](https://github.com/mrveiss/AutoBot-AI/pull/3365))

- *(knowledge-graph)* Add 3D force-graph view toggle (#3330) ([#3359](https://github.com/mrveiss/AutoBot-AI/pull/3359))

- *(autoresearch)* Self-referential meta-agent for code-level improvement (#3224) ([#3344](https://github.com/mrveiss/AutoBot-AI/pull/3344))

- *(slm-frontend)* Add typed response interfaces for security API endpoints (#3184) (#3343) ([#3343](https://github.com/mrveiss/AutoBot-AI/pull/3343))

- *(backend)* Add /api/project/* and /api/phases/* endpoints (#3331) (#3339) ([#3339](https://github.com/mrveiss/AutoBot-AI/pull/3339))

- *(autoresearch)* Docker per-experiment isolation in ExperimentRunner (#3320) ([#3320](https://github.com/mrveiss/AutoBot-AI/pull/3320))

- *(autoresearch)* Quality-diversity archive replacing top-K in PromptOptimizer (#3321) ([#3321](https://github.com/mrveiss/AutoBot-AI/pull/3321))

- *(autoresearch)* Staged eval — cheap-first scorer chain gating (#3221) (#3319) ([#3319](https://github.com/mrveiss/AutoBot-AI/pull/3319))

- *(changelog)* Add fragment-based changelog system (A+B)

- *(wizard)* Pre-fill API key secrets on re-run (#3226)

- *(frontend)* AutoResearch experiment dashboard (#3201) (#3207) ([#3207](https://github.com/mrveiss/AutoBot-AI/pull/3207))

- *(autoresearch)* Prompt optimizer + API endpoints + M3 integration (#3200) (#3206) ([#3206](https://github.com/mrveiss/AutoBot-AI/pull/3206))

- *(autoresearch)* Knowledge synthesizer + enriched ChromaDB indexing (#3199) (#3203) ([#3203](https://github.com/mrveiss/AutoBot-AI/pull/3203))

- *(autoresearch)* Scorer interface + 3 implementations (#3198) (#3202) ([#3202](https://github.com/mrveiss/AutoBot-AI/pull/3202))

- *(frontend)* Add real-time workflow execution dashboard (#2155) (#3181) ([#3181](https://github.com/mrveiss/AutoBot-AI/pull/3181))

- *(wizard)* Add API keys step for HF_TOKEN and gated model licenses (#3079)

- *(frontend)* Restore agent settings panel with runtime config (#1822) (#3177) ([#3177](https://github.com/mrveiss/AutoBot-AI/pull/3177))

- *(backend)* Add conversation export and import API (#1808) (#3176) ([#3176](https://github.com/mrveiss/AutoBot-AI/pull/3176))

- *(backend)* Add malloc_trim(0) to clean_memory() for Linux heap reclamation (#3165) (#3170) ([#3170](https://github.com/mrveiss/AutoBot-AI/pull/3170))

- *(notifications)* Add UI for per-workflow notification config (#3139) (#3161) ([#3161](https://github.com/mrveiss/AutoBot-AI/pull/3161))

- *(optimization)* Assemble end-to-end LayerInference pipeline (#3140) (#3160) ([#3160](https://github.com/mrveiss/AutoBot-AI/pull/3160))

- *(optimization)* Add empty-weight model inspection for hardware routing (#1945) (#3159) ([#3159](https://github.com/mrveiss/AutoBot-AI/pull/3159))

- *(frontend)* Add API key configuration step to setup wizard (#3079) (#3156) ([#3156](https://github.com/mrveiss/AutoBot-AI/pull/3156))

- *(workflow)* Add UI for per-workflow notification config (#3139) (#3154) ([#3154](https://github.com/mrveiss/AutoBot-AI/pull/3154))

- *(backend)* Add DELETE /sessions/{id}/checkpoints endpoint (#1482) (#3157) ([#3157](https://github.com/mrveiss/AutoBot-AI/pull/3157))

- *(frontend)* Add togglable quick-actions bar in ChatInput (#1569) (#3155) ([#3155](https://github.com/mrveiss/AutoBot-AI/pull/3155))

- *(frontend)* Add HeartbeatPanel route at /agents/heartbeat (#1521) (#3150) ([#3150](https://github.com/mrveiss/AutoBot-AI/pull/3150))

- *(backend)* Add multi-provider LLM abstraction layer (#1806) (#3145) ([#3145](https://github.com/mrveiss/AutoBot-AI/pull/3145))

- *(npu)* Implement prefetch/overlap I/O pattern (#1944) (#3143) ([#3143](https://github.com/mrveiss/AutoBot-AI/pull/3143))

- *(backend)* Wire quantization config to HfQuantizer in OptimizationRouter (#1943) (#3141) ([#3141](https://github.com/mrveiss/AutoBot-AI/pull/3141))

- *(backend)* Wire NotificationService into workflow executor events (#3101) (#3133) ([#3133](https://github.com/mrveiss/AutoBot-AI/pull/3133))

- *(backend)* Register LayerInferenceEngine as LLM provider in routing (#3104) (#3136) ([#3136](https://github.com/mrveiss/AutoBot-AI/pull/3136))

- *(backend)* Wire NotificationService into workflow executor events (#3101)

- *(backend)* Auto-inject WorkflowMemory findings into agent prompt context (#3099)

- *(backend)* Register LayerInferenceEngine as LLM provider (#3104)

- *(backend)* Replace mcp_sync HTTP-only client with transport-agnostic MCPClient (#3103)

- *(frontend)* Wire full code intelligence features into codebase analytics (#3073) ([#3093](https://github.com/mrveiss/AutoBot-AI/pull/3093))

- *(frontend)* Add navigation tabs for orphaned analytics sub-routes (#3067) ([#3091](https://github.com/mrveiss/AutoBot-AI/pull/3091))

- *(inference)* Add layer-by-layer inference mode for batch processing (#1946) (#3089) ([#3089](https://github.com/mrveiss/AutoBot-AI/pull/3089))

- *(inference)* Add meta device eviction for processed layers (#1952) (#3088) ([#3088](https://github.com/mrveiss/AutoBot-AI/pull/3088))

- *(inference)* Add attention backend fallback chain (#1951) (#3085) ([#3085](https://github.com/mrveiss/AutoBot-AI/pull/3085))

- *(inference)* Add HfQuantizer integration for GPTQ/AWQ models (#1954) (#3083) ([#3083](https://github.com/mrveiss/AutoBot-AI/pull/3083))

- *(frontend)* Add data-testid attributes to RedisServiceControl.vue (#3069) (#3080) ([#3080](https://github.com/mrveiss/AutoBot-AI/pull/3080))

- *(inference)* Add layer-aligned KV cache management (#1964) (#3074) ([#3074](https://github.com/mrveiss/AutoBot-AI/pull/3074))

- *(backend)* Add web pipeline Phase 1 — XHR interceptor + accessibility snapshot (#1967) (#3071) ([#3071](https://github.com/mrveiss/AutoBot-AI/pull/3071))

- *(slm)* Add provision log streaming with heartbeat for long tasks (#3033) (#3068) ([#3068](https://github.com/mrveiss/AutoBot-AI/pull/3068))

- *(orchestration)* Add sub-workflow composition as reusable blocks (#2143) (#3063) ([#3063](https://github.com/mrveiss/AutoBot-AI/pull/3063))

- *(browser)* Add local ML-based CAPTCHA solver via NPU (#1974) (#3064) ([#3064](https://github.com/mrveiss/AutoBot-AI/pull/3064))

- *(backend)* Add workflow input forms and output formatting (#2161) (#3060) ([#3060](https://github.com/mrveiss/AutoBot-AI/pull/3060))

- *(backend)* Add workflow version history and rollback (#2145) (#3058) ([#3058](https://github.com/mrveiss/AutoBot-AI/pull/3058))

- *(backend)* Add event-driven trigger system for workflows (#2139) (#3050) ([#3050](https://github.com/mrveiss/AutoBot-AI/pull/3050))

- *(backend)* Add workflow export/import and sharing (#2165) (#3048) ([#3048](https://github.com/mrveiss/AutoBot-AI/pull/3048))

- *(backend)* Add multi-channel notification service for workflows (#2157) (#3047) ([#3047](https://github.com/mrveiss/AutoBot-AI/pull/3047))

- *(orchestration)* Add shared memory between parallel workflow agents (#3019) (#3046) ([#3046](https://github.com/mrveiss/AutoBot-AI/pull/3046))

- *(security)* Add JWT authentication to all WebSocket endpoints (#2818) (#3040) ([#3040](https://github.com/mrveiss/AutoBot-AI/pull/3040))

- *(orchestration)* Add workflow dry-run validation and debug mode (#2148) (#3038) ([#3038](https://github.com/mrveiss/AutoBot-AI/pull/3038))

- *(security)* Add PreToolUse hooks for command blocking, secret scanning, and file protection (#3021, #3022, #3026) ([#3035](https://github.com/mrveiss/AutoBot-AI/pull/3035))

- *(orchestration)* Add workflow resume-from-failure and error handlers (#2154) (#3036) ([#3036](https://github.com/mrveiss/AutoBot-AI/pull/3036))

- *(shared)* Add unified tool SDK with input validation and permissions (#3018) (#3037) ([#3037](https://github.com/mrveiss/AutoBot-AI/pull/3037))

- *(shared)* Add feature flag system for optional subsystems (#3017) (#3034) ([#3034](https://github.com/mrveiss/AutoBot-AI/pull/3034))

- *(research)* Add AutoResearch M2 orchestrator with web search (#2599) (#3023) ([#3023](https://github.com/mrveiss/AutoBot-AI/pull/3023))

- *(orchestration)* Add structured variable piping between workflow steps (#2141) (#3008) ([#3008](https://github.com/mrveiss/AutoBot-AI/pull/3008))

- *(rag)* Add agentic RAG with search-as-tool and iterative retrieval (#1718) (#3004) ([#3004](https://github.com/mrveiss/AutoBot-AI/pull/3004))

- *(orchestration)* Add DAG executor for conditional workflow branching (#2140) (#3003) ([#3003](https://github.com/mrveiss/AutoBot-AI/pull/3003))

- *(research)* Add native OSINT intelligence sweep engine (#1949) (#3001) ([#3001](https://github.com/mrveiss/AutoBot-AI/pull/3001))

- *(mcp)* Add full MCP spec support with stdio/SSE/HTTP transports (#2133) (#2999) ([#2999](https://github.com/mrveiss/AutoBot-AI/pull/2999))

- *(shared)* Add delta engine for change detection monitoring (#1947) (#2996) ([#2996](https://github.com/mrveiss/AutoBot-AI/pull/2996))

- *(mesh)* Add concrete MeshDB/MeshGraph PostgreSQL adapter (#2548) (#2994) ([#2994](https://github.com/mrveiss/AutoBot-AI/pull/2994))

- *(slm)* Report partial success for update discovery (#1816) (#2993) ([#2993](https://github.com/mrveiss/AutoBot-AI/pull/2993))

- *(backend)* Make chat message timeout configurable (#1907) (#2992) ([#2992](https://github.com/mrveiss/AutoBot-AI/pull/2992))

- *(rag)* Add retrieval pattern distillation (#2095) (#2988) ([#2988](https://github.com/mrveiss/AutoBot-AI/pull/2988))

- *(security)* Add adaptive threat detection learner (#2110) (#2986) ([#2986](https://github.com/mrveiss/AutoBot-AI/pull/2986))

- *(backend)* Add Q-Learning reinforcement router (#2092) (#2982) ([#2982](https://github.com/mrveiss/AutoBot-AI/pull/2982))

- *(shared)* Add multi-tier alert cooldown system (#1948) (#2979) ([#2979](https://github.com/mrveiss/AutoBot-AI/pull/2979))

- *(llm)* Enable model pulling by default after Ollama install (#2960) (#2974) ([#2974](https://github.com/mrveiss/AutoBot-AI/pull/2974))

- *(rag)* Wire staleness propagation into reindexing and reranking (#2547) (#2976) ([#2976](https://github.com/mrveiss/AutoBot-AI/pull/2976))

- *(backend)* Add work-stealing for stale agent tasks (#2109) (#2975) ([#2975](https://github.com/mrveiss/AutoBot-AI/pull/2975))

- *(slm)* Add failure_reason column to FleetSyncJobModel (#1980) (#2973) ([#2973](https://github.com/mrveiss/AutoBot-AI/pull/2973))

- *(backend)* Support multi-GPU VRAM detection (#2032) (#2971) ([#2971](https://github.com/mrveiss/AutoBot-AI/pull/2971))

- *(rag)* Add MMR diversity scoring to reranker (#2090) (#2968) ([#2968](https://github.com/mrveiss/AutoBot-AI/pull/2968))

- *(mesh)* Persist EWC++ weights and importance to Redis (#2546) (#2967) ([#2967](https://github.com/mrveiss/AutoBot-AI/pull/2967))

- *(slm)* Serve SLM at /slm subroute for single-host (#2716) (#2965) ([#2965](https://github.com/mrveiss/AutoBot-AI/pull/2965))

- *(backend)* Add Apple Silicon GPU detection (#2014) (#2963) ([#2963](https://github.com/mrveiss/AutoBot-AI/pull/2963))

- *(backend)* Add per-worker task tracking to failover monitor (#2496)

- *(backend)* Auto-create idx:agent_memory vector index on startup (#2645)

- *(config)* Add missing agents to agents.yaml (#2815)

- *(ansible)* Auto-register VNC credentials in SLM database (#2926) (#2937) ([#2937](https://github.com/mrveiss/AutoBot-AI/pull/2937))

- *(backend)* Add .env drift detection against SSOT config (#2650) (#2938) ([#2938](https://github.com/mrveiss/AutoBot-AI/pull/2938))

- *(deploy)* Pre-check node SSH reachability before provisioning (#2897) (#2903) ([#2903](https://github.com/mrveiss/AutoBot-AI/pull/2903))

- *(deploy)* Auto-pull code_source before Ansible playbook runs (#2896) (#2902) ([#2902](https://github.com/mrveiss/AutoBot-AI/pull/2902))

- *(ansible)* Add VNC node bootstrap and provisioning workflow (#1525, #2407)

- *(setup-wizard)* Stream Ansible provisioning logs via WebSocket (#2754) (#2812) ([#2812](https://github.com/mrveiss/AutoBot-AI/pull/2812))

- *(config)* Implement 6-tier agent-model mapping (#2553) ([#2800](https://github.com/mrveiss/AutoBot-AI/pull/2800))

- *(redis-mcp)* Auto-expire agent memory keys with 24h TTL (#2646) (#2788) ([#2788](https://github.com/mrveiss/AutoBot-AI/pull/2788))

- *(ansible)* Extract shared dependency roles (nginx, python312, nodejs) (#2747)

- *(install)* Auto-assign SLM Manager as code source during install (#2755)

- *(docs)* Add end-user documentation and guides (#1805) (#2713) ([#2713](https://github.com/mrveiss/AutoBot-AI/pull/2713))

- *(autoresearch)* Standalone experiment runner + result store (#2597) ([#2615](https://github.com/mrveiss/AutoBot-AI/pull/2615))

- *(fleet)* Add re-enroll endpoint and UI for decommissioned nodes (#2681)

- *(mcp)* Add Redis MCP Bridge with 25 tools (#2511) ([#2614](https://github.com/mrveiss/AutoBot-AI/pull/2614))

- *(mcp)* Tool prompt injection, cache TTL, and RBAC filtering (#2596, #2598) ([#2621](https://github.com/mrveiss/AutoBot-AI/pull/2621))

- *(workflow)* Vision step chaining, SSOT URL, and web OCR pipeline (#2601) ([#2613](https://github.com/mrveiss/AutoBot-AI/pull/2613))

- *(chat)* Add web_search convenience tool and sync tool docs (#2306, #2593, #2594) ([#2575](https://github.com/mrveiss/AutoBot-AI/pull/2575))

- *(workflows)* Implement DROP_OLDEST with cancellation callback (#2573) ([#2602](https://github.com/mrveiss/AutoBot-AI/pull/2602))

- *(mcp)* Dynamic tool discovery and dispatch for agents (#2513) ([#2590](https://github.com/mrveiss/AutoBot-AI/pull/2590))

- *(workflow)* Add vision step execution handlers (#2397) ([#2581](https://github.com/mrveiss/AutoBot-AI/pull/2581))

- *(chat)* Auto-inject tools reminder after invalid tool calls (#2310) ([#2567](https://github.com/mrveiss/AutoBot-AI/pull/2567))

- *(agents)* Align agent-model mapping with 6-tier SSOT architecture (#2553)

- *(inference)* Layered inference profiler with per-stage timing (#1956) ([#2549](https://github.com/mrveiss/AutoBot-AI/pull/2549))

- *(inference)* Flash Attention v2 with variable-length sequences (#1955) ([#2541](https://github.com/mrveiss/AutoBot-AI/pull/2541))

- *(workflows)* Safety limits with per-step timeouts and cost budgets (#2159) ([#2550](https://github.com/mrveiss/AutoBot-AI/pull/2550))

- *(llm)* Active token budget optimization with context compaction (#2098) ([#2538](https://github.com/mrveiss/AutoBot-AI/pull/2538))

- *(inference)* Only-last-logit optimization for generation (#1968) ([#2545](https://github.com/mrveiss/AutoBot-AI/pull/2545))

- *(mesh)* BFS staleness propagation on Neural Mesh knowledge graph (#2111) ([#2543](https://github.com/mrveiss/AutoBot-AI/pull/2543))

- *(mesh)* EWC++ catastrophic forgetting prevention for EdgeLearner (#2097) ([#2539](https://github.com/mrveiss/AutoBot-AI/pull/2539))


### Miscellaneous

- Merge main into Dev_new_gui to resolve PR #9300 conflicts (#9321) ([#9321](https://github.com/mrveiss/AutoBot-AI/pull/9321))

- *(ci/visual)* Regenerate Storybook visual baselines on CI runner (MVA-1480) (#8933) ([#8933](https://github.com/mrveiss/AutoBot-AI/pull/8933))

- *(deps)* Bump the npm_and_yarn group across 3 directories with 2 updates (#8904) ([#8904](https://github.com/mrveiss/AutoBot-AI/pull/8904))

- *(npu)* Fix suggest_profile docstring mismatch + _load_tiers bugs (GH#8674) (#8887) ([#8887](https://github.com/mrveiss/AutoBot-AI/pull/8887))

- *(ci)* Fix pre-existing flake8 violations blocking code-quality CI (MVA-1334) ([#8848](https://github.com/mrveiss/AutoBot-AI/pull/8848))

- *(nav)* Remove dead adminOnly filter in App.vue (GH#8811) (#8820) ([#8820](https://github.com/mrveiss/AutoBot-AI/pull/8820))

- *(ci)* Fix pre-existing flake8 violations blocking code-quality CI (MVA-1187) (#8731) ([#8731](https://github.com/mrveiss/AutoBot-AI/pull/8731))

- *(ci)* Fix pre-existing Black formatting violations in Dev_new_gui (MVA-1173) ([#8725](https://github.com/mrveiss/AutoBot-AI/pull/8725))

- *(orchestration)* Call task_workspace.release() on task completion/cancel (MVA-1152) (#8721) ([#8721](https://github.com/mrveiss/AutoBot-AI/pull/8721))

- *(deps)* Update starlette requirement in /autobot-slm-backend (#8612) ([#8612](https://github.com/mrveiss/AutoBot-AI/pull/8612))

- *(deps-dev)* Bump jsdom from 29.1.0 to 29.1.1 in /autobot-frontend (#8621) ([#8621](https://github.com/mrveiss/AutoBot-AI/pull/8621))

- *(deps)* Update huggingface-hub requirement in /autobot-tts-worker (#8629) ([#8629](https://github.com/mrveiss/AutoBot-AI/pull/8629))

- *(deps)* Bump jsonschema from 4.24.0 to 4.26.0 (#8637) ([#8637](https://github.com/mrveiss/AutoBot-AI/pull/8637))

- *(deps)* Update transformers requirement (#8640) ([#8640](https://github.com/mrveiss/AutoBot-AI/pull/8640))

- *(deps)* Bump docker/setup-buildx-action from 4.0.0 to 4.1.0 (#8609) ([#8609](https://github.com/mrveiss/AutoBot-AI/pull/8609))

- *(deps)* Update tree-sitter requirement in /autobot-backend (#8610) ([#8610](https://github.com/mrveiss/AutoBot-AI/pull/8610))

- *(deps)* Bump codecov/codecov-action from 6.0.0 to 6.0.1 (#8611) ([#8611](https://github.com/mrveiss/AutoBot-AI/pull/8611))

- *(deps)* Update weasyprint requirement in /autobot-backend (#8613) ([#8613](https://github.com/mrveiss/AutoBot-AI/pull/8613))

- *(deps)* Update xxhash requirement from >=3.6.0 to >=3.7.0 (#8638) ([#8638](https://github.com/mrveiss/AutoBot-AI/pull/8638))

- *(deps)* Update huggingface-hub requirement (#8641) ([#8641](https://github.com/mrveiss/AutoBot-AI/pull/8641))

- *(deps)* Update uvicorn requirement (#8642) ([#8642](https://github.com/mrveiss/AutoBot-AI/pull/8642))

- *(deps)* Bump actions/checkout from 4.1.1 to 6.0.2 (#8614) ([#8614](https://github.com/mrveiss/AutoBot-AI/pull/8614))

- *(deps)* Update fastapi requirement in /autobot-slm-backend (#8615) ([#8615](https://github.com/mrveiss/AutoBot-AI/pull/8615))

- *(deps)* Update numpy requirement in /autobot-backend (#8616) ([#8616](https://github.com/mrveiss/AutoBot-AI/pull/8616))

- *(deps)* Update opentelemetry-instrumentation-redis requirement (#8617) ([#8617](https://github.com/mrveiss/AutoBot-AI/pull/8617))

- *(deps)* Update uvicorn requirement in /autobot-slm-backend (#8618) ([#8618](https://github.com/mrveiss/AutoBot-AI/pull/8618))

- *(deps)* Update cachetools requirement in /autobot-backend (#8619) ([#8619](https://github.com/mrveiss/AutoBot-AI/pull/8619))

- *(deps-dev)* Bump @vitest/coverage-v8 in /autobot-frontend (#8620) ([#8620](https://github.com/mrveiss/AutoBot-AI/pull/8620))

- *(deps-dev)* Bump vue-tsc in /autobot-slm-frontend (#8622) ([#8622](https://github.com/mrveiss/AutoBot-AI/pull/8622))

- *(deps-dev)* Bump jiti from 2.6.1 to 2.7.0 in /autobot-frontend (#8623) ([#8623](https://github.com/mrveiss/AutoBot-AI/pull/8623))

- *(deps-dev)* Bump @storybook/vue3-vite in /autobot-slm-frontend (#8624) ([#8624](https://github.com/mrveiss/AutoBot-AI/pull/8624))

- *(deps-dev)* Bump oxlint from 1.63.0 to 1.66.0 in /autobot-frontend (#8625) ([#8625](https://github.com/mrveiss/AutoBot-AI/pull/8625))

- *(deps-dev)* Bump postcss in /autobot-slm-frontend (#8626) ([#8626](https://github.com/mrveiss/AutoBot-AI/pull/8626))

- *(deps)* Bump vega-embed from 6.29.0 to 7.1.0 in /autobot-frontend (#8627) ([#8627](https://github.com/mrveiss/AutoBot-AI/pull/8627))

- *(deps)* Update fastapi requirement in /autobot-tts-worker (#8628) ([#8628](https://github.com/mrveiss/AutoBot-AI/pull/8628))

- *(deps)* Update numpy requirement in /autobot-tts-worker (#8630) ([#8630](https://github.com/mrveiss/AutoBot-AI/pull/8630))

- *(deps)* Update numpy requirement in /autobot-npu-worker (#8631) ([#8631](https://github.com/mrveiss/AutoBot-AI/pull/8631))

- *(deps)* Update chromadb requirement (#8632) ([#8632](https://github.com/mrveiss/AutoBot-AI/pull/8632))

- *(deps)* Update faiss-cpu requirement from >=1.13.2 to >=1.14.2 (#8633) ([#8633](https://github.com/mrveiss/AutoBot-AI/pull/8633))

- *(deps)* Update protobuf requirement (#8634) ([#8634](https://github.com/mrveiss/AutoBot-AI/pull/8634))

- *(deps)* Update pydantic requirement (#8635) ([#8635](https://github.com/mrveiss/AutoBot-AI/pull/8635))

- *(deps)* Update anthropic requirement from >=0.87.0 to >=0.104.1 (#8636) ([#8636](https://github.com/mrveiss/AutoBot-AI/pull/8636))

- *(deps)* Bump click from 8.1.8 to 8.4.1 (#8639) ([#8639](https://github.com/mrveiss/AutoBot-AI/pull/8639))

- *(ci)* Update vue-tsc baseline from 93 to 236

- *(deps)* Bump numpy>=2.4.5 (npu-worker) + transformers>=5.8.1 (tts-worker)

- *(deps-dev)* Bump eslint (#8123) ([#8123](https://github.com/mrveiss/AutoBot-AI/pull/8123))

- *(deps)* Bump undici (#8122) ([#8122](https://github.com/mrveiss/AutoBot-AI/pull/8122))

- *(deps-dev)* Bump vite from 8.0.9 to 8.0.13 in /autobot-slm-frontend (#8121) ([#8121](https://github.com/mrveiss/AutoBot-AI/pull/8121))

- *(deps-dev)* Bump playwright in /autobot-frontend (#8120) ([#8120](https://github.com/mrveiss/AutoBot-AI/pull/8120))

- *(deps-dev)* Bump @types/node in /autobot-slm-frontend (#8119) ([#8119](https://github.com/mrveiss/AutoBot-AI/pull/8119))

- *(deps)* Bump dompurify from 3.4.2 to 3.4.5 in /autobot-frontend (#8118) ([#8118](https://github.com/mrveiss/AutoBot-AI/pull/8118))

- *(deps)* Bump vue-i18n in /autobot-slm-frontend (#8117) ([#8117](https://github.com/mrveiss/AutoBot-AI/pull/8117))

- *(deps)* Bump apexcharts from 5.10.4 to 5.12.0 in /autobot-frontend (#8116) ([#8116](https://github.com/mrveiss/AutoBot-AI/pull/8116))

- *(deps-dev)* Bump @types/node in /autobot-frontend (#8113) ([#8113](https://github.com/mrveiss/AutoBot-AI/pull/8113))

- *(deps)* Bump onnxruntime-web in /autobot-frontend (#8112) ([#8112](https://github.com/mrveiss/AutoBot-AI/pull/8112))

- *(deps)* Update pydantic requirement (#8140) ([#8140](https://github.com/mrveiss/AutoBot-AI/pull/8140))

- *(deps)* Update huggingface-hub requirement (#8139) ([#8139](https://github.com/mrveiss/AutoBot-AI/pull/8139))

- *(deps)* Update pytest requirement (#8138) ([#8138](https://github.com/mrveiss/AutoBot-AI/pull/8138))

- *(deps)* Update spacy requirement (#8137) ([#8137](https://github.com/mrveiss/AutoBot-AI/pull/8137))

- *(deps)* Update llama-index-core requirement (#8136) ([#8136](https://github.com/mrveiss/AutoBot-AI/pull/8136))

- *(deps)* Update transformers requirement (#8135) ([#8135](https://github.com/mrveiss/AutoBot-AI/pull/8135))

- *(deps)* Update torch requirement in /autobot-tts-worker (#8133) ([#8133](https://github.com/mrveiss/AutoBot-AI/pull/8133))

- *(deps)* Bump aiofiles from 24.1.0 to 25.1.0 (#8132) ([#8132](https://github.com/mrveiss/AutoBot-AI/pull/8132))

- *(deps)* Bump uvicorn from 0.35.0 to 0.47.0 (#8131) ([#8131](https://github.com/mrveiss/AutoBot-AI/pull/8131))

- *(deps)* Update datasketch requirement from >=1.9.0 to >=1.10.0 (#8130) ([#8130](https://github.com/mrveiss/AutoBot-AI/pull/8130))

- *(deps)* Update python-multipart requirement in /autobot-tts-worker (#8129) ([#8129](https://github.com/mrveiss/AutoBot-AI/pull/8129))

- *(deps)* Bump kombu from 5.5.4 to 5.6.2 (#8128) ([#8128](https://github.com/mrveiss/AutoBot-AI/pull/8128))

- *(deps)* Update langgraph requirement (#8127) ([#8127](https://github.com/mrveiss/AutoBot-AI/pull/8127))

- *(deps)* Update playwright requirement in /autobot-browser-worker (#8126) ([#8126](https://github.com/mrveiss/AutoBot-AI/pull/8126))

- *(deps)* Update torch requirement in /autobot-npu-worker (#8124) ([#8124](https://github.com/mrveiss/AutoBot-AI/pull/8124))

- *(deps)* Update langgraph requirement in /autobot-backend (#8115) ([#8115](https://github.com/mrveiss/AutoBot-AI/pull/8115))

- *(deps)* Update torch requirement in /autobot-backend (#8114) ([#8114](https://github.com/mrveiss/AutoBot-AI/pull/8114))

- *(deps)* Update prometheus-client requirement (#8111) ([#8111](https://github.com/mrveiss/AutoBot-AI/pull/8111))

- *(deps)* Update cachetools requirement in /autobot-backend (#8110) ([#8110](https://github.com/mrveiss/AutoBot-AI/pull/8110))

- *(deps)* Update python-multipart requirement in /autobot-slm-backend (#8109) ([#8109](https://github.com/mrveiss/AutoBot-AI/pull/8109))

- *(deps)* Update networkx requirement in /autobot-backend (#8108) ([#8108](https://github.com/mrveiss/AutoBot-AI/pull/8108))

- *(deps)* Update uvicorn requirement in /autobot-slm-backend (#8107) ([#8107](https://github.com/mrveiss/AutoBot-AI/pull/8107))

- *(deps)* Update vllm requirement in /autobot-backend (#8105) ([#8105](https://github.com/mrveiss/AutoBot-AI/pull/8105))

- *(deps)* Bump sigstore/cosign-installer from 3.7.0 to 4.1.2 (#8106) ([#8106](https://github.com/mrveiss/AutoBot-AI/pull/8106))

- *(deps)* Bump actions/download-artifact from 4 to 8 (#8104) ([#8104](https://github.com/mrveiss/AutoBot-AI/pull/8104))

- *(deps)* Bump actions/setup-node from 4.0.2 to 6.4.0 (#8103) ([#8103](https://github.com/mrveiss/AutoBot-AI/pull/8103))

- *(deps)* Bump the npm_and_yarn group across 6 directories with 4 updates (#8018) ([#8018](https://github.com/mrveiss/AutoBot-AI/pull/8018))

- *(docs)* Enforce PR template with Thinking Path + Model Used CI check (#6474) (#7937) ([#7937](https://github.com/mrveiss/AutoBot-AI/pull/7937))

- *(api)* Remove _get_llm_interface() compat wrapper (#6944)

- *(tools)* Rename audit-unwired-trackers.py to audit_unwired_trackers.py (#7009) (#7844) ([#7844](https://github.com/mrveiss/AutoBot-AI/pull/7844))

- *(ansible)* Delete dead redis.service.j2 template (#6954) (#7806) ([#7806](https://github.com/mrveiss/AutoBot-AI/pull/7806))

- *(deps)* Phase D batch 4 — remove ast-tools + OTel floor fix + Dependabot grouping (#6959, #6960, #6961) ([#7784](https://github.com/mrveiss/AutoBot-AI/pull/7784))

- *(docs)* Enforce PR template with Thinking Path + Model Used CI check (#6474) (#7735) ([#7735](https://github.com/mrveiss/AutoBot-AI/pull/7735))

- *(ci/visual-regression)* Commit generated baselines from ubuntu-latest CI (GH#7410)

- *(deps)* Update onnxruntime requirement (#7589) ([#7589](https://github.com/mrveiss/AutoBot-AI/pull/7589))

- *(deps)* Update googleapis-common-protos requirement (#7588) ([#7588](https://github.com/mrveiss/AutoBot-AI/pull/7588))

- *(deps)* Update aiohttp requirement (#7587) ([#7587](https://github.com/mrveiss/AutoBot-AI/pull/7587))

- *(deps)* Update openvino requirement (#7586) ([#7586](https://github.com/mrveiss/AutoBot-AI/pull/7586))

- *(deps)* Update huggingface-hub requirement (#7585) ([#7585](https://github.com/mrveiss/AutoBot-AI/pull/7585))

- *(deps)* Update uvicorn requirement (#7584) ([#7584](https://github.com/mrveiss/AutoBot-AI/pull/7584))

- *(deps)* Bump pypdf from 6.10.2 to 6.11.0 (#7583) ([#7583](https://github.com/mrveiss/AutoBot-AI/pull/7583))

- *(deps)* Bump langchain-classic from 1.0.2 to 1.0.7 (#7582) ([#7582](https://github.com/mrveiss/AutoBot-AI/pull/7582))

- *(deps)* Update mcp requirement from >=1.27.0 to >=1.27.1 (#7581) ([#7581](https://github.com/mrveiss/AutoBot-AI/pull/7581))

- *(deps)* Update asyncssh requirement from >=2.22.0 to >=2.23.0 (#7580) ([#7580](https://github.com/mrveiss/AutoBot-AI/pull/7580))

- *(deps)* Bump playwright from 1.54.0 to 1.59.0 (#7579) ([#7579](https://github.com/mrveiss/AutoBot-AI/pull/7579))

- *(deps)* Bump zod (#7578) ([#7578](https://github.com/mrveiss/AutoBot-AI/pull/7578))

- *(deps)* Update fastapi requirement in /autobot-tts-worker (#7577) ([#7577](https://github.com/mrveiss/AutoBot-AI/pull/7577))

- *(deps)* Update transformers requirement in /autobot-tts-worker (#7576) ([#7576](https://github.com/mrveiss/AutoBot-AI/pull/7576))

- *(deps)* Update python-multipart requirement in /autobot-tts-worker (#7575) ([#7575](https://github.com/mrveiss/AutoBot-AI/pull/7575))

- *(deps-dev)* Bump @types/node (#7574) ([#7574](https://github.com/mrveiss/AutoBot-AI/pull/7574))

- *(deps-dev)* Bump eslint-plugin-vue in /autobot-slm-frontend (#7563) ([#7563](https://github.com/mrveiss/AutoBot-AI/pull/7563))

- *(deps-dev)* Bump typescript-eslint in /autobot-slm-frontend (#7562) ([#7562](https://github.com/mrveiss/AutoBot-AI/pull/7562))

- *(deps-dev)* Bump vite-plugin-vue-devtools in /autobot-frontend (#7561) ([#7561](https://github.com/mrveiss/AutoBot-AI/pull/7561))

- *(deps)* Bump vue-router in /autobot-slm-frontend (#7560) ([#7560](https://github.com/mrveiss/AutoBot-AI/pull/7560))

- *(deps)* Update llama-index-core requirement in /autobot-backend (#7558) ([#7558](https://github.com/mrveiss/AutoBot-AI/pull/7558))

- *(deps)* Bump dorny/paths-filter from 3.0.3 to 4.0.1 (#7557) ([#7557](https://github.com/mrveiss/AutoBot-AI/pull/7557))

- *(deps)* Update opentelemetry-instrumentation-fastapi requirement (#7555) ([#7555](https://github.com/mrveiss/AutoBot-AI/pull/7555))

- *(deps)* Bump actions/setup-node from 4.0.1 to 6.4.0 (#7554) ([#7554](https://github.com/mrveiss/AutoBot-AI/pull/7554))

- *(deps)* Update langchain-core requirement in /autobot-backend (#7553) ([#7553](https://github.com/mrveiss/AutoBot-AI/pull/7553))

- *(deps-dev)* Bump start-server-and-test in /autobot-frontend (#7552) ([#7552](https://github.com/mrveiss/AutoBot-AI/pull/7552))

- *(deps)* Bump actions/checkout from 4 to 6 (#7551) ([#7551](https://github.com/mrveiss/AutoBot-AI/pull/7551))

- *(deps)* Update langchain-ollama requirement in /autobot-backend (#7550) ([#7550](https://github.com/mrveiss/AutoBot-AI/pull/7550))

- *(deps)* Bump @tanstack/vue-virtual in /autobot-frontend (#7549) ([#7549](https://github.com/mrveiss/AutoBot-AI/pull/7549))

- *(deps)* Update python-multipart requirement in /autobot-slm-backend (#7548) ([#7548](https://github.com/mrveiss/AutoBot-AI/pull/7548))

- *(deps)* Update paramiko requirement in /autobot-backend (#7547) ([#7547](https://github.com/mrveiss/AutoBot-AI/pull/7547))

- *(deps)* Update pydantic-settings requirement (#7546) ([#7546](https://github.com/mrveiss/AutoBot-AI/pull/7546))

- *(deps)* Update paramiko requirement in /autobot-slm-backend (#7545) ([#7545](https://github.com/mrveiss/AutoBot-AI/pull/7545))

- *(deps-dev)* Bump eslint-plugin-oxlint in /autobot-frontend (#7556) ([#7556](https://github.com/mrveiss/AutoBot-AI/pull/7556))

- *(deps-dev)* Bump oxlint from 1.58.0 to 1.63.0 in /autobot-frontend (#7559) ([#7559](https://github.com/mrveiss/AutoBot-AI/pull/7559))

- *(frontend/types)* Clear two TS2339 composable hotspots — 110→93 (partial #7275) (#7500) ([#7500](https://github.com/mrveiss/AutoBot-AI/pull/7500))

- *(frontend/types)* Clear TS18046 in composables — 76→11 (closes #7274) (#7494) ([#7494](https://github.com/mrveiss/AutoBot-AI/pull/7494))

- *(frontend/types)* Clear Storybook stories vue-tsc cluster — 64 errors → 0 (closes #7273) (#7486) ([#7486](https://github.com/mrveiss/AutoBot-AI/pull/7486))

- *(lint)* Zero flake8 errors — 642 → 0 (closes #7360, completes #6946) (#7395) ([#7395](https://github.com/mrveiss/AutoBot-AI/pull/7395))

- *(format)* Black reformat 1322 backend files (closes #7046, #6946) (#7338) ([#7338](https://github.com/mrveiss/AutoBot-AI/pull/7338))

- *(deps-dev)* Bump prettier from 3.8.1 to 3.8.3 in /autobot-frontend (#7295) ([#7295](https://github.com/mrveiss/AutoBot-AI/pull/7295))

- *(deps)* Bump github/codeql-action from 4.35.3 to 4.35.4 (#7294) ([#7294](https://github.com/mrveiss/AutoBot-AI/pull/7294))

- *(deps)* Bump vue from 3.5.31 to 3.5.34 in /autobot-frontend (#7293) ([#7293](https://github.com/mrveiss/AutoBot-AI/pull/7293))

- *(deps)* Update tree-sitter-javascript requirement (#7292) ([#7292](https://github.com/mrveiss/AutoBot-AI/pull/7292))

- *(deps)* Update authlib requirement in /autobot-slm-backend (#7290) ([#7290](https://github.com/mrveiss/AutoBot-AI/pull/7290))

- *(deps-dev)* Bump @tailwindcss/postcss in /autobot-frontend (#7288) ([#7288](https://github.com/mrveiss/AutoBot-AI/pull/7288))

- *(deps)* Update pydantic requirement in /autobot-slm-backend (#7287) ([#7287](https://github.com/mrveiss/AutoBot-AI/pull/7287))

- *(deps)* Update numpy requirement in /autobot-backend (#7286) ([#7286](https://github.com/mrveiss/AutoBot-AI/pull/7286))

- *(deps)* Update sentence-transformers requirement (#7285) ([#7285](https://github.com/mrveiss/AutoBot-AI/pull/7285))

- *(deps)* Update chromadb requirement in /autobot-backend (#7284) ([#7284](https://github.com/mrveiss/AutoBot-AI/pull/7284))

- *(deps)* Update numpy requirement in /autobot-tts-worker (#7311) ([#7311](https://github.com/mrveiss/AutoBot-AI/pull/7311))

- *(deps)* Bump structlog from 25.4.0 to 25.5.0 (#7326) ([#7326](https://github.com/mrveiss/AutoBot-AI/pull/7326))

- *(deps)* Bump langchain from 1.2.13 to 1.2.18 (#7325) ([#7325](https://github.com/mrveiss/AutoBot-AI/pull/7325))

- *(deps)* Update numpy requirement (#7321) ([#7321](https://github.com/mrveiss/AutoBot-AI/pull/7321))

- *(deps)* Update fastapi requirement (#7320) ([#7320](https://github.com/mrveiss/AutoBot-AI/pull/7320))

- *(deps)* Update tokenizers requirement (#7319) ([#7319](https://github.com/mrveiss/AutoBot-AI/pull/7319))

- *(deps)* Update openvino requirement in /autobot-npu-worker (#7318) ([#7318](https://github.com/mrveiss/AutoBot-AI/pull/7318))

- *(deps)* Update numpy requirement in /autobot-npu-worker (#7317) ([#7317](https://github.com/mrveiss/AutoBot-AI/pull/7317))

- *(deps)* Update python-json-logger requirement (#7316) ([#7316](https://github.com/mrveiss/AutoBot-AI/pull/7316))

- *(deps)* Update llama-index requirement (#7315) ([#7315](https://github.com/mrveiss/AutoBot-AI/pull/7315))

- *(deps)* Update packaging requirement (#7314) ([#7314](https://github.com/mrveiss/AutoBot-AI/pull/7314))

- *(deps)* Update uvicorn requirement in /autobot-tts-worker (#7312) ([#7312](https://github.com/mrveiss/AutoBot-AI/pull/7312))

- *(deps)* Update huggingface-hub requirement in /autobot-tts-worker (#7310) ([#7310](https://github.com/mrveiss/AutoBot-AI/pull/7310))

- *(deps)* Update playwright requirement in /autobot-browser-worker (#7307) ([#7307](https://github.com/mrveiss/AutoBot-AI/pull/7307))

- *(deps-dev)* Bump eslint in /autobot-slm-frontend (#7303) ([#7303](https://github.com/mrveiss/AutoBot-AI/pull/7303))

- *(deps-dev)* Bump tailwindcss in /autobot-slm-frontend (#7302) ([#7302](https://github.com/mrveiss/AutoBot-AI/pull/7302))

- *(deps-dev)* Bump @types/node in /autobot-slm-frontend (#7301) ([#7301](https://github.com/mrveiss/AutoBot-AI/pull/7301))

- *(deps-dev)* Bump vue-tsc from 3.2.6 to 3.2.8 in /autobot-frontend (#7300) ([#7300](https://github.com/mrveiss/AutoBot-AI/pull/7300))

- *(deps-dev)* Bump @types/node in /autobot-frontend (#7298) ([#7298](https://github.com/mrveiss/AutoBot-AI/pull/7298))

- *(deps)* Bump the npm_and_yarn group across 6 directories with 5 updates (#7281) ([#7281](https://github.com/mrveiss/AutoBot-AI/pull/7281))

- *(deps)* Bump the npm_and_yarn group across 6 directories with 4 updates (#7130) ([#7130](https://github.com/mrveiss/AutoBot-AI/pull/7130))

- *(deps)* Bump the uv group across 2 directories with 1 update (#7129) ([#7129](https://github.com/mrveiss/AutoBot-AI/pull/7129))

- *(install)* Mark install.sh as executable in git tree (mode +x) (#7063) ([#7063](https://github.com/mrveiss/AutoBot-AI/pull/7063))

- *(format)* Black autobot_shared + autobot-slm-backend (65 files, partial #6946) (#6974) ([#6974](https://github.com/mrveiss/AutoBot-AI/pull/6974))

- *(frontend/ui)* Remove dead useAppStore import in SystemStatusNotification (#6879) (#6963) ([#6963](https://github.com/mrveiss/AutoBot-AI/pull/6963))

- *(security)* Delete deprecated command_executor.py shim (#6515) (#6952) ([#6952](https://github.com/mrveiss/AutoBot-AI/pull/6952))

- *(deps)* Update python-multipart requirement in /autobot-slm-backend (#6883) ([#6883](https://github.com/mrveiss/AutoBot-AI/pull/6883))

- *(deps)* Bump dompurify from 3.4.1 to 3.4.2 in /autobot-frontend (#6898) ([#6898](https://github.com/mrveiss/AutoBot-AI/pull/6898))

- *(deps)* Bump cytoscape from 3.33.1 to 3.33.3 in /autobot-frontend (#6895) ([#6895](https://github.com/mrveiss/AutoBot-AI/pull/6895))

- *(deps-dev)* Bump @vitejs/plugin-vue in /autobot-frontend (#6894) ([#6894](https://github.com/mrveiss/AutoBot-AI/pull/6894))

- *(deps)* Bump axios from 1.15.2 to 1.16.0 in /autobot-slm-frontend (#6901) ([#6901](https://github.com/mrveiss/AutoBot-AI/pull/6901))

- *(deps-dev)* Bump tailwindcss in /autobot-frontend (#6896) ([#6896](https://github.com/mrveiss/AutoBot-AI/pull/6896))

- *(deps)* Update opentelemetry-instrumentation-fastapi requirement (#6890) ([#6890](https://github.com/mrveiss/AutoBot-AI/pull/6890))

- *(deps)* Update fastapi requirement in /autobot-slm-backend (#6884) ([#6884](https://github.com/mrveiss/AutoBot-AI/pull/6884))

- *(deps)* Update langgraph-checkpoint-redis requirement (#6885) ([#6885](https://github.com/mrveiss/AutoBot-AI/pull/6885))

- *(deps)* Update opentelemetry-instrumentation-aiohttp-client requirement (#6893) ([#6893](https://github.com/mrveiss/AutoBot-AI/pull/6893))

- *(deps)* Update opentelemetry-instrumentation-aiohttp-client requirement (#6892) ([#6892](https://github.com/mrveiss/AutoBot-AI/pull/6892))

- *(deps)* Update ast-tools requirement in /autobot-backend (#6886) ([#6886](https://github.com/mrveiss/AutoBot-AI/pull/6886))

- *(deps)* Update psycopg2-binary requirement in /autobot-slm-backend (#6887) ([#6887](https://github.com/mrveiss/AutoBot-AI/pull/6887))

- *(deps)* Update fastapi requirement in /autobot-backend (#6889) ([#6889](https://github.com/mrveiss/AutoBot-AI/pull/6889))

- *(deps-dev)* Bump eslint-plugin-vue in /autobot-slm-frontend (#6897) ([#6897](https://github.com/mrveiss/AutoBot-AI/pull/6897))

- *(deps)* Bump opentelemetry-api in /autobot-backend (#6888) ([#6888](https://github.com/mrveiss/AutoBot-AI/pull/6888))

- *(deps)* Update opentelemetry-exporter-otlp requirement (#6891) ([#6891](https://github.com/mrveiss/AutoBot-AI/pull/6891))

- *(deps-dev)* Bump @vitejs/plugin-vue in /autobot-slm-frontend (#6899) ([#6899](https://github.com/mrveiss/AutoBot-AI/pull/6899))

- *(deps-dev)* Bump eslint-plugin-cypress in /autobot-frontend (#6900) ([#6900](https://github.com/mrveiss/AutoBot-AI/pull/6900))

- *(ci)* Test + CI-integrate hardcoded-values pre-commit hook (#6725) (#6762) ([#6762](https://github.com/mrveiss/AutoBot-AI/pull/6762))

- *(prompts)* Inject SSOT VM/port vars into chat prompt templates (#6724) (#6742) ([#6742](https://github.com/mrveiss/AutoBot-AI/pull/6742))

- *(cleanup)* Delete stale audit artifacts (#6716) (#6717) ([#6717](https://github.com/mrveiss/AutoBot-AI/pull/6717))

- *(chat)* Remove duplicate stacked @with_error_handling decorators (#6501) (#6518) ([#6518](https://github.com/mrveiss/AutoBot-AI/pull/6518))

- *(chat_workflow)* Remove dead _append_verbatim_turn method (#6450) (#6477) ([#6477](https://github.com/mrveiss/AutoBot-AI/pull/6477))

- *(deps)* Bump dompurify from 3.4.0 to 3.4.1 in /autobot-frontend (#6334) ([#6334](https://github.com/mrveiss/AutoBot-AI/pull/6334))

- *(deps-dev)* Bump postcss in /autobot-slm-frontend (#6333) ([#6333](https://github.com/mrveiss/AutoBot-AI/pull/6333))

- *(deps)* Bump axios from 1.15.1 to 1.15.2 in /autobot-slm-frontend (#6332) ([#6332](https://github.com/mrveiss/AutoBot-AI/pull/6332))

- *(deps-dev)* Bump vue-tsc in /autobot-slm-frontend (#6331) ([#6331](https://github.com/mrveiss/AutoBot-AI/pull/6331))

- *(deps-dev)* Bump jsdom from 29.0.1 to 29.1.0 in /autobot-frontend (#6330) ([#6330](https://github.com/mrveiss/AutoBot-AI/pull/6330))

- *(deps-dev)* Bump vitest from 4.1.4 to 4.1.5 in /autobot-frontend (#6329) ([#6329](https://github.com/mrveiss/AutoBot-AI/pull/6329))

- *(deps-dev)* Bump msw from 2.12.14 to 2.13.6 in /autobot-frontend (#6328) ([#6328](https://github.com/mrveiss/AutoBot-AI/pull/6328))

- *(deps)* Update opentelemetry-instrumentation-redis requirement (#6327) ([#6327](https://github.com/mrveiss/AutoBot-AI/pull/6327))

- *(deps)* Update pydantic requirement in /autobot_shared (#6326) ([#6326](https://github.com/mrveiss/AutoBot-AI/pull/6326))

- *(deps)* Update pandas requirement in /autobot-backend (#6325) ([#6325](https://github.com/mrveiss/AutoBot-AI/pull/6325))

- *(deps-dev)* Bump eslint-plugin-vue in /autobot-frontend (#6324) ([#6324](https://github.com/mrveiss/AutoBot-AI/pull/6324))

- *(deps)* Update opentelemetry-api requirement in /autobot_shared (#6323) ([#6323](https://github.com/mrveiss/AutoBot-AI/pull/6323))

- *(deps)* Update graspologic requirement in /autobot-backend (#6322) ([#6322](https://github.com/mrveiss/AutoBot-AI/pull/6322))

- *(deps)* Update openai requirement in /autobot-backend (#6321) ([#6321](https://github.com/mrveiss/AutoBot-AI/pull/6321))

- *(deps)* Update cryptography requirement in /autobot-slm-backend (#6320) ([#6320](https://github.com/mrveiss/AutoBot-AI/pull/6320))

- *(deps)* Update mcp requirement in /autobot-backend (#6319) ([#6319](https://github.com/mrveiss/AutoBot-AI/pull/6319))

- *(deps)* Update uvicorn requirement in /autobot-slm-backend (#6318) ([#6318](https://github.com/mrveiss/AutoBot-AI/pull/6318))

- *(deps)* Update uvicorn requirement in /autobot-backend (#6317) ([#6317](https://github.com/mrveiss/AutoBot-AI/pull/6317))

- *(deps)* Bump actions/setup-node from 4 to 6 (#6316) ([#6316](https://github.com/mrveiss/AutoBot-AI/pull/6316))

- *(deps)* Update authlib requirement in /autobot-slm-backend (#6315) ([#6315](https://github.com/mrveiss/AutoBot-AI/pull/6315))

- *(backend)* Wire IsolatedBridgeRegistry graceful shutdown on backend exit (#4107) (#6287) ([#6287](https://github.com/mrveiss/AutoBot-AI/pull/6287))

- *(deps)* Remove dead llama-index-vector-stores-redis and llama-index-readers-file (#6127) (#6207) ([#6207](https://github.com/mrveiss/AutoBot-AI/pull/6207))

- *(composables)* Delete useAsyncOperation.ts and AsyncOperationExample.vue — all callers migrated (#6020) (#6117) ([#6117](https://github.com/mrveiss/AutoBot-AI/pull/6117))

- *(redis)* Migrate 3 remaining get_redis_client(async_client=True) callers to get_async_redis_client() (#5661) (#5668) ([#5668](https://github.com/mrveiss/AutoBot-AI/pull/5668))

- *(services)* Delete byte-identical CronScheduler duplicate in services/scheduler/ (#5428) (#5459) ([#5459](https://github.com/mrveiss/AutoBot-AI/pull/5459))

- *(infra)* Delete dead commented import for non-existent SemanticChunker class (#5396) (#5404) ([#5404](https://github.com/mrveiss/AutoBot-AI/pull/5404))

- *(deps-dev)* Bump vite from 7.3.2 to 8.0.9 in /autobot-slm-frontend (#5300) ([#5300](https://github.com/mrveiss/AutoBot-AI/pull/5300))

- *(deps-dev)* Bump eslint-plugin-cypress in /autobot-frontend (#5298) ([#5298](https://github.com/mrveiss/AutoBot-AI/pull/5298))

- *(deps-dev)* Bump typescript in /autobot-slm-frontend (#5303) ([#5303](https://github.com/mrveiss/AutoBot-AI/pull/5303))

- *(deps)* Bump three and @types/three in /autobot-frontend (#5302) ([#5302](https://github.com/mrveiss/AutoBot-AI/pull/5302))

- *(deps)* Bump codecov/codecov-action from 4 to 6 (#5296) ([#5296](https://github.com/mrveiss/AutoBot-AI/pull/5296))

- *(deps)* Bump docker/build-push-action from 4 to 7 (#5295) ([#5295](https://github.com/mrveiss/AutoBot-AI/pull/5295))

- *(deps)* Bump actions/upload-artifact from 4 to 7 (#5294) ([#5294](https://github.com/mrveiss/AutoBot-AI/pull/5294))

- *(deps)* Bump axios from 1.15.0 to 1.15.1 in /autobot-slm-frontend (#5301) ([#5301](https://github.com/mrveiss/AutoBot-AI/pull/5301))

- *(deps-dev)* Bump vite from 8.0.5 to 8.0.9 in /autobot-frontend (#5297) ([#5297](https://github.com/mrveiss/AutoBot-AI/pull/5297))

- *(deps-dev)* Bump happy-dom in /autobot-frontend (#5299) ([#5299](https://github.com/mrveiss/AutoBot-AI/pull/5299))

- *(deps-dev)* Bump eslint from 10.2.0 to 10.2.1 in /autobot-frontend (#5304) ([#5304](https://github.com/mrveiss/AutoBot-AI/pull/5304))

- *(frontend)* Delete useApiRequest (0 callers) (#5183) (#5217) ([#5217](https://github.com/mrveiss/AutoBot-AI/pull/5217))

- *(cleanup)* Remove accidentally-committed MERGE_PLAN.md + gitignore agent scratch (#5098)

- *(deps)* Bump 3d-force-graph in /autobot-frontend

- *(deps-dev)* Bump @types/node in /autobot-slm-frontend

- *(deps)* Bump docker/setup-buildx-action from 3 to 4

- *(deps)* Bump actions/checkout from 4 to 6

- *(deps)* Bump actions/upload-artifact from 4 to 7

- *(deps-dev)* Bump @types/node in /autobot-frontend

- *(deps-dev)* Bump typescript in /autobot-frontend

- *(deps-dev)* Bump cypress in /autobot-frontend

- *(deps-dev)* Bump eslint from 10.1.0 to 10.2.0 in /autobot-frontend

- *(deps)* Bump vue from 3.5.31 to 3.5.32 in /autobot-slm-frontend

- *(deps-dev)* Bump typescript-eslint in /autobot-slm-frontend

- Update package-lock.json after vitest run

- *(release)* Merge Dev_new_gui into main — 486 commits, 25+ batch PRs

- *(deps)* Bump the npm_and_yarn group across 2 directories with 2 updates

- *(deps)* Bump the npm_and_yarn group across 5 directories with 2 updates (#4845) ([#4845](https://github.com/mrveiss/AutoBot-AI/pull/4845))

- *(deps)* Bump the npm_and_yarn group across 2 directories with 2 updates (#4844) ([#4844](https://github.com/mrveiss/AutoBot-AI/pull/4844))

- *(deps)* Add networkx, graspologic, tree-sitter for mesh+AST gaps (#4818 #4819 #4820)

- *(deps)* Bump follow-redirects (#4596) ([#4596](https://github.com/mrveiss/AutoBot-AI/pull/4596))

- *(dead-code)* Remove orphaned HomeView.vue and TheWelcome.vue (#4510)

- *(py312)* Target only Python 3.12 in black config

- *(deps)* Bump actions/github-script from 4 to 9 (#4329) ([#4329](https://github.com/mrveiss/AutoBot-AI/pull/4329))

- *(deps)* Bump actions/download-artifact from 4 to 8 (#4330) ([#4330](https://github.com/mrveiss/AutoBot-AI/pull/4330))

- *(deps)* Bump softprops/action-gh-release from 2 to 3 (#4331) ([#4331](https://github.com/mrveiss/AutoBot-AI/pull/4331))

- *(deps-dev)* Bump vitest from 4.1.2 to 4.1.4 in /autobot-frontend (#4332) ([#4332](https://github.com/mrveiss/AutoBot-AI/pull/4332))

- *(deps-dev)* Bump cypress in /autobot-frontend (#4334) ([#4334](https://github.com/mrveiss/AutoBot-AI/pull/4334))

- *(deps-dev)* Bump @vitest/eslint-plugin in /autobot-frontend (#4335) ([#4335](https://github.com/mrveiss/AutoBot-AI/pull/4335))

- *(deps-dev)* Bump start-server-and-test in /autobot-frontend (#4336) ([#4336](https://github.com/mrveiss/AutoBot-AI/pull/4336))

- *(frontend)* Update package dependencies

- *(install)* Add validation for required service distributions (#4130)

- *(claude)* Add pre-commit hook for mass deletion detection (#4111)

- *(deps)* Bump the npm_and_yarn group across 2 directories with 1 update

- *(deps)* Bump the npm_and_yarn group across 2 directories with 1 update (#4077) ([#4077](https://github.com/mrveiss/AutoBot-AI/pull/4077))

- *(infrastructure)* Remove hardcoded .19 host references

- *(infrastructure)* Add pre-deployment validation (#4056) (#4072) ([#4072](https://github.com/mrveiss/AutoBot-AI/pull/4072))

- *(redis)* Clarify async client initialization pattern in documentation (#3972)

- *(redis)* Update MANDATORY USAGE PATTERN docstring (#4058) (#4068) ([#4068](https://github.com/mrveiss/AutoBot-AI/pull/4068))

- *(redis)* Add get_async_redis_client to __all__ (#4057) (#4069) ([#4069](https://github.com/mrveiss/AutoBot-AI/pull/4069))

- *(infrastructure)* Update browser-worker uvicorn config (#4062) (#4064) ([#4064](https://github.com/mrveiss/AutoBot-AI/pull/4064))

- *(infrastructure)* Update autobot-browser-worker.service template to Node.js/Express (#4062)

- Remove old issue worktree directories (#3205, #3938)

- *(redis)* Clarify async client initialization pattern in docstring (#3972) (#4042) ([#4042](https://github.com/mrveiss/AutoBot-AI/pull/4042))

- *(redis)* Clarify async client initialization pattern in documentation (#3972) (#3993) ([#3993](https://github.com/mrveiss/AutoBot-AI/pull/3993))

- *(redis)* Clarify async client initialization pattern in documentation (#3972)

- *(deps)* Bump npm_and_yarn dependencies across 4 directories

- *(deps)* Bump the npm_and_yarn group across 4 directories with 2 updates

- *(deps)* Bump the npm_and_yarn group across 4 directories with 2 updates (#3949) ([#3949](https://github.com/mrveiss/AutoBot-AI/pull/3949))

- *(retry)* Remove tenacity from llm_pattern_analyzer_test.py (#3936)

- *(autoresearch)* Refactor _register_autoresearch_hypothesis_target (#3884) (#3951) ([#3951](https://github.com/mrveiss/AutoBot-AI/pull/3951))

- *(agents)* Remove duplicate session_id assignment in sentiment_analysis_agent.py (#3944) (#3950) ([#3950](https://github.com/mrveiss/AutoBot-AI/pull/3950))

- *(config)* Delete tombstoned config.py — shadowed by config/ package (#3933) (#3934) ([#3934](https://github.com/mrveiss/AutoBot-AI/pull/3934))

- *(backend)* Migrate models/settings.py — 8 BaseSettings to pydantic v2 model_config (#3911) ([#3923](https://github.com/mrveiss/AutoBot-AI/pull/3923))

- *(config)* Remove leftover Issue:#3803 comment from TimeoutConfig (#3912) ([#3922](https://github.com/mrveiss/AutoBot-AI/pull/3922))

- *(mcp)* Delete dead mcp_manual_integration.py (#3849) ([#3906](https://github.com/mrveiss/AutoBot-AI/pull/3906))

- *(config)* Tombstone root-level config.py ConfigManager; migrate top callers to ssot_config (#3829) ([#3909](https://github.com/mrveiss/AutoBot-AI/pull/3909))

- *(backend)* Delete dead type_definitions/ package (#3839) (#3892) ([#3892](https://github.com/mrveiss/AutoBot-AI/pull/3892))

- *(autoresearch)* Rename test_issue_3208.py to benchmark_test.py (#3883) (#3893) ([#3893](https://github.com/mrveiss/AutoBot-AI/pull/3893))

- *(types)* Rename 3 competing TaskComplexity enums to distinct names (#3878) ([#3878](https://github.com/mrveiss/AutoBot-AI/pull/3878))

- *(backend)* Delete confirmed dead root-level modules (#3847) (#3887) ([#3887](https://github.com/mrveiss/AutoBot-AI/pull/3887))

- *(config)* Refactor sync_config to ≤65 lines per function (#3863) (#3888) ([#3888](https://github.com/mrveiss/AutoBot-AI/pull/3888))

- Post-merge polish — hoist diary fetch limit, document property_graph serialisation, explain FeatureConfig alias suffixes

- *(backend)* Add TimeoutConfig to SSOT config (#3820) ([#3820](https://github.com/mrveiss/AutoBot-AI/pull/3820))

- *(ansible)* Move _SECRET_TO_ANSIBLE_VAR to shared location (#3778) (#3819) ([#3819](https://github.com/mrveiss/AutoBot-AI/pull/3819))

- *(autoresearch)* Deduplicate _NOTIFY_KEY format string (#3795) (#3818) ([#3818](https://github.com/mrveiss/AutoBot-AI/pull/3818))

- *(backend)* Use config.path.docs_path in mcp_manual_integration (#3802) (#3817) ([#3817](https://github.com/mrveiss/AutoBot-AI/pull/3817))

- *(backend)* Delete legacy chat_history_manager.py monolith (#3838) ([#3842](https://github.com/mrveiss/AutoBot-AI/pull/3842))

- *(backend)* Expand hardcoding prevention for file paths and model names (#3397) (#3799) ([#3799](https://github.com/mrveiss/AutoBot-AI/pull/3799))

- *(ansible)* Move _SECRET_TO_ANSIBLE_VAR to shared location to avoid drift (#3778) (#3782) ([#3782](https://github.com/mrveiss/AutoBot-AI/pull/3782))

- *(chat-workflow)* Remove orphaned system_prompt param from _build_full_prompt (#3794) (#3801) ([#3801](https://github.com/mrveiss/AutoBot-AI/pull/3801))

- *(frontend)* Add i18n keys for KB vectorization UI components (#3785) ([#3785](https://github.com/mrveiss/AutoBot-AI/pull/3785))

- *(frontend)* Adopt getApiBase() in AppConfig.js and ServiceDiscovery.js (#3751) (#3769) ([#3769](https://github.com/mrveiss/AutoBot-AI/pull/3769))

- *(frontend)* Adopt getApiBase() in ApiClientMonitor.js (#3752) (#3767) ([#3767](https://github.com/mrveiss/AutoBot-AI/pull/3767))

- *(frontend)* Adopt getApiBase() in remaining 7 SecretsApiClient.js paths (#3746) (#3757) ([#3757](https://github.com/mrveiss/AutoBot-AI/pull/3757))

- *(frontend)* Adopt getApiBase() in JS utility files (#3726) (#3730) ([#3730](https://github.com/mrveiss/AutoBot-AI/pull/3730))

- *(slm-frontend)* Replace remaining 2 hardcoded /api/ with getSlmApiBase() (#3725) (#3733) ([#3733](https://github.com/mrveiss/AutoBot-AI/pull/3733))

- *(tests)* Extend get_test_backend_url() to remaining 14 backend test files (#3661) (#3727) ([#3727](https://github.com/mrveiss/AutoBot-AI/pull/3727))

- *(analytics)* Fix flake8 E501 line-length violation in analytics_evolution.py (#3724) (#3741) ([#3741](https://github.com/mrveiss/AutoBot-AI/pull/3741))

- *(dev)* Uncomment aiosqlite in autobot-backend/requirements.txt (#3723) (#3745) ([#3745](https://github.com/mrveiss/AutoBot-AI/pull/3745))

- *(dev)* Add requirements-dev.txt with structlog and aiosqlite (#3723) ([#3736](https://github.com/mrveiss/AutoBot-AI/pull/3736))

- *(backend)* Add explicit encoding='utf-8' to file I/O (#3391) ([#3710](https://github.com/mrveiss/AutoBot-AI/pull/3710))

- *(frontend)* Adopt getApiBase() in analytics Vue components (#3681) ([#3708](https://github.com/mrveiss/AutoBot-AI/pull/3708))

- *(frontend)* Adopt getApiBase() in knowledge Vue components (Phase 5c) (#3629) ([#3700](https://github.com/mrveiss/AutoBot-AI/pull/3700))

- *(frontend)* Adopt getApiBase() in security, visualizations, workflow, and research Vue components (#3684) (#3706) ([#3706](https://github.com/mrveiss/AutoBot-AI/pull/3706))

- *(frontend)* Adopt getApiBase() in knowledge Vue components (#3682) (#3703) ([#3703](https://github.com/mrveiss/AutoBot-AI/pull/3703))

- *(frontend)* Replace hardcoded /api/advanced/ with getApiBase() in BusinessIntelligenceView (#3674) ([#3704](https://github.com/mrveiss/AutoBot-AI/pull/3704))

- *(frontend)* Use getApiBase() instead of getBackendUrl() in notification composables (#3675) ([#3697](https://github.com/mrveiss/AutoBot-AI/pull/3697))

- *(infrastructure)* Standardise Redis file ownership to autobot:autobot (#3396) ([#3696](https://github.com/mrveiss/AutoBot-AI/pull/3696))

- *(slm-frontend)* Replace hardcoded /autobot-api/ with getBackendUrl() (#3652) (no-op — already in #3662) ([#3694](https://github.com/mrveiss/AutoBot-AI/pull/3694))

- *(frontend)* Adopt getApiBase() in chat Vue components (Phase 5b) ([#3690](https://github.com/mrveiss/AutoBot-AI/pull/3690))

- *(frontend)* Adopt getApiBase() in Vue components and views (Phase 4) ([#3678](https://github.com/mrveiss/AutoBot-AI/pull/3678))

- *(ci)* Add doc linting to catch stale file references in developer guides (#3425) ([#3692](https://github.com/mrveiss/AutoBot-AI/pull/3692))

- *(slm-frontend)* Replace hardcoded /api/ with getSlmApiBase() (#3627) (#3676) ([#3676](https://github.com/mrveiss/AutoBot-AI/pull/3676))

- *(frontend)* Remove duplicate getApiBase() declarations from ssot-config.ts (#3628) ([#3665](https://github.com/mrveiss/AutoBot-AI/pull/3665))

- *(slm-frontend)* Replace hardcoded /autobot-api/ with getBackendUrl() ([#3662](https://github.com/mrveiss/AutoBot-AI/pull/3662))

- *(tests)* Replace hardcoded localhost:8001 with get_test_backend_url() helper ([#3660](https://github.com/mrveiss/AutoBot-AI/pull/3660))

- *(frontend)* Remove duplicate getApiBase() declarations from ssot-config.ts (#3631) ([#3663](https://github.com/mrveiss/AutoBot-AI/pull/3663))

- *(ci)* Align isort line_length with Black at 120 in pyproject.toml (#3408) ([#3657](https://github.com/mrveiss/AutoBot-AI/pull/3657))

- *(frontend)* Adopt getApiBase() in stores, models, and components (#3631) (#3641) ([#3641](https://github.com/mrveiss/AutoBot-AI/pull/3641))

- *(frontend)* Adopt getApiBase() in service and utils layer (#3629) ([#3638](https://github.com/mrveiss/AutoBot-AI/pull/3638))

- *(frontend)* Adopt getApiBase() in composables (#3630) ([#3633](https://github.com/mrveiss/AutoBot-AI/pull/3633))

- *(slm-frontend)* Replace hardcoded /api/ with getSlmApiBase() in 3 remaining files (#3627) ([#3634](https://github.com/mrveiss/AutoBot-AI/pull/3634))

- *(frontend)* Add getApiBase() to ssot-config for configurable API prefix (#3628) ([#3632](https://github.com/mrveiss/AutoBot-AI/pull/3632))

- *(deps-dev)* Bump eslint-plugin-oxlint in /autobot-frontend (#3603) ([#3603](https://github.com/mrveiss/AutoBot-AI/pull/3603))

- *(deps-dev)* Bump @playwright/test in /autobot-frontend (#3602) ([#3602](https://github.com/mrveiss/AutoBot-AI/pull/3602))

- *(deps-dev)* Bump @types/node in /autobot-frontend (#3601) ([#3601](https://github.com/mrveiss/AutoBot-AI/pull/3601))

- *(deps-dev)* Bump esbuild from 0.27.4 to 0.28.0 in /autobot-frontend (#3600) ([#3600](https://github.com/mrveiss/AutoBot-AI/pull/3600))

- *(deps)* Bump vue-i18n from 11.3.0 to 11.3.1 in /autobot-frontend (#3599) ([#3599](https://github.com/mrveiss/AutoBot-AI/pull/3599))

- *(deps)* Bump docker/build-push-action from 5 to 7 (#3598) ([#3598](https://github.com/mrveiss/AutoBot-AI/pull/3598))

- *(deps)* Bump docker/login-action from 3 to 4 (#3597) ([#3597](https://github.com/mrveiss/AutoBot-AI/pull/3597))

- *(deps)* Bump actions/checkout from 4 to 6 (#3596) ([#3596](https://github.com/mrveiss/AutoBot-AI/pull/3596))

- Enforce Black + isort formatting in pre-commit and CI (#3571) ([#3571](https://github.com/mrveiss/AutoBot-AI/pull/3571))

- *(backend)* Delete dead api/phase_management.py superseded by api/phases.py (#3504) ([#3508](https://github.com/mrveiss/AutoBot-AI/pull/3508))

- *(deps)* Bump the npm_and_yarn group across 5 directories with 3 updates

- *(deps)* Bump the npm_and_yarn group across 2 directories with 2 updates (#3623) ([#3623](https://github.com/mrveiss/AutoBot-AI/pull/3623))

- *(deps)* Bump defu (#3624) ([#3624](https://github.com/mrveiss/AutoBot-AI/pull/3624))

- *(backend)* Delete deprecated terminal modules, update tests to ConsolidatedTerminalWebSocket (#3357) (#3373) ([#3373](https://github.com/mrveiss/AutoBot-AI/pull/3373))

- *(backend)* Clarify kb_librarian is internal-only, delete unreachable e2e tests (#3348) (#3368) ([#3368](https://github.com/mrveiss/AutoBot-AI/pull/3368))

- *(backend)* Delete dead code mesh_brain.py and monitoring_compat.py (#3354) (#3367) ([#3367](https://github.com/mrveiss/AutoBot-AI/pull/3367))

- *(docs)* Remove stale phase-D analysis reports — issues filed (#3374, #3375, #3376)

- *(frontend)* Tailwind v4 audit — verify no remaining v3 patterns (#3153) (#3361) ([#3361](https://github.com/mrveiss/AutoBot-AI/pull/3361))

- *(deps)* Bump the npm_and_yarn group across 5 directories with 2 updates (#3269) ([#3269](https://github.com/mrveiss/AutoBot-AI/pull/3269))

- *(docs)* Move docs/CHANGELOG.md into docs/changelog/ (#3317) ([#3317](https://github.com/mrveiss/AutoBot-AI/pull/3317))

- *(docs)* Delete stale planning/tasks/ breakdown files (#3316) ([#3316](https://github.com/mrveiss/AutoBot-AI/pull/3316))

- *(gitignore)* Ignore Obsidian workspace.json in docs vault

- *(deps)* Bump the pip group across 3 directories with 3 updates ([#3213](https://github.com/mrveiss/AutoBot-AI/pull/3213))

- *(deps)* Resolve merge conflicts with Dev_new_gui

- *(ansible)* Audit and document clean task single-host guards (#2836) (#2947) ([#2947](https://github.com/mrveiss/AutoBot-AI/pull/2947))

- *(ansible)* Move autobot_key to /etc/autobot/ssh/ for multi-user access (#2828) (#2936) ([#2936](https://github.com/mrveiss/AutoBot-AI/pull/2936))

- *(deps)* Bump the pip group across 2 directories with 2 updates (#2928) ([#2928](https://github.com/mrveiss/AutoBot-AI/pull/2928))

- *(deps-dev)* Bump eslint from 9.39.4 to 10.1.0 in /autobot-frontend (#2892) ([#2892](https://github.com/mrveiss/AutoBot-AI/pull/2892))

- *(deps-dev)* Bump typescript in /autobot-frontend (#2889) ([#2889](https://github.com/mrveiss/AutoBot-AI/pull/2889))

- *(deps-dev)* Bump start-server-and-test in /autobot-frontend (#2893) ([#2893](https://github.com/mrveiss/AutoBot-AI/pull/2893))

- *(deps-dev)* Bump @types/cookie in /autobot-frontend (#2891) ([#2891](https://github.com/mrveiss/AutoBot-AI/pull/2891))

- *(backend)* Remove stale TODO comments referencing closed issues (#2867) (#2895) ([#2895](https://github.com/mrveiss/AutoBot-AI/pull/2895))

- *(deps)* Bump uv group — cryptography 46.0.6, langchain-core 1.2.22 ([#2619](https://github.com/mrveiss/AutoBot-AI/pull/2619))

- *(deps)* Bump cryptography 46.0.6 and langchain-core 1.2.22 (pip group) ([#2618](https://github.com/mrveiss/AutoBot-AI/pull/2618))

- *(deps-dev)* Bump happy-dom

- *(deps-dev)* Bump eslint-plugin-oxlint in /autobot-frontend

- *(deps)* Bump opentelemetry-api in /autobot-backend

- *(deps)* Bump actions/checkout from 4 to 6

- *(deps)* Bump codecov/codecov-action from 5 to 6

- *(deps-dev)* Bump autoprefixer in /autobot-frontend

- *(deps-dev)* Bump @vitejs/plugin-vue-jsx in /autobot-frontend

- *(deps)* Bump the pip group across 3 directories with 3 updates

- *(deps)* Audit and clean stale comments in requirements.txt files (#2471)

- *(devops)* Add stale worktree cleanup script (#2467)


### Performance

- *(voice-rbac)* Cache tool counts + _is_admin helper (#8979 #8980) (#9032) ([#9032](https://github.com/mrveiss/AutoBot-AI/pull/9032))

- *(voice-rbac)* Replace N+1 bundle loop with Promise.all (MVA-1163) (#8712) ([#8712](https://github.com/mrveiss/AutoBot-AI/pull/8712))

- *(vector-search)* Batch ChromaDB queries, expand search cache, add SQ8 quantization (#8153, #8154, #8155) (#8363) ([#8363](https://github.com/mrveiss/AutoBot-AI/pull/8363))

- *(classification,llm-cache)* Add request dedup, batch classify, and semantic cache (#8164, #8168) (#8358) ([#8358](https://github.com/mrveiss/AutoBot-AI/pull/8358))

- *(npu)* Add Redis-backed L2 embedding cache across uvicorn workers (#8159) (#8356) ([#8356](https://github.com/mrveiss/AutoBot-AI/pull/8356))

- *(vector-search)* Wire IVFPQ index via FAISS for autobot_memory (#8157) (#8355) ([#8355](https://github.com/mrveiss/AutoBot-AI/pull/8355))

- *(embedding-cache)* Replace fixed LRU with ARC for hot-query resilience (#8156) (#8354) ([#8354](https://github.com/mrveiss/AutoBot-AI/pull/8354))

- *(redis,async)* Pipeline N+1 expire calls, atomic SET EX, async file I/O (#8162,#8163,#8165) ([#8349](https://github.com/mrveiss/AutoBot-AI/pull/8349))

- *(code-analysis)* Add AST cache to eliminate O(2N) re-parsing in cross-file finalize pass (#7902) ([#7902](https://github.com/mrveiss/AutoBot-AI/pull/7902))

- *(llm)* Deterministic payload ordering to maximise cache hits (#7368) (#7867) ([#7867](https://github.com/mrveiss/AutoBot-AI/pull/7867))

- *(skill-router)* Prepared-runtime-facts pattern for skill router + LLM gateway (#7370) ([#7691](https://github.com/mrveiss/AutoBot-AI/pull/7691))

- *(chat/search_web)* Eliminate duplicate Playwright call in fetch_full fallback (closes #7478) (#7491) ([#7491](https://github.com/mrveiss/AutoBot-AI/pull/7491))

- *(web_fetch)* Collapse _fetch_bs4 double round-trip into single request (closes #7459) (#7480) ([#7480](https://github.com/mrveiss/AutoBot-AI/pull/7480))

- *(voice)* Make _TTS_PIPELINE_DEPTH env-configurable; default 2 (#6811) (#6812) ([#6812](https://github.com/mrveiss/AutoBot-AI/pull/6812))

- *(api/skills)* Replace N sequential redis.get() calls with single mget() in traces endpoint (#6312) (#6348) ([#6348](https://github.com/mrveiss/AutoBot-AI/pull/6348))

- *(planner)* Add tool description compressor with Redis cache (#5065) (#5822) ([#5822](https://github.com/mrveiss/AutoBot-AI/pull/5822))

- *(frontend)* Lazy-load cytoscape in KnowledgeGraph.vue via useCytoscapeLibrary (#5234)

- *(knowledge)* Refactor LineageService.get_ancestors() to O(depth) via per-ID lookup (#4788)

- *(frontend)* Add keep-alive for ChatInterface to reduce remounting (#4356) (#4376) ([#4376](https://github.com/mrveiss/AutoBot-AI/pull/4376))

- *(frontend)* Add keep-alive wrapper for ChatInterface to reduce remounting (#4356)

- *(frontend)* Add keep-alive for ChatInterface to reduce remounting (#4356) (#4369) ([#4369](https://github.com/mrveiss/AutoBot-AI/pull/4369))

- *(frontend)* Implement virtual scrolling for KnowledgeEntries list (#4011)

- *(frontend)* Extract analytics tab SVGs to sprite sheet (#4014)

- *(frontend)* Use blob URLs instead of base64 for thumbnails (#4012)

- *(frontend)* Optimize CodeQualityDashboard computed properties and memoize utilities (#4010)

- *(frontend)* Implement offline caching with service worker (#4015)

- *(frontend)* Apply CSS containment to prevent layout thrashing (#4008)

- *(frontend)* Fix debounce import and usage in KnowledgeGraph (#4009)

- *(frontend)* Lazy-load Cytoscape graph components (#3998) (#4082) ([#4082](https://github.com/mrveiss/AutoBot-AI/pull/4082))

- *(frontend)* Add CSS containment to chart/card/panel components (#4005) (#4078) ([#4078](https://github.com/mrveiss/AutoBot-AI/pull/4078))

- *(analytics)* Memoize expensive computed properties in dashboards (#4036) (#4043) ([#4043](https://github.com/mrveiss/AutoBot-AI/pull/4043))

- *(frontend)* Debounce search/filter handlers to reduce graph re-renders (#4034) (#4046) ([#4046](https://github.com/mrveiss/AutoBot-AI/pull/4046))

- *(frontend)* Add loading='lazy' to deferred images (#4033) (#4045) ([#4045](https://github.com/mrveiss/AutoBot-AI/pull/4045))

- *(deps)* Optimize PROTOCOL_BUFFERS workaround for ChromaDB (#3973) (#3978) ([#3978](https://github.com/mrveiss/AutoBot-AI/pull/3978))

- *(backend)* Convert delete_session os.remove() to async (#3812) ([#3812](https://github.com/mrveiss/AutoBot-AI/pull/3812))

- *(backend)* Convert file I/O to aiofiles in chat_history_manager and simple_pty (#3783) ([#3783](https://github.com/mrveiss/AutoBot-AI/pull/3783))

- *(autoresearch)* Replace HumanReviewScorer polling loop with BLPOP (#3781) ([#3781](https://github.com/mrveiss/AutoBot-AI/pull/3781))

- *(startup)* Parallelize Phase 1 critical services into 4 tiers (#3015) (#3043) ([#3043](https://github.com/mrveiss/AutoBot-AI/pull/3043))

- *(backend)* Convert 10 heavy module-level imports to lazy loading (#3016) (#3045) ([#3045](https://github.com/mrveiss/AutoBot-AI/pull/3045))

- *(backend)* Cache get_local_ips() with 60s TTL (#2791) (#2929) ([#2929](https://github.com/mrveiss/AutoBot-AI/pull/2929))

- *(autoresearch)* Parallelize get_stats() with asyncio.gather (#2718) (#2786) ([#2786](https://github.com/mrveiss/AutoBot-AI/pull/2786))

- *(autoresearch)* Batch Redis calls in get_stats to fix N+1 pattern (#2684) (#2710) ([#2710](https://github.com/mrveiss/AutoBot-AI/pull/2710))


### Refactoring

- *(frontend)* Consolidate ChartCell.vue implementations (#9220) (#9332) ([#9332](https://github.com/mrveiss/AutoBot-AI/pull/9332))

- *(frontend)* Complete useGlobalWebSocket migration to useEventBus (#9062) (#9211) ([#9211](https://github.com/mrveiss/AutoBot-AI/pull/9211))

- *(voice)* Consolidate VALID_BUNDLES and BundleAssignRequest into voice_bundle_constants.py (#9048) (#9186) ([#9186](https://github.com/mrveiss/AutoBot-AI/pull/9186))

- *(backend)* Consolidate STARTUP_ERROR_FILE to autobot_shared (#9066) (#9156) ([#9156](https://github.com/mrveiss/AutoBot-AI/pull/9156))

- *(frontend)* Extract PresetFormBody.vue — eliminates duplication (#MVA-1951) ([#9152](https://github.com/mrveiss/AutoBot-AI/pull/9152))

- *(frontend)* Remove orphaned ChatInterface.ts composable (#9062) ([#9150](https://github.com/mrveiss/AutoBot-AI/pull/9150))

- *(frontend)* Consolidate virtual scroll, WebSocket migration, host composables (#9061 #9062 #9063) (#9121) ([#9121](https://github.com/mrveiss/AutoBot-AI/pull/9121))

- *(enums)* Consolidate TrustLevel to reference a2a vs skills domains (#8957)

- *(enums)* Consolidate AccessLevelFilter to reference AccessLevel values (#8958)

- *(auth)* Move connector auth objects to autobot_shared (GH#8962)

- *(llc)* Remove dead enhanced_background_init and unreachable helpers (MVA-922) (#8500) ([#8500](https://github.com/mrveiss/AutoBot-AI/pull/8500))

- *(llc/8229)* Rename HeartbeatScheduler → RoutineScheduler, move to routine_scheduler.py

- *(async)* Phase 1 — unify task queues onto Celery, delete BackgroundTaskManager (#6505) (#8441) ([#8441](https://github.com/mrveiss/AutoBot-AI/pull/8441))

- *(async)* Phase 1 — unify task queues onto Celery (#6505) (#8426) ([#8426](https://github.com/mrveiss/AutoBot-AI/pull/8426))

- *(backend)* Deduplicate router registrations + document registry (#4203) (#8366) ([#8366](https://github.com/mrveiss/AutoBot-AI/pull/8366))

- *(frontend/icons)* Phase 2 — migrate 199 files FA→Icon.vue, fix AddSourceModal submit button (#8295) ([#8338](https://github.com/mrveiss/AutoBot-AI/pull/8338))

- *(frontend/ws)* Phase 2 — migrate useLiveEvents callers to useEventBus (#8292) ([#8337](https://github.com/mrveiss/AutoBot-AI/pull/8337))

- *(events)* Migrate 22 files from direct EventManager/LiveEventManager to events.bus (#8291) ([#8333](https://github.com/mrveiss/AutoBot-AI/pull/8333))

- *(events/audit/ws)* Minimum-safe consolidation of duplicated systems (#6475, #6486, #6488) (#8294) ([#8294](https://github.com/mrveiss/AutoBot-AI/pull/8294))

- *(resilience,async)* Min-safe consolidation #6494 #6495 (#8298) ([#8298](https://github.com/mrveiss/AutoBot-AI/pull/8298))

- *(async)* Wakeup coalescing + scheduler docs (#6472, #6505, #6507) (#8270) ([#8270](https://github.com/mrveiss/AutoBot-AI/pull/8270))

- *(backend)* Complete optional_import migration for remaining 5 modules (#7895) (#8090) ([#8090](https://github.com/mrveiss/AutoBot-AI/pull/8090))

- *(orchestration)* Unify AgentRegistry, decompose WorkflowExecutor god class (#6828, #6827, #6826) ([#8082](https://github.com/mrveiss/AutoBot-AI/pull/8082))

- *(frontend)* Rename useWorkflowBuilder.WorkflowPlan → OrchestratorWorkflowPlan (closes #7228) (#7998) ([#7998](https://github.com/mrveiss/AutoBot-AI/pull/7998))

- *(system-health)* Retire legacy health vocab — use probe vocab everywhere (#6909) (#7917) ([#7917](https://github.com/mrveiss/AutoBot-AI/pull/7917))

- *(frontend)* Deduplicate *HealthResponse interfaces and probe-status mapping (#6920) (#7916) ([#7916](https://github.com/mrveiss/AutoBot-AI/pull/7916))

- *(voice)* Migrate VoiceConversationOverlay to useVoiceOutput for wsConnected (GH #6825) (#7908) ([#7908](https://github.com/mrveiss/AutoBot-AI/pull/7908))

- *(orchestration)* Decompose ExecutionStrategyHandler into Strategy pattern (GH #6830) (#7903) ([#7903](https://github.com/mrveiss/AutoBot-AI/pull/7903))

- *(backend)* Phase 4 sunset — delete 44 grace-period /health routes (#6902) (#7905) ([#7905](https://github.com/mrveiss/AutoBot-AI/pull/7905))

- *(frontend)* Swap space-x-* with gap-* for flex containers (#6841) (#7900) ([#7900](https://github.com/mrveiss/AutoBot-AI/pull/7900))

- *(backend)* Migrate log_forwarder to optional_import; mark single-symbol sites deferred (#7007) (#7892) ([#7892](https://github.com/mrveiss/AutoBot-AI/pull/7892))

- *(tooling)* DRY closure-gate wiring check into check-new-module-callers.sh (#6930) (#7891) ([#7891](https://github.com/mrveiss/AutoBot-AI/pull/7891))

- *(llm)* Rename llm_interface_pkg to llm_shared post-LLMInterface retirement (#6941)

- *(chat)* Make ChatHistoryManager.add_message keyword-only (#7084)

- *(frontend/knowledge)* Add Storybook stories for 43 components (#6846) (#7862) ([#7862](https://github.com/mrveiss/AutoBot-AI/pull/7862))

- *(frontend/analytics)* Add Storybook stories for 32 components (#6847) (#7861) ([#7861](https://github.com/mrveiss/AutoBot-AI/pull/7861))

- *(frontend/chat)* Add Storybook stories for 28 chat components (#6848) (#7860) ([#7860](https://github.com/mrveiss/AutoBot-AI/pull/7860))

- *(frontend/terminal)* Add Storybook stories for 14 components (#6849) (#7858) ([#7858](https://github.com/mrveiss/AutoBot-AI/pull/7858))

- *(backend)* Migrate hand-rolled singletons to lazy_singleton (#7445) (#7856) ([#7856](https://github.com/mrveiss/AutoBot-AI/pull/7856))

- *(typing)* Adopt PEP 604 X|None codemod; clean Optional imports (#7443) (#7855) ([#7855](https://github.com/mrveiss/AutoBot-AI/pull/7855))

- *(infra)* Add autobot doctor CLI for startup repair (#7371) (#7854) ([#7854](https://github.com/mrveiss/AutoBot-AI/pull/7854))

- *(chat)* Decompose handleStreamingResponse into focused methods (#7693) (#7850) ([#7850](https://github.com/mrveiss/AutoBot-AI/pull/7850))

- *(frontend/workflow)* Add Storybook stories for 11 workflow components (#6851) (#7848) ([#7848](https://github.com/mrveiss/AutoBot-AI/pull/7848))

- *(frontend/charts)* Add Storybook stories for 11 chart components (#6850) (#7847) ([#7847](https://github.com/mrveiss/AutoBot-AI/pull/7847))

- *(frontend/file-browser)* Add Storybook stories for 7 file-browser components (#6852) (#7845) ([#7845](https://github.com/mrveiss/AutoBot-AI/pull/7845))

- *(frontend/settings)* Add Storybook stories for 6 settings components (#6853) (#7843) ([#7843](https://github.com/mrveiss/AutoBot-AI/pull/7843))

- *(frontend/manpage)* Add Storybook stories for 6 manpage components (#6855) (#7842) ([#7842](https://github.com/mrveiss/AutoBot-AI/pull/7842))

- *(frontend/collaboration)* Add Storybook stories for 6 collaboration components (#6854) (#7841) ([#7841](https://github.com/mrveiss/AutoBot-AI/pull/7841))

- *(frontend/autoresearch)* Add Storybook stories for 4 autoresearch components (#6862) (#7840) ([#7840](https://github.com/mrveiss/AutoBot-AI/pull/7840))

- *(frontend/visualizations)* Add Storybook stories for 5 visualization components (#6857) (#7839) ([#7839](https://github.com/mrveiss/AutoBot-AI/pull/7839))

- *(frontend/operations)* Add Storybook stories for 5 operations components (#6856) (#7838) ([#7838](https://github.com/mrveiss/AutoBot-AI/pull/7838))

- *(frontend/desktop)* Add Storybook stories for 4 desktop components (#6860) (#7836) ([#7836](https://github.com/mrveiss/AutoBot-AI/pull/7836))

- *(frontend/feature-flags)* Add Storybook stories for 4 feature-flag components (#6861) (#7834) ([#7834](https://github.com/mrveiss/AutoBot-AI/pull/7834))

- *(frontend/vision)* Add Storybook stories for 4 vision components (#6859) (#7833) ([#7833](https://github.com/mrveiss/AutoBot-AI/pull/7833))

- *(frontend/secrets)* Add Storybook stories for SecretAuditLog, SecretVault, and ShareSecretDialog (#6863) (#7832) ([#7832](https://github.com/mrveiss/AutoBot-AI/pull/7832))

- *(frontend/plugins)* Add Storybook stories for MarketplaceSourcesModal and PluginInstallModal (#6868) (#7831) ([#7831](https://github.com/mrveiss/AutoBot-AI/pull/7831))

- *(frontend/audit)* Add Storybook stories for 4 audit components (#6858) (#7830) ([#7830](https://github.com/mrveiss/AutoBot-AI/pull/7830))

- *(frontend/browser)* Add Storybook stories for BrowserSessionManager and InteractiveScreenshot (#6867) (#7826) ([#7826](https://github.com/mrveiss/AutoBot-AI/pull/7826))

- *(frontend/async)* Add Storybook stories for AsyncComponentWrapper and AsyncErrorFallback (#6866) (#7825) ([#7825](https://github.com/mrveiss/AutoBot-AI/pull/7825))

- *(frontend/agents)* Add Storybook stories for AgentSettingsPanel and HeartbeatPanel (#6865) (#7824) ([#7824](https://github.com/mrveiss/AutoBot-AI/pull/7824))

- *(middleware,skills)* GH#6919 log on legacy health intercept + GH#6877 remove stale generate_structured note (#7805) ([#7805](https://github.com/mrveiss/AutoBot-AI/pull/7805))

- *(frontend)* Phase C batch 6 — icon system + ESLint console guard (GH#6935, GH#6937, GH#7085) (#7794) ([#7794](https://github.com/mrveiss/AutoBot-AI/pull/7794))

- *(llm)* Consolidate UnifiedLLMInterface + MockLLMInterface + AgentProfile overlap (#6942, #6943, #6931) (#7791) ([#7791](https://github.com/mrveiss/AutoBot-AI/pull/7791))

- *(frontend)* Phase C batch 5 — i18n audit + Storybook DRY + size/variant enums (GH#6936, GH#6939, GH#6979) ([#7786](https://github.com/mrveiss/AutoBot-AI/pull/7786))

- *(schemas)* Consolidate duplicate lowercase-id regex + rename FailsafeLLMResponse (GH#6958, GH#6978, GH#6977) ([#7785](https://github.com/mrveiss/AutoBot-AI/pull/7785))

- *(frontend/api)* Consolidate API + error + notification surfaces (GH#7446, GH#7447, GH#7448)

- *(pydantic)* Migrate v1 patterns to v2 across 6 files (#7442) (#7749) ([#7749](https://github.com/mrveiss/AutoBot-AI/pull/7749))

- *(logging)* Migrate 1,141 callsites to canonical logging_manager.get_logger (GH#7438) (#7740) ([#7740](https://github.com/mrveiss/AutoBot-AI/pull/7740))

- *(config)* Migrate all 675 os.getenv/os.environ callsites to ssot_config (#7437) ([#7745](https://github.com/mrveiss/AutoBot-AI/pull/7745))

- *(constants)* Consolidate 12 backend constants files into autobot_shared/ssot_constants.py (GH#7440)

- *(frontend/security)* Add Storybook stories for 3 security components (#6864) (#7738) ([#7738](https://github.com/mrveiss/AutoBot-AI/pull/7738))

- *(frontend)* Complete useApiWithState Group 3 composables migration (#7600) ([#7672](https://github.com/mrveiss/AutoBot-AI/pull/7672))

- *(llm)* Phase 2 — move provider implementations to llm_interface_pkg/providers/ (GH#7637) ([#7674](https://github.com/mrveiss/AutoBot-AI/pull/7674))

- *(auth)* Deduplicate SYSTEM_PERMISSIONS/SYSTEM_ROLES + fix stray jwt import (MVA-125) (#7601) ([#7601](https://github.com/mrveiss/AutoBot-AI/pull/7601))

- *(frontend/api)* Deprecate useApi, migrate to useFetchEndpoint/useApiClient (#6487) (#7599) ([#7599](https://github.com/mrveiss/AutoBot-AI/pull/7599))

- *(security)* Consolidate SSRF guards into autobot_shared.url_safety (#6533) (#7594) ([#7594](https://github.com/mrveiss/AutoBot-AI/pull/7594))

- *(auth)* Move Permission/Role/ROLE_PERMISSIONS to autobot_shared — Phase 1 of #6511 (#7565) ([#7565](https://github.com/mrveiss/AutoBot-AI/pull/7565))

- *(web_fetch)* Extract SSRF guard to autobot_shared.url_safety (closes #7477) (#7490) ([#7490](https://github.com/mrveiss/AutoBot-AI/pull/7490))

- *(media/link)* Extract _parse_jina_output to autobot_shared.jina_parser (closes #7460) (#7487) ([#7487](https://github.com/mrveiss/AutoBot-AI/pull/7487))

- *(web_fetch)* Remove unreachable defensive guard in is_allowed (closes #7461) (#7475) ([#7475](https://github.com/mrveiss/AutoBot-AI/pull/7475))

- *(test/knowledge)* Migrate test_synthesis_provenance.py — partial canonical (#7280 round 10) (#7470) ([#7470](https://github.com/mrveiss/AutoBot-AI/pull/7470))

- *(test/rag)* Migrate rag_service_events_test.py to canonical fixture (#7280 round 8) (#7424) ([#7424](https://github.com/mrveiss/AutoBot-AI/pull/7424))

- *(types)* Document command_execution.RiskLevel divergence + bridge to canonical (closes #7258) (#7417) ([#7417](https://github.com/mrveiss/AutoBot-AI/pull/7417))

- *(types)* Rename causal_inference_engine.Severity → CausalSeverity (closes #7255) (#7416) ([#7416](https://github.com/mrveiss/AutoBot-AI/pull/7416))

- *(types)* Consolidate anti_pattern_detector.Severity onto canonical (closes #7253) (#7414) ([#7414](https://github.com/mrveiss/AutoBot-AI/pull/7414))

- *(test/audit)* Migrate audit_logger_test.py to canonical pipeline fixture (#7280 round 7) (#7412) ([#7412](https://github.com/mrveiss/AutoBot-AI/pull/7412))

- *(test/audit)* Migrate audit_log_test.py to canonical pipeline fixture (#7280 round 6) (#7408) ([#7408](https://github.com/mrveiss/AutoBot-AI/pull/7408))

- *(test/retrieval_learner)* Migrate to canonical async-redis fixture (#7280 round 5) (#7388) ([#7388](https://github.com/mrveiss/AutoBot-AI/pull/7388))

- *(test/mesh)* Migrate edge_learner_test.py to canonical fixture (#7280 round 4) (#7383) ([#7383](https://github.com/mrveiss/AutoBot-AI/pull/7383))

- *(test/knowledge)* Migrate knowledge_base_async_test.py to canonical fixture (#7280 round 3) (#7381) ([#7381](https://github.com/mrveiss/AutoBot-AI/pull/7381))

- *(tests)* Migrate workflow_versioning_test.py to canonical async-redis fixture (#7280 round 1) (#7340) ([#7340](https://github.com/mrveiss/AutoBot-AI/pull/7340))

- *(security)* Consolidate per-IP rate limit into autobot_shared.rate_limit (#7271 + #7270) (#7327) ([#7327](https://github.com/mrveiss/AutoBot-AI/pull/7327))

- *(ansible)* Extract reusable stat_tls_certs.yml helper (#7272) (#7278) ([#7278](https://github.com/mrveiss/AutoBot-AI/pull/7278))

- *(frontend/composables)* Extract useProbeBackedHealth + ProbeResponse (#7247, #7248) (#7277) ([#7277](https://github.com/mrveiss/AutoBot-AI/pull/7277))

- *(types)* Consolidate Workflow/Job *Status enums onto canonical TaskStatus + add lint rule (closes #6973) (#7266) ([#7266](https://github.com/mrveiss/AutoBot-AI/pull/7266))

- *(types)* Consolidate 11 Severity/Risk/Level duplicates onto canonical (closes #6689) (#7261) ([#7261](https://github.com/mrveiss/AutoBot-AI/pull/7261))

- *(status)* Consolidate 5 TaskStatus duplicates into canonical (closes #6520) (#7241) ([#7241](https://github.com/mrveiss/AutoBot-AI/pull/7241))

- *(ansible)* Shared idempotent apt-repository helper across 7 roles (closes #7218) (#7239) ([#7239](https://github.com/mrveiss/AutoBot-AI/pull/7239))

- *(frontend)* Rename useWorkflowBuilder.WorkflowPlan → OrchestratorWorkflowPlan (closes #7228) (#7236) ([#7236](https://github.com/mrveiss/AutoBot-AI/pull/7236))

- *(hooks)* Migrate 5 file-scanning hooks to lib/_common.sh (#7203 partial) (#7214) ([#7214](https://github.com/mrveiss/AutoBot-AI/pull/7214))

- *(infra/shared)* Re-export mocks from canonical autobot-backend SSOT (#7125) (#7191) ([#7191](https://github.com/mrveiss/AutoBot-AI/pull/7191))

- *(intelligence)* Move demos to runner scripts so they actually run (#7127) (#7183) ([#7183](https://github.com/mrveiss/AutoBot-AI/pull/7183))

- *(tests)* Extract canonical make_llm_response fixture (#7134) (#7139) ([#7139](https://github.com/mrveiss/AutoBot-AI/pull/7139))

- *(ansible)* Consolidate 6 role clean.yml into shared parameterized tasks (closes #7058) (#7136) ([#7136](https://github.com/mrveiss/AutoBot-AI/pull/7136))

- *(packaging)* Drop autobot_shared/requirements.txt — pyproject.toml is now canonical (closes #7040) (#7113) ([#7113](https://github.com/mrveiss/AutoBot-AI/pull/7113))

- *(ansible/provision)* Mirror cleanup-side shared facts in provision gates (#7051) (#7064) ([#7064](https://github.com/mrveiss/AutoBot-AI/pull/7064))

- *(ansible)* Shared role-active facts replace per-role cleanup gates (#7031) (#7050) ([#7050](https://github.com/mrveiss/AutoBot-AI/pull/7050))

- *(packaging)* Autobot_shared setup.py → pyproject.toml (closes #7016) (#7022) ([#7022](https://github.com/mrveiss/AutoBot-AI/pull/7022))

- *(observability)* Probe_long_running uses public accessor (#6921) (#7004) ([#7004](https://github.com/mrveiss/AutoBot-AI/pull/7004))

- *(frontend)* DesignTokens story imports from canonical tokens.ts (#6938) (#7000) ([#7000](https://github.com/mrveiss/AutoBot-AI/pull/7000))

- *(schemas)* Retire duplicate ModelPricingInfo (#6668) (#6967) ([#6967](https://github.com/mrveiss/AutoBot-AI/pull/6967))

- *(llm)* Retire LLMInterface god-class — full migration to LLMService (#3185) (#6881) ([#6881](https://github.com/mrveiss/AutoBot-AI/pull/6881))

- *(orchestration)* Rename enhanced WorkflowPlanner → StrategyPlanner (#6817) (#6923) ([#6923](https://github.com/mrveiss/AutoBot-AI/pull/6923))

- *(agents)* Rename AgentCapability dataclass → AgentCapabilityDescriptor (#6818) (#6924) ([#6924](https://github.com/mrveiss/AutoBot-AI/pull/6924))

- *(orchestration)* Move subagent_dispatcher to enhanced_orchestration (#6822) (#6925) ([#6925](https://github.com/mrveiss/AutoBot-AI/pull/6925))

- *(system-health)* Composable probe helpers + migrate 14 probes to one-liners (#6904) (#6911) ([#6911](https://github.com/mrveiss/AutoBot-AI/pull/6911))

- *(backend)* Consolidate 45 /health endpoints behind register_health_probe registry (#3333) (#6870) ([#6870](https://github.com/mrveiss/AutoBot-AI/pull/6870))

- *(media)* Consolidate 5 Pipeline __init__ blocks via class-level constants (#6779) (#6835) ([#6835](https://github.com/mrveiss/AutoBot-AI/pull/6835))

- *(voice)* Unify duplicate /api/voice/stream WS — single owner (#6788) (#6810) ([#6810](https://github.com/mrveiss/AutoBot-AI/pull/6810))

- *(chat)* Delete duplicate useAppStore.sessions store (#6813) (#6815) ([#6815](https://github.com/mrveiss/AutoBot-AI/pull/6815))

- *(schemas)* Alias GitHubProviderInfo to VCSProviderInfo — identical shape (#6792) (#6804) ([#6804](https://github.com/mrveiss/AutoBot-AI/pull/6804))

- *(schemas)* Remove duplicate IDE schemas from ide_integration.py (#6042) (#6612) ([#6612](https://github.com/mrveiss/AutoBot-AI/pull/6612))

- *(schemas)* Migrate Phase 39 endpoint schemas — http_client_mcp (#6042) (#6610) ([#6610](https://github.com/mrveiss/AutoBot-AI/pull/6610))

- *(schemas)* Migrate Phase 38 endpoint schemas — analytics_bug_prediction (#6042) (#6608) ([#6608](https://github.com/mrveiss/AutoBot-AI/pull/6608))

- *(schemas)* Migrate Phase 37 endpoint schemas — 5 files, 10 classes (#6042) (#6607) ([#6607](https://github.com/mrveiss/AutoBot-AI/pull/6607))

- *(schemas)* Migrate Phase 36 endpoint schemas — 6 files, 12 classes (#6042) (#6603) ([#6603](https://github.com/mrveiss/AutoBot-AI/pull/6603))

- *(schemas)* Migrate Phase 35 endpoint schemas — 7 files, 8 classes (#6042) (#6601) ([#6601](https://github.com/mrveiss/AutoBot-AI/pull/6601))

- *(schemas)* Migrate Phase 34 endpoint schemas — 8 files, 8 classes (#6042) (#6598) ([#6598](https://github.com/mrveiss/AutoBot-AI/pull/6598))

- *(schemas)* Migrate Phase 33 endpoint schemas — 6 files, 12 classes (#6042) (#6582) ([#6582](https://github.com/mrveiss/AutoBot-AI/pull/6582))

- *(schemas)* Migrate Phase 32 endpoint schemas — ide_integration.py 15 classes + 4 enums (#6042) (#6581) ([#6581](https://github.com/mrveiss/AutoBot-AI/pull/6581))

- *(schemas)* Migrate Phase 31 endpoint schemas — batch_jobs.py 10 classes + 2 enums (#6042) (#6574) ([#6574](https://github.com/mrveiss/AutoBot-AI/pull/6574))

- *(schemas)* Migrate Phase 30 endpoint schemas — 2 files, 13 classes + 5 enums (#6042) (#6573) ([#6573](https://github.com/mrveiss/AutoBot-AI/pull/6573))

- *(async)* Delete dead services/scheduling/ package (#6507) (#6564) ([#6564](https://github.com/mrveiss/AutoBot-AI/pull/6564))

- *(schemas)* Migrate Phase 29 endpoint schemas — 2 files, 9 classes (#6042) (#6567) ([#6567](https://github.com/mrveiss/AutoBot-AI/pull/6567))

- *(schemas)* Migrate Phase 28 endpoint schemas — 2 files, 8 classes + 2 enums (#6042) (#6561) ([#6561](https://github.com/mrveiss/AutoBot-AI/pull/6561))

- *(schemas)* Migrate Phase 27 endpoint schemas — 2 files, 10 classes + 4 enums (#6042) (#6557) ([#6557](https://github.com/mrveiss/AutoBot-AI/pull/6557))

- *(schemas)* Migrate Phase 26 endpoint schemas — 2 files, 6 classes + 7 enums (#6042) (#6554) ([#6554](https://github.com/mrveiss/AutoBot-AI/pull/6554))

- *(schemas)* Migrate Phase 25 endpoint schemas — 2 files, 6 classes + 4 enums (#6042) (#6553) ([#6553](https://github.com/mrveiss/AutoBot-AI/pull/6553))

- *(schemas)* Migrate Phase 24 endpoint schemas — 2 files, 7 classes (#6042) (#6552) ([#6552](https://github.com/mrveiss/AutoBot-AI/pull/6552))

- *(schemas)* Migrate Phase 23 endpoint schemas — 5 files, 15 classes (#6042) (#6548) ([#6548](https://github.com/mrveiss/AutoBot-AI/pull/6548))

- *(plugins)* Replace _VALID_* sets with Enums; promote BUILTIN_SOURCE_ID; close #6526 (#6534) (#6547) ([#6547](https://github.com/mrveiss/AutoBot-AI/pull/6547))

- *(schemas)* Migrate Phase 22 endpoint schemas — 6 files, 18 classes (#6042) (#6545) ([#6545](https://github.com/mrveiss/AutoBot-AI/pull/6545))

- *(async)* Unify progress tracking via task_execution_tracker (#6506) (#6531) ([#6531](https://github.com/mrveiss/AutoBot-AI/pull/6531))

- *(browser)* Extract region-marking state into useRegionMarking composable (#6447) (#6543) ([#6543](https://github.com/mrveiss/AutoBot-AI/pull/6543))

- *(schemas)* Migrate Phase 21 endpoint schemas — 8 files, 24 classes (#6042) (#6544) ([#6544](https://github.com/mrveiss/AutoBot-AI/pull/6544))

- *(chat)* Type process_chat_message and _execute_enhanced_chat_pipeline returns (#6502) (#6519) ([#6519](https://github.com/mrveiss/AutoBot-AI/pull/6519))

- *(schemas)* Migrate Phase 20 endpoint schemas — 8 files, 24 classes (#6042) (#6535) ([#6535](https://github.com/mrveiss/AutoBot-AI/pull/6535))

- *(app)* Replace isLoginPage path-check with route meta.isPublic (#6508) (#6517) ([#6517](https://github.com/mrveiss/AutoBot-AI/pull/6517))

- *(schemas)* Migrate Phase 19 endpoint schemas — 4 files, 16 classes (#6042) (#6522) ([#6522](https://github.com/mrveiss/AutoBot-AI/pull/6522))

- *(schemas)* Migrate Phase 18 endpoint schemas — 4 files, 16 classes (#6042) (#6516) ([#6516](https://github.com/mrveiss/AutoBot-AI/pull/6516))

- *(schemas)* Migrate Phase 17 endpoint schemas — 5 files, 20 classes (#6042) (#6513) ([#6513](https://github.com/mrveiss/AutoBot-AI/pull/6513))

- *(schemas)* Migrate Phase 16 endpoint schemas — 6 files, 24 classes + 1 enum (#6042) (#6503) ([#6503](https://github.com/mrveiss/AutoBot-AI/pull/6503))

- *(schemas)* Migrate Phase 15 endpoint schemas — 5 files, 22 classes (#6042) (#6491) ([#6491](https://github.com/mrveiss/AutoBot-AI/pull/6491))

- *(schemas)* Migrate Phase 14 endpoint schemas — 3 files, 15 classes (#6042) (#6484) ([#6484](https://github.com/mrveiss/AutoBot-AI/pull/6484))

- *(schemas)* Phase 13 — migrate 20 classes (knowledge, multimodal, NL search, prometheus MCP) (#6042) (#6483) ([#6483](https://github.com/mrveiss/AutoBot-AI/pull/6483))

- *(schemas)* Migrate Phase 12 endpoint schemas — 3 analytics files, 18 classes + 11 enums (#6042) (#6467) ([#6467](https://github.com/mrveiss/AutoBot-AI/pull/6467))

- *(schemas)* Migrate Phase 11 endpoint schemas — 2 files, 10 classes (#6042) (#6463) ([#6463](https://github.com/mrveiss/AutoBot-AI/pull/6463))

- *(schemas)* Migrate Phase 10 endpoint schemas — 6 files, 41 classes (#6042) (#6458) ([#6458](https://github.com/mrveiss/AutoBot-AI/pull/6458))

- *(app)* Replace isChatPage path-check with route meta hideFooter (#6417 #6418) (#6461) ([#6461](https://github.com/mrveiss/AutoBot-AI/pull/6461))

- *(nav)* Move /operations under /analytics/operations sub-route (#6347)

- *(execution_strategies)* Extract _is_required_failure helper, fix gather exception handling, fix _wait_for_dependencies terminal status, add group_stages_fn to _make_handler (#6448 #6449 #6454 #6455) (#6456) ([#6456](https://github.com/mrveiss/AutoBot-AI/pull/6456))

- *(schemas)* Migrate Phase 9 endpoint schemas — 6 files, 52 classes (#6042) (#6437) ([#6437](https://github.com/mrveiss/AutoBot-AI/pull/6437))

- *(schemas)* Migrate local BaseModel subclasses to domain schema files phases 1–8 (#6042) ([#6370](https://github.com/mrveiss/AutoBot-AI/pull/6370))

- *(schemas_agent)* Move execution_time to AgentTaskData base class (#6406) (#6409) ([#6409](https://github.com/mrveiss/AutoBot-AI/pull/6409))

- *(orchestration)* 5 targeted fixes from discovery audit (#6399 #6400 #6401 #6402 #6403) (#6404) ([#6404](https://github.com/mrveiss/AutoBot-AI/pull/6404))

- *(schemas_agent)* MultiAgentCoordinationData inherits AgentTaskData (#6389) (#6398) ([#6398](https://github.com/mrveiss/AutoBot-AI/pull/6398))

- *(chat_utils)* Rename create_success_response → create_chat_response (#6388) (#6397) ([#6397](https://github.com/mrveiss/AutoBot-AI/pull/6397))

- *(workflow_runner)* Extract CollaborationCoordinator and AgentRouter (#6393 #6392) ([#6396](https://github.com/mrveiss/AutoBot-AI/pull/6396))

- *(utils)* Create_success_response() returns DataResponse[T] generic (#6371) (#6380) ([#6380](https://github.com/mrveiss/AutoBot-AI/pull/6380))

- *(api)* Add schemas_ai_stack.py — type 14 opaque AI Stack endpoint data payloads (#6372) (#6379) ([#6379](https://github.com/mrveiss/AutoBot-AI/pull/6379))

- *(schemas)* Extract AgentTaskData base — reduce duplication in 3-4 agent execution models (#6373) (#6378) ([#6378](https://github.com/mrveiss/AutoBot-AI/pull/6378))

- *(orchestrator)* Decompose god class into collaborators (#5058) ([#6375](https://github.com/mrveiss/AutoBot-AI/pull/6375))

- *(api)* DataResponse[T] generic — type 23 agent/ai_stack endpoints (#5772) (#6369) ([#6369](https://github.com/mrveiss/AutoBot-AI/pull/6369))

- *(api/knowledge_boards)* Migrate _get_redis(req) to kb.redis() (#6360) (#6368) ([#6368](https://github.com/mrveiss/AutoBot-AI/pull/6368))

- *(nav)* Move operations after secrets so it falls into overflow menu (#6347)

- *(plugins)* Convert marketplace to /plugins/marketplace child route (#6347)

- *(shared)* Extract fire-and-forget Redis write helper to autobot_shared; wire into mcp_trace (#6335) (#6350) ([#6350](https://github.com/mrveiss/AutoBot-AI/pull/6350))

- *(nav)* Reorder nav, merge usage into analytics, marketplace into plugins (#6347)

- *(services/ai_stack_client)* Extract _handle_transient_error to remove duplicate retry logic (#6307) (#6344) ([#6344](https://github.com/mrveiss/AutoBot-AI/pull/6344))

- *(api)* Consolidate 5 rate limiters into shared autobot_shared/rate_limiter.py (#4460) (#6309) ([#6309](https://github.com/mrveiss/AutoBot-AI/pull/6309))

- *(composables)* Migrate 11 composables from manual isLoading to useLoadingState (#5869) ([#5878](https://github.com/mrveiss/AutoBot-AI/pull/5878))

- *(composables)* Migrate remaining manual isLoading patterns to useLoadingState (#5869) (#5875) ([#5875](https://github.com/mrveiss/AutoBot-AI/pull/5875))

- *(composables)* Migrate useTLSCredentials to useLoadingState (#5869) (#5874) ([#5874](https://github.com/mrveiss/AutoBot-AI/pull/5874))

- *(composables)* Extract useLoadingState from useBrowserAutomation (#5861) (#5867) ([#5867](https://github.com/mrveiss/AutoBot-AI/pull/5867))

- *(api)* Replace response_model=None with typed schemas in chat_sessions, chat, chat_knowledge, chat_compare (#5773) (#5838) ([#5838](https://github.com/mrveiss/AutoBot-AI/pull/5838))

- *(composables)* Implement useFetchEndpoint on top of useApiResource for unified race handling (#5180) (#5817) ([#5817](https://github.com/mrveiss/AutoBot-AI/pull/5817))

- *(composables)* Implement useFetchEndpoint on top of useApiResource for unified race handling (#5180) (#5808) ([#5808](https://github.com/mrveiss/AutoBot-AI/pull/5808))

- *(knowledge)* Type gpu_vector_search.py client params as BaseClient (#5732) (#5797) ([#5797](https://github.com/mrveiss/AutoBot-AI/pull/5797))

- *(knowledge)* Migrate autonomous_loop.py from chromadb.EphemeralClient to knowledge backends AsyncInMemoryClient (#5732) (#5788) ([#5788](https://github.com/mrveiss/AutoBot-AI/pull/5788))

- *(redis)* Upgrade UserBehaviorAnalytics to AsyncRedisClientLockedMixin (#5770) (#5776) ([#5776](https://github.com/mrveiss/AutoBot-AI/pull/5776))

- *(composables)* Deprecate useAnalyticsFetch as thin alias of useAnalyticsEndpoint (#5172) (#5771) ([#5771](https://github.com/mrveiss/AutoBot-AI/pull/5771))

- *(analytics)* Move budget alert Redis ops into LLMCostTracker methods (#5731) (#5761) ([#5761](https://github.com/mrveiss/AutoBot-AI/pull/5761))

- *(redis)* Migrate user_behavior_analytics to AsyncRedisClientMixin (#5730) (#5760) ([#5760](https://github.com/mrveiss/AutoBot-AI/pull/5760))

- *(llm_cache)* Remove dead get_llm_cache_async export (#5740) (#5745) ([#5745](https://github.com/mrveiss/AutoBot-AI/pull/5745))

- *(redis)* Add AsyncRedisClientMixin and migrate 9 services to eliminate lazy-init boilerplate (#5671) (#5705) ([#5705](https://github.com/mrveiss/AutoBot-AI/pull/5705))

- *(vision)* Pass refreshInterval ref directly to usePollingJob, drop watch+restart (#5644) (#5653) ([#5653](https://github.com/mrveiss/AutoBot-AI/pull/5653))

- *(vision)* Pass refreshInterval ref directly to usePollingJob, drop watch+restart (#5644) (#5650) ([#5650](https://github.com/mrveiss/AutoBot-AI/pull/5650))

- *(utils)* Add lazy_optional_singleton + complete task_queue and secure_sandbox migrations (#5576) (#5634) ([#5634](https://github.com/mrveiss/AutoBot-AI/pull/5634))

- *(singleton)* Extract _SkillsEngineManager class for lifecycle-aware engine management (#5629) (#5637) ([#5637](https://github.com/mrveiss/AutoBot-AI/pull/5637))

- *(singleton)* Extract _OllamaPoolManager class for lifecycle-aware pool management (#5628) (#5636) ([#5636](https://github.com/mrveiss/AutoBot-AI/pull/5636))

- *(utils)* Migrate 12 module-level threading.Lock() singleton patterns to lazy_singleton phase 3 (#5619) (#5625) ([#5625](https://github.com/mrveiss/AutoBot-AI/pull/5625))

- *(utils)* Migrate 40 module-level threading.Lock() singleton patterns to lazy_singleton phase 2 (#5579) (#5618) ([#5618](https://github.com/mrveiss/AutoBot-AI/pull/5618))

- *(ui)* Replace Font Awesome icon in EmptyState with Icon component (#5606) (#5615) ([#5615](https://github.com/mrveiss/AutoBot-AI/pull/5615))

- *(composables)* Migrate 10 composables from raw setInterval to usePollingJob (#5604) (#5612) ([#5612](https://github.com/mrveiss/AutoBot-AI/pull/5612))

- *(utils)* Migrate task_queue get_task_queue() to lazy_singleton — missed in #5529 (#5578) (#5583) ([#5583](https://github.com/mrveiss/AutoBot-AI/pull/5583))

- *(knowledge)* Replace Dict[str, Any] with CategoryMeta TypedDict (#5591) (#5596) ([#5596](https://github.com/mrveiss/AutoBot-AI/pull/5596))

- *(knowledge)* Migrate remaining production callers onto BaseCollection/BaseClient ABCs (#5194) (#5600) ([#5600](https://github.com/mrveiss/AutoBot-AI/pull/5600))

- *(knowledge)* Split facts.py into ingestion/entries/query schema modules (#5486) (#5597) ([#5597](https://github.com/mrveiss/AutoBot-AI/pull/5597))

- *(frontend)* Replace 7 raw setInterval loops with usePollingJob (#5561) (#5582) ([#5582](https://github.com/mrveiss/AutoBot-AI/pull/5582))

- *(slm-backend)* Extract _extract_failure_summary to ansible_utils (#5564) (#5581) ([#5581](https://github.com/mrveiss/AutoBot-AI/pull/5581))

- *(events)* Replace string literals with event_type constants (#5131) (#5580) ([#5580](https://github.com/mrveiss/AutoBot-AI/pull/5580))

- *(tests)* Consolidate _FakeConnector into tests/helpers/fake_connector.py (#5558) (#5573) ([#5573](https://github.com/mrveiss/AutoBot-AI/pull/5573))

- *(tests)* Consolidate _FakeKB into tests/helpers/fake_kb.py (#5557) (#5572) ([#5572](https://github.com/mrveiss/AutoBot-AI/pull/5572))

- *(utils)* Migrate 13 threading.Lock() singletons to lazy_singleton (#5529) (#5571) ([#5571](https://github.com/mrveiss/AutoBot-AI/pull/5571))

- *(composables)* SourceManager + CodebaseAnalyticsLanding → usePollingJob (#5508) (#5565) ([#5565](https://github.com/mrveiss/AutoBot-AI/pull/5565))

- *(frontend)* Migrate 5 single-key expand toggles to useExpansion (#5521) (#5556) ([#5556](https://github.com/mrveiss/AutoBot-AI/pull/5556))

- *(frontend)* Migrate 6 setInterval polling loops to usePollingJob (#5535) (#5554) ([#5554](https://github.com/mrveiss/AutoBot-AI/pull/5554))

- *(composables)* SourceManager + CodebaseAnalyticsLanding → usePollingJob (#5508) (#5553) ([#5553](https://github.com/mrveiss/AutoBot-AI/pull/5553))

- *(frontend)* Migrate 2 boolean-map expansions to useExpansion (#5522) (#5552) ([#5552](https://github.com/mrveiss/AutoBot-AI/pull/5552))

- *(frontend)* Migrate 5 single-key expand toggles to useExpansion (#5521) (#5551) ([#5551](https://github.com/mrveiss/AutoBot-AI/pull/5551))

- *(utils)* Add arg-guard to lazy_singleton — raise on mismatched non-first-call args (#5445) (#5548) ([#5548](https://github.com/mrveiss/AutoBot-AI/pull/5548))

- *(schemas)* Fix extra=allow on request models; complete inline request model migration (#5536, #5537) (#5547) ([#5547](https://github.com/mrveiss/AutoBot-AI/pull/5547))

- *(npu-worker)* Extract aiohttp_with_backoff primitive, migrate config_bootstrap + backend_telemetry (#5430) (#5542) ([#5542](https://github.com/mrveiss/AutoBot-AI/pull/5542))

- *(backend)* Datetime.now(timezone.utc) → now_utc() consistency pass (#5514) (#5533) ([#5533](https://github.com/mrveiss/AutoBot-AI/pull/5533))

- *(schemas)* Migrate BatchVectorizeRequest and ReindexWithContextRequest from inline to knowledge/schemas/ (#5528) (#5530) ([#5530](https://github.com/mrveiss/AutoBot-AI/pull/5530))

- *(services)* Collapse claude_agent_service into re-export shim — specialized_agent_service canonical (#5429) (#5527) ([#5527](https://github.com/mrveiss/AutoBot-AI/pull/5527))

- *(tests)* Consolidate FakeRedis implementations into tests/helpers/fake_redis.py (#5431) (#5526) ([#5526](https://github.com/mrveiss/AutoBot-AI/pull/5526))

- *(utils)* Extract lazy_singleton primitive, migrate 3 chunker factories (#5423) (#5525) ([#5525](https://github.com/mrveiss/AutoBot-AI/pull/5525))

- *(composables)* PatternAnalysis 4-key accordion → useExpansion<Section> (#5505) (#5520) ([#5520](https://github.com/mrveiss/AutoBot-AI/pull/5520))

- *(composables)* 4 single-key expand toggles → useExpansion<Key> (#5506) (#5519) ([#5519](https://github.com/mrveiss/AutoBot-AI/pull/5519))

- *(composables)* KnowledgePersistenceDialog boolean-map → useBatchSelection (#5507) (#5518) ([#5518](https://github.com/mrveiss/AutoBot-AI/pull/5518))

- *(composables)* DocumentOverview.vue reactive(Set) → useExpansion (#5504) (#5517) ([#5517](https://github.com/mrveiss/AutoBot-AI/pull/5517))

- *(npu-worker)* Collapse 5 config getters in config_bootstrap.py (#5436) (#5485) ([#5485](https://github.com/mrveiss/AutoBot-AI/pull/5485))

- *(api)* Remove redundant .replace("Z", "+00:00") inside parse_utc_iso (#5473) (#5474) ([#5474](https://github.com/mrveiss/AutoBot-AI/pull/5474))

- *(infra)* Tighten except Exception to specific types in verify_knowledge_consistency (#5441) (#5461) ([#5461](https://github.com/mrveiss/AutoBot-AI/pull/5461))

- *(lint+api)* Shared lint scan helper + analytics.py parse_utc_iso adoption (#5448, #5449) (#5453) ([#5453](https://github.com/mrveiss/AutoBot-AI/pull/5453))

- *(analytics)* Migrate exportReport through parseResponse hook (#5388) (#5402) ([#5402](https://github.com/mrveiss/AutoBot-AI/pull/5402))

- *(utils)* Extract SemanticChunkerBase + collapse shared pipeline (#5363) (#5392) ([#5392](https://github.com/mrveiss/AutoBot-AI/pull/5392))

- *(analytics)* DRY sources endpoint + parseResponse hook + audit doc (#5276) (#5386) ([#5386](https://github.com/mrveiss/AutoBot-AI/pull/5386))

- *(codebase-analytics)* Env-analysis normalizer parity (#5367) (#5375) ([#5375](https://github.com/mrveiss/AutoBot-AI/pull/5375))

- *(knowledge_collaboration)* Rename aioredis_client parameter to redis (#5337) (#5354) ([#5354](https://github.com/mrveiss/AutoBot-AI/pull/5354))

- *(codebase-analytics)* Rename _DEFAULT_HARDCODE_SEVERITY → public (#5348) (#5355) ([#5355](https://github.com/mrveiss/AutoBot-AI/pull/5355))

- *(backend)* Migrate Pattern A timing + cutoff sites in 10 files (#5211 phase B3.2) (#5342) ([#5342](https://github.com/mrveiss/AutoBot-AI/pull/5342))

- *(analytics)* Remove orphaned refactoringSuggestions ref (#5340) (#5341) ([#5341](https://github.com/mrveiss/AutoBot-AI/pull/5341))

- *(base-table)* Collapse toggleRowSelection to toggleByKey (#5333) (#5335) ([#5335](https://github.com/mrveiss/AutoBot-AI/pull/5335))

- *(knowledge)* Rename aioredis_client -> _aioredis_client + lint guard (Closes #5225) (#5330) ([#5330](https://github.com/mrveiss/AutoBot-AI/pull/5330))

- *(base-table)* Adopt useBatchSelection for row selection (closes #5283) (#5325) ([#5325](https://github.com/mrveiss/AutoBot-AI/pull/5325))

- *(composables)* Delegate toggle/select to *ByKey primitives (#5331) (#5332) ([#5332](https://github.com/mrveiss/AutoBot-AI/pull/5332))

- *(analytics)* Consolidate 4 duplicate HardcodedValue type defs (#5311) (#5324) ([#5324](https://github.com/mrveiss/AutoBot-AI/pull/5324))

- *(analytics)* Migrate 6 expansion sites from Record/Array to useExpansion (#5323) (#5327) ([#5327](https://github.com/mrveiss/AutoBot-AI/pull/5327))

- *(composables)* Migrate useConversationFiles selection to useBatchSelection (#5322) (#5326) ([#5326](https://github.com/mrveiss/AutoBot-AI/pull/5326))

- *(integrations)* Migrate Pattern A timing to time.monotonic (#5211 phase B3) (#5321) ([#5321](https://github.com/mrveiss/AutoBot-AI/pull/5321))

- *(knowledge)* Migrate 2 production callers onto BaseCollection ABC (#5194) (#5310) ([#5310](https://github.com/mrveiss/AutoBot-AI/pull/5310))

- *(frontend)* Migrate callers off useKnowledgeBase BC shim (#5193) (#5309) ([#5309](https://github.com/mrveiss/AutoBot-AI/pull/5309))

- *(codebase-analytics)* Import _DEFAULT_HARDCODE_SEVERITY from analyzers (#5312) (#5314) ([#5314](https://github.com/mrveiss/AutoBot-AI/pull/5314))

- *(components)* Adopt useBatchSelection in 4 non-knowledge components (#5283) (#5288) ([#5288](https://github.com/mrveiss/AutoBot-AI/pull/5288))

- *(frontend)* Complete reactive refs migration for useKnowledgeFacts/Files/Jobs (#5195) (#5286) ([#5286](https://github.com/mrveiss/AutoBot-AI/pull/5286))

- *(knowledge)* Migrate batch-select state to useBatchSelection composable (#5247) (#5278) ([#5278](https://github.com/mrveiss/AutoBot-AI/pull/5278))

- *(knowledge)* Migrate KB mixin self.aioredis_client callers to self.redis() (Part of #5225, Phase 3) (#5272) ([#5272](https://github.com/mrveiss/AutoBot-AI/pull/5272))

- *(analytics)* Migrate useIndexingJob + useDashboardLoaders fetches (#5257)

- *(typescript)* Delete parseApiResponse entirely (#5033) (#5246) ([#5246](https://github.com/mrveiss/AutoBot-AI/pull/5246))

- *(knowledge)* Batch embeddings + collapse duplicate NPU-first branch (#5231) (#5262) ([#5262](https://github.com/mrveiss/AutoBot-AI/pull/5262))

- *(knowledge)* Migrate remaining kb.aioredis_client direct access to KB.redis() (#5230) (#5261) ([#5261](https://github.com/mrveiss/AutoBot-AI/pull/5261))

- *(analytics)* Migrate useCrossLanguageAnalysis to useFetchEndpoint (#5253)

- *(api)* Migrate 21 cross-module kb.aioredis_client sites to kb.redis() (#5225 phase 1) (#5252) ([#5252](https://github.com/mrveiss/AutoBot-AI/pull/5252))

- *(analytics)* Migrate CodebaseAnalyticsLanding + useSourceRegistry fetches (#5153 scope B)

- *(composables)* Extend useFetchEndpoint with onResponse + reset; migrate last 2 hand-rolled fetchers (#5235)

- *(backend)* Migrate Phase 3 datetime.utcnow() producers to utc_timestamp() (#5178 part B phase 3) (#5236) ([#5236](https://github.com/mrveiss/AutoBot-AI/pull/5236))

- *(backend)* Migrate Phase 2 datetime.utcnow() producers to utc_timestamp() (#5178 part B phase 2) (#5233) ([#5233](https://github.com/mrveiss/AutoBot-AI/pull/5233))

- *(composables)* Migrate remaining 3 useAnalyticsFetch consumers and delete the helper (#5208)

- *(composables)* POC migrate useConfigDuplicates from useAnalyticsFetch -> useFetchEndpoint (#5208)

- *(charts)* Extract useCytoscapeLibrary composable (#5206)

- *(knowledge)* Migrate /api/embeddings direct callers to services.npu_client canonical (#5182) (#5219) ([#5219](https://github.com/mrveiss/AutoBot-AI/pull/5219))

- *(knowledge)* Add KB.redis() public accessor; migrate 4 production call sites (#5184) (#5218) ([#5218](https://github.com/mrveiss/AutoBot-AI/pull/5218))

- *(llm)* Migrate agent_loop/think_tool to call_ollama_generate (#5181) (#5216) ([#5216](https://github.com/mrveiss/AutoBot-AI/pull/5216))

- *(backend)* Migrate Phase 1 datetime.utcnow() producers to utc_timestamp() (#5178 part B phase 1) (#5213) ([#5213](https://github.com/mrveiss/AutoBot-AI/pull/5213))

- *(composables)* Complete the rehome — delete alias, migrate call-sites, add DELETE support (#5174) (#5187) ([#5187](https://github.com/mrveiss/AutoBot-AI/pull/5187))

- *(frontend)* Remove parseApiResponse wrapper in 17 knowledge Vue components (#5033) (#5177) ([#5177](https://github.com/mrveiss/AutoBot-AI/pull/5177))

- *(redis)* Route backend accessors through autobot_shared canonical (#5101) (#5171) ([#5171](https://github.com/mrveiss/AutoBot-AI/pull/5171))

- *(frontend)* Make knowledge composables return reactive refs + managed fetch state (#5149) (#5167) ([#5167](https://github.com/mrveiss/AutoBot-AI/pull/5167))

- *(llm)* Migrate rlm/benchmark.py _generate to call_ollama_generate (#5155) (#5166) ([#5166](https://github.com/mrveiss/AutoBot-AI/pull/5166))

- *(composables)* Rehome useAnalyticsEndpoint -> useFetchEndpoint with flipped defaults (#5153 C)

- *(analytics)* Extend useAnalyticsEndpoint with POST+body, migrate useCodeSmellAnalysis (#5153)

- *(analytics)* Extract runTimed helper (#5153 D-2)

- *(frontend)* Audit + POC migration of fetcher boilerplate to useAnalyticsEndpoint (#5154) (#5164) ([#5164](https://github.com/mrveiss/AutoBot-AI/pull/5164))

- *(shared)* Add utc_timestamp_z() and migrate workflow_versioning._utc_now (#5152) (#5163) ([#5163](https://github.com/mrveiss/AutoBot-AI/pull/5163))

- *(frontend)* Rationalize loading composables (#5108) (#5156) ([#5156](https://github.com/mrveiss/AutoBot-AI/pull/5156))

- *(frontend)* Move formatters out of types/ + consolidate duplicates (#5107) (#5148) ([#5148](https://github.com/mrveiss/AutoBot-AI/pull/5148))

- *(llm)* Extract shared call_ollama_generate helper (#5102) (#5147) ([#5147](https://github.com/mrveiss/AutoBot-AI/pull/5147))

- *(frontend)* Split useKnowledgeBase into 6 domain composables + drop dead try/catch boilerplate (#5122 #5123) (#5145) ([#5145](https://github.com/mrveiss/AutoBot-AI/pull/5145))

- *(analytics)* Extract useAnalyticsEndpoint<T> composable (#5112) (#5137) ([#5137](https://github.com/mrveiss/AutoBot-AI/pull/5137))

- *(shared)* Consolidate UTC-timestamp helpers into autobot_shared.time_utils (#5106) (#5126) ([#5126](https://github.com/mrveiss/AutoBot-AI/pull/5126))

- *(redis)* Consolidate _decode helpers into autobot_shared.redis_utils (#5100) (#5125) ([#5125](https://github.com/mrveiss/AutoBot-AI/pull/5125))

- *(frontend)* Remove no-op 'const data = response' aliases in useKnowledgeBase (#5092) (#5128) ([#5128](https://github.com/mrveiss/AutoBot-AI/pull/5128))

- *(knowledge)* Migrate facts.py embedding path to services.npu_client canonical helpers (#5105) (#5127) ([#5127](https://github.com/mrveiss/AutoBot-AI/pull/5127))

- *(frontend)* Unify uploadKnowledgeFile with apiClient pattern (#5093) (#5116) ([#5116](https://github.com/mrveiss/AutoBot-AI/pull/5116))

- *(orchestrator)* Preserve unbounded gather behavior via len(coros) (#5059)

- *(orchestrator)* Migrate to bounded_gather primitive (#5059, closes #5059)

- *(typescript)* Delete parseApiResponse from useKnowledgeBase (#5033) (#5091) ([#5091](https://github.com/mrveiss/AutoBot-AI/pull/5091))

- *(knowledge)* Add ConnectorRegistry public API; replace 3 _connectors private accesses (#5057) (#5089) ([#5089](https://github.com/mrveiss/AutoBot-AI/pull/5089))

- *(typescript)* Delete parseApiResponse from useKnowledgeVectorization (#5033)

- *(backend)* Clean up stale AgentOrchestrator reference in agent_config (#5040)

- *(backend)* Remove all backward-compat shims and name aliases (#5040)

- *(backend)* Align ResourceFactory and tests with single Orchestrator (#5040, closes #5038, #5039)

- *(services)* Rename specialized orchestrators (SLM, deployment, subagent, loop, workflow, agent) (#5040)

- *(orchestrator)* Rename ConsolidatedOrchestrator → Orchestrator (single conductor, #5040)

- *(orchestrator)* Merge EnhancedMultiAgentOrchestrator into ConsolidatedOrchestrator (#5040)

- *(testing)* Check deps via importlib.metadata instead of find_spec (#5044)

- *(ui)* Remove spinner special-case from Icon.vue (#5043)

- *(typescript)* Make parseApiResponse generic + type 77 call sites (#4438)

- *(tokens)* Rename --spacing-44px to --touch-target-min, inline --spacing-140px (#5036)

- *(ui)* Type Icon 'name' prop as union of registry keys (#5035)

- *(backend)* Clean up stale EnhancedOrchestrator docstrings (#4048)

- *(backend)* Consolidate orchestrator files 5→4 (#4048)

- *(llm)* Split llm_multi_provider into plugin-per-provider architecture (#4411)

- *(frontend)* Add ManPageManager stub and barrel index files for TS7016 compatibility (#4534)

- *(extensions)* Register LoggingExtension builtin extension (#4182) (#4883) ([#4883](https://github.com/mrveiss/AutoBot-AI/pull/4883))

- *(config)* Complete ConfigManager → get_config_manager() migration (#4047) (#4870) ([#4870](https://github.com/mrveiss/AutoBot-AI/pull/4870))

- *(backend)* Remove backward-compat shim orchestrator files (#3393) (#4869) ([#4869](https://github.com/mrveiss/AutoBot-AI/pull/4869))

- *(backend)* Replace deprecated get_event_loop() with get_running_loop() (#4717)

- *(docs)* Remove incorrect ON_ prefix from HookPoint docstring examples (#4391)

- *(tools)* Move 12 inline _BUILTIN_TOOL_SCHEMAS to authoritative schema constants per tool module (#4726) (#4784) ([#4784](https://github.com/mrveiss/AutoBot-AI/pull/4784))

- *(slm-frontend)* Delete deprecated NodesSettings.vue (#4707) (#4774) ([#4774](https://github.com/mrveiss/AutoBot-AI/pull/4774))

- *(components)* Wire orphaned OperationDetail component (#4270) (#4770) ([#4770](https://github.com/mrveiss/AutoBot-AI/pull/4770))

- *(components)* Wire orphaned OperationDetail component (#4270) (#4769) ([#4769](https://github.com/mrveiss/AutoBot-AI/pull/4769))

- *(rag)* Wire NeuralMeshRetriever deletion — remove 488-line dead class and tests (#4724) (#4748) ([#4748](https://github.com/mrveiss/AutoBot-AI/pull/4748))

- *(routing)* Consolidate nav — remove orphan routes, merge into parent tabs

- *(components)* Wire CodeEvolutionTimeline (#4268) (#4349) ([#4349](https://github.com/mrveiss/AutoBot-AI/pull/4349))

- *(components)* Wire KnowledgeMainCategories (#4282)

- *(components)* Wire FlagChangeHistory (#4271)

- *(components)* Wire AccessMetrics (#4269)

- *(router)* Register presence_ws router (#4257)

- *(router)* Register self_capabilities router (#4258)

- *(router)* Register manual_mcp router (#4256)

- *(router)* Register knowledge_grounding router (#4255)

- *(router)* Register diagnostics router (#4254)

- *(router)* Register analytics_export router (#4253)

- *(router)* Register analytics_cost router (#4252)

- *(router)* Register analytics_code router in feature_routers (#4251)

- *(backend)* Consolidate router registries (#4203)

- *(extensions)* Redesign hook invocation strategy (#4202)

- *(frontend)* Wire orphaned views (#4185)

- *(frontend)* Audit design-implementation gap (#4194)

- *(frontend)* Audit orphaned Vue components (#4184)

- *(extensions)* Register SecretMaskingExtension builtin extension (#4183)

- *(backend)* Register unregistered API routers (#4179)

- *(backend)* Register 6 unregistered knowledge routers (#4179)

- *(backend)* Register 17 unregistered API routers (#4180)

- *(extensions)* Wire uninvoked HookPoints (#4181)

- *(components)* Wire orphaned component KnowledgeScopeSelector (#4276)

- *(components)* Wire orphaned component EnforcementModeSelector (#4273)

- *(components)* Wire orphaned component RelationshipViewer (#4272)

- *(components)* Delete orphaned KnowledgeScopeSelector component (#4276)

- *(components)* Wire orphaned component KnowledgeContentViewer (#4278)

- *(components)* Wire orphaned component StableLoadingState (#4283)

- *(components)* Wire orphaned component KnowledgeBrowserHeader (#4284) (#4321) ([#4321](https://github.com/mrveiss/AutoBot-AI/pull/4321))

- *(components)* Delete orphaned IconTooling component (#4287) (#4319) ([#4319](https://github.com/mrveiss/AutoBot-AI/pull/4319))

- *(components)* Wire orphaned component FilePathNavigation (#4286) (#4317) ([#4317](https://github.com/mrveiss/AutoBot-AI/pull/4317))

- *(browser-worker)* Extract automation code from src/ (#4310) (#4316) ([#4316](https://github.com/mrveiss/AutoBot-AI/pull/4316))

- *(npu-worker)* Extract NPU integration code from backend (#4311) (#4315) ([#4315](https://github.com/mrveiss/AutoBot-AI/pull/4315))

- *(provisioning)* Replace timeout-based waits with retry-based health checks across all critical services

- *(cleanup)* Remove dead code icon components and shadow router (#4288 #4289 #4290 #4291 #4292) ([#4304](https://github.com/mrveiss/AutoBot-AI/pull/4304))

- *(ansible)* Centralize ChromaDB/AI-Stack config generation (#4087)

- *(knowledge)* Async background task for populate_autobot_docs (#4103)

- *(config)* Migrate infrastructure callers from ConfigManager to ssot_config (#3829) (#4101) ([#4101](https://github.com/mrveiss/AutoBot-AI/pull/4101))

- *(ai-stack)* Unified service account to autobot:autobot (#4091)

- *(config)* Eliminate double ConfigManager instantiation in chat_history (#3945) (#4081) ([#4081](https://github.com/mrveiss/AutoBot-AI/pull/4081))

- *(html)* Remove redundant role="button" and fix duplicate var (#4039)

- *(svg)* Extract inline SVG to sprite sheets (#4040)

- *(redis)* Migrate get_redis_client(async_client=True) to get_async_redis_client (#4059) (#4070) ([#4070](https://github.com/mrveiss/AutoBot-AI/pull/4070))

- *(service-worker)* Enhance caching strategy with expiration and offline fallback (#4041)

- *(nav)* Move browser-automation from main menu to Automation sidebar

- Enhance feature request template with triage guidance

- Enhance bug report template with triage guidance

- *(perf)* Add SVG sprite sheets for icon optimization (#4040)

- *(a11y)* Replace non-semantic HTML with proper buttons (#4039)

- *(services)* Migrate DistributedServiceDiscovery to AsyncInitializable (#3947) (#4022) ([#4022](https://github.com/mrveiss/AutoBot-AI/pull/4022))

- *(agents)* Migrate 3 agents to StandardizedAgent base class (#3387) (#3989) ([#3989](https://github.com/mrveiss/AutoBot-AI/pull/3989))

- *(backend)* Consolidate orchestrator files (#3393) (#3982) ([#3982](https://github.com/mrveiss/AutoBot-AI/pull/3982))

- *(config)* Migrate 27 ConfigManager() callers to get_config_manager() (#3829) (#3981) ([#3981](https://github.com/mrveiss/AutoBot-AI/pull/3981))

- *(services)* Migrate 4 singletons to AsyncInitializable lazy-init pattern (#3390) (#3935) ([#3935](https://github.com/mrveiss/AutoBot-AI/pull/3935))

- *(config)* Migrate 8 ConfigManager callers to ssot_config (#3829) (#3932) ([#3932](https://github.com/mrveiss/AutoBot-AI/pull/3932))

- *(retry)* Standardize all retry/backoff on retry_mechanism.py (#3830) (#3928) ([#3928](https://github.com/mrveiss/AutoBot-AI/pull/3928))

- *(frontend)* Route raw WebSocket() calls through useWebSocket composable (#3841) ([#3913](https://github.com/mrveiss/AutoBot-AI/pull/3913))

- *(auth)* Extract JWT/bcrypt core into autobot_shared — eliminate SLM duplication (#3840) ([#3910](https://github.com/mrveiss/AutoBot-AI/pull/3910))

- *(backend)* Migrate singletons to AsyncInitializable lazy-init (#3885) ([#3885](https://github.com/mrveiss/AutoBot-AI/pull/3885))

- *(knowledge)* Consolidate vector search under VectorSearchEngine (#3828) (#3879) ([#3879](https://github.com/mrveiss/AutoBot-AI/pull/3879))

- *(http)* Consolidate HTTP clients — TracedHttpClient wraps HTTPClientManager, extract sign_request (#3827) (#3870) ([#3870](https://github.com/mrveiss/AutoBot-AI/pull/3870))

- *(chat)* Tombstone legacy conversation.py, remove dead ConversationManager from orchestrator (#3831) (#3865) ([#3865](https://github.com/mrveiss/AutoBot-AI/pull/3865))

- *(backend)* Consolidate terminal API implementations, remove compat aliases (#3383) (#3833) ([#3833](https://github.com/mrveiss/AutoBot-AI/pull/3833))

- *(llm)* Consolidate llm_providers/ with llm_interface_pkg adapters (#3185) ([#3837](https://github.com/mrveiss/AutoBot-AI/pull/3837))

- *(tests)* Co-locate single-module tests from autobot-backend/ root (#3364) ([#3712](https://github.com/mrveiss/AutoBot-AI/pull/3712))

- *(backend)* Remove dead doc_generation_threshold attribute (#3656) ([#3669](https://github.com/mrveiss/AutoBot-AI/pull/3669))

- *(agents)* Cap exponential backoff in agent_client.py via exponential_backoff_delay (#3658) ([#3666](https://github.com/mrveiss/AutoBot-AI/pull/3666))

- *(backend)* Give context_window_manager its own config YAML (#3650) ([#3668](https://github.com/mrveiss/AutoBot-AI/pull/3668))

- *(agents)* Declare _get_system_prompt @abstractmethod in StandardizedAgent (#3606) ([#3645](https://github.com/mrveiss/AutoBot-AI/pull/3645))

- *(backend)* Remove dead AgentThresholds import and replace magic 0.8 in orchestrator.py (#3607) ([#3644](https://github.com/mrveiss/AutoBot-AI/pull/3644))

- *(helpers)* Cap exponential backoff via TimingConstants (#3565) ([#3643](https://github.com/mrveiss/AutoBot-AI/pull/3643))

- *(helpers)* Remove duplicate raise_not_found_error in catalog_http_exceptions (#3566) ([#3642](https://github.com/mrveiss/AutoBot-AI/pull/3642))

- *(helpers)* Add extra_data support to TaskResult (#3564) ([#3640](https://github.com/mrveiss/AutoBot-AI/pull/3640))

- *(constants)* Add TTL_1_HOUR/TTL_5_MINUTES and replace raw cache TTL literals (#3614) (#3617) ([#3617](https://github.com/mrveiss/AutoBot-AI/pull/3617))

- *(agents)* Migrate 6 agents to StandardizedAgent base class (#3387)

- *(backend)* Consolidate orchestrator files — delete enhanced_orchestrator.py (#3393) ([#3589](https://github.com/mrveiss/AutoBot-AI/pull/3589))

- *(backend)* Consolidate orchestrator files — delete enhanced_orchestrator.py (#3393)

- *(backend)* Consolidate 4 competing terminal API implementations (#3383) (#3576) ([#3576](https://github.com/mrveiss/AutoBot-AI/pull/3576))

- *(constants)* Add TaskStatus.PARTIALLY_COMPLETED — wire 2 orchestration sites (#3578) ([#3580](https://github.com/mrveiss/AutoBot-AI/pull/3580))

- *(analytics)* Extract _resolve_source_or_404 to shared helper (#3440) (#3573) ([#3573](https://github.com/mrveiss/AutoBot-AI/pull/3573))

- *(constants)* Wire ERR_EXPERIMENT_NOT_FOUND (#3562) ([#3570](https://github.com/mrveiss/AutoBot-AI/pull/3570))

- *(constants)* TaskStatus defaults in orchestration/types.py (#3563) ([#3569](https://github.com/mrveiss/AutoBot-AI/pull/3569))

- *(constants)* Enforce StatusEnum in orchestration production code (#3544) ([#3560](https://github.com/mrveiss/AutoBot-AI/pull/3560))

- *(constants)* Complete error_constants adoption (#3550) ([#3559](https://github.com/mrveiss/AutoBot-AI/pull/3559))

- *(constants)* Centralize Redis TTL and async timeout constants (#3529) ([#3543](https://github.com/mrveiss/AutoBot-AI/pull/3543))

- *(constants)* Enforce ModelConstants — replace hardcoded model strings (#3528) (#3542) ([#3542](https://github.com/mrveiss/AutoBot-AI/pull/3542))

- *(constants)* Create api_constants.py — centralize API path strings (#3531) (#3540) ([#3540](https://github.com/mrveiss/AutoBot-AI/pull/3540))

- *(constants)* Create error_constants.py — centralize repeated error strings (#3530) (#3539) ([#3539](https://github.com/mrveiss/AutoBot-AI/pull/3539))

- *(constants)* Enforce StatusEnum in tests — replace hardcoded status strings (#3533) (#3537) ([#3537](https://github.com/mrveiss/AutoBot-AI/pull/3537))

- *(setup_wizard)* Replace port magic numbers with _ROLE_INFRA_VARS and _CHROMADB_PORT constant (#3526) ([#3527](https://github.com/mrveiss/AutoBot-AI/pull/3527))

- *(backend)* Introduce get_config DI dependency for global_config_manager (#3455) ([#3455](https://github.com/mrveiss/AutoBot-AI/pull/3455))

- *(slm)* Reuse DEFAULT_REPO_PATH from git_tracker in drift_checker (#3434) ([#3454](https://github.com/mrveiss/AutoBot-AI/pull/3454))

- *(analytics)* Remove unneeded flat-path redirect routes (#3436)

- *(backend)* Deprecate 9 redundant health endpoints, keep /api/system/health primary (#3333) (#3353) ([#3353](https://github.com/mrveiss/AutoBot-AI/pull/3353))

- *(backend)* Document KB API boundaries, deprecate unregistered kb_librarian routes (#3336) (#3347) ([#3347](https://github.com/mrveiss/AutoBot-AI/pull/3347))

- *(backend)* Deprecate base_terminal, simple/secure_terminal_websocket in favour of terminal.py (#3332) (#3346) ([#3346](https://github.com/mrveiss/AutoBot-AI/pull/3346))

- *(backend)* Deprecate duplicate /settings/settings endpoints, fix audit middleware stale /api/config refs (#3334) (#3345) ([#3345](https://github.com/mrveiss/AutoBot-AI/pull/3345))

- *(slm-frontend)* Export useSlmApi internal interfaces to shared types (#3196) (#3342) ([#3342](https://github.com/mrveiss/AutoBot-AI/pull/3342))

- *(slm-frontend)* Extract formatRelativeTime to shared dateUtils (#3314) (#3318) ([#3318](https://github.com/mrveiss/AutoBot-AI/pull/3318))

- Extract shared escapeHtml utility, remove duplicates (#3215) (#3256) ([#3256](https://github.com/mrveiss/AutoBot-AI/pull/3256))

- *(chat)* Expose load_full_session public API to avoid private method access (#3189) (#3252) ([#3252](https://github.com/mrveiss/AutoBot-AI/pull/3252))

- *(frontend)* Extract shared escapeHtml utility from duplicated implementations (#3215) (#3251) ([#3251](https://github.com/mrveiss/AutoBot-AI/pull/3251))

- *(ansible)* Move all inline template defaults to role defaults/main.yml (#3226)

- Condense CLAUDE.md, extract full rules to dedicated docs

- Rename autobot-shared to autobot_shared, remove symlink workarounds (#2934)

- *(frontend)* Consolidate code-intelligence into /analytics/codebase (#3067, #3073)

- *(chat)* Simplify callers to use kwargs directly instead of functools.partial (#2958) (#2978) ([#2978](https://github.com/mrveiss/AutoBot-AI/pull/2978))

- *(backend)* Decompose _generate_dynamic_inventory into 5 helpers (#2823) (#2945) ([#2945](https://github.com/mrveiss/AutoBot-AI/pull/2945))

- *(frontend)* Remove 7 orphaned workflow sub-components (#2819) (#2920) ([#2920](https://github.com/mrveiss/AutoBot-AI/pull/2920))

- *(config)* Centralize Redis DB allocation — load from YAML SSOT (#2670) (#2804) ([#2804](https://github.com/mrveiss/AutoBot-AI/pull/2804))

- *(frontend)* Replace error.value race with errors array (#2626) ([#2792](https://github.com/mrveiss/AutoBot-AI/pull/2792))

- *(config)* Centralize Redis DB allocation (#2670) ([#2790](https://github.com/mrveiss/AutoBot-AI/pull/2790))

- *(infra)* Replace hardcoded model strings with SSOT (#2584) ([#2784](https://github.com/mrveiss/AutoBot-AI/pull/2784))

- *(backend)* Derive ToolRegistry tools from shared constant (#2609) ([#2783](https://github.com/mrveiss/AutoBot-AI/pull/2783))

- *(backend)* Migrate Pydantic V1 patterns to V2 (#2630) ([#2781](https://github.com/mrveiss/AutoBot-AI/pull/2781))

- *(frontend)* Align ConsoleLogEntry with variadic log() (#2627) ([#2778](https://github.com/mrveiss/AutoBot-AI/pull/2778))

- *(shared)* Consolidate local-node detection into network_utils (#2759) (#2774) ([#2774](https://github.com/mrveiss/AutoBot-AI/pull/2774))

- *(analytics)* Extract resolve_source_root into shared helper (#2760) (#2772) ([#2772](https://github.com/mrveiss/AutoBot-AI/pull/2772))

- *(workflow)* Remove redundant StepTimeoutError except clause (#2746) (#2771) ([#2771](https://github.com/mrveiss/AutoBot-AI/pull/2771))

- *(devops)* Extract shared backend env vars (#2727) ([#2777](https://github.com/mrveiss/AutoBot-AI/pull/2777))

- *(devops)* Extract shared backend env vars to DRY up playbooks (#2727)

- *(analytics)* Extract methods from long analytics functions (#2735) ([#2739](https://github.com/mrveiss/AutoBot-AI/pull/2739))

- *(chat)* Extract methods from long chat/service functions (#2735) ([#2743](https://github.com/mrveiss/AutoBot-AI/pull/2743))

- *(api)* Extract methods from long API functions (#2735) ([#2742](https://github.com/mrveiss/AutoBot-AI/pull/2742))

- *(services)* Extract methods from long functions (#2735) ([#2741](https://github.com/mrveiss/AutoBot-AI/pull/2741))

- *(config)* Migrate hardcoded values to SSOT config (#2671)

- *(agents)* Simplify to 3-tier model mapping with gemma3:4b (#2553)

- *(infra)* Replace 58 print() calls with logger in seq_auth_setup.py (#2569) (#2574) ([#2574](https://github.com/mrveiss/AutoBot-AI/pull/2574))

- *(infra)* Replace 46 print() calls with logger in setup_seq_analytics.py (#2554) (#2566) ([#2566](https://github.com/mrveiss/AutoBot-AI/pull/2566))

- *(backend)* Remove unused PROMPTS_DIR constant (#2498)

- *(backend)* Remove duplicate prompts/chat/, keep backend resources copy (#2472)

- Consolidate duplicate prompt files to single source (#2472)

- Consolidate duplicate prompt files (#2472) ([#2483](https://github.com/mrveiss/AutoBot-AI/pull/2483))

- *(backend)* Decompose scanner.py orchestrator (#2364) (#2474) ([#2474](https://github.com/mrveiss/AutoBot-AI/pull/2474))


### Styling

- *(base)* Apply Black formatting to 5 files in Dev_new_gui (MVA-2892)

- Fix Black formatting in celery_app.py

- Fix Black formatting violations

- *(formatting)* Fix Black and isort violations on 6 files

- *(formatting)* Fix Black formatting on 5 pre-existing files

- *(frontend)* Remove banned design patterns from chat and SLM UIs (#9013)

- Fix isort ordering in test_model_param_registry.py

- Fix Black formatting in test_model_param_registry.py (blank line after import)

- *(backend)* Black-format 5 pre-existing unformatted files (MVA-1307-black) (#8832) ([#8832](https://github.com/mrveiss/AutoBot-AI/pull/8832))

- *(ci)* Black format agent_loop/types.py, npu_models.py, loop.py (MVA-1141 followup)

- *(ci)* Black format 4 files from merged #8648/#8658 (MVA-1141 followup)

- *(ci)* Remove 125 unused imports to fix flake8 F401 (code-quality CI)

- Fix isort on 5 base-branch files (unblock code-quality CI on all PRs)

- Fix isort import ordering on 13 files (unblock code-quality CI)

- Apply Black formatting to 6 files (unblock code-quality CI)

- Fix isort import ordering on LLC/services/tests files

- Apply Black formatting to base LLC/agents files

- Fix isort import ordering on LLC/services/tests files

- Apply Black formatting (line-length=120) on issue-8253

- Fix isort import ordering on LLC/services/tests files

- Apply Black formatting (line-length=120) to LLC/agents dirs

- Fix isort import ordering on LLC/services/tests files

- Apply Black formatting to base LLC/agents files

- Apply Black formatting (line-length=120) on issue-8258

- Fix isort import ordering on LLC/services/tests files

- Apply Black formatting to base LLC/agents files

- Apply Black formatting (line-length=120) on issue-8260

- Fix isort import ordering on LLC/services/tests files

- Apply Black formatting to base LLC/agents files

- Fix isort import ordering on LLC/services/tests files

- Apply Black formatting to base LLC/agents files

- Apply Black formatting (line-length=120) on issue-8252

- Apply Black formatting (line-length=120) on issue-8254

- Apply Black formatting to base LLC/agents files

- Apply Black formatting (line-length=120) on LLC P6 company import

- Apply Black formatting to base LLC/agents files

- Apply Black formatting (line-length=120) on LLC P5 artifact ingestor

- Apply Black formatting to base LLC/agents files

- Apply Black formatting (line-length=120) on issue-8257

- Apply Black formatting to base LLC/agents files

- Apply Black formatting (line-length=120) on LLC P5 agent diary

- Apply Black formatting to base LLC/agents files

- Apply Black formatting (line-length=120) on LLC P5 KB collections

- Apply Black formatting (line-length=120) on LLC P5 heartbeat context builder

- *(llc/8225)* Apply Black formatting to remaining PR files (line-length=120)

- *(llc/8225)* Apply Black formatting (line-length=120)

- *(mva454/mva468)* Autoflake cleanup + pre-commit py3.12 + health check journalctl (#7709, #7686) ([#7822](https://github.com/mrveiss/AutoBot-AI/pull/7822))

- Fix Black formatting regressions in Dev_new_gui (MVA-454) (#7815) ([#7815](https://github.com/mrveiss/AutoBot-AI/pull/7815))

- *(a2a)* Black formatting for pii_pipeline + task_executor (#7355)

- *(ci)* Fix Black 3.12 + isort + unused import in test file — unblocks code-quality CI (MVA-303) ([#7704](https://github.com/mrveiss/AutoBot-AI/pull/7704))

- Fix import sorting with isort (MVA-160)

- Apply Black formatting to fix CI code-quality check (MVA-160)

- Apply Black formatting to run_jwt files (CI fix)

- Apply Black formatting to chat_phase2_test.py (CI fix)

- Isort 21 pre-existing import-sort failures to fix code-quality CI

- Fix pre-existing Black formatting failures on Dev_new_gui ([#7645](https://github.com/mrveiss/AutoBot-AI/pull/7645))

- Black-format 9 files at line-length=120 (MVA-68) (#7532) ([#7532](https://github.com/mrveiss/AutoBot-AI/pull/7532))

- Black + isort format restoration (closes #7225 part 2) (#7515) ([#7515](https://github.com/mrveiss/AutoBot-AI/pull/7515))

- *(tokens)* Remove 3 unused --spacing-micro-* tokens (#5036) (#5224) ([#5224](https://github.com/mrveiss/AutoBot-AI/pull/5224))

- *(tokens)* Delete pixel-value spacing tokens; round call sites to rem scale (#5036)

- *(tokens)* Add missing spacing tokens for negative margins and non-standard sizes (#4948)

- *(tokens)* Replace hardcoded padding/margin/gap with spacing design tokens (#4651) ([#4942](https://github.com/mrveiss/AutoBot-AI/pull/4942))

- *(tokens)* Replace hardcoded padding/margin/gap values with spacing design tokens (#4651)

- *(tokens)* Replace hardcoded transition values with design tokens (#4590) (#4613) ([#4613](https://github.com/mrveiss/AutoBot-AI/pull/4613))

- *(tokens)* Replace hardcoded font-size values with design tokens (#4589) (#4612) ([#4612](https://github.com/mrveiss/AutoBot-AI/pull/4612))

- *(tokens)* Replace hardcoded border-radius values with design tokens (#4559) (#4611) ([#4611](https://github.com/mrveiss/AutoBot-AI/pull/4611))

- Reformat all Python files with Black --line-length=120 (#4124) ([#4250](https://github.com/mrveiss/AutoBot-AI/pull/4250))

- Apply Black formatting to 89 Python files (#3408) ([#3409](https://github.com/mrveiss/AutoBot-AI/pull/3409))

- Fix isort import ordering across 16 Python files

- *(slm,shared)* Apply Black formatting to slm-backend and autobot_shared

- *(backend)* Apply Black formatting to skills, tests, utils modules

- *(backend)* Apply Black formatting to orchestration, security, services modules

- *(backend)* Apply Black formatting to agents, api, knowledge, llm, multimodal modules

- *(slm)* Restore unicode section headers in setup_wizard.py (#2951) (#2998) ([#2998](https://github.com/mrveiss/AutoBot-AI/pull/2998))

- *(backend)* Auto-format 53 Python files with Black + isort (#2919) (#2942) ([#2942](https://github.com/mrveiss/AutoBot-AI/pull/2942))

- Apply Black formatting to 9 mesh_brain/neural_mesh files (#2582) ([#2589](https://github.com/mrveiss/AutoBot-AI/pull/2589))


### Testing

- *(voice)* Fix TTL override test — reload ssot_config before telemetry module (#7421)

- *(config)* Regression guard for logging_manager on config-manager init path (MVA-1465, GH#8766) ([#8903](https://github.com/mrveiss/AutoBot-AI/pull/8903))

- *(a2a)* Add regression test for get_trust_manager() lazy_singleton (MVA-1359 / GH#8741) (#8888) ([#8888](https://github.com/mrveiss/AutoBot-AI/pull/8888))

- *(llm/tiered-routing)* Add long_context tier routing tests (MVA-1372) ([#8863](https://github.com/mrveiss/AutoBot-AI/pull/8863))

- *(heartbeat)* Integration test for paused agent wakeup queue drain (GH#6476 AC-9) (#8733)

- *(heartbeat)* Integration test for paused agent wakeup queue drain (GH#6476 AC-9) ([#8793](https://github.com/mrveiss/AutoBot-AI/pull/8793))

- *(auth)* Unit tests for authenticate_websocket user_id forwarding (MVA-914) ([#8716](https://github.com/mrveiss/AutoBot-AI/pull/8716))

- *(autoresearch)* Add edge-case and endpoint coverage (#3211) (#8364) ([#8364](https://github.com/mrveiss/AutoBot-AI/pull/8364))

- *(ci)* Add authenticated-WebSocket smoke tests for /ws/live and /ws/events (#6699) (#8273) ([#8273](https://github.com/mrveiss/AutoBot-AI/pull/8273))

- *(hooks)* Add 27-case test suite for block-dangerous-commands.sh (#8262)

- *(system-health)* Add probe data-contract tests for batch_jobs and long_running (#6916) (#7924) ([#7924](https://github.com/mrveiss/AutoBot-AI/pull/7924))

- *(slm/rbac)* Add 22 unit tests for Redis L2 cache + pub/sub invalidation (MVA-313 / GH#7568) (#8046) ([#8046](https://github.com/mrveiss/AutoBot-AI/pull/8046))

- *(ci)* Run audit-unwired-trackers tests before cron audit (#6929) (#7873) ([#7873](https://github.com/mrveiss/AutoBot-AI/pull/7873))

- *(redis-mocks)* Migrate 3 test files to canonical mock helpers (closes #7753) ([#7857](https://github.com/mrveiss/AutoBot-AI/pull/7857))

- *(celery)* Add regression test for task registration to prevent repeat of unregistered-task bug (#7766) (#7829) ([#7829](https://github.com/mrveiss/AutoBot-AI/pull/7829))

- *(enhanced_orchestration)* Phase 2+3 integration tests for GH#7268 (#7770) ([#7770](https://github.com/mrveiss/AutoBot-AI/pull/7770))

- *(rbac,marketplace)* RBAC cache-invalidation + HTTP-422 tests (GH#7609, GH#7328) (#7751) ([#7751](https://github.com/mrveiss/AutoBot-AI/pull/7751))

- *(slm/rbac)* 22 unit tests for Redis L2 cache + pub/sub invalidation (MVA-313 / GH#7568) ([#7718](https://github.com/mrveiss/AutoBot-AI/pull/7718))

- *(scheduler)* Add integration tests for multi-worker restart recovery (MVA-160)

- *(auth)* Cross-service parity test + docs/architecture/auth.md (MVA-127) ([#7633](https://github.com/mrveiss/AutoBot-AI/pull/7633))

- *(security)* P0 regression tests for GH #6568 / #6838 / #6876 (#6570) (#7542) ([#7542](https://github.com/mrveiss/AutoBot-AI/pull/7542))

- *(chat_history/cache)* Pin TTL resolver + document env-var override (#6743) (#7363) ([#7363](https://github.com/mrveiss/AutoBot-AI/pull/7363))

- *(api/code-sync)* Unit tests for POST /drift/resolve (closes #7224) (#7231) ([#7231](https://github.com/mrveiss/AutoBot-AI/pull/7231))

- *(hooks)* Unit tests for lib/_common.sh — 9 cases (closes #7193) (#7195) ([#7195](https://github.com/mrveiss/AutoBot-AI/pull/7195))

- *(ci)* Cover vars_files codepath + diff-guard fact-file dup (#7094 + #7095) ([#7114](https://github.com/mrveiss/AutoBot-AI/pull/7114))

- *(ci)* Regression guard for shared role_*_active facts (#7056) (#7068) ([#7068](https://github.com/mrveiss/AutoBot-AI/pull/7068))

- *(autobot_shared)* Add MissingDep unit tests (#6807) (#6969) ([#6969](https://github.com/mrveiss/AutoBot-AI/pull/6969))

- *(hooks)* Cover the 8 untested check_* categories of the hardcoded-values hook (closes #6786) (#6945) ([#6945](https://github.com/mrveiss/AutoBot-AI/pull/6945))

- *(ci)* Add backend startup-import smoke test (#6540) (#6673) ([#6673](https://github.com/mrveiss/AutoBot-AI/pull/6673))

- *(nav)* Add navItems coverage test for requiresAuth routes (#6499) (#6542) ([#6542](https://github.com/mrveiss/AutoBot-AI/pull/6542))

- *(mcp)* Add integration tests for isolated MCP bridge deployment (#4106) (#6445) ([#6445](https://github.com/mrveiss/AutoBot-AI/pull/6445))

- *(mcp)* Add concurrency test for unique request IDs in isolated bridge runtime (#4105) (#6384) ([#6384](https://github.com/mrveiss/AutoBot-AI/pull/6384))

- *(shared)* Add rate_limiter_test.py covering sliding-window logic and graceful Redis fallback (#6337) (#6353) ([#6353](https://github.com/mrveiss/AutoBot-AI/pull/6353))

- *(lint)* Add tests and extend check_response_models to SuccessMessageResponse/SuccessDataResponse (#5924 #5925) (#5931) ([#5931](https://github.com/mrveiss/AutoBot-AI/pull/5931))

- *(composables)* Add useApiResource tests for abortPrior:false and zero-arg fetcher semantics (#5803) (#5863) ([#5863](https://github.com/mrveiss/AutoBot-AI/pull/5863))

- *(browser)* Add URL normalization unit tests for VisualBrowserPanel (#5575) (#5778) ([#5778](https://github.com/mrveiss/AutoBot-AI/pull/5778))

- *(utils)* Add lazy_optional_singleton unit tests (#5645) (#5654) ([#5654](https://github.com/mrveiss/AutoBot-AI/pull/5654))

- *(utils)* Add lazy_optional_singleton unit tests (#5645) (#5651) ([#5651](https://github.com/mrveiss/AutoBot-AI/pull/5651))

- *(knowledge)* Grow RAG ground-truth eval dataset from 5 to ≥50 queries (#5196) (#5640) ([#5640](https://github.com/mrveiss/AutoBot-AI/pull/5640))

- *(provision)* Update heartbeat assertion for task-name-always-shown (#5607)

- *(autobot_shared)* Add singleton_factory_test.py — lazy_singleton arg-guard and thread-safety (#5568) (#5574) ([#5574](https://github.com/mrveiss/AutoBot-AI/pull/5574))

- *(utils)* Add pytest structural tests for OptimizedSemanticChunker (#5439) (#5544) ([#5544](https://github.com/mrveiss/AutoBot-AI/pull/5544))

- *(backend)* Migrate asyncio.run() test runners to @pytest.mark.asyncio (#5435) (#5543) ([#5543](https://github.com/mrveiss/AutoBot-AI/pull/5543))

- *(conftest)* Add mock_llm fixture to root conftest (#5432) (#5484) ([#5484](https://github.com/mrveiss/AutoBot-AI/pull/5484))

- *(utils)* Redis-mocked tests for _mark_orphans + get_status auto-recovery (#5463) (#5466) ([#5466](https://github.com/mrveiss/AutoBot-AI/pull/5466))

- *(frontend)* Fix 4 pre-existing baseline test failures (#5366) (#5446) ([#5446](https://github.com/mrveiss/AutoBot-AI/pull/5446))

- *(analytics)* Component unit tests for Hardcodes/Duplicates/Declarations sections (#5369) (#5378) ([#5378](https://github.com/mrveiss/AutoBot-AI/pull/5378))

- *(api)* Freeze api_endpoint_migrations_test.py pending audit (#5359) (#5362) ([#5362](https://github.com/mrveiss/AutoBot-AI/pull/5362))

- *(api)* Fix TestVectorizeExistingFactsEndpoint (#5336) (#5353) ([#5353](https://github.com/mrveiss/AutoBot-AI/pull/5353))

- *(knowledge)* Fix KnowledgeBase imports after _composed.py refactor (#5292) (#5352) ([#5352](https://github.com/mrveiss/AutoBot-AI/pull/5352))

- *(codebase-analytics)* Contract tests for /hardcodes normalizer (#5313) (#5334) ([#5334](https://github.com/mrveiss/AutoBot-AI/pull/5334))

- *(api)* Update stale source-inspection assertion for kb.redis() (#5338) (#5339) ([#5339](https://github.com/mrveiss/AutoBot-AI/pull/5339))

- *(knowledge)* Migrate 27 test-mock sites to KB.redis() pattern (#5282) (#5293) ([#5293](https://github.com/mrveiss/AutoBot-AI/pull/5293))

- *(lint)* Add unit tests for check_no_utcnow_isoformat.py (#5269) (#5279) ([#5279](https://github.com/mrveiss/AutoBot-AI/pull/5279))

- *(knowledge_audit)* Fix 3 tests that bypass FastAPI injection (#5254) (#5273) ([#5273](https://github.com/mrveiss/AutoBot-AI/pull/5273))

- *(shared)* Add unit tests for autobot_shared.time_utils helpers (#5170) (#5175) ([#5175](https://github.com/mrveiss/AutoBot-AI/pull/5175))

- *(knowledge)* Type useKnowledgeBase.test.ts mock fixtures — drop 'as any' casts (#5034)

- *(rag)* Add coverage for RAGService._get_kb_synthesis_context multi-collection path (#4659) ([#4950](https://github.com/mrveiss/AutoBot-AI/pull/4950))

- *(rag)* Add coverage for RAGService._get_kb_synthesis_context multi-collection path (#4659)

- *(knowledge)* Add coverage for _find_collection_config and _run_kb_synthesis (#4658) ([#4949](https://github.com/mrveiss/AutoBot-AI/pull/4949))

- *(knowledge)* Add coverage for _find_collection_config and _run_kb_synthesis (#4658)

- *(rag)* Verify staleness-penalty × provenance-boost ordering in ResultReranker (#4897) ([#4941](https://github.com/mrveiss/AutoBot-AI/pull/4941))

- *(rag)* Verify staleness-penalty × provenance-boost ordering in ResultReranker (#4897)

- *(mesh)* Add CommunityClusterer-with-MeshDbAdapter integration test (#4864) (#4879) ([#4879](https://github.com/mrveiss/AutoBot-AI/pull/4879))

- *(agent)* Add unit tests for first_turn_note injection in agent loop (#4563)

- *(a2a)* Assert _save() calls expire on _KEY_TASKS with correct TTL (#4649)

- *(a2a)* Add coverage for _event_generator task-expiry and reader-exception paths (#4650) (#4832) ([#4832](https://github.com/mrveiss/AutoBot-AI/pull/4832))

- *(agents)* Add unit tests for slack_hook.py lazy init and async methods (#4535) (#4809) ([#4809](https://github.com/mrveiss/AutoBot-AI/pull/4809))

- *(a2a)* Add SSE stream endpoint tests for critical _event_generator paths (#4627) (#4640) ([#4640](https://github.com/mrveiss/AutoBot-AI/pull/4640))

- *(a2a)* Assert get_task() slides TTL on all three Redis keys (#4626) (#4639) ([#4639](https://github.com/mrveiss/AutoBot-AI/pull/4639))

- *(a2a)* Add unit tests for publish_event() happy path and failure isolation (#4606) (#4618) ([#4618](https://github.com/mrveiss/AutoBot-AI/pull/4618))

- *(tools)* Add unit tests for Pydantic schema self-correction retry loop (#4522) (#4556) ([#4556](https://github.com/mrveiss/AutoBot-AI/pull/4556))

- *(marketplace)* Add unit tests for catalog API and validate seed data (#4521) (#4555) ([#4555](https://github.com/mrveiss/AutoBot-AI/pull/4555))

- *(execution)* Add unit tests for code_interpreter tool (#4520) (#4549) ([#4549](https://github.com/mrveiss/AutoBot-AI/pull/4549))

- *(prompts)* Add unit tests for YAML-sectioned prompt format (#4519) (#4548) ([#4548](https://github.com/mrveiss/AutoBot-AI/pull/4548))

- *(llm)* Add unit tests for OllamaProvider.chat_completion template path (#4526) (#4547) ([#4547](https://github.com/mrveiss/AutoBot-AI/pull/4547))

- *(doc_indexer)* Add comprehensive DocIndexerService test coverage (#4383) (#4405) ([#4405](https://github.com/mrveiss/AutoBot-AI/pull/4405))

- *(frontend)* Add comprehensive tests for useSvgIcons composable (#4204)

- *(kb)* Add boards API tests and fix Pydantic V1 validator (#3242)

- *(composables)* Add comprehensive unit tests for useKnowledgeBase (#4233)

- *(services)* Add AsyncInitializable tests for DistributedServiceDiscovery (#3947) (#4189) ([#4189](https://github.com/mrveiss/AutoBot-AI/pull/4189))

- *(llm)* Add tests for vLLM model name analytics recording (#3943)

- Replace asyncio.get_event_loop() with asyncio.run() (#3605) ([#3639](https://github.com/mrveiss/AutoBot-AI/pull/3639))

- Add unit tests for drift_checker.py (#3428) (#3574) ([#3574](https://github.com/mrveiss/AutoBot-AI/pull/3574))

- *(slm)* Fix code_source_test.py collection — add python-multipart stub (#3525) (#3532) ([#3532](https://github.com/mrveiss/AutoBot-AI/pull/3532))

- *(slm)* Add conftest.py so api/nodes_execution_test.py collects in dev (#3499) (#3511) ([#3511](https://github.com/mrveiss/AutoBot-AI/pull/3511))

- *(slm)* Add models.database to sys.modules stub in _ensure_local_node tests (#3479) (#3485) ([#3485](https://github.com/mrveiss/AutoBot-AI/pull/3485))

- *(frontend)* Add automated test coverage for file upload components (#3376) (#3456) ([#3456](https://github.com/mrveiss/AutoBot-AI/pull/3456))

- *(security)* Add coverage for domain_security wildcard-to-regex (#3217) (#3250) ([#3250](https://github.com/mrveiss/AutoBot-AI/pull/3250))

- *(autoresearch)* Add runner, routes, and ChromaDB indexing tests (#2637) (#3075) ([#3075](https://github.com/mrveiss/AutoBot-AI/pull/3075))

- Add edge case tests for flash attention and token optimizer (#2576) ([#2592](https://github.com/mrveiss/AutoBot-AI/pull/2592))


### WIP

- Preserve work from issue-3294

- Preserve work from issue-3291 (#4241) ([#4241](https://github.com/mrveiss/AutoBot-AI/pull/4241))

- Preserve work from issue-3290 (#4240) ([#4240](https://github.com/mrveiss/AutoBot-AI/pull/4240))

- Preserve work from issue-3281 (#4239) ([#4239](https://github.com/mrveiss/AutoBot-AI/pull/4239))

- Preserve work from issue-4095

- Preserve work from issue-4094


### A11y

- *(ui)* Fix ARIA roles, touch targets, and keyboard access in 6 UI components (#4806) (#5584) ([#5584](https://github.com/mrveiss/AutoBot-AI/pull/5584))

- *(ChatSidebar)* Remove duplicate chatHistory label from mobile header (#5456) (#5549) ([#5549](https://github.com/mrveiss/AutoBot-AI/pull/5549))

- *(dialogs)* Add focus trap + escape + restore to 8 modal dialogs (#5371) (#5390) ([#5390](https://github.com/mrveiss/AutoBot-AI/pull/5390))


### Arch

- *(chat)* Phase 4 observability and rollout gate (MVA-165 / GH#7590) ([#7701](https://github.com/mrveiss/AutoBot-AI/pull/7701))

- *(frontend)* Phase 3 chat store consolidation — SSOT enforcement (#7573) ([#7690](https://github.com/mrveiss/AutoBot-AI/pull/7690))

- *(chat)* Phase 2 backend persistence consolidation (MVA-161) ([#7652](https://github.com/mrveiss/AutoBot-AI/pull/7652))

- *(chat)* Phase 2 backend persistence consolidation (#7572)

- *(mcp)* Add process/container isolation for MCP tool bridges (#4089) ([#4089](https://github.com/mrveiss/AutoBot-AI/pull/4089))

- *(orchestration)* Unified graph model for DAG executor and LangGraph (#3228) (#3836) ([#3836](https://github.com/mrveiss/AutoBot-AI/pull/3836))

- *(knowledge)* Replace Redis adjacency list with queryable property graph (#3230) (#3844) ([#3844](https://github.com/mrveiss/AutoBot-AI/pull/3844))


### Audit

- *(ansible)* Standardize become: yes→true across all playbooks (#7454) (#7782) ([#7782](https://github.com/mrveiss/AutoBot-AI/pull/7782))


### Batch

- *(L)* Code-analysis consolidation + LLC interfaces + gateway + audit #6757 #8261 #8268 #8290 #8312 ([#8378](https://github.com/mrveiss/AutoBot-AI/pull/8378))


### Benchmark

- *(belief-state)* A/B measurement — 3/5 tasks ≥10% token reduction (MVA-1408) ([#8874](https://github.com/mrveiss/AutoBot-AI/pull/8874))


### Bug

- *(llc)* Skip LivenessMonitor DB checks in single_user mode (#9089) (#9145) ([#9145](https://github.com/mrveiss/AutoBot-AI/pull/9145))

- *(knowledge/base)* Guard __del__ against unset self.initialized (#5357) (#5360) ([#5360](https://github.com/mrveiss/AutoBot-AI/pull/5360))

- *(backend)* Fix ChatHistoryManager create_task race with explicit initialize() (#3797) (#3815) ([#3815](https://github.com/mrveiss/AutoBot-AI/pull/3815))

- *(memory)* Validate compression_threshold <= context_window_tokens at load (#3811) (#3855) ([#3855](https://github.com/mrveiss/AutoBot-AI/pull/3855))


### Build

- *(format)* Add scripts/format.sh wrapper + make targets — pin py3.12 settings (#7249) (#7262) ([#7262](https://github.com/mrveiss/AutoBot-AI/pull/7262))


### Cleanup

- *(backend)* Remove stale run_autobot from process detection keywords (#2564)

- *(backend)* Remove placeholder Issue #XXX comment (#2481)

- *(devops)* Remove orphaned init-databases.sh (#2491)


### Config

- Mark remaining 71 edge-case os.getenv calls with ssot-config-exempt (closes GH#7743) (#7870) ([#7870](https://github.com/mrveiss/AutoBot-AI/pull/7870))


### Debug

- *(devops)* Trace slm_host pipe lookup and whoami in VNC role

- *(devops)* Extended VNC slm_api_url debug with hostvars chain

- *(devops)* Add temporary debug output for VNC slm_api_url resolution


### Deprecate

- *(orchestrator)* Add DeprecationWarning to process_user_request (closes GH#7423) (#7752) ([#7752](https://github.com/mrveiss/AutoBot-AI/pull/7752))


### Deps

- Llama-index 0.13→0.14 migration (#2642) (#4206) ([#4206](https://github.com/mrveiss/AutoBot-AI/pull/4206))

- *(frontend)* Upgrade SLM frontend to eslint 10 with unified typescript-eslint (#2639) (#3132) ([#3132](https://github.com/mrveiss/AutoBot-AI/pull/3132))

- *(backend)* Standardize numpy 2.x pins and upgrade opencv (#1971)

- *(frontend)* Unblock TypeScript 6 upgrade by removing unused vitest-mock-extended (#2640)

- *(python)* Upgrade infrastructure & worker requirements (#2558) ([#2620](https://github.com/mrveiss/AutoBot-AI/pull/2620))

- *(python)* Upgrade backend requirements to latest compatible (#2557) ([#2610](https://github.com/mrveiss/AutoBot-AI/pull/2610))

- *(slm-frontend)* Upgrade npm packages to latest compatible (#2561)

- *(infra)* Align Ansible node OpenTelemetry pins with main requirements (#2562)

- *(frontend)* Upgrade npm packages to latest including major versions (#2559)


### Discovery

- *(backend)* Implement missing BackupScheduler (backup/scheduler.py) (#7912) (#8091) ([#8091](https://github.com/mrveiss/AutoBot-AI/pull/8091))

- *(i18n)* Add CI check for en.json→locale completeness (#5829) (#5840) ([#5840](https://github.com/mrveiss/AutoBot-AI/pull/5840))


### Enhance

- *(verify_knowledge_consistency)* Add --deep flag for vector-shape chunker consistency check (#5440) (#5550) ([#5550](https://github.com/mrveiss/AutoBot-AI/pull/5550))


### Enhancement

- *(ci)* Extend check-pre-commit-hook-pr.sh for Python validators; retire 2 per-hook wrappers (closes #6991) (#7852) ([#7852](https://github.com/mrveiss/AutoBot-AI/pull/7852))

- *(llm)* Expose per-request LLM cost via x-llm-cost header (#6589) (#7543) ([#7543](https://github.com/mrveiss/AutoBot-AI/pull/7543))

- *(llm)* Reserve auto model names for tiered LLM routing (#6592) (#7528) ([#7528](https://github.com/mrveiss/AutoBot-AI/pull/7528))


### Governance

- Delegate batch-implement wiring check to canonical script (#7894) (#8096) ([#8096](https://github.com/mrveiss/AutoBot-AI/pull/8096))


### Hotfix

- *(migrations)* Fix 4 duplicate LLC Alembic revision IDs + deferred FK chain ([#8466](https://github.com/mrveiss/AutoBot-AI/pull/8466))

- *(migrations)* Fix 4 duplicate LLC Alembic revision IDs (20260523_022) (#8464) ([#8464](https://github.com/mrveiss/AutoBot-AI/pull/8464))


### I18n

- *(frontend)* Backfill ui.offlineBanner.* across 10 locales (#6988) (#7874) ([#7874](https://github.com/mrveiss/AutoBot-AI/pull/7874))

- *(frontend/ui)* Wire OfflineBanner through vue-i18n (#6878) (#6953) ([#6953](https://github.com/mrveiss/AutoBot-AI/pull/6953))

- *(nav)* Add translated nav.about key to all non-English locales (#6366) (#6377) ([#6377](https://github.com/mrveiss/AutoBot-AI/pull/6377))

- Add missing en.json fallback keys to 10 locale files (#5004) (#5820) ([#5820](https://github.com/mrveiss/AutoBot-AI/pull/5820))

- *(analytics)* Add hardcodes keys to 10 non-English locales (#5004 partial) (#5383) ([#5383](https://github.com/mrveiss/AutoBot-AI/pull/5383))


### Impl

- *(frontend/css)* Refactor scoped styles to canonical theming (#7880) (#8274) ([#8274](https://github.com/mrveiss/AutoBot-AI/pull/8274))

- *(frontend)* Promote runtimeHttpProto to top-level export (#6809) ([#7913](https://github.com/mrveiss/AutoBot-AI/pull/7913))


### Improvement

- *(ci)* Add disk-space threshold guard and composite action for smoke-test cleanup (GH#8914) ([#8916](https://github.com/mrveiss/AutoBot-AI/pull/8916))


### Infra

- *(gitignore)* Exclude .claude/scheduled_tasks.lock (#6980) (#7846) ([#7846](https://github.com/mrveiss/AutoBot-AI/pull/7846))

- *(tests)* Create tests/helpers/ directory as shared-fixture infrastructure (#5437) (#5460) ([#5460](https://github.com/mrveiss/AutoBot-AI/pull/5460))


### Lint

- Add pre-commit hook for i18n plural third arg (#7155) (#7875) ([#7875](https://github.com/mrveiss/AutoBot-AI/pull/7875))

- *(frontend)* Add vue/no-undef-components error rule to catch missing imports (#6236) (#6278) ([#6278](https://github.com/mrveiss/AutoBot-AI/pull/6278))


### Merge

- Rate limiting integration (#4162)

- Resolve conflicts from Dev_new_gui optimization merge

- Combine orchestrator and scroll fixes from temp-3949 ([#3975](https://github.com/mrveiss/AutoBot-AI/pull/3975))

- Resolve conflict with Dev_new_gui, keep upgraded package versions


### Migrate

- *(composables)* UseWorkflowBuilder/usePatternAnalysis/useVoiceProfiles/useWorkflowTemplates to useLoadingState (#5942) (#5952) ([#5952](https://github.com/mrveiss/AutoBot-AI/pull/5952))

- *(composables)* UseLoadingState sweep batch 3 — 12 composables (#5921) ([#5929](https://github.com/mrveiss/AutoBot-AI/pull/5929))

- *(composables)* UseVncControls/useVncConnection/usePlugins to useLoadingState; fix doc (#5909 #5910) (#5915) ([#5915](https://github.com/mrveiss/AutoBot-AI/pull/5915))


### Monitor

- *(ci)* Alert on stale self-hosted runner state (closes #7045) (#7787) ([#7787](https://github.com/mrveiss/AutoBot-AI/pull/7787))


### Observability

- *(backend)* Aggregate feature-router load results across workers via Redis (#6808) (#7872) ([#7872](https://github.com/mrveiss/AutoBot-AI/pull/7872))

- *(health)* Complete #6919 — user_agent label + INFO log + tests + docs (#7812) ([#7812](https://github.com/mrveiss/AutoBot-AI/pull/7812))

- *(health)* Add logging/metering to SunsetLegacyHealthMiddleware (#6919) (#7807) ([#7807](https://github.com/mrveiss/AutoBot-AI/pull/7807))


### Ops

- *(chromadb)* Standalone service — wire backend dependency and fix health check endpoints (MVA-1445) ([#8894](https://github.com/mrveiss/AutoBot-AI/pull/8894))


### Preserve

- *(#7007)* Refactor(backend): migrate log_forwarder to optional_import; mark single-symbol sites deferred (#7007) (#7971) ([#7971](https://github.com/mrveiss/AutoBot-AI/pull/7971))


### Refact

- *(docker)* Extract shared nginx config to nginx-common.conf + nginx-locations.conf (#6252) (#6274) ([#6274](https://github.com/mrveiss/AutoBot-AI/pull/6274))

- *(composables)* Wave 5 — migrate 12 composables from fetchWithAuth to useFetchEndpoint/apiClient (#6224) (#6250) ([#6250](https://github.com/mrveiss/AutoBot-AI/pull/6250))

- *(orchestration)* Consolidate duplicate AgentCapability enum — enhanced_orchestration imports from orchestration.types (#6192) (#6214) ([#6214](https://github.com/mrveiss/AutoBot-AI/pull/6214))

- *(components)* Extract inline fetching from InviteUserDialog to useCollaborationInvites (#6091) (#6206) ([#6206](https://github.com/mrveiss/AutoBot-AI/pull/6206))

- *(composables)* Create useCollaborationInvite and migrate InviteUserDialog fetchWithAuth (#6091) (#6204) ([#6204](https://github.com/mrveiss/AutoBot-AI/pull/6204))

- *(composables)* Create useThreatIntelligence and migrate ThreatIntelligenceDashboard fetchWithAuth (#6090) (#6203) ([#6203](https://github.com/mrveiss/AutoBot-AI/pull/6203))

- *(components)* Extract fetchWithAuth from HostSelector (terminal/) to useHostSelection (#6089) (#6202) ([#6202](https://github.com/mrveiss/AutoBot-AI/pull/6202))

- *(composables)* Migrate CommandPermissionDialog fetchWithAuth to useCommandApproval (#6088) (#6201) ([#6201](https://github.com/mrveiss/AutoBot-AI/pull/6201))

- *(composables)* Migrate HostSelector (ui/) fetchWithAuth to useHostSelection (#6087) (#6200) ([#6200](https://github.com/mrveiss/AutoBot-AI/pull/6200))

- *(composables)* Create useKnowledgeMaintenance and migrate KnowledgeMaintenance fetchWithAuth (#6053) (#6199) ([#6199](https://github.com/mrveiss/AutoBot-AI/pull/6199))

- *(knowledge)* Extract inline fetching from KnowledgeStats to useKnowledgeStats (#6052) (#6198) ([#6198](https://github.com/mrveiss/AutoBot-AI/pull/6198))

- *(knowledge)* Extract inline fetching from CleanupStatistics to useKnowledgeCleanupStats (#6051) (#6190) ([#6190](https://github.com/mrveiss/AutoBot-AI/pull/6190))

- *(knowledge)* Extract inline fetching from GraphRAGQuery to useKnowledgeGraphRAG (#6050) (#6189) ([#6189](https://github.com/mrveiss/AutoBot-AI/pull/6189))

- *(knowledge)* Extract inline fetching from MemoryOrphanManager to useKnowledgeOrphans (#6048) (#6188) ([#6188](https://github.com/mrveiss/AutoBot-AI/pull/6188))

- *(knowledge)* Extract inline fetching from EntityGraphManager to useKnowledgeEntityGraph (#6046) (#6187) ([#6187](https://github.com/mrveiss/AutoBot-AI/pull/6187))

- *(knowledge)* Extract inline fetching from KnowledgeSystemDocs to useKnowledgeSystemDocs (#6045) (#6186) ([#6186](https://github.com/mrveiss/AutoBot-AI/pull/6186))

- *(composables)* Migrate KnowledgeCategories fetchWithAuth to useKnowledgeCategories (#6049) (#6185) ([#6185](https://github.com/mrveiss/AutoBot-AI/pull/6185))

- *(knowledge)* Extract inline fetching from SessionOrphanManager to useKnowledgeOrphans (#6047) (#6184) ([#6184](https://github.com/mrveiss/AutoBot-AI/pull/6184))

- *(knowledge)* Extract inline fetching from CategoryEditModal to useKnowledgeCategories (#6044) (#6183) ([#6183](https://github.com/mrveiss/AutoBot-AI/pull/6183))

- *(knowledge)* Extract inline fetching from DeduplicationManager to useKnowledgeDeduplication (#6043) (#6182) ([#6182](https://github.com/mrveiss/AutoBot-AI/pull/6182))

- *(knowledge)* Extract inline fetching from FailedVectorizationsManager to useKnowledgeVectorization (#6041) (#6181) ([#6181](https://github.com/mrveiss/AutoBot-AI/pull/6181))

- *(knowledge)* Extract inline fetching from KnowledgeGraph to useKnowledgeGraph (#6040) (#6180) ([#6180](https://github.com/mrveiss/AutoBot-AI/pull/6180))

- *(knowledge)* Extract inline fetching from KnowledgePromptEditor to useKnowledgePrompt (#6039) (#6179) ([#6179](https://github.com/mrveiss/AutoBot-AI/pull/6179))

- *(knowledge)* Extract inline fetching from BackupManager to useKnowledgeBackup (#6038) (#6178) ([#6178](https://github.com/mrveiss/AutoBot-AI/pull/6178))

- *(composables)* Extract fetchWithAuth from SystemArchitectureDiagram to useSystemArchitectureData (#6085) (#6177) ([#6177](https://github.com/mrveiss/AutoBot-AI/pull/6177))

- *(composables)* Extract fetchWithAuth from SecretsManager to useSecretsAuditApi (#6081) (#6176) ([#6176](https://github.com/mrveiss/AutoBot-AI/pull/6176))

- *(composables)* Extract fetchWithAuth from AgentActivityVisualization to useAgentActivityData (#6079) (#6175) ([#6175](https://github.com/mrveiss/AutoBot-AI/pull/6175))

- *(knowledge)* Extract inline fetching from KnowledgeBrowser to useKnowledgeBrowser (#6037) (#6174) ([#6174](https://github.com/mrveiss/AutoBot-AI/pull/6174))

- *(components)* Extract inline fetching from FileBrowser to useFileBrowser (#6075) (#6173) ([#6173](https://github.com/mrveiss/AutoBot-AI/pull/6173))

- *(chat)* Extract fetchWithAuth from TranslationShortcutPanel to useChatTranslation (#6077) (#6170) ([#6170](https://github.com/mrveiss/AutoBot-AI/pull/6170))

- *(components)* Extract fetchWithAuth from DocumentationSearchSidebar to useDocumentationSearch (#6076) (#6169) ([#6169](https://github.com/mrveiss/AutoBot-AI/pull/6169))

- *(composables)* Migrate useBackgroundTask clearStuckTasks to ApiClient; document postAnalyze + poll exemptions (#6033) (#6168) ([#6168](https://github.com/mrveiss/AutoBot-AI/pull/6168))

- *(composables)* Migrate useCommandApproval fetchWithAuth POST to ApiClient; exempt polling GET (#6032) (#6167) ([#6167](https://github.com/mrveiss/AutoBot-AI/pull/6167))

- *(components)* Extract fetchWithAuth from PopoutChromiumBrowser to useBrowserSessionData (#6074) (#6165) ([#6165](https://github.com/mrveiss/AutoBot-AI/pull/6165))

- *(composables)* Extract fetchWithAuth from CodeEvolutionTimeline to composable (#6072) (#6164) ([#6164](https://github.com/mrveiss/AutoBot-AI/pull/6164))

- *(composables)* Extract fetchWithAuth from ConversationFlowDashboard to useConversationFlowData (#6071) (#6163) ([#6163](https://github.com/mrveiss/AutoBot-AI/pull/6163))

- *(composables)* Migrate ShareSourceModal fetchWithAuth to useSourceRegistry (#6070) (#6161) ([#6161](https://github.com/mrveiss/AutoBot-AI/pull/6161))

- *(composables)* Migrate useWorkflowTemplates fetchWithAuth to ApiClient (#6029) (#6159) ([#6159](https://github.com/mrveiss/AutoBot-AI/pull/6159))

- *(composables)* Migrate useToolApproval fetchWithAuth POST to ApiClient (#6028) (#6158) ([#6158](https://github.com/mrveiss/AutoBot-AI/pull/6158))

- *(composables)* Extract fetchWithAuth from CodebaseAnalytics to composable (#6068) (#6157) ([#6157](https://github.com/mrveiss/AutoBot-AI/pull/6157))

- *(composables)* Create useSourceRegistry and migrate AddSourceModal fetchWithAuth (#6069) (#6156) ([#6156](https://github.com/mrveiss/AutoBot-AI/pull/6156))

- *(terminal)* Extract fetchWithAuth from Terminal to useTerminalStore (#6080) (#6155) ([#6155](https://github.com/mrveiss/AutoBot-AI/pull/6155))

- *(chat)* Extract fetchWithAuth from ChatMessages to chat composables (#6078) (#6154) ([#6154](https://github.com/mrveiss/AutoBot-AI/pull/6154))

- *(knowledge)* Extract fetchWithAuth from EntityExtractor to useKnowledgeEntities (#6054) (#6153) ([#6153](https://github.com/mrveiss/AutoBot-AI/pull/6153))

- *(composables)* Extract fetchWithAuth from LogPatternDashboard to useLogPatternData (#6064) (#6151) ([#6151](https://github.com/mrveiss/AutoBot-AI/pull/6151))

- *(composables)* Extract fetchWithAuth from CodeGenerationDashboard to useCodeGenerationData (#6060) (#6150) ([#6150](https://github.com/mrveiss/AutoBot-AI/pull/6150))

- *(composables)* Extract fetchWithAuth from LLMPatternDashboard to useLLMPatternData (#6059) (#6149) ([#6149](https://github.com/mrveiss/AutoBot-AI/pull/6149))

- *(composables)* Extract fetchWithAuth from TechnicalDebtDashboard to useTechnicalDebtData (#6058) (#6147) ([#6147](https://github.com/mrveiss/AutoBot-AI/pull/6147))

- *(composables)* Extract fetchWithAuth from SourceManager to useAnalyticsSourceManagement (#6057) (#6146) ([#6146](https://github.com/mrveiss/AutoBot-AI/pull/6146))

- *(composables)* Extract fetchWithAuth from CodeQualityDashboard to useCodeQualityData (#6055) (#6145) ([#6145](https://github.com/mrveiss/AutoBot-AI/pull/6145))

- *(composables)* Migrate useAnalyticsDebug fetchWithAuth to ApiClient (#6027) (#6142) ([#6142](https://github.com/mrveiss/AutoBot-AI/pull/6142))

- *(composables)* Migrate useBugPrediction loadCachedBugPrediction fetchWithAuth to ApiClient (#6026) (#6141) ([#6141](https://github.com/mrveiss/AutoBot-AI/pull/6141))

- *(composables)* Migrate usePatternAnalysis GET/DELETE/POST helpers to ApiClient (#6025) (#6140) ([#6140](https://github.com/mrveiss/AutoBot-AI/pull/6140))

- *(composables)* Migrate useVoiceProfiles fetchWithAuth to useFetchEndpoint + ApiClient (#6023) (#6133) ([#6133](https://github.com/mrveiss/AutoBot-AI/pull/6133))

- *(composables)* Migrate useEnvironmentAnalysis fetchWithAuth GET to useFetchEndpoint (#6022) (#6132) ([#6132](https://github.com/mrveiss/AutoBot-AI/pull/6132))

- *(visualizations)* Extract ResourceHeatmap inline fetching to useResourceMetrics (#6086) (#6120) ([#6120](https://github.com/mrveiss/AutoBot-AI/pull/6120))

- *(research)* Extract CaptchaNotification inline fetching to useCaptchaStatus (#6082) (#6119) ([#6119](https://github.com/mrveiss/AutoBot-AI/pull/6119))

- *(manpage)* Migrate ManPageManager from useAsyncOperation to useLoadingState (#6110) (#6114) ([#6114](https://github.com/mrveiss/AutoBot-AI/pull/6114))

- *(api)* Add named Pydantic schemas for 34 misc endpoints (#5991) (#6107) ([#6107](https://github.com/mrveiss/AutoBot-AI/pull/6107))

- *(ui)* Refactor UnifiedLoadingView to props-driven, delete useUnifiedLoading singleton (#6021) (#6108) ([#6108](https://github.com/mrveiss/AutoBot-AI/pull/6108))

- *(knowledge)* Migrate KnowledgeBrowser from useAsyncOperation to useLoadingState (#6018) (#6109) ([#6109](https://github.com/mrveiss/AutoBot-AI/pull/6109))

- *(api)* Add named Pydantic schemas for 77 code/integration endpoints (#5987) (#6105) ([#6105](https://github.com/mrveiss/AutoBot-AI/pull/6105))

- *(api)* Add named Pydantic schemas for 51 workflow endpoints (#5989) (#6106) ([#6106](https://github.com/mrveiss/AutoBot-AI/pull/6106))

- *(api)* Add named Pydantic schemas to system management endpoints (#5990) (#6104) ([#6104](https://github.com/mrveiss/AutoBot-AI/pull/6104))

- *(knowledge)* Migrate FailedVectorizationsManager from useAsyncOperation to useLoadingState (#6019) (#6103) ([#6103](https://github.com/mrveiss/AutoBot-AI/pull/6103))

- *(api)* Add named Pydantic schemas for 37 knowledge endpoints (#5984) (#6102) ([#6102](https://github.com/mrveiss/AutoBot-AI/pull/6102))

- *(api)* Add named Pydantic schemas for 42 analytics endpoints (#5983) (#6101) ([#6101](https://github.com/mrveiss/AutoBot-AI/pull/6101))

- *(api)* Add named schemas for 19 agent/auth/chat response_model=None endpoints (#5985) (#6100) ([#6100](https://github.com/mrveiss/AutoBot-AI/pull/6100))

- *(api)* Add named Pydantic schemas for 42 analytics endpoints (#5983) (#6099) ([#6099](https://github.com/mrveiss/AutoBot-AI/pull/6099))

- *(backend)* Replace 20+ manual module-level singletons with lazy_singleton (#5948) (#6098) ([#6098](https://github.com/mrveiss/AutoBot-AI/pull/6098))

- *(components)* Migrate remaining 3 components to useLoadingState (#5949) (#6097) ([#6097](https://github.com/mrveiss/AutoBot-AI/pull/6097))

- *(knowledge)* Migrate SystemKnowledgeManager from useAsyncOperation to useLoadingState (#6017) (#6096) ([#6096](https://github.com/mrveiss/AutoBot-AI/pull/6096))

- *(desktop)* Migrate DesktopInterface from useAsyncOperation to useLoadingState (#6016) (#6095) ([#6095](https://github.com/mrveiss/AutoBot-AI/pull/6095))

- *(ui)* Migrate CommandPermissionDialog from useAsyncOperation to useLoadingState (#6015) (#6094) ([#6094](https://github.com/mrveiss/AutoBot-AI/pull/6094))

- *(frontend)* Migrate LoginForm + KnowledgeGraph + KnowledgeSystemDocs to useLoadingState (#5949) (#6084) ([#6084](https://github.com/mrveiss/AutoBot-AI/pull/6084))

- *(api)* Add named schemas for 12 agent/auth/chat endpoints (#5985) (#6073) ([#6073](https://github.com/mrveiss/AutoBot-AI/pull/6073))

- *(services)* Migrate 9 service files from hand-rolled _get_redis() to AsyncRedisClientMixin (#5946) (#6066) ([#6066](https://github.com/mrveiss/AutoBot-AI/pull/6066))

- *(services)* Migrate 9 service files from hand-rolled _get_redis() to AsyncRedisClientMixin (#5946) (#6061) ([#6061](https://github.com/mrveiss/AutoBot-AI/pull/6061))

- *(api)* Merge terminal_models.py into schemas_terminal.py (#5996) (#6013) ([#6013](https://github.com/mrveiss/AutoBot-AI/pull/6013))

- *(api)* Merge analytics_models.py into schemas_analytics.py (#5996) (#6012) ([#6012](https://github.com/mrveiss/AutoBot-AI/pull/6012))

- *(api)* Merge knowledge_models.py into schemas_knowledge.py (#5996) (#6011) ([#6011](https://github.com/mrveiss/AutoBot-AI/pull/6011))

- *(api)* Merge analytics_models.py into schemas_analytics.py (#5996) (#6010) ([#6010](https://github.com/mrveiss/AutoBot-AI/pull/6010))

- *(api)* Merge terminal_models.py into schemas_terminal.py (#5996) (#6009) ([#6009](https://github.com/mrveiss/AutoBot-AI/pull/6009))

- *(api)* Merge analytics_models.py into schemas_analytics.py (#5996) (#6008) ([#6008](https://github.com/mrveiss/AutoBot-AI/pull/6008))

- *(api)* Add named Pydantic schemas to 61 response_model=None endpoints (#5960) (#6007) ([#6007](https://github.com/mrveiss/AutoBot-AI/pull/6007))

- *(config)* Consolidate LMSTUDIO_HOST into ssot_config.py, replace 3 scattered os.getenv calls (#6000) (#6005) ([#6005](https://github.com/mrveiss/AutoBot-AI/pull/6005))

- *(config)* Move VNC_PASSWD_FILE into PathConfig.vnc_passwd_file in ssot_config.py (#6001) (#6004) ([#6004](https://github.com/mrveiss/AutoBot-AI/pull/6004))

- *(services)* Extract 5.0s eviction poll deadline to _EVICTION_POLL_SECONDS constant (#6002) (#6003) ([#6003](https://github.com/mrveiss/AutoBot-AI/pull/6003))

- *(api)* Move GoalRequest/GoalResponse/HealthResponse from intelligent_agent.py to schemas_agent.py (#5977) (#5992) ([#5992](https://github.com/mrveiss/AutoBot-AI/pull/5992))

- *(api)* Move GoalRequest/GoalResponse/HealthResponse from intelligent_agent.py to schemas_agent.py (#5977) (#5988) ([#5988](https://github.com/mrveiss/AutoBot-AI/pull/5988))

- *(api)* Move GoalRequest/GoalResponse/HealthResponse from intelligent_agent.py to schemas_agent.py (#5977) (#5982) ([#5982](https://github.com/mrveiss/AutoBot-AI/pull/5982))

- *(api)* Resolve schema name collisions from #5799 domain split (#5935 #5936 #5937) (#5951) ([#5951](https://github.com/mrveiss/AutoBot-AI/pull/5951))

- *(composables)* Migrate useEnvironmentAnalysis to useLoadingState (#5923) (#5939) ([#5939](https://github.com/mrveiss/AutoBot-AI/pull/5939))

- *(composables)* Replace axios with ApiClient + useLoadingState in useEvolution (#5922) (#5938) ([#5938](https://github.com/mrveiss/AutoBot-AI/pull/5938))

- *(api)* Add proper named response schemas for 52 reverted endpoints (#5912) ([#5930](https://github.com/mrveiss/AutoBot-AI/pull/5930))

- *(api)* Split schemas_common.py into 7 per-domain modules (#5799) ([#5916](https://github.com/mrveiss/AutoBot-AI/pull/5916))

- *(api)* Migrate 16 schemas to SuccessMessageResponse base (#5905) (#5911) ([#5911](https://github.com/mrveiss/AutoBot-AI/pull/5911))

- *(api)* Add SuccessMessageResponse and SuccessDataResponse base models (#5844) (#5876) ([#5876](https://github.com/mrveiss/AutoBot-AI/pull/5876))

- *(api)* Remove unused SuccessResponse import from 82 API files (#5846) (#5865) ([#5865](https://github.com/mrveiss/AutoBot-AI/pull/5865))

- *(api)* Add response_model= to all remaining FastAPI endpoints — 100% coverage (#5317) (#5834) ([#5834](https://github.com/mrveiss/AutoBot-AI/pull/5834))


### Sec

- *(deps)* Bump qs past CVE-2026-8723 in mcp-structured-thinking (MVA-1311) ([#8842](https://github.com/mrveiss/AutoBot-AI/pull/8842))

- *(backend)* Block SSRF in ExternalSkillImporter.import_git_repo (MVA-1307) (#8826) ([#8826](https://github.com/mrveiss/AutoBot-AI/pull/8826))

- *(scanning)* Exclude vendored JS bundles from secret scanning (MVA-1306) (#8823) ([#8823](https://github.com/mrveiss/AutoBot-AI/pull/8823))

- Bump langchain >=1.2.24 across all requirements files (PVE-2026-88512) (#8681) ([#8681](https://github.com/mrveiss/AutoBot-AI/pull/8681))

- Enforce aud claim in validate_run_jwt to prevent cross-validator token reuse (MVA-155)

- *(slm)* Refuse SSH connection when no known_hosts file exists (#3469) (#3505) ([#3505](https://github.com/mrveiss/AutoBot-AI/pull/3505))


### Security

- *(transcriber)* Fix arbitrary file read vulnerability (#9214) ([#9306](https://github.com/mrveiss/AutoBot-AI/pull/9306))

- *(transcriber)* Sanitize error responses to prevent information leakage (#9216) (#9311) ([#9311](https://github.com/mrveiss/AutoBot-AI/pull/9311))

- *(external_importer)* Fix SSRF vulnerability (MVA-2584) (#9313) ([#9313](https://github.com/mrveiss/AutoBot-AI/pull/9313))

- *(transcriber)* Add user ownership checks to prevent IDOR (#9215) (#9307) ([#9307](https://github.com/mrveiss/AutoBot-AI/pull/9307))

- *(embed)* Add per-IP rate limiting with spoofing protection (#9180) ([#9180](https://github.com/mrveiss/AutoBot-AI/pull/9180))

- *(auth+embed)* Rate-limit shared link access + embed origin allowlist (#9127 #9117) (#9140) ([#9140](https://github.com/mrveiss/AutoBot-AI/pull/9140))

- *(audit)* Fix emit() outside try-block in set_user_bundle (GH#8982) (#9082) ([#9082](https://github.com/mrveiss/AutoBot-AI/pull/9082))

- *(execution)* Add ownership check on snapshot restore/delete (GH#8968) (#9080) ([#9080](https://github.com/mrveiss/AutoBot-AI/pull/9080))

- *(a2a)* Default-deny callers without X-A2A-Agent-Id header ([#8783](https://github.com/mrveiss/AutoBot-AI/pull/8783))

- Bump vulnerable dependencies for GH#8323-#8326 CVEs (MVA-707) ([#8335](https://github.com/mrveiss/AutoBot-AI/pull/8335))

- *(ci)* Add semgrep custom rules + cosign image signing (MVA-207) (#7708) ([#7708](https://github.com/mrveiss/AutoBot-AI/pull/7708))

- *(ci)* Add semgrep custom rules + cosign image signing (MVA-207)

- *(onboarding)* Auth-gate /presets, /doctor, /apply (#6568) ([#7527](https://github.com/mrveiss/AutoBot-AI/pull/7527))

- *(P1)* /v1/chat/completions rate limit via Redis sorted-set (#6588) (#7263) ([#7263](https://github.com/mrveiss/AutoBot-AI/pull/7263))

- *(P1)* Fix 2 regressions + 2 test rots in EnhancedSecurityLayer (#7161) (#7232) ([#7232](https://github.com/mrveiss/AutoBot-AI/pull/7232))

- *(P1)* Remove committed Fernet encryption key from repo (#7088) ([#7108](https://github.com/mrveiss/AutoBot-AI/pull/7108))

- *(deps)* Bump uuid 8/9/11 → 14.0.0 — fix buffer bounds check CVE (#5665)

- *(codeql)* Fix JS/TS frontend CodeQL alerts (#5697) (#5706) ([#5706](https://github.com/mrveiss/AutoBot-AI/pull/5706))

- *(codeql)* Fix py/incomplete-url-substring-sanitization in 2 test files (#5696) (#5703) ([#5703](https://github.com/mrveiss/AutoBot-AI/pull/5703))

- *(codeql)* Fix bad-tag-filter, polynomial-redos, full-ssrf (#5695) (#5702) ([#5702](https://github.com/mrveiss/AutoBot-AI/pull/5702))

- *(codeql)* Fix ldap-injection, command-injection, weak-hashing (#5694) (#5701) ([#5701](https://github.com/mrveiss/AutoBot-AI/pull/5701))

- *(codeql)* Fix py/clear-text-logging-sensitive-data in 8 locations (#5693) (#5700) ([#5700](https://github.com/mrveiss/AutoBot-AI/pull/5700))

- *(codeql)* Fix py/stack-trace-exposure in 14 remaining locations (#5692) (#5699) ([#5699](https://github.com/mrveiss/AutoBot-AI/pull/5699))

- *(codeql)* Suppress py/path-injection false positives in 9 files (#5691) (#5698) ([#5698](https://github.com/mrveiss/AutoBot-AI/pull/5698))

- Convert # codeql-suppress to # codeql[...] across 20 files (#5675) ([#5688](https://github.com/mrveiss/AutoBot-AI/pull/5688))

- Safe_http_detail helper + fix all str(exc) leaks in HTTP responses (#5680 #5676 #5678 #5679) ([#5687](https://github.com/mrveiss/AutoBot-AI/pull/5687))

- Resolve all 22 CodeQL code-scanning alerts ([#5672](https://github.com/mrveiss/AutoBot-AI/pull/5672))

- *(deps)* Bump vulnerable dependencies to fix all open Dependabot alerts (#5656) (#5663) ([#5663](https://github.com/mrveiss/AutoBot-AI/pull/5663))

- *(codeql)* Fix SSRF, command injection, LDAP injection, ReDoS, clear-text storage (#1733) (#2552) ([#2552](https://github.com/mrveiss/AutoBot-AI/pull/2552))

- *(docker)* Fix TLS ciphers, add HTTP/2, fix header inheritance (#1984) (#2536) ([#2536](https://github.com/mrveiss/AutoBot-AI/pull/2536))

- *(docker)* Add filesystem hardening — read_only, cap_drop, tmpfs (#1983) (#2537) ([#2537](https://github.com/mrveiss/AutoBot-AI/pull/2537))

- *(vnc)* Fix insecure docs example + disable AlwaysShared (#1970) (#2522) ([#2522](https://github.com/mrveiss/AutoBot-AI/pull/2522))

- *(deps)* Bump pypdf >=6.8.0 → >=6.9.1 (#1972) (#2529) ([#2529](https://github.com/mrveiss/AutoBot-AI/pull/2529))

- *(infra)* Redact sensitive data from log output (#2348) (#2531) ([#2531](https://github.com/mrveiss/AutoBot-AI/pull/2531))

- *(neural-mesh)* Fix QueryDecomposer prompt injection + error handling (#2169) (#2528) ([#2528](https://github.com/mrveiss/AutoBot-AI/pull/2528))


### Tech-debt

- *(api)* Type DataResponse generics — Batch E long-tail (#6509) (#8376) ([#8376](https://github.com/mrveiss/AutoBot-AI/pull/8376))

- *(api)* Type bare DataResponse Batch B — LLM, research, security domain (#6509) ([#8347](https://github.com/mrveiss/AutoBot-AI/pull/8347))

- *(api)* Type bare DataResponse Batch A — code-analysis domain (#6509) ([#8346](https://github.com/mrveiss/AutoBot-AI/pull/8346))

- *(api)* Type bare DataResponse — analytics, orchestration, enterprise domain (GH #6509 Batch D) (#8307) ([#8307](https://github.com/mrveiss/AutoBot-AI/pull/8307))

- *(api)* Type bare DataResponse batch C — knowledge/chat-ext/multimodal (#6509c) ([#8299](https://github.com/mrveiss/AutoBot-AI/pull/8299))

- *(backend)* Add module docstrings to 10+ undocumented files (#7457) (#7933) ([#7933](https://github.com/mrveiss/AutoBot-AI/pull/7933))

- *(naming)* Clarify plugin vs extension vs skill terminology with rename (#7426) (#8005) ([#8005](https://github.com/mrveiss/AutoBot-AI/pull/8005))

- *(backend/redis)* Suppress two noqa false-positives in redis scanner (#7439) (#8034) ([#8034](https://github.com/mrveiss/AutoBot-AI/pull/8034))

- *(frontend/css)* Establish canonical theming pattern and tokens (#7453) (#7896) ([#7896](https://github.com/mrveiss/AutoBot-AI/pull/7896))

- *(ansible)* Canonicalize role names to autobot-X form (#7053) (#7877) ([#7877](https://github.com/mrveiss/AutoBot-AI/pull/7877))

- *(naming)* Clarify plugin vs extension vs skill terminology with rename (#7426) (#7869) ([#7869](https://github.com/mrveiss/AutoBot-AI/pull/7869))

- *(architecture)* Enforce import boundaries for extensions/skills/plugins (#7372) (#7868) ([#7868](https://github.com/mrveiss/AutoBot-AI/pull/7868))

- *(backend)* Canonical session_scope + error_handling standardization (GH#7441, GH#7435) (#7748) ([#7748](https://github.com/mrveiss/AutoBot-AI/pull/7748))

- *(backend/redis)* Suppress two noqa false-positives in redis scanner (MVA-199 / GH#7439) ([#7678](https://github.com/mrveiss/AutoBot-AI/pull/7678))

- *(backend/orm)* Canonical skills_session_context — standardize SQLAlchemy lifecycle (GH#7441) (#7677) ([#7677](https://github.com/mrveiss/AutoBot-AI/pull/7677))

- *(helpers)* Add raise_not_found/raise_rate_limit helpers to catalog_http_exceptions (#3548) (#3557) ([#3557](https://github.com/mrveiss/AutoBot-AI/pull/3557))

- *(constants)* Replace asyncio.sleep() magic numbers with TimingConstants (#3549) (#3556) ([#3556](https://github.com/mrveiss/AutoBot-AI/pull/3556))

- *(helpers)* Create RedisCache JSON wrapper (#3547) (#3553) ([#3553](https://github.com/mrveiss/AutoBot-AI/pull/3553))

- *(helpers)* Create TaskResult builders — 2200+ raw dicts (#3545) (#3552) ([#3552](https://github.com/mrveiss/AutoBot-AI/pull/3552))

- *(helpers)* Extract PaginationParams model (#3546) (#3555) ([#3555](https://github.com/mrveiss/AutoBot-AI/pull/3555))


### Tooling

- AUTOBOT_* env-var registry with auto-generated CLAUDE_RULES.md section (#7081) (#7928) ([#7928](https://github.com/mrveiss/AutoBot-AI/pull/7928))

- AUTOBOT_* env-var registry with auto-generated CLAUDE_RULES.md section (#7081) (#7876) ([#7876](https://github.com/mrveiss/AutoBot-AI/pull/7876))

- Add worktree cleanup integration (closes GH#7104) (#7871) ([#7871](https://github.com/mrveiss/AutoBot-AI/pull/7871))

- *(audit)* Add behavioral-grep utility for extraction audits (#7087) (#7808) ([#7808](https://github.com/mrveiss/AutoBot-AI/pull/7808))

- *(lint)* Orphan-ref audit script for Vue composables (#5349) (#5364) ([#5364](https://github.com/mrveiss/AutoBot-AI/pull/5364))


### Ux

- *(dashboard)* Dirty-state indicator and save feedback for CustomDashboard (#8759) (#8809) ([#8809](https://github.com/mrveiss/AutoBot-AI/pull/8809))

- *(analytics)* Unify tab nav to Icon component, remove SVG sprite (GH#8756) (#8808) ([#8808](https://github.com/mrveiss/AutoBot-AI/pull/8808))

- *(chat)* Group voice header buttons with divider — fix Gestalt proximity (GH#8755, MVA-1239) ([#8804](https://github.com/mrveiss/AutoBot-AI/pull/8804))

- *(nav)* Add /documents to main nav — AI Documents discoverability (GH#8757)

- *(nav)* Consolidate navigation to ≤7 items — Miller's Law fix ([#8785](https://github.com/mrveiss/AutoBot-AI/pull/8785))

- *(onboarding)* Replace progress dots with labeled step indicator ([#8791](https://github.com/mrveiss/AutoBot-AI/pull/8791))

- *(slm-frontend/code-sync)* Move 'Pull from Source' button next to 'Refresh' in page header ([#7098](https://github.com/mrveiss/AutoBot-AI/pull/7098))


### Wire-in

- Alert_cooldown and workflow_versioning (#7799 #7801) (#7821) ([#7821](https://github.com/mrveiss/AutoBot-AI/pull/7821))

- MountAllPlugins, datetime_utils, fact_extractor (#7793 #7797 #7804) (#7820) ([#7820](https://github.com/mrveiss/AutoBot-AI/pull/7820))


## [0.2.0] - 2026-03-26

### Bug Fixes

- *(docker)* Set executable permission on entrypoint scripts (#2459)

- *(deps)* Align all OpenTelemetry packages to 1.40.0 (#2465)

- *(frontend)* Auto-load CodebaseSecurityPanel on page visit (#2404) (#2453) ([#2453](https://github.com/mrveiss/AutoBot-AI/pull/2453))

- *(backend)* Return 410 Gone for LLM config write endpoints (#2400) (#2451) ([#2451](https://github.com/mrveiss/AutoBot-AI/pull/2451))

- *(backend)* Add advisory lock to fleet sync guard (#2401) (#2448) ([#2448](https://github.com/mrveiss/AutoBot-AI/pull/2448))

- *(frontend)* Add .vscode/settings.json exception to .gitignore (#2412)

- *(backend)* Move imports after copyright header in 2 files (#2414)

- *(backend)* Replace postgresql.UUID with dialect-neutral Uuid type (#2402)

- *(backend)* Add missing __init__.py for search_components test discovery (#2395)

- *(docs)* Update missed setup.sh refs in prompts and cleanup script (#2420)

- *(docker)* Use correct networks for autobot-worker service (#2423)

- *(backend)* Fix test_complex_code assertion in call_graph_resolution_test (#2393)

- *(frontend)* Wire all analytics panels to load on page visit (#2390)

- *(frontend)* Add withSourceId to loadRedisHealth endpoint (#2374) (#2411) ([#2411](https://github.com/mrveiss/AutoBot-AI/pull/2411))

- *(security)* Remove stack trace exposure from API responses (#2195) (#2398) ([#2398](https://github.com/mrveiss/AutoBot-AI/pull/2398))

- *(security)* Scope redact_secrets to workflow owner's secrets only (#2321) (#2392) ([#2392](https://github.com/mrveiss/AutoBot-AI/pull/2392))

- *(slm)* Add SELECT FOR UPDATE to fleet sync guard (#1937) (#2389) ([#2389](https://github.com/mrveiss/AutoBot-AI/pull/2389))

- *(frontend)* Add source_id to Redis health endpoint (#2374) ([#2384](https://github.com/mrveiss/AutoBot-AI/pull/2384))

- *(npu)* Add logger and decompose oversized functions in npu_worker.py (#2346) (#2382) ([#2382](https://github.com/mrveiss/AutoBot-AI/pull/2382))

- *(npu)* Add logger and decompose oversized functions in npu_worker.py (#2346) (#2377) ([#2377](https://github.com/mrveiss/AutoBot-AI/pull/2377))

- *(slm)* Warn when _generate_node_id falls back from ansible_name (#2175) (#2376) ([#2376](https://github.com/mrveiss/AutoBot-AI/pull/2376))

- *(analytics)* Update stale autobot-vue path references (#2016) ([#2375](https://github.com/mrveiss/AutoBot-AI/pull/2375))

- *(slm)* Add unique constraint and validation on ansible_name (#2011) (#2352) ([#2352](https://github.com/mrveiss/AutoBot-AI/pull/2352))

- *(analytics)* Expand INTERNAL_MODULE_PREFIXES for call graph (#2360) ([#2369](https://github.com/mrveiss/AutoBot-AI/pull/2369))

- *(security)* Validate X-Forwarded-For against trusted proxies (#2252) (#2366) ([#2366](https://github.com/mrveiss/AutoBot-AI/pull/2366))

- *(shared)* Re-raise HTTPException in with_error_handling decorator (#2327) (#2365) ([#2365](https://github.com/mrveiss/AutoBot-AI/pull/2365))

- *(security)* Make HMAC API key secret configurable (#2160) (#2361) ([#2361](https://github.com/mrveiss/AutoBot-AI/pull/2361))

- *(security)* Replace hardcoded VNC password with random generation (#1987) (#2362) ([#2362](https://github.com/mrveiss/AutoBot-AI/pull/2362))

- *(agents)* Normalise task_type in clear_strategy (#2325) (#2353) ([#2353](https://github.com/mrveiss/AutoBot-AI/pull/2353))

- *(rag)* Thread max_results through _diversify_results (#2200) (#2349) ([#2349](https://github.com/mrveiss/AutoBot-AI/pull/2349))

- *(security)* Add TLS to websockify VNC proxy (#1962) (#2350) ([#2350](https://github.com/mrveiss/AutoBot-AI/pull/2350))

- *(api)* Address code review findings from PR #2335 (#1733)

- *(rag)* Persist EdgeLearner cursors to Redis (#2210) ([#2345](https://github.com/mrveiss/AutoBot-AI/pull/2345))

- *(security)* Require VNC password authentication in all x11vnc launches (#1969) (#2344) ([#2344](https://github.com/mrveiss/AutoBot-AI/pull/2344))

- *(workflow)* Replace pg_insert with dialect-neutral upsert (#2320) (#2334) ([#2334](https://github.com/mrveiss/AutoBot-AI/pull/2334))

- *(chat)* Wire knowledge base into chat manager after Phase 2 init (#2309) (#2336) ([#2336](https://github.com/mrveiss/AutoBot-AI/pull/2336))

- *(ansible)* Add fix-node-ownership playbook and sudo rsync (#2296) (#2340) ([#2340](https://github.com/mrveiss/AutoBot-AI/pull/2340))

- *(ansible)* Add slm_server/infrastructure groups to production.yml (#2294) (#2339) ([#2339](https://github.com/mrveiss/AutoBot-AI/pull/2339))

- *(slm)* Load db credentials in migration runner (#2293) (#2338) ([#2338](https://github.com/mrveiss/AutoBot-AI/pull/2338))

- *(db)* Resolve Alembic revision collision — deduplicate 20260324_015 (#2302) (#2316) ([#2316](https://github.com/mrveiss/AutoBot-AI/pull/2316))

- *(devtools)* Disable format-on-save to prevent edit conflicts (#1518) (#2332) ([#2332](https://github.com/mrveiss/AutoBot-AI/pull/2332))

- *(hooks)* Reduce orphan detector false positives (#2094) (#2329) ([#2329](https://github.com/mrveiss/AutoBot-AI/pull/2329))

- *(slm)* Remove \$ escape so REDIS_HOST resolves at bootstrap time (#2326) (#2330) ([#2330](https://github.com/mrveiss/AutoBot-AI/pull/2330))

- *(chat)* Return error for unknown tool names instead of silent drop (#2305) (#2331) ([#2331](https://github.com/mrveiss/AutoBot-AI/pull/2331))

- *(ansible)* Make SLM login resilient in update-all-nodes.yml (#2295) (#2328) ([#2328](https://github.com/mrveiss/AutoBot-AI/pull/2328))

- *(monitoring)* Correct decorator order, prefix, GPU guard, tags (#2315) (#2324) ([#2324](https://github.com/mrveiss/AutoBot-AI/pull/2324))

- *(test)* Mock datetime on correct module in redis_thread_safety_test (#2211) (#2319) ([#2319](https://github.com/mrveiss/AutoBot-AI/pull/2319))

- *(workflow)* Eliminate race in parallel step execution (#2204) (#2318) ([#2318](https://github.com/mrveiss/AutoBot-AI/pull/2318))

- *(security)* Remove path echo from _validate_admin_path 403 response (#2307) (#2317) ([#2317](https://github.com/mrveiss/AutoBot-AI/pull/2317))

- *(db)* Resolve Alembic revision collision — deduplicate 20260324_015 (#2302) (#2314) ([#2314](https://github.com/mrveiss/AutoBot-AI/pull/2314))

- *(routing)* Normalise task_type vocabulary for learned strategies (#2208) (#2299) ([#2299](https://github.com/mrveiss/AutoBot-AI/pull/2299))

- *(topology)* Set last_updated in _update_pair (#2213) (#2297) ([#2297](https://github.com/mrveiss/AutoBot-AI/pull/2297))

- *(slm)* Remove hardcoded Redis IP from bootstrap-slm.sh (#2224) (#2292) ([#2292](https://github.com/mrveiss/AutoBot-AI/pull/2292))

- *(security)* Add auth to workflow-secrets API and fix path disclosure (#2303, #2304, #2311)

- *(security)* Sanitize session_id in tempfile.mkdtemp prefix (#2298)

- *(slm)* Fix User.roles -> User.user_roles in user_service.py

- *(analytics)* Add stale collection retry for problems storage (#1712) ([#2291](https://github.com/mrveiss/AutoBot-AI/pull/2291))

- *(db)* Add mesh_nodes_archive migration (#2212) ([#2284](https://github.com/mrveiss/AutoBot-AI/pull/2284))

- *(logs)* Preserve subdirectory in _validate_log_path (#2194) ([#2285](https://github.com/mrveiss/AutoBot-AI/pull/2285))

- *(security)* Add VNC passwd pre-check before server start (#1965) ([#2279](https://github.com/mrveiss/AutoBot-AI/pull/2279))

- *(tests)* Update 8 stale mock patches to correct module name (#2261) ([#2268](https://github.com/mrveiss/AutoBot-AI/pull/2268))

- *(slm)* Fix User import crash in models/__init__.py

- *(hooks)* Update header comments to include new exclusions (#2273)

- *(ci)* Replace global B113 bandit skip with per-file annotations (#2272)

- *(shared)* Document backend coupling in redis_client imports (#2220)

- *(shared)* Update redis_client.py docstring to canonical import path (#2219)

- *(ci)* Add missing autoflake flags to match pre-commit (#2218)

- *(docs)* Update CLAUDE.md line length to match .flake8 (120 chars) (#2217)

- *(analytics)* Correct inaccurate comment about POST-based triggers (#2271) ([#2276](https://github.com/mrveiss/AutoBot-AI/pull/2276))

- *(analytics)* Wire extraScans and fix debug composable init order (#2258, #2259) ([#2264](https://github.com/mrveiss/AutoBot-AI/pull/2264))

- *(ci)* Add CodeQL config with scan paths and workflow (#1826) ([#2203](https://github.com/mrveiss/AutoBot-AI/pull/2203))

- *(orchestrator)* Address code review findings from PR #2233 (#2235) ([#2254](https://github.com/mrveiss/AutoBot-AI/pull/2254))

- *(auth)* Add typed response model for login endpoint (#2240) (#2247) ([#2247](https://github.com/mrveiss/AutoBot-AI/pull/2247))

- *(auth)* Validate X-Forwarded-For against trusted proxies (#2239) (#2251) ([#2251](https://github.com/mrveiss/AutoBot-AI/pull/2251))

- *(auth)* Add audit log for MFA challenge path (#2242) (#2246) ([#2246](https://github.com/mrveiss/AutoBot-AI/pull/2246))

- *(auth)* Restore user_type field in /me response (#2241) (#2250) ([#2250](https://github.com/mrveiss/AutoBot-AI/pull/2250))

- *(chat)* Stop silently swallowing exceptions in load_session (#1906) ([#2176](https://github.com/mrveiss/AutoBot-AI/pull/2176))

- *(slm)* Remove stale SQLite references, use PostgreSQL in bootstrap (#1815) ([#2198](https://github.com/mrveiss/AutoBot-AI/pull/2198))

- *(slm)* Add tablename collision check for dual SQLAlchemy bases (#1878) ([#2205](https://github.com/mrveiss/AutoBot-AI/pull/2205))

- *(ci)* Make Code Quality workflow fully green (#2128) ([#2164](https://github.com/mrveiss/AutoBot-AI/pull/2164))

- *(rag)* Handle abbreviations in sentence splitter to prevent false splits (#2170)

- *(orchestration)* Wire WorkflowExecutor into scheduler startup (#2166) (#2201) ([#2201](https://github.com/mrveiss/AutoBot-AI/pull/2201))

- *(mesh)* Clean stale Redis entries on edge sync cycle (#2053)

- *(orchestration)* Add circuit breaker and parallel step execution (#2168, #2172) (#2197) ([#2197](https://github.com/mrveiss/AutoBot-AI/pull/2197))

- *(scheduler)* Implement real dependency checking in WorkflowQueue (#2180) (#2187) ([#2187](https://github.com/mrveiss/AutoBot-AI/pull/2187))

- *(workflow)* Warn when unsupported condition nodes are dropped on save (#2182) (#2185) ([#2185](https://github.com/mrveiss/AutoBot-AI/pull/2185))

- *(rag)* Handle abbreviations in sentence splitter to prevent false splits (#2170) (#2192) ([#2192](https://github.com/mrveiss/AutoBot-AI/pull/2192))

- *(rag)* Skip crude diversity filter when reranking is enabled (#2103) (#2191) ([#2191](https://github.com/mrveiss/AutoBot-AI/pull/2191))

- *(reports)* Use PROJECT_ROOT for data_base path instead of relative Path (#2163) (#2190) ([#2190](https://github.com/mrveiss/AutoBot-AI/pull/2190))

- *(security)* Remove str(e) from batch vectorize error response (#2173) (#2188) ([#2188](https://github.com/mrveiss/AutoBot-AI/pull/2188))

- *(agents)* Wire AgentRouter to read TaskPatternLearner strategies (#2105) (#2158) ([#2158](https://github.com/mrveiss/AutoBot-AI/pull/2158))

- Add placeholder states for Code Intelligence findings (#2068) (#2107) ([#2107](https://github.com/mrveiss/AutoBot-AI/pull/2107))

- *(frontend)* Add missing navigation links for registered routes (#2071) (#2100) ([#2100](https://github.com/mrveiss/AutoBot-AI/pull/2100))

- *(rag)* Use exclusive cursor to prevent pagination duplicates (#2102)

- *(agents)* Wire AgentRouter to read TaskPatternLearner strategies (#2105) (#2158)

- Add placeholder states for Code Intelligence findings (#2068) (#2107)

- *(frontend)* Add missing navigation links for registered routes (#2071) (#2100)

- *(rag)* Consume feedback streams with cursor tracking (#2102)

- *(nodes)* Use ansible_name or ip_address for node_id hash instead of display hostname (#1936) (#2146) ([#2146](https://github.com/mrveiss/AutoBot-AI/pull/2146))

- *(rag)* Align relationship extractor threshold to chunk count like entity extractor (#2052) (#2144) ([#2144](https://github.com/mrveiss/AutoBot-AI/pull/2144))

- *(tracker)* Cap experiment Redis list at 10k entries with ltrim (#2031) (#2142) ([#2142](https://github.com/mrveiss/AutoBot-AI/pull/2142))

- *(rag)* Use mean-pooled embeddings for RAPTOR L1+ levels instead of random (#2044) (#2127) ([#2127](https://github.com/mrveiss/AutoBot-AI/pull/2127))

- *(analytics)* Remove dead _store_problem_to_chromadb with unawaited coroutine (#2017) (#2126) ([#2126](https://github.com/mrveiss/AutoBot-AI/pull/2126))

- *(search)* Skip per-item BM25 recompute in bulk_delete, refresh once after batch (#2079) (#2125) ([#2125](https://github.com/mrveiss/AutoBot-AI/pull/2125))

- *(search)* Use Redis EXISTS check for BM25 lazy recompute instead of sentinel (#2082) (#2124) ([#2124](https://github.com/mrveiss/AutoBot-AI/pull/2124))

- *(security)* Add backward-compat dual-check for HMAC API key migration (#2083) (#2123) ([#2123](https://github.com/mrveiss/AutoBot-AI/pull/2123))

- *(frontend,backend)* Replace ShareKnowledgeDialog mock data with API (#2072) (#2087) ([#2087](https://github.com/mrveiss/AutoBot-AI/pull/2087))

- *(frontend)* Align ServiceStatus type with backend health response values (#2076) (#2093) ([#2093](https://github.com/mrveiss/AutoBot-AI/pull/2093))

- *(frontend)* Unify ChatMessage type definitions into single canonical type (#2066) (#2088) ([#2088](https://github.com/mrveiss/AutoBot-AI/pull/2088))

- *(frontend)* Wire LiveEventService into app startup and create useLiveEvents composable (#2064) (#2084) ([#2084](https://github.com/mrveiss/AutoBot-AI/pull/2084))

- *(frontend)* Align KnowledgeBaseStatus type with actual backend response (#2073) (#2086) ([#2086](https://github.com/mrveiss/AutoBot-AI/pull/2086))

- *(search)* Wire BM25 corpus stats recomputation into KB mutations (#2033) (#2070) ([#2070](https://github.com/mrveiss/AutoBot-AI/pull/2070))

- *(pipeline)* Use chunk_id as canonical node ID in MeshSeeder (#2050) (#2062) ([#2062](https://github.com/mrveiss/AutoBot-AI/pull/2062))

- *(rag)* Separate pre-rerank and post-rerank IDs in feedback events (#2035) (#2078) ([#2078](https://github.com/mrveiss/AutoBot-AI/pull/2078))

- *(rag)* Forward rerank_weights from config to reranker (#2034) (#2075) ([#2075](https://github.com/mrveiss/AutoBot-AI/pull/2075))

- *(model)* Compare model memory against GPU VRAM instead of system RAM (#2015) (#2063) ([#2063](https://github.com/mrveiss/AutoBot-AI/pull/2063))

- *(cost)* Use exact-then-prefix model matching instead of substring (#2030) (#2061) ([#2061](https://github.com/mrveiss/AutoBot-AI/pull/2061))

- *(hardware)* Check openvino_npu key instead of openvino in NPU selection (#2022) (#2054) ([#2054](https://github.com/mrveiss/AutoBot-AI/pull/2054))

- *(rag)* Use analytics Redis DB for feedback stream (#2045)

- *(deps)* Add spacy + scikit-learn for Neural Mesh RAG (#2043)

- *(backend)* Update LLM pricing, add staleness check + fallback (#1961) (#2010) ([#2010](https://github.com/mrveiss/AutoBot-AI/pull/2010))

- *(models)* Add VRAM check to dict API path + expose public API (#1966) (#2007) ([#2007](https://github.com/mrveiss/AutoBot-AI/pull/2007))

- *(slm)* Wire fleet sync concurrent guard into schedule paths (#1979) (#2009) ([#2009](https://github.com/mrveiss/AutoBot-AI/pull/2009))

- *(docker)* Add dev entrypoint scripts to fix bind mount issues (#1985) (#2006) ([#2006](https://github.com/mrveiss/AutoBot-AI/pull/2006))

- *(analytics)* Add post-indexing verification for empty sections (#1712) (#2002) ([#2002](https://github.com/mrveiss/AutoBot-AI/pull/2002))

- *(costs)* Update MODEL_PRICING with 2025-2026 models (#1961) (#1999) ([#1999](https://github.com/mrveiss/AutoBot-AI/pull/1999))

- *(slm)* Auto-populate ansible_name from heartbeat hostname (#1986) (#1997) ([#1997](https://github.com/mrveiss/AutoBot-AI/pull/1997))

- *(docker)* Add missing autobot_users database to init-databases.sql (#1981) (#2001) ([#2001](https://github.com/mrveiss/AutoBot-AI/pull/2001))

- *(hardware)* Replace placeholder Intel detection with real OpenVINO check (#1950) (#1996) ([#1996](https://github.com/mrveiss/AutoBot-AI/pull/1996))

- *(slm)* Add fleet sync guard to schedule and executor paths (#1979) (#1995) ([#1995](https://github.com/mrveiss/AutoBot-AI/pull/1995))

- *(infra)* Add dependabot.yml to guard against breaking dep upgrades (#1938) (#1992) ([#1992](https://github.com/mrveiss/AutoBot-AI/pull/1992))

- *(backend)* Read AUTOBOT_OLLAMA_ENDPOINT before OLLAMA_HOST fallback (#1963) (#1991) ([#1991](https://github.com/mrveiss/AutoBot-AI/pull/1991))

- *(backend)* Expand GPU detection beyond RTX to all vendors (#1959) (#1989) ([#1989](https://github.com/mrveiss/AutoBot-AI/pull/1989))

- *(security)* Harden VNC to require password authentication (#1939, #1940) ([#1941](https://github.com/mrveiss/AutoBot-AI/pull/1941))

- *(docker)* Resolve 8 Docker deployment bugs (#1910, #1908, #1909, #1877, #1895, #1879, #1892, #1893) ([#1926](https://github.com/mrveiss/AutoBot-AI/pull/1926))

- *(slm)* Add ansible_name column for proper Ansible targeting (#1814) ([#1932](https://github.com/mrveiss/AutoBot-AI/pull/1932))

- *(slm)* Fleet sync startup reconciliation + concurrent guard (#1729, #1730) ([#1928](https://github.com/mrveiss/AutoBot-AI/pull/1928))

- *(knowledge)* Lazy-load heavy deps to fix pipeline test imports (#1514) ([#1929](https://github.com/mrveiss/AutoBot-AI/pull/1929))

- *(ci)* Replace nonexistent autobot-user-backend/ with autobot-backend/ in code-quality workflow (#1933)

- Use db_service.session() instead of get_session() in a2a_card_fetcher (#1876) (#1913) ([#1913](https://github.com/mrveiss/AutoBot-AI/pull/1913))

- Use Path(__file__).parent for _PROJECT_ROOT in conversation_file_manager (#1861) (#1919) ([#1919](https://github.com/mrveiss/AutoBot-AI/pull/1919))

- *(backend)* Replace datetime.UTC with datetime.timezone.utc for Python 3.10 compat (#1889) (#1918) ([#1918](https://github.com/mrveiss/AutoBot-AI/pull/1918))

- *(backend)* Replace nonexistent require_auth with get_current_user (#1880) (#1917) ([#1917](https://github.com/mrveiss/AutoBot-AI/pull/1917))

- *(frontend)* Remove hardcoded SLM IP, use /slm proxy path as default (#1875) (#1916) ([#1916](https://github.com/mrveiss/AutoBot-AI/pull/1916))

- *(testing)* Add pythonpath to pytest.ini for reliable test collection (#1884) (#1915) ([#1915](https://github.com/mrveiss/AutoBot-AI/pull/1915))

- *(backend)* Break model_constants circular import with static defaults (#1882) (#1914) ([#1914](https://github.com/mrveiss/AutoBot-AI/pull/1914))

- *(ci)* Remove continue-on-error from code-quality.yml checks (#1870) (#1905) ([#1905](https://github.com/mrveiss/AutoBot-AI/pull/1905))

- *(config)* Add re-entry guard to prevent KeyError during circular init (#1862, #1866)

- Check monitored services only for code_status in node health (#1709) (#1901) ([#1901](https://github.com/mrveiss/AutoBot-AI/pull/1901))

- Persist SLM SECRET_KEY/ENCRYPTION_KEY to data/.slm_keys (#1726) (#1894) ([#1894](https://github.com/mrveiss/AutoBot-AI/pull/1894))

- Add noqa: redis to NPU worker standalone Redis instantiation (#1793) (#1888) ([#1888](https://github.com/mrveiss/AutoBot-AI/pull/1888))

- *(testing)* Fix pytest.ini testpaths and add directory exclusions (#1865) (#1887) ([#1887](https://github.com/mrveiss/AutoBot-AI/pull/1887))

- *(backend)* Lazy-init LLMFailsafeAgent to prevent import-time crash (#1858) (#1885) ([#1885](https://github.com/mrveiss/AutoBot-AI/pull/1885))

- *(backend)* Lazy-import config_manager in logging_manager to break circular import (#1862) (#1883) ([#1883](https://github.com/mrveiss/AutoBot-AI/pull/1883))

- *(ci)* Remove continue-on-error from code-quality.yml checks (#1870) (#1881) ([#1881](https://github.com/mrveiss/AutoBot-AI/pull/1881))

- Use AUTOBOT_BASE_DIR for CompletionTrainer model_dir (#1857) (#1874) ([#1874](https://github.com/mrveiss/AutoBot-AI/pull/1874))

- Rename SLM admin users table to slm_users to resolve FK mismatch (#1854) (#1872) ([#1872](https://github.com/mrveiss/AutoBot-AI/pull/1872))

- *(ci)* Remove || echo patterns from frontend test steps (#1855) (#1869) ([#1869](https://github.com/mrveiss/AutoBot-AI/pull/1869))

- *(ci)* Remove || echo from frontend-test.yml test steps (#1867) (#1868) ([#1868](https://github.com/mrveiss/AutoBot-AI/pull/1868))

- Use AUTOBOT_BASE_DIR for CompletionTrainer model_dir (#1857) (#1864) ([#1864](https://github.com/mrveiss/AutoBot-AI/pull/1864))

- *(backend)* Resolve installed version for ESM-only packages via dpkg-query (#1856) (#1863) ([#1863](https://github.com/mrveiss/AutoBot-AI/pull/1863))

- Use per-node service list in apply-system-updates verification (#1828) (#1860) ([#1860](https://github.com/mrveiss/AutoBot-AI/pull/1860))

- *(ci)* Remove || echo patterns that silently swallow CI failures (#1855) (#1859) ([#1859](https://github.com/mrveiss/AutoBot-AI/pull/1859))

- *(backend)* Detect Ubuntu Pro ESM security updates in check-system-updates (#1847) (#1852) ([#1852](https://github.com/mrveiss/AutoBot-AI/pull/1852))

- Check analysis keywords before implementation in _categorize_agent (#1844) (#1851) ([#1851](https://github.com/mrveiss/AutoBot-AI/pull/1851))

- Update test import path after agent service rename (#1846) (#1850) ([#1850](https://github.com/mrveiss/AutoBot-AI/pull/1850))

- *(ci)* Remove continue-on-error from backend code quality checks (#1848) (#1849) ([#1849](https://github.com/mrveiss/AutoBot-AI/pull/1849))

- *(frontend)* Resolve 11 TypeScript type errors in analytics panels (#1665) (#1843) ([#1843](https://github.com/mrveiss/AutoBot-AI/pull/1843))

- No-direct-redis hook uses tokenize to skip comments and docstrings (#1829) (#1842) ([#1842](https://github.com/mrveiss/AutoBot-AI/pull/1842))

- *(backend)* Classify security updates by repo origin instead of grep (#1827) (#1841) ([#1841](https://github.com/mrveiss/AutoBot-AI/pull/1841))

- *(security)* Add path traversal validation to session_id (#1825) (#1840) ([#1840](https://github.com/mrveiss/AutoBot-AI/pull/1840))

- No-direct-redis hook uses tokenize to skip comments and docstrings (#1829) (#1834) ([#1834](https://github.com/mrveiss/AutoBot-AI/pull/1834))

- *(security)* Mask secrets and connection details in log output (#1733)

- *(updates)* Remove delegate_to localhost from save report task (#1789)

- *(security)* Fix JavaScript CodeQL alerts — randomness, XSS, prototype pollution (#1733)

- *(updates)* Fix dpkg lock check and specific_packages parsing (#1789)

- *(frontend)* Pass source_id to duplicates task, dependencies, import-tree (#1817)

- *(frontend)* Restore backend-wait polling after max reconnects (#1795) (#1813) ([#1813](https://github.com/mrveiss/AutoBot-AI/pull/1813))

- *(updates)* Add tab badges and fetch code sync status on mount (#1789)

- *(security)* Add GH Actions permissions + fix regex/tag-filter alerts (#1733)

- *(updates)* Handle multi-line Ansible output in discover parser (#1789)

- *(updates)* Parse inventory to map IPs to Ansible hostnames (#1789)

- *(nginx)* Inject X-Internal-API-Key into /autobot-api proxy (#1791) (#1798) ([#1798](https://github.com/mrveiss/AutoBot-AI/pull/1798))

- *(tests)* Update stale autobot-user-* paths in test files (#1796) (#1799) ([#1799](https://github.com/mrveiss/AutoBot-AI/pull/1799))

- *(updates)* Use ip_address for Ansible --limit instead of hostname (#1789)

- *(updates)* Resolve hosts by IP when hostname doesn't match (#1789)

- *(security)* Mask sensitive data in log messages (#1733)

- *(security)* Add path traversal validation to prevent path injection (#1733)

- *(codebase)* Add source_id filtering to remaining analytics endpoints (#1772)

- *(workflow)* Re-enable POST /api/workflow/execute via workflow_automation (#1770)

- *(audit)* Handle asyncio.create_task() from sync endpoint context (#1568)

- *(hooks)* Add 120s timeout to flock serialization (#1765)

- *(slm-frontend)* Recursive org tree rendering for deep hierarchies (#1780)

- *(auth)* Accept X-Internal-API-Key in get_current_user for SLM proxy (#1779)

- *(middleware)* Register LLMAwarenessMiddleware in middleware chain (#1768)

- *(analytics)* Update stale directory paths in pattern_extractor (#1725)

- *(rag)* Add max size limit to query_cache (#1732)

- *(analytics)* Remove dead api_call_tracker code (#1731)

- *(frontend)* Normalize _backendWaitTimer field initialization (#1519)

- *(ansible)* Replace 36 hardcoded IPs in 13 playbooks with inventory vars (#1766)

- *(security)* Fix CodeQL alerts — stack-trace exposure, path injection, command injection (#1733)

- *(codebase)* Remove misleading Redis fallback for problems (#1759)

- *(codebase)* Allow local source paths in _get_last_commit (#1756)

- *(codebase)* Add source_id to problem documents in scanner (#1710)

- *(ansible)* Replace hardcoded IPs with inventory vars in deploy-full.yml (#1744)

- *(security)* Move emergency admin password hash to Ansible Vault (#1743)

- *(security)* Add authentication to knowledge_vectorization endpoints (#1738)

- *(security)* Correct Redis key prefix in validate-service-auth.sh (#1742)

- *(knowledge)* Break long line to satisfy E501 (#1737)

- *(security)* Deploy service auth keys via Ansible setup + safe rotation (#1734)

- *(codebase)* Persist indexing queue to Redis for restart survival (#1717)

- *(knowledge)* Address code review findings for #1513

- *(knowledge)* Wire up query_cache in AdvancedRAGOptimizer (#1548)

- *(analytics)* Normalize endpoints and bound api_frequencies dict (#1554)

- *(knowledge)* Add _LOAD_FAILED sentinel to get_cross_encoder (#1562)

- *(code-intel)* Enforce TTL check in _learn_bug_patterns_async (#1563)

- *(knowledge)* Align score_threshold defaults to 0.3 across all retrieval paths (#1532)

- *(codebase)* Fix sync failures, local sources, and auto-sync (#1711, #1714, #1715)

- *(slm)* Persist fleet sync jobs to DB for restart survival (#1707)

- *(hooks)* Skip post-checkout on file checkouts to prevent branch switching (#1705)

- *(hooks)* Fix flock deadlock, fallback anchor, and permissions pattern (#1699, #1700) ([#1704](https://github.com/mrveiss/AutoBot-AI/pull/1704))

- *(i18n)* Prune 461 orphaned translation keys with no EN counterpart (#1702)

- *(hooks)* Serialize worktree commits via flock to prevent stash contamination (#1684)

- *(hooks)* Wrap pre-commit with branch guard at git hook level (#1689)

- *(prompts)* Add doc-first safeguard to 3 intent context files (#1517)

- *(vllm)* Replace removed destroy_model_parallel with vllm 0.8+ cleanup (#1571)

- *(hooks)* Add branch guard to abort commits on stash-induced branch switch (#1670)

- *(lint)* Wrap bug_predictor.py line 1202 to fix E501 violation (#1564)

- *(i18n)* RTL tests now exercise real setLocale, not mock copy (#1598)

- Narrow .gitignore core.* pattern to only match core dumps (#1663)

- *(frontend)* Document getSeverityColor for canvas contexts, remove dead import (#1667)

- *(ci)* Resolve dep conflicts and split requirements into roles (#1655)

- *(hooks)* Add worktree branch guard to prevent stash corruption (#1654)

- *(config)* Add TTS worker URL mapping and shell helper port (#1648)

- *(config)* Use SSOT URL properties instead of manual f-strings (#1618)

- *(deps)* Align llama-index companion packages with core 0.13.0 + bump transformers 5.x (#1637, #1638)

- *(chat)* Eliminate set_chat_context race on singleton (#1641)

- *(config)* Replace hardcoded IPs with SSOT config in voice tests (#1618)

- *(ansible)* Replace hardcoded IPs with inventory variables in update-all-nodes.yml (#1636)

- *(ansible)* Deploy gaps — SLM migrations, shared ownership, NPU health (#1630, #1632, #1633, #1629)

- *(slm)* Fix frontend ownership before npm build in self-sync (#1624)

- *(ansible)* Sync slm_agent role files with canonical agent code (#1623)

- *(slm)* Widen code_status column from VARCHAR(20) to VARCHAR(50) (#1622)

- *(scheduler)* Wire default template executor for scheduled workflows (#1614)

- *(chat)* Wire set_chat_context before slash command execution (#1613)

- *(deploy)* Run Alembic migrations for user backend during code-sync (#1608)

- *(slm)* Code_status reflects service health, not just commit match (#1605)

- *(deploy)* Install pip/npm dependencies during code-sync (#1603)

- *(slm)* Add pip install and frontend build to self-sync path (#1607)

- *(chat)* Use correct SSOT accessors for checkpointer Redis URI (#1583)

- *(middleware)* Store asyncio task refs to prevent fire-and-forget leaks (#1556)

- *(i18n)* Replace physical Tailwind directional classes with logical properties (#1509)

- *(memory)* Add TTL eviction to kb_librarian tool_cache and BugPredictor git caches (#1551)

- *(tasks)* Clear latest_result cache key in clear_all() (#1552)

- *(i18n)* Always set html[lang] and sync language on reset (#1502, #1547, #1550)

- *(i18n)* Translate all remaining knowledge subsections across 6 locales (#1545)

- *(security)* Require auth on GET /api/chat/sessions and remove dead code (#1543, #1542)

- *(i18n)* Translate knowledge categories page and persist indexing state (#1538, #1539)

- *(chat)* Empty history from wrong endpoint and response format mismatch (#1541)

- *(analytics)* Prevent auto-start of analysis on mount and fix orphan API detection (#1469)

- *(voice)* Remove duplicate tts_end from flush sentinel (#1537)

- *(rag)* Normalize cross-encoder logits in search reranking (#1533)

- *(rag)* Use real ChromaDB similarity scores and lower threshold (#1526)

- *(voice)* Gapless TTS audio scheduling to eliminate chunk stuttering (#1527)

- *(voice)* TTS replay, interrupt, and hallucination bugs (#1420)

- *(events)* Restore LiveEventService.ts to correct #1408 version (#1511)

- Remove remaining 3 feat/1408 files from Dev_new_gui (final)

- Remove remaining feat/1408 files from Dev_new_gui (cont. b6326d66)

- Remove feat/1408 files accidentally committed in b1628204

- *(test)* Update stale src.chat_intent_detector patch paths in TestSelectContextPrompt (#1501)

- *(ansible)* Replace TCP wait_for with /api/health polling in update-all-nodes.yml (#1499)

- *(chat)* Enforce doc-first lookup for AutoBot setup/install questions (#1476)

- *(tts)* Prime cursor on voice-enable to prevent re-speaking mid-stream content (#1491)

- *(slm)* Clear NodeCredential and NodeConfig on node decommission (#1489)

- *(tts)* Treat unloaded historical messages as already-spoken on session switch (#1490)

- *(tts)* Prime TTS cursor on session switch to prevent re-speaking existing messages (#1488)

- *(slm)* Clear service records on node decommission (#1479)

- *(chat)* Auto-clear corrupted LangGraph checkpoints on graph error (#1475)

- *(ansible)* Restart NPU worker and browser services after deploy (#1474)

- *(security)* Add explicit Dict[str, Any] annotation for results in validate_research_safety (#1466)

- *(deps)* Update stale llama-index sub-package pins to >=0.5.0,<1.0.0 (#1473)

- *(chat,analytics)* LangGraph config type + scan runner concurrency (#1459, #1461)

- *(websocket)* Add backend-wait mode for reconnection during restart (#1463)

- *(security-scanner)* Use dict access for research results (#1465)

- *(analytics)* Fix bug prediction display filter and raise file limit (#1430)

- *(chat)* LangGraph checkpointer + ConfigManager model method (#1433)


### CI/CD

- *(docker)* Remove Docker Build Cloud workflow — building manually (#1809)

- *(docker)* Add Docker Build Cloud workflow (#1809)


### Documentation

- *(setup)* Update PHASE_5_DEVELOPER_SETUP.md to current install paths (#2440)

- *(system-state)* Replace stale setup.sh references (#2441)

- Add Docker quick-start to README and INSTALL.md (#2443)

- *(ops)* Document SLM-based deployment architecture in CLAUDE.md (#2342)

- Add self-improvement loop, elegance gate, skills, and plans (#2245)

- Add Neural Mesh RAG implementation plan (#1994)

- Add Neural Mesh RAG design document (#1994)

- Add web pipeline engine design document (#1967)

- LangChain 1.x import compatibility verification report (#1600) (#1837) ([#1837](https://github.com/mrveiss/AutoBot-AI/pull/1837))

- *(dev)* Add approach guidelines, pre-commit self-healing, and issue labels (#1771)

- *(processes)* Delineate ProcessAdapter vs long_running_operations (#1751)

- *(context7)* Add project metadata and how-to guides index (#1749)

- Add Dependabot security remediation implementation plan (#1567)

- *(plans)* Codebase analytics test suite refactor plan

- *(browser)* Interactive browser control design and implementation plan (#1416)

- *(claude)* Add operational Q&A research requirement to Rule 1 (#1476)


### Features

- *(docker)* Serve SLM frontend as static build via nginx (#1809)

- *(frontend)* Move browser-automation route under /automation namespace (#2367)

- *(slm)* Move LLM config from main frontend to SLM admin settings (#2371) (#2391) ([#2391](https://github.com/mrveiss/AutoBot-AI/pull/2391))

- *(automation)* Add 6 vision node types to workflow canvas (#2381) (#2386) ([#2386](https://github.com/mrveiss/AutoBot-AI/pull/2386))

- *(automation)* Add VISION sidebar group with screen analysis, video, gallery (#2380) (#2385) ([#2385](https://github.com/mrveiss/AutoBot-AI/pull/2385))

- *(automation)* Remove /vision route, nav, store refs; delete VisionView (#2379) (#2387) ([#2387](https://github.com/mrveiss/AutoBot-AI/pull/2387))

- *(workflow)* Add encrypted secret management for credentials (#2153) ([#2282](https://github.com/mrveiss/AutoBot-AI/pull/2282))

- *(workflow)* Add per-workflow RBAC and audit trail (#2152) ([#2280](https://github.com/mrveiss/AutoBot-AI/pull/2280))

- *(monitoring)* Wire GPU acceleration optimizer to API endpoints (#2267) ([#2281](https://github.com/mrveiss/AutoBot-AI/pull/2281))

- *(mesh)* Add AgentTopology pruning + last_updated (#2167)

- *(mesh)* Implement MeshDB methods for Pruner and Promoter (#2178)

- *(db)* Add Alembic migration for agent topology tables (#2177)

- *(mesh)* Add A-RAG autonomous strategy selection (#2136) (#2156) ([#2156](https://github.com/mrveiss/AutoBot-AI/pull/2156))

- *(mesh)* Add topology-aware routing + agent specialization (#2138) (#2151) ([#2151](https://github.com/mrveiss/AutoBot-AI/pull/2151))

- *(mesh)* Add EvidenceExtractor — sentence-level precision (#2135) (#2150) ([#2150](https://github.com/mrveiss/AutoBot-AI/pull/2150))

- *(mesh)* Add AgentTopology — dynamic DAG with Hebbian evolution (#2137) (#2149) ([#2149](https://github.com/mrveiss/AutoBot-AI/pull/2149))

- *(mesh)* Add QueryDecomposer — MA-RAG multi-hop decomposition (#2134) (#2147) ([#2147](https://github.com/mrveiss/AutoBot-AI/pull/2147))

- Add batch vectorization endpoint (#2077) (#2106) ([#2106](https://github.com/mrveiss/AutoBot-AI/pull/2106))

- *(mesh)* Add A-RAG autonomous strategy selection (#2136) (#2156)

- *(mesh)* Add topology-aware routing + agent specialization (#2138) (#2151)

- *(mesh)* Add EvidenceExtractor — sentence-level precision (#2135) (#2150)

- *(mesh)* Add AgentTopology — dynamic DAG with Hebbian evolution (#2137) (#2149)

- *(mesh)* Add QueryDecomposer — MA-RAG multi-hop decomposition (#2134) (#2147)

- Add batch vectorization endpoint (#2077) (#2106)

- *(mesh)* Add MeshBrainScheduler + health API endpoints (#2120)

- *(mesh)* Add NodePromoter — daily anchor emergence (#2119)

- *(mesh)* Add MeshPruner — weekly entropy control and decay (#2118)

- *(mesh)* Add EdgeDiscoverer — LLM-based relationship naming (#2117)

- *(rag)* Add mesh_retriever_enabled flag and RAGService integration (#2059)

- *(mesh)* Add NeuralMeshRetriever — unified mesh-aware retrieval (#2058)

- *(mesh)* Add PersonalizedPageRank for graph expansion (#2057)

- *(mesh)* Add EdgeLearner — Hebbian reinforcement from retrieval feedback (#2056)

- *(mesh)* Add PostgreSQL mesh schema and async MeshDB client (#2055)

- *(pipeline)* Wire RAPTOR build_raptor_tree into process() (#2051) (#2074) ([#2074](https://github.com/mrveiss/AutoBot-AI/pull/2074))

- *(pipeline)* Add SIMILAR_TO cosine edges to MeshSeeder (#2049) (#2065) ([#2065](https://github.com/mrveiss/AutoBot-AI/pull/2065))

- *(rag)* Integrate complexity classifier into feedback hook (#2024)

- *(pipeline)* Add NLP-light entity extraction mode (#2025)

- *(pipeline)* Add NLP-light relationship extraction mode (#2026)

- *(pipeline)* Add MeshSeeder loader for graph edge creation (#2028)

- *(pipeline)* Add RAPTOR recursive clustering summarizer (#2027)

- *(mesh)* Add PostgreSQL to Redis edge sync service (#2029)

- *(rag)* Emit retrieval feedback events via publish_live_event (#1516) (#2023) ([#2023](https://github.com/mrveiss/AutoBot-AI/pull/2023))

- *(search)* Upgrade keyword search to BM25 scoring (#1720) (#2021) ([#2021](https://github.com/mrveiss/AutoBot-AI/pull/2021))

- *(search)* Configurable reranker blend weights (#2004) (#2020) ([#2020](https://github.com/mrveiss/AutoBot-AI/pull/2020))

- *(search)* Add query complexity classifier (#1719) (#2018) ([#2018](https://github.com/mrveiss/AutoBot-AI/pull/2018))

- *(search)* Add context tracker for multi-step retrieval (#2005) (#2019) ([#2019](https://github.com/mrveiss/AutoBot-AI/pull/2019))

- *(perf)* Experiment tracker, pipeline profiler, cache benchmark (#1988) (#2008) ([#2008](https://github.com/mrveiss/AutoBot-AI/pull/2008))

- *(models)* VRAM-aware model selection — prevent OOM (#1966) (#1993) ([#1993](https://github.com/mrveiss/AutoBot-AI/pull/1993))

- *(docker)* Add dev override for hot-reload (#1911) ([#1935](https://github.com/mrveiss/AutoBot-AI/pull/1935))

- *(docker)* Add optional TLS/HTTPS support (#1896) ([#1934](https://github.com/mrveiss/AutoBot-AI/pull/1934))

- *(docker)* Resource limits + production hardening (#1897) ([#1930](https://github.com/mrveiss/AutoBot-AI/pull/1930))

- Add timeout + granular error mapping to chat processing (#1797) (#1899) ([#1899](https://github.com/mrveiss/AutoBot-AI/pull/1899))

- *(docker)* Ubuntu 22.04 + Python 3.12 Docker stack (#1886) ([#1886](https://github.com/mrveiss/AutoBot-AI/pull/1886))

- *(frontend)* Pass source_id to all codebase analytics endpoints (#1772)

- *(docker)* Fresh containerization for current codebase (#1809) (#1818) ([#1818](https://github.com/mrveiss/AutoBot-AI/pull/1818))

- *(processes)* WebSocket log streaming for running processes (#1777)

- *(slm-frontend)* Add admin panels for org chart, config history, processes (#1404, #1405, #1406)

- *(agents)* Implement task delegation and escalation (#1753)

- *(agents)* Create central SQL agents table with startup seeding (#1754)

- *(config)* Wire ConfigRevisionService into mutation endpoints (#1747)

- *(processes)* Wire ProcessAdapterService into app lifecycle (#1748)

- *(codebase)* Add project header card in detail view (#1713)

- *(codebase)* Show commit message on project cards (#1713)

- *(codebase)* Frontend source_id filtering + per-source last_indexed (#1710, #1716)

- *(codebase)* Add source_id filtering to query endpoints (#1710, #1716)

- *(codebase)* Thread source_id through scanner and indexing pipeline (#1710)

- *(knowledge)* Add GET /reindex_with_context/status endpoint (#1761)

- *(processes)* Add process adapters for background task decomposition (#1406)

- *(agents)* Add agent org charts with role hierarchy (#1405)

- *(config)* Add config audit trail with versioning and rollback (#1404)

- *(knowledge)* Add POST /reindex_with_context endpoint (#1513)

- *(i18n)* Complete analytics translations for all 6 locales (#1555)

- *(i18n)* Translate audit, collaboration, manpage keys (#1555)

- *(i18n)* Translate 345 keys across 6 locales (#1555)

- *(frontend)* Add routes for 11 analytics dashboard components (#1677)

- *(i18n)* Add browser locale auto-detection with Arabic support (#1508)

- *(analytics)* Shared getCssVar composable + wire uniqueEndpoints display (#1602)

- *(slm)* Detect crash-looping services and degrade node status (#1604)

- *(i18n)* Add Hebrew, Persian, and Urdu locale files (#1505)

- *(i18n)* Translate 438 flat knowledge.* keys + common/nav across 6 locales (#1553, #1555)

- *(i18n)* Add RTL layout support for Arabic and other RTL locales (#1337)

- *(i18n)* Add ar.json Arabic locale file (#1337)

- *(chat)* Add TTL to LangGraph Redis checkpoints (#1481)

- *(analytics)* Add cached-result endpoints for background-task scans (#1540)

- *(i18n)* Add voice_ids types and i18n key for voice-per-language mapping (#1333)

- *(i18n)* Add agent cost tracking translation keys (#1401)

- *(cost)* Per-agent cost tracking and workflow template improvements (#1401)

- *(agents)* Add heartbeat router registration and HeartbeatPanel frontend (#1407)

- *(events)* Register live_events in api package __init__ (#1408)

- *(knowledge)* Add CONTEXT_* env vars to .env.example (#1498)

- *(knowledge)* Add contextual retrieval cognifier to RAG pipeline (#1498)

- *(agents)* Add heartbeat API, scheduler service, and lifespan bootstrap (#1407)

- *(agents)* Add heartbeat system models and DB migration (#1407)

- *(events)* Add scoped real-time event channels and frontend service (#1408)

- *(analytics)* Add MD/JSON export buttons and remove dead CSS (#1493, #1496)

- *(i18n)* Add ar.json Arabic locale file (#1337)

- *(i18n)* Add RTL layout support for Arabic and other RTL locales (#1337)

- *(chat)* Re-wire intent-based context injection into chat workflow (#1494)

- *(ansible)* Add wait_for tasks after Play 2 service restarts (#1497)

- *(ansible)* Add tags: [always] to housekeeping tasks in playbooks/update-all-nodes.yml (#1495)

- *(ansible)* Add component tags to deploy tasks in playbooks/update-all-nodes.yml (#1492)

- *(ansible)* Add restart tags to playbooks/update-all-nodes.yml (#1480)

- *(slm)* Add force decommission to skip Ansible for already-removed nodes (#1479)

- *(analytics)* Restore sync/delete actions and batch summary endpoint (#1468)


### Miscellaneous

- Replace stale mistral:7b-instruct refs with qwen3.5:9b (#2418) ([#2470](https://github.com/mrveiss/AutoBot-AI/pull/2470))

- *(frontend)* Remove unused variables in CodebaseAnalytics.vue (#2405) ([#2466](https://github.com/mrveiss/AutoBot-AI/pull/2466))

- *(frontend)* Remove orphaned VisionAutomationPage.vue (#2396)

- *(deps)* Bump opentelemetry-proto in /autobot-backend

- *(deps)* Bump opentelemetry-exporter-otlp in /autobot-backend

- *(deps)* Bump github/codeql-action from 3 to 4

- *(deps-dev)* Bump picomatch

- *(deps)* Bump vue from 3.5.28 to 3.5.31 in /autobot-frontend

- *(deps)* Bump onnxruntime-web in /autobot-frontend

- *(deps)* Bump the npm_and_yarn group across 3 directories with 1 update

- *(deps)* Bump @xterm/addon-web-links in /autobot-frontend

- *(scripts)* Remove legacy setup_wizard.sh (#2425)

- *(deps)* Bump the pip group across 3 directories with 3 updates

- *(deps-dev)* Bump the npm_and_yarn group across 3 directories with 1 update (#1978)

- *(docs)* Remove legacy setup.sh, update install references (#2420)

- *(infra)* Rename setup-runner-pyenv.sh + legacy cleanup (#1924) ([#1931](https://github.com/mrveiss/AutoBot-AI/pull/1931))

- Add deprecation warnings for langchain_community OllamaEmbeddings fallback (#1845) (#1853) ([#1853](https://github.com/mrveiss/AutoBot-AI/pull/1853))

- *(i18n)* Extract hardcoded strings in AgentRegistryView.vue (#1820) (#1838) ([#1838](https://github.com/mrveiss/AutoBot-AI/pull/1838))

- Rename claude_agent_service.py to specialized_agent_service.py (#1819) (#1832) ([#1832](https://github.com/mrveiss/AutoBot-AI/pull/1832))

- Add plan docs, skills, and settings (#1771)

- *(hooks)* Add post-checkout auto-install mechanism (#1692)

- Add context7 platform verification token

- Add context7 platform verification token

- *(docs)* Document worktree --unset-upstream to prevent PR bypass (#1695)

- *(ci)* Convert auto-close workflow to comment-only notification (#1659, #1660)

- *(ci)* Upgrade GitHub Actions to Node.js 24 runtime (#1664)

- *(ci)* Auto-close issues for PRs merged to Dev_new_gui (#1601)

- *(docs)* Warn against isolation:worktree for PR-creating agents (#1597)

- *(docs)* Document subagent Bash permission constraints (#1580)

- *(deps)* Generate uv.lock for knowledge-base-mcp (#1578)


### Performance

- Add in-memory TTL cache for learned strategies (#2209) ([#2351](https://github.com/mrveiss/AutoBot-AI/pull/2351))

- *(mesh)* Vectorize SIMILAR_TO edge extraction with numpy (#2081) (#2189) ([#2189](https://github.com/mrveiss/AutoBot-AI/pull/2189))

- *(rag)* Share CrossEncoder singleton per worker process (#1549)

- *(i18n)* Guard usePreferences init to run once (#1502)

- *(chat)* Cache compiled graph as module-level singleton (#1483)


### Refactoring

- *(shared)* Move redis_management to autobot-shared (#2313)

- *(frontend)* Decompose useSpecializedAnalysis into focused composables (#2372)

- *(shared)* Extract _check_tablename_collisions into importable utility (#2413)

- *(shared)* Consolidate proxy_utils into autobot-shared (#2408)

- *(frontend)* Remove orphaned LLM config files (#2399)

- *(infra)* Decompose oversized functions in optimize_llm_models.py (#2410)

- *(config)* Remove hardcoded mistral:7b-instruct, read LLM model from .env (#2383)

- *(config)* Replace hardcoded mistral:7b-instruct with DEFAULT_LLM_MODEL (#2383) (#2406) ([#2406](https://github.com/mrveiss/AutoBot-AI/pull/2406))

- *(frontend)* Decompose useCodeIntelAnalysis.ts (#2260) ([#2370](https://github.com/mrveiss/AutoBot-AI/pull/2370))

- *(codebase_analytics)* Decompose scanner.py god module into 5 focused sub-modules (#2013) ([#2347](https://github.com/mrveiss/AutoBot-AI/pull/2347))

- Move co-located test files to tests/ directory (#2037) ([#2354](https://github.com/mrveiss/AutoBot-AI/pull/2354))

- Consolidate EnhancedOrchestrator into singleton (#2207) ([#2337](https://github.com/mrveiss/AutoBot-AI/pull/2337))

- Move workflow_rbac.py to services/ (#2323) ([#2343](https://github.com/mrveiss/AutoBot-AI/pull/2343))

- *(frontend)* Extract shared CodeSource interface (#2238) (#2333) ([#2333](https://github.com/mrveiss/AutoBot-AI/pull/2333))

- *(analytics)* Decompose CodebaseAnalytics.vue script into composables (#2228, #2230) ([#2253](https://github.com/mrveiss/AutoBot-AI/pull/2253))

- *(analytics)* Continue decomposing CodebaseAnalytics.vue (#1579) ([#2236](https://github.com/mrveiss/AutoBot-AI/pull/2236))

- *(orchestrator)* Consolidate overlapping orchestrators (#2181) ([#2233](https://github.com/mrveiss/AutoBot-AI/pull/2233))

- *(auth)* Remove dead AuthService.authenticate_user() and verify_password() (#2227) ([#2231](https://github.com/mrveiss/AutoBot-AI/pull/2231))

- *(gpu)* Reuse nvidia-smi GPU name and handle multi-GPU (#2222) ([#2237](https://github.com/mrveiss/AutoBot-AI/pull/2237))

- *(frontend)* Decompose CodebaseAnalytics.vue (#1469) ([#2225](https://github.com/mrveiss/AutoBot-AI/pull/2225))

- *(auth)* Deduplicate SLM login endpoints (#1922) ([#2223](https://github.com/mrveiss/AutoBot-AI/pull/2223))

- *(gpu)* Cache vendor detection to avoid duplicate subprocess calls (#1990) ([#2221](https://github.com/mrveiss/AutoBot-AI/pull/2221))

- *(tests)* Migrate legacy redis_client imports to autobot_shared (#2047) ([#2171](https://github.com/mrveiss/AutoBot-AI/pull/2171))

- *(slm)* Consolidate User models to single UUID-PK model (#1900) (#1921) ([#1921](https://github.com/mrveiss/AutoBot-AI/pull/1921))

- *(infra)* Standardize Python to deadsnakes PPA + Python 3.12 venv (#1898) (#1920) ([#1920](https://github.com/mrveiss/AutoBot-AI/pull/1920))

- Extract helpers from infra scripts exceeding 65-line limit (#1792) (#1890) ([#1890](https://github.com/mrveiss/AutoBot-AI/pull/1890))

- *(i18n)* Derive RTL_LOCALES from locale file _meta.dir (#1812) (#1873) ([#1873](https://github.com/mrveiss/AutoBot-AI/pull/1873))

- Replace deprecated asyncio.get_event_loop() across backend (#1752) (#1839) ([#1839](https://github.com/mrveiss/AutoBot-AI/pull/1839))

- *(i18n)* Derive SUPPORTED_LOCALES from locale file glob (#1675) (#1810) ([#1810](https://github.com/mrveiss/AutoBot-AI/pull/1810))

- *(knowledge)* Make ContextGeneratorCognifier.is_enabled() public (#1760)

- *(frontend)* Migrate 4 arrow-function getCssVar copies to shared composable (#1666)

- *(config)* Derive ssot_mappings from Pydantic model defaults (#1653)

- *(frontend)* Consolidate getCssVar + add getSeverityColor to shared composable (#1606, #1647)

- *(analytics)* Migrate ~2,914 lines of scoped CSS to 8 panels (#1589)

- *(backend)* Remove 8 dead functions found by call graph analysis (#1612)

- *(analytics)* Extract 6 oversized functions from CodebaseAnalytics.vue (#1588)

- *(analytics)* Decompose CodebaseAnalytics.vue into sub-components (#1469)

- *(chat)* Remove unused imports and fix deprecated substr in ChatInput.vue (#1565)

- *(voice)* Extract _stream_chunks_pipelined shared TTS helper (#1535, #1536)

- *(analytics)* Wire up CodeSmells/Duplicates/Declarations components; remove stale UI state (#1486, #1487)

- *(analytics)* Extract 3 focused sub-components from CodebaseAnalytics.vue (#1469)


### Reverted

- Remove accidental feat/1337 i18n commits from Dev_new_gui (#1506)


### Testing

- *(mesh)* Add EvidenceExtractor abbreviation-aware splitting tests (#2202) (#2359) ([#2359](https://github.com/mrveiss/AutoBot-AI/pull/2359))

- *(mesh)* Add EdgeLearner multi-batch pagination test (#2214) (#2358) ([#2358](https://github.com/mrveiss/AutoBot-AI/pull/2358))

- *(slm)* Add tablename collision unit test (#2226) (#2357) ([#2357](https://github.com/mrveiss/AutoBot-AI/pull/2357))

- *(gpu)* Add unit tests for gpu_detection.py (#2243) (#2356) ([#2356](https://github.com/mrveiss/AutoBot-AI/pull/2356))

- *(security)* Add path_validator unit tests (#2162) (#2355) ([#2355](https://github.com/mrveiss/AutoBot-AI/pull/2355))

- Add unit tests for SpecializedAgentService (#1821) (#1833) ([#1833](https://github.com/mrveiss/AutoBot-AI/pull/1833))

- *(i18n)* Add unit tests for detectBrowserLocale (#1674) (#1811) ([#1811](https://github.com/mrveiss/AutoBot-AI/pull/1811))

- *(i18n)* Add automated RTL layout tests for setLocale() and usePreferences (#1510)


### Build

- *(deps)* Bump the npm_and_yarn group across 7 directories with 13 updates

- *(deps)* Cherry-pick llama-index-core 0.13.0 bump from PR #1450

- *(deps)* Bump llama-index-core in the pip group across 1 directory

- *(deps)* Bump @modelcontextprotocol/sdk to 1.26.0 (security fix GHSA-345p-7cg4-v4c7)

- *(deps)* Bump cryptography and pillow (safe subset of #1435)

- *(deps)* Bump qs


### Cleanup

- *(orchestration)* Remove dead _check_step_dependencies (#2206) (#2378) ([#2378](https://github.com/mrveiss/AutoBot-AI/pull/2378))

- Remove dead _ComplexWorkflowRequired exception (#2256) ([#2341](https://github.com/mrveiss/AutoBot-AI/pull/2341))

- *(analytics)* Remove dead barrel exports for deleted components (#2262) ([#2270](https://github.com/mrveiss/AutoBot-AI/pull/2270))

- *(tests)* Remove dead archive path references from llm_interface_core_test (#2265) ([#2269](https://github.com/mrveiss/AutoBot-AI/pull/2269))

- *(analytics)* Remove orphaned CodebaseStatsSection.vue (#2229) ([#2275](https://github.com/mrveiss/AutoBot-AI/pull/2275))

- *(analytics)* Remove 826 lines of dead CSS from CodebaseAnalytics.vue (#2244) ([#2249](https://github.com/mrveiss/AutoBot-AI/pull/2249))

- *(frontend)* Remove dead defineExpose({ getCssVar }) from 2 dashboards (#1671)

- *(knowledge)* Remove unused hasChanges variable in DocumentChangeFeed.vue (#1558)


### Deps

- Raise numpy lower bound to >=2.0.0 in 7 satellite requirement files (#1661)


### Infra

- *(pre-commit)* Add untracked-file warning hook (#1503)


### Merge

- Dev_new_gui → main — Docker containerization + recent fixes (#1824)

- Resolve conflicts with Dev_new_gui (#2102)

- Resolve conflict with Dev_new_gui in models/__init__.py (#1406)

- Resolve conflicts with main — keep newer deps, drop deprecated server-github

- Resolve conflict with Dev_new_gui in code_sync.py


### Security

- Fix CodeQL stack-trace-exposure + sensitive-logging alerts (#1733) ([#2335](https://github.com/mrveiss/AutoBot-AI/pull/2335))

- Fix path injection CodeQL alerts (#1721) (#2101) ([#2101](https://github.com/mrveiss/AutoBot-AI/pull/2101))

- Fix path injection CodeQL alerts (#1721) (#2101)

- Fix stack trace exposure CodeQL alerts (#1721) (#2089) ([#2089](https://github.com/mrveiss/AutoBot-AI/pull/2089))

- Fix critical injection CodeQL alerts (#1721) (#2080) ([#2080](https://github.com/mrveiss/AutoBot-AI/pull/2080))

- Fix sensitive data logging/storage CodeQL alerts (#1721) (#2069) ([#2069](https://github.com/mrveiss/AutoBot-AI/pull/2069))

- *(deps)* Migrate LangChain ecosystem to 1.x (#1572)

- *(deps)* Replace python-jose with PyJWT (#1575)

- *(deps)* Override minimatch to >=9.0.7 in frontend (#1567)

- *(deps)* Remove deprecated @modelcontextprotocol/server-github (#1567)

- *(deps)* Remove orphaned uv.lock in mcp-structured-thinking (no pyproject.toml) (#1567)

- *(deps)* Bump vllm to >=0.14.1 (#1567)

- *(deps)* Bump torch to >=2.6.0, remove <2.6.0 upper bound (#1567)

- *(deps)* Bump llama-index floor to >=0.12.41 (#1567)

- *(deps)* Bump transformers to >=4.53.0 in ai-stack (#1567)

- *(deps)* Bump starlette to 0.49.1 and pypdf to 6.8.0 in requirements-ci (#1567)

- *(deps)* Bump mcp to >=1.23.0 and langgraph to >=1.0.10 in backend (#1567)

- *(deps)* Bump pypdf to >=6.8.0 in root requirements (#1567)

- *(deps)* Bump pypdf, nltk, aiohttp, requests in ai-stack (#1567)

- *(deps)* Bump python-multipart, pypdf, nltk, markdown, opencv, pycryptodome in shared/config (#1567)

- *(deps)* Bump aiohttp, requests, scikit-learn, numpy in code_analysis (#1567)


## [0.1.0] - 2026-03-01

### Bug Fixes

- *(analytics)* Store sync task reference and log errors (#1467)

- *(judges)* Fail-open in production path step_evaluator (#1464)

- *(analytics)* Address code review findings (#1458)

- *(judges)* Fail-open when LLM judge is unavailable (#1464)

- *(i18n)* Add Language tab to ProfileModal (#1451)

- *(judges)* Fix test mocks for chat_completion signature (#1457)

- *(setup-wizard)* Treat SLM roles as pre-existing on manager (#1455)

- *(setup-wizard)* Provision logging, SLM roles, role dedup (#1455)

- *(ci)* Install jq for git-cliff release workflow (#1453)

- *(deploy)* Broken approval import + NPU SSOT violations (#1456)

- *(ssot)* Move noqa comments to IP lines after black reformatting (#1453)

- *(ssot)* Eliminate all 372 SSOT compliance violations (#1453)

- *(chat)* LangGraph checkpointer + ConfigManager model method (#1433)

- *(approval)* Add auth, input validation, and security hardening (#1402)

- *(analytics)* Raise bug prediction file limit and fix display (#1430)

- *(wizard)* Filter active roles and add infra vars to dynamic inventory (#1431)

- *(approval)* Add auth, input validation, and security hardening (#1402)

- *(wizard)* Filter active roles and add infra vars to dynamic inventory (#1431)

- *(analytics)* Raise bug prediction file limit and fix display (#1430)

- *(slm)* Route voice API through SLM backend proxy (#1429)

- *(analytics)* Prevent 409 retry storm in CodebaseAnalytics (#1432)

- *(frontend)* Correct knowledge index endpoint in CodebaseAnalytics (#1421)

- *(workflow)* Remove duplicate openPreview declaration in WorkflowTemplateGallery.vue (#1425)

- *(analytics)* Add missing currentScanId ref to scan runner (#1418)

- *(ci)* Bump langchain-core 0.3.68→0.3.83 to resolve pip conflict

- *(tts)* Normalize audio to 90% peak for consistent volume (#1394)

- *(tts)* Normalize audio to 90% peak for consistent volume (#1394)

- *(i18n)* Replace hardcoded title strings in KnowledgeUpload.vue (#1410)

- *(config)* Migrate TTS worker from .22 to .24 (#1394)

- *(chromadb)* Fix HNSW space, seq_id, pickle bugs in ChromaDB 0.5.23 (#1390)

- *(monitoring)* Correct Prometheus metrics_path for autobot-backend (#1397)

- *(ansible)* Add secure VNC password generation to vnc and browser roles (#1392)

- *(analytics)* Pattern analysis batching, checkpointing and zombie cleanup (#1370)

- *(chat)* Resolve 4 E501 line-length violations in SSE yield lines (#1339)

- *(workflow)* Address code review feedback for WorkflowStateMachine (#1380)

- *(shared)* Address code review feedback for ServiceMessageBus (#1379)

- *(slm)* Add fallback SLM Manager detection by node_id prefix (#1369)

- *(chat+voice)* Prevent message disappearance and voice echo loop (#1371)

- *(workflow)* Completed history, view-workflow, template edit (#1367)

- *(slm)* Wire DecommissionPreflightResponse as response_model (#1369)

- *(security)* Add auth to MEDIUM severity API files (#1360)

- *(analytics)* Consolidate dual progress blocks into single unified status bar (#1366)

- *(analytics)* Prevent dual status blocks on codebase analytics (#1365)

- *(chat)* Set message type immediately on stream creation to prevent filter flicker (#1364)

- *(chromadb)* Paginate collection.get() to avoid SQLite 999-variable limit (#1361)

- *(backend)* Add router-level auth to 16 unprotected API files (#1354)

- *(backend)* Add router-level auth to 16 unprotected API files (#1354)

- *(backend)* Migrate legacy ChromaDB collection configs for 0.5.x (#1355)

- *(slm-backend)* Generate role-based Ansible inventory groups (#1346)

- *(backend)* Call graph/bug prediction 502 + indexing watchdog (#1341)

- *(templates)* Remove invalid metadata kwarg from WorkflowStep (#1338)

- *(analytics)* Use background task for pattern summary fallback (#1332)

- *(analytics)* Add missing clear-stuck endpoints to all bg-task routers (#1304)

- *(voice)* Deploy ort-wasm-simd-threaded.mjs for hands-free VAD (#1322)

- *(analytics)* Prevent false orphan detection in multi-worker backend (#1320)

- *(voice)* Barge-in cancels queue worker + tts_task null guard (#1319)

- *(voice)* Add COOP/COEP headers for SharedArrayBuffer + better errors (#1311)

- *(chat)* Remove fleet hosts from main UI, add message type badges (#1310)

- *(voice)* Filter non-response messages from auto-speak TTS

- *(rag)* Category filter fallback when no documents match (#1305)

- *(nginx)* Add WebSocket proxy for workflow automation (#1308)

- Orchestrator attr rename, error_boundary API, stats bar alignment (#1307)

- *(chat)* Dark-mode CSS, tag cleanup, and Body() annotation (#1302)

- *(analytics)* Report embedding progress and lower subprocess priority (#1303)

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

- Remove obsolete finished and legacy reports

- Update stale directory paths and metrics across 245 docs (#1452)

- Add design and plan docs for node decommission and message bus (#1370)

- Add streaming TTS implementation plan (#1319)

- Add streaming sentence-level TTS design (#1319)

- *(release)* Add release system implementation plan (#1296)

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

- *(monitoring)* Extract unique compat endpoints to registered routers (#1283)

- *(router)* Register services/advanced_workflow, delete obsolete prototype (#1280)

- *(analytics)* Route-based source, no auto-load, stop button (#1458)

- *(analytics)* Create landing page with project cards (#1458)

- *(analytics)* Add landing page routes and i18n keys (#1458)

- *(analytics)* Add source summary endpoint for landing page (#1458)

- *(analytics)* Add cancel support to scan runner (#1458)

- *(i18n)* Add translated locale files for 6 languages (#1335)

- *(llm)* Add formal adapter registry for LLM backends (#1403)

- *(approval)* Add approval gates for agent workflows (#1402)

- *(voice)* Add language awareness to voice conversation pipeline (#1334)

- *(analytics)* Convert bug prediction to background task with progress (#1418)

- *(analytics)* Add background task endpoints for bug prediction (#1418)

- *(analytics)* Add scan progress bar and sequential scan runner (#1418)

- *(analytics)* Add useAnalyticsScanRunner composable (#1418)

- *(cost)* Add per-agent cost tracking backend (#1401)

- *(cost)* Add AgentCostPanel and BI dashboard integration (#1401)

- *(templates)* Community template descriptions, secrets metadata, and UI (#1415)

- *(templates)* Community template icon and secrets workflow usage (#1415)

- *(browser)* Add interactive screenshot component and backend proxy (#1416)

- *(browser)* Add interactive control endpoints to playwright-server (#1416)

- *(voice)* TTS voice-per-language mapping in personality profiles (#1333)

- *(secrets)* System secrets management with encrypted storage (#1417)

- *(tts)* Wire vault_hf_token to tts-worker role defaults (#1411)

- *(i18n)* Locale persistence in usePreferences composable (#1331)

- *(i18n)* Language switcher component in Settings (#1330)

- *(voice)* STT multilingual support with Whisper airgapped fallback (#1329)

- *(i18n)* Wire TranslationAgent to chat tool shortcuts (#1328)

- *(i18n)* Inject language instruction into all agent system prompts (#1327)

- *(voice)* Add language parameter to TTS synthesize endpoint (#1326)

- *(chat)* Add language parameter to chat API request models (#1325)

- *(knowledge)* Consolidate doc indexing with ChromaDB as single source (#1385)

- *(slm)* Async provisioning + fleet-wide role uniqueness (#1384, #1389)

- *(i18n)* Extract chat/knowledge/analytics/terminal strings and fix remaining hardcoded text (#1318)

- *(i18n)* Extract remaining App/desktop/feature-flag strings (#1318)

- *(i18n)* Extract UI/base/auth/misc strings to translation keys (#1359)

- *(workflow)* Integrate WorkflowStateMachine into workflow listing (#1380)

- *(workflow)* Integrate state machine routing into workflow executor (#1380)

- *(api+ui)* Add service message query API and timeline widget (#1379)

- *(workflow)* Add Redis-persisted WorkflowStateMachine with route_next (#1380)

- *(shared)* Add serialization helpers for ServiceMessage (#1377)

- *(rag)* Add predicate-bounded cache invalidation (#1378)

- *(rlm)* Add recursive document summarizer to knowledge pipeline (#1383)

- *(shared)* Add ServiceMessageBus for cross-service audit trail (#1379)

- *(rag)* Add topic-level retrieval context cache (#1376)

- *(rag)* Add SHA-256 content fingerprinting for KB cache invalidation (#1375)

- *(rlm)* Wire AdaptiveRAGRefiner into RAG optimizer (#1382)

- *(rlm)* Add benchmark and adaptive RAG refinement (#1381, #1382)

- *(rag)* Add context sufficiency evaluation for cached responses (#1374)

- *(shared)* Add ServiceMessage schema for cross-service communication (#1377)

- *(ansible)* Decouple VNC from browser-service role (#1363)

- *(slm)* Wire decommission action into fleet UI (#1369)

- *(rlm)* Add recursive self-reflection to LangGraph chat workflow (#1373)

- *(rag)* Add semantic query cache with cosine similarity matching (#1372)

- *(slm)* Add DecommissionModal component (#1369)

- *(slm)* Add decommission API functions to useRoles (#1369)

- *(slm)* Add decommission preflight + execute endpoints (#1369)

- *(slm)* Add decommission-node Ansible playbook (#1369)

- *(workflow)* Add completed workflows API client and state (#1367)

- *(slm)* Add disk cleanup to remove-role playbook (#1369)

- *(i18n)* Extract knowledge/workflow strings to translation keys (#1358)

- *(slm)* Add DECOMMISSIONED node status (#1369)

- *(browser)* Wire browser tools into chat AI tool dispatch (#1368)

- *(i18n)* Extract analytics/charts strings to translation keys (#1357)

- *(browser)* Expose CDP endpoint and configure custom MCP server (#1368)

- *(i18n)* Batch 2 — Settings/Terminal/LLM/Profile string extraction (#1356)

- *(slm)* Surface detected_roles and show running/assigned/available state per chip (#1353)

- *(slm-frontend)* Group required/optional roles and auto-inject infra roles in step 5 (#1350, #1349, #1344)

- *(i18n)* Extract VoiceSettingsPanel default label (#1356)

- *(i18n)* Extract SettingsPanel strings to translation keys (#1356)

- *(slm)* Add required and degraded_without fields to RoleInfo (#1350)

- *(i18n)* Add language_code field to PersonalityProfile (#1324)

- *(i18n)* Extract chat module strings to translation keys (#1318)

- *(frontend)* Add tabbed layout to ProfileModal (#1340)

- *(slm-frontend)* Add useTimezone composable for fleet-wide date formatting

- *(i18n)* Install vue-i18n and create locale scaffolding (#1323)

- *(personality)* Add built-in Rude personality profile

- *(voice)* Use streaming TTS in _dispatchTranscript (#1319)

- *(voice)* Replace auto-speak with sentence accumulator (#1319)

- *(voice)* Add WS streaming TTS in useVoiceOutput (#1319)

- *(voice)* Add sentence-level streaming TTS queue worker (#1319)

- *(vision)* Restore deleted vision views and re-wire routes (#1301)

- *(frontend)* Wire CodebaseAnalytics to background task endpoints (#1304)

- *(analytics)* Add background pattern summary analysis (#1304)

- *(analytics)* Add background dashboard overview analysis (#1304)

- *(analytics)* Add BackgroundTaskManager to code intelligence (#1304)

- *(analytics)* Migrate duplicate analysis to BackgroundTaskManager (#1304)

- *(analytics)* Shared background task manager with Redis persistence (#1304)

- *(slm)* General settings defaults, wizard card, and time sync timeout (#1306)

- *(installer)* Fix install script + setup wizard end-to-end (#1294)

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

- Document .worktrees/ preference in CLAUDE.md

- Add .worktrees/ to .gitignore for parallel worktree support

- Add Obsidian editor config files to gitignore

- *(release)* Replace manual changelog with git-cliff generated version (#1296)

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

- *(chat)* Remove per-chunk debug logging in SSE stream (#1313)

- *(chat)* Use list accumulation for O(1) streaming append (#1313)

- *(chat)* Batch DB writes and O(1) message lookups (#1316)

- *(chat)* Yield progress indicator before RAG retrieval (#1315)

- *(chat)* Virtual scrolling for message list (#1314)

- *(chat)* Throttle streaming updates, memoize formatting, consolidate watchers (#1312)

- *(chat)* Defer per-chunk regex filtering and tag-boundary detection (#1313)

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

- *(step-evaluator)* Extract _check_judge_errors helper (#1464)

- *(agents)* Consolidate web research into single module (#1443)

- *(slm-frontend)* Adopt useTimezone in views (batch 2/2)

- *(slm-frontend)* Adopt useTimezone in views (batch 1/2)

- *(analytics)* Extract loader functions into reusable composables (#1321)

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


### Build

- *(deps)* Bump @modelcontextprotocol/sdk to 1.26.0 (security fix GHSA-345p-7cg4-v4c7)

- *(deps)* Bump cryptography and pillow (safe subset of #1435)

- *(deps)* Bump qs

- *(deps)* Safe dependency bumps from #1388 review

- *(deps)* Safe dependency bumps from #1388 review


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

- *(ansible)* Migrate TTS worker from .22 to .24 in inventory (#1394)

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



