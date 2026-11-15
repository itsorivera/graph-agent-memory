# Glossary

One sentence per term, in plain English. Written for a developer who has never touched
Neo4j, graphs, or PydanticAI. Linked from every module README.

## The basics

- <a id="llm"></a>**LLM** — A large language model (here, OpenAI's) is the AI engine that reads text and writes replies by predicting plausible continuations — it does not "know" facts on its own.
- <a id="embedding"></a>**Embedding** — A numeric fingerprint of a piece of text (a list of numbers) that lets a computer find text with similar *meaning*, even when the words are different.
- <a id="graph"></a>**Graph** — A way of storing information as connected things (customers, products, tickets) instead of rows in tables, so the connections are first-class citizens.
- <a id="node"></a>**Node** — One "thing" in a graph — a customer, a product, a message — drawn as a circle.
- <a id="edge"></a>**Edge** — A connection between two nodes — "customer REPORTED incident" — drawn as a line (also called a relationship).
- <a id="label"></a>**Label** — A tag on a node that says what kind of thing it is, like `Customer` or `Message`.
- <a id="property"></a>**Property** — A key–value fact stored on a node or edge, like `email: "maya@example.com"` on a `Customer` node.
- <a id="cypher"></a>**Cypher** — Neo4j's query language, where you describe the graph *pattern* you want (it reads a bit like ASCII art) instead of writing table joins.
- <a id="neo4j"></a>**Neo4j** — A graph database: a database built to store nodes and edges and answer questions about connections quickly.
- <a id="auradb"></a>**AuraDB** — Neo4j's hosted cloud service: a managed Neo4j database you create at console.neo4j.io without installing anything.
- <a id="sqlite"></a>**SQLite** — A tiny database that lives in a single file (here, `data/acme_cloud.db`) and needs no server — the workshop's stand-in for a company's real business database.

## The agent stack

- <a id="agent"></a>**Agent** — A program that pairs an LLM with instructions and tools so it can decide what to do, call the tools, and act — not just chat.
- <a id="tool"></a>**Tool** — A plain function the agent is allowed to call (like `lookup_account`) so it can fetch real data or take real actions instead of guessing.
- <a id="pydanticai"></a>**PydanticAI** — A Python library for building agents: you declare the tools and the shapes of results, and it handles talking to the LLM reliably.

## The memory system

- <a id="short-term-memory"></a>**Short-term memory** — The stored record of the current conversation (the messages, in order) so the agent survives restarts and continues mid-chat.
- <a id="long-term-memory"></a>**Long-term memory** — The facts and entities distilled from conversations — who the customer is, their plan, their preferences — that persist across sessions.
- <a id="reasoning-memory"></a>**Reasoning memory** — Records of *how* the agent solved past tasks (steps, tool calls, outcomes) so it can recall procedures, not just facts.
- <a id="ontology"></a>**Ontology** — A written definition of what kinds of things and relationships exist in your domain (here, `module_3/ontology/acme_cloud.yaml`) — a schema that extraction must follow.
- <a id="poleo"></a>**POLE+O** — The memory library's built-in generic ontology (Person, Organization, Location, Event, + Object), which this workshop replaces with an Acme Cloud–specific one.
- <a id="entity-extraction"></a>**Entity extraction** — Automatically finding the people, companies, products, etc. mentioned in a conversation and adding them to the graph as typed nodes.
- <a id="entity-resolution"></a>**Entity resolution** — Recognizing that two mentions ("Acme Cloud" and "AcmeCloud") are the same thing and merging them into one node.
- <a id="hydration"></a>**Hydration** — Filling in an extracted entity's facts (email, plan, signup date) from the real business database, instead of letting the LLM invent them.
- <a id="enrichment"></a>**Enrichment** — Adding outside knowledge (here, Wikipedia summaries and links) to entities about real-world third parties like Stripe.
- <a id="trace"></a>**Trace** — A recorded play-by-play of one agent run: the task, each step, each tool call with its inputs and outputs, and the outcome.
- <a id="provenance"></a>**Provenance** — Being able to point at exactly which message, tool call, or trace a piece of knowledge came from — the graph's receipts.
- <a id="skill-distillation"></a>**Skill distillation** — Deriving a reusable procedure from selected agent memory, packaging it as SKILL.md, and retaining source links for review.
- <a id="grounding-score"></a>**Grounding score** — A signal of how much of a generated skill is supported by source evidence. Inspect individual links and test the procedure against current policy.
- <a id="coverage-score"></a>**Coverage score** — A signal of how much of the selected evidence the generated procedure represents.
- <a id="nams"></a>**NAMS** — The Neo4j Agent Memory Service (memory.neo4jlabs.com): a hosted, managed version of the same memory system, used in module 5.
- <a id="bolt-backend"></a>**Bolt backend** — Running the memory system against *your own* Neo4j database over the Bolt protocol (support apps in modules 2–5), instead of the hosted NAMS service.

## The workshop machinery

- <a id="codespaces"></a>**Codespaces** — GitHub's browser-based dev environment: click the badge, get a prebuilt Linux machine in the cloud with everything already installed.
- <a id="uv"></a>**uv** — A fast Python package manager that installs the exact pinned dependency versions from `uv.lock`, so every attendee's environment is identical.
