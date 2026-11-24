---
type: fix
scope: backend
issue: 21943
pr: 22014
---
A not-found, conflict, forbidden or bad request no longer answers "Internal server error". Every 4xx that said so (109 sites across the Company OS, knowledge, user-management and SLM routes, for example `GET /api/llc/companies/<missing id>`) now answers its fixed text from the one refusal table in `autobot_shared.http_refusal`, extended with 401 and 429; a new guard fails any 4xx that says "Internal server error".
The error boundary's 4xx message now uses the same wording as a route's refusal (`REFUSAL_TEXT`, through `refusal_text()`): for example "Not found" and "Forbidden" instead of "The requested resource was not found." and "You do not have access to this resource.". 5xx and service categories keep their own wording.
