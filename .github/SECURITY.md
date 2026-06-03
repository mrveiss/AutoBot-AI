# Security Policy

## Supported Versions

Only the latest release of AutoBot AI receives security patches. We do not backport fixes to older versions.

| Version | Supported |
|---------|-----------|
| Latest  | ✅ Yes    |
| Older   | ❌ No     |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

### Preferred: GitHub Private Vulnerability Reporting

Use [GitHub's private vulnerability reporting](https://github.com/mrveiss/AutoBot-AI/security/advisories/new) to submit a report. This keeps the details confidential while we investigate and prepare a fix.

### Alternative: Email

If you prefer email, send your report to **martins.veiss@gmail.com** with the subject line:

```
[SECURITY] AutoBot AI – <short description>
```

Use PGP encryption if you have sensitive details to share (contact us first for a public key).

## What to Include

A useful report includes:

- A description of the vulnerability and its potential impact
- The component or module affected (e.g., auth, API endpoint, LLM integration, connector framework)
- Step-by-step instructions to reproduce the issue
- Any proof-of-concept code or screenshots
- The environment where you observed the issue (OS, Python version, Docker version, browser, etc.)
- Your assessment of severity (Critical / High / Medium / Low)

## Response Timeline

| Milestone | Target |
|-----------|--------|
| Initial acknowledgement | 48 hours |
| Severity assessment | 5 business days |
| Fix or mitigation available | 30 days for critical; 90 days for others |
| Public disclosure | After fix is deployed |

We follow [coordinated vulnerability disclosure](https://cheatsheetseries.owasp.org/cheatsheets/Vulnerability_Disclosure_Cheat_Sheet.html). If you need a different timeline for coordinated disclosure, let us know in your initial report and we will work with you.

## Scope

In scope for security reports:

- Authentication and authorisation bypasses
- Remote code execution (RCE)
- SQL / NoSQL injection
- Server-side request forgery (SSRF) in the crawler or LLM integrations
- Secrets or credentials exposed in logs, API responses, or config defaults
- Insecure deserialization
- Cross-site scripting (XSS) or CSRF in the web frontend
- Privilege escalation in the RBAC model
- NPU or worker process sandbox escapes

Out of scope:

- Denial-of-service (DoS) without meaningful business impact
- Social engineering of maintainers or contributors
- Issues in third-party dependencies that have a public CVE and a recommended upgrade path already documented
- Theoretical vulnerabilities without a working proof of concept

## Recognition

AutoBot AI does not operate a paid bug bounty program. We do credit security researchers publicly in the advisory and in the changelog when a fix is shipped, unless you prefer to remain anonymous.

## Security Advisories

Published advisories are available in the [GitHub Security Advisories tab](https://github.com/mrveiss/AutoBot-AI/security/advisories).

## Safe Harbour

We will not take legal action against researchers who:

- Report vulnerabilities in good faith via the channels above
- Do not exploit the vulnerability beyond what is necessary to demonstrate the issue
- Do not access or exfiltrate user data, production systems, or internal infrastructure
- Do not disclose the vulnerability publicly before we have had a reasonable opportunity to remediate it

Thank you for helping keep AutoBot AI and its users safe.
