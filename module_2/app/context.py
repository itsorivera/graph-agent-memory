"""Short-term memory retrieval: what the agent recalls before each model call.

Two paths, each tagged in the evidence the UI shows:

- recent_conversation: the newest messages of *this* conversation, passed to
  PydanticAI as `message_history` so the model sees real prior turns.
- semantic_message: earlier user statements from *any* conversation in this
  namespace that are similar to the new message (vector similarity).

Why hand-written Cypher instead of `memory.short_term.search_messages()`? The
library asks the vector index for the global top-k first and filters afterwards.
Every workshop run writes into a namespace (replay-…, eval-…), so a global top-k
can be filled by other runs' messages. Scoring only this namespace's messages
keeps retrieval exact; at workshop scale the full scan is cheap.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart

RECENT_LIMIT = 10  # Turns of this conversation the model sees.
SEMANTIC_LIMIT = 5  # Similar statements from other conversations.
SIMILARITY_THRESHOLD = 0.5  # Cosine score; lower admits looser matches.


@dataclass
class Context:
    history: list[ModelMessage] = field(default_factory=list)  # → message_history
    prompt: str = ""  # Retrieved evidence appended to the instructions.
    evidence: list[dict] = field(default_factory=list)  # Everything retrieved, for the UI.


async def recent_messages(memory, session_id, *, exclude_id=None):
    """The newest messages of one conversation, returned oldest first."""
    rows = await memory.query.cypher(
        """// workshop:recent
        MATCH (:Conversation {session_id:$session_id})-[:HAS_MESSAGE]->(m:Message)
        WHERE $exclude_id IS NULL OR m.id <> $exclude_id
        RETURN m.id AS id,m.role AS role,m.content AS content
        ORDER BY m.timestamp DESC,m.id DESC LIMIT $limit""",
        {"session_id": session_id, "exclude_id": exclude_id, "limit": RECENT_LIMIT},
    )
    return list(reversed(rows))


def as_model_history(rows) -> list[ModelMessage]:
    """Convert stored messages into PydanticAI's message types."""
    history: list[ModelMessage] = []
    for row in rows:
        if row["role"] == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=row["content"])]))
        elif row["role"] == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=row["content"])]))
    return history


async def search_messages(memory, query, embedding, namespace, *, exclude_id=None):
    """Earlier user messages in this namespace that are similar to `query`."""
    rows = await memory.query.cypher(
        """// workshop:semantic
        MATCH (c:Conversation)-[:HAS_MESSAGE]->(m:Message)
        WHERE c.session_id STARTS WITH $namespace AND m.id <> coalesce($exclude_id,'')
          AND m.role='user' AND m.embedding IS NOT NULL
          AND toLower(m.content) <> toLower($query)
        WITH m,c,vector.similarity.cosine(m.embedding,$embedding) AS score
        WHERE score >= $threshold
        RETURN m.id AS id,m.role AS role,m.content AS content,
               c.session_id AS session_id,score
        ORDER BY score DESC LIMIT 40""",
        {
            "namespace": namespace + ":",
            "exclude_id": exclude_id,
            "embedding": embedding,
            "query": query,
            "threshold": SIMILARITY_THRESHOLD,
        },
    )
    evidence = []
    seen = set()
    for row in rows:
        key = row["content"].strip().casefold()
        # Skip duplicates and common recall prompts. Other questions can still
        # match, so check the cited message for the fact itself.
        if key in seen or key.startswith(
            ("do you remember", "what did we", "what is my", "who is", "how long")
        ):
            continue
        seen.add(key)
        evidence.append({**row, "path": "semantic_message"})
        if len(evidence) == SEMANTIC_LIMIT:
            break
    return evidence


async def build_context(memory, message, session_id, embedder, namespace, *, exclude_id=None):
    recent = await recent_messages(memory, session_id, exclude_id=exclude_id)
    embedding = await embedder.embed(message)
    retrieved = await search_messages(memory, message, embedding, namespace, exclude_id=exclude_id)
    return Context(
        history=as_model_history(recent),
        prompt=json.dumps(retrieved, ensure_ascii=False, default=str) if retrieved else "",
        evidence=[{**r, "path": "recent_conversation"} for r in recent] + retrieved,
    )
