---
type: fix
scope: ci
issue: 15204
pr: 0000
---
A malformed CI token can no longer reach a CI log. http.client refuses an illegal header value with ValueError("Invalid header value %r" % value), where the %r is the credential, and an unhandled ValueError in a workflow step writes its traceback to the log. ci_dispatch_watchdog now validates GITHUB_TOKEN through the new pipeline-scripts/header_safe_secret.py before the value is handed to the HTTP layer, raising a configuration error that names the fault, its position and the value's length but never the value. The check runs both where the token enters and where the API client is constructed, and main() now builds that client inside its error handler so a refusal reports cleanly instead of escaping as the traceback this prevents.
