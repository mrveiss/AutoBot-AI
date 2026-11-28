---
type: fix
scope: ai-ml
issue: 21929
pr: 0000
---
A provider rate limit (429) no longer reports one attempt twice. The rate-limit check now runs before the response is reported, so a rate-limited attempt ends in a single `notify_error` carrying the `RateLimitError`, and the retry is its own attempt with its own start and end. The Prometheus `requests_in_flight` gauge no longer drifts below zero under sustained rate limiting, the 429 still counts as an error, and the completion counter no longer counts a request that failed.
