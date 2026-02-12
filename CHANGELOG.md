# AutoBot Changelog

All notable changes to AutoBot will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added - Infrastructure
- **Grafana External Host Support** (#854)
  - Migration playbook for moving Grafana to dedicated VM
  - Ansible role variables for local vs external deployment
  - CORS configuration for cross-origin iframe embedding
  - Comprehensive documentation for external Grafana setup
  - Quick reference card with common commands and troubleshooting

### Fixed - Monitoring
- **Grafana Dashboard Display** (#853)
  - Fixed missing `serve_from_sub_path` configuration
  - Deployed 14 AutoBot dashboard JSON files
  - Enabled anonymous authentication for iframe embedding
  - Configured allow_embedding and cookie_samesite settings
  - Fixed nginx proxy_pass to preserve /grafana/ prefix
  - Fixed frontend dashboard ID mapping for all 6 dashboard types

### Changed - Ansible
- Made Grafana installation and configuration conditional
- Nginx proxy template now uses variables for Grafana host
- Added optional CORS headers for external Grafana instances

## Previous Changes

See project memory at `~/.claude/projects/-home-kali-Desktop-AutoBot/memory/MEMORY.md` for historical changes.
