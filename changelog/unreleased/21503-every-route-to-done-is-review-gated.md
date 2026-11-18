---
type: fix
scope: backend
issue: 21503
---

Every way of setting a work item to done now goes through the one review-gated path: the agent status call, the work-item transition and the board move. When the company's review policy requires a human review for the item's type, an agent that holds the item is answered `200` with the status `in_review` and the item goes to its reviewer (the item's reviewer, else the person who created it); no reviewer, or an agent that does not hold the item, is a `409`. A credential that is neither a person nor a known agent asking for done on such a type is also a `409`. A person marking an item done is not gated and keeps the past-reviewer and own-task rules. A completed work item now always writes the "work item completed" audit row, whichever route moved it. The agent status call now answers a refused move with `409` instead of an internal error, and reports the status as its value (`done`) rather than the enum's name. The reviewer a gated finish hands the item to must be a current member of the company, or the move is refused. With authentication disabled the single local user is treated as a person, so gated items can still be finished from the interface; an API token that is not a login session is refused.
