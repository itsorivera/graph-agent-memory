# Frontend and backend contract

`make dev MODULE=N` serves the selected local agent on :8000 and Vite on :5173.
Health polling recovers from startup delays; the launcher prints Ready only when
both HTTP surfaces respond. There is no module selector in the URL query string.

| Route | Contract |
| --- | --- |
| GET /api/health | status, module and active memory_layers. Startup capability checks are in make check. |
| POST /api/chat | message, session_id, request_id, account_email, incident_id, authorize_refund, policy_plan. Only operator-selected case metadata authorizes a write. |
| GET /api/accounts, /api/cases | Current SQL identities and billing cases for explicit selection. |
| GET /api/operations/{request_id} | Saved local operation response; inspect before retrying uncertain completion. |
| GET /api/graph | layer=all/short_term/long_term/reasoning; optional session_id. Explicit JSON-safe Neo4j maps; bounded newest subset; embeddings omitted; truncated flag. |
| GET /api/replays | Saved immutable CLI/extraction/enrichment artifacts plus their conversation IDs for live graph scope. |
| GET /api/replays/{id} | Actual measured replay plus an NVL graph projection; extraction snapshots identify fixed-transcript provenance. |
| POST /api/eval | Optional id; starts one isolated evaluation, returns 202 and its ID. Reusing the ID reads the existing operation. |
| GET /api/eval | Saved evaluation list only, no model calls or business writes. |
| GET /api/eval/{id} | Running/partial/final results, rubric checks, source IDs, timings and errors. |
| GET /api/graph/nams | Existing module-5-only hosted graph proxy; unchanged by this non-NAMS work. |

Chat responses contain reply, canonical session_id, request_id, tool_calls, status,
execution_status, business_status, warnings, timing and context. Tool calls retain
actual executed SQL (with bound values rendered by SQLite's trace callback), input,
output and duration; memory tools have sql=null. The reject-only server policy check
has origin=server_validation, distinct from a model-selected tool.

context.evidence lists source IDs and paths: recent_conversation, semantic_message,
grounded_entity, customer_preference or reasoning_trace. context.hydrated records
pre-answer grounding; written_layers identifies writes separately. A response may
be degraded when persistence/retrieval is unavailable even when a business action
already completed. Receipts preserve the result. Incident uniqueness prevents a
second refund regardless of request retry ID.

NVL shape: nodes[{id,labels,properties}], relationships[{id,from,to,type,properties}],
truncated, session_id. Relationship endpoints are in the returned induced subgraph.
Current conversation, All stored memory, saved output projections and Live memory
for each replay conversation are explicit choices.
A session-scoped graph includes the User and HAS_PREFERENCE edges for a customer
mentioned in that conversation. The owner identifier ties the customer's SQL
email to the memory namespace. The broader All stored memory view includes other
customers. Selecting a node exposes its incoming and outgoing edges for keyboard navigation.

Choosing a saved replay switches the evidence panel to its recorded turns.
A comparison separates the control and treatment, a restart exposes its process
IDs, and a fixed-transcript extraction exposes its SHA-256. Returning to Current
conversation restores evidence from browser turns, stored per module in localStorage.
