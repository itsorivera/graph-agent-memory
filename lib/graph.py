"""Graph endpoints: map Neo4j (Bolt) and NAMS (REST) graph state to the NVL shape
defined in docs/frontend-contract.md."""

from __future__ import annotations

from typing import Any

import httpx
from neo4j_agent_memory import MemoryClient

from .settings import AppSettings

_LAYER_LABELS = {
    "short_term": ["Conversation", "Message"],
    "long_term": ["Entity", "User", "Preference", "Fact"],
    "reasoning": ["ReasoningTrace", "ReasoningStep", "ToolCall", "Tool"],
}


def _labels_for_layer(layer: str) -> list[str]:
    return _LABELS_FOR_ALL if layer == "all" else _LAYER_LABELS.get(layer, _LABELS_FOR_ALL)


_LABELS_FOR_ALL = [lbl for labels in _LAYER_LABELS.values() for lbl in labels]


def _json_value(value):
    if isinstance(value, dict):
        return {k: _json_value(v) for k, v in value.items() if "embedding" not in k.lower()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if hasattr(value, "iso_format"):
        return value.iso_format()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


async def bolt_graph(
    client: MemoryClient,
    layer: str = "all",
    *,
    session_id: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Return bounded, induced graph maps, never serialized driver objects."""
    labels = _labels_for_layer(layer)
    rows = await client.query.cypher(
        """
        MATCH (n)
        WHERE any(l IN labels(n) WHERE l IN $labels)
          AND ($session_id IS NULL OR n.session_id = $session_id
            OR EXISTS {
              MATCH (c:Conversation {session_id: $session_id})-[:HAS_MESSAGE]->(msg)
              WHERE n = c OR n = msg OR (msg)-[:MENTIONS]->(n)
            }
            OR EXISTS {
              MATCH (t:ReasoningTrace {session_id: $session_id})-[:HAS_STEP*0..1]->(s)
              WHERE n = s OR (s)-[:USES_TOOL]->(n) OR (s)-[:TOUCHED]->(n)
                OR EXISTS { MATCH (s)-[:USES_TOOL]->(:ToolCall)-[:INSTANCE_OF]->(n) }
            }
            OR EXISTS {
              MATCH (:Conversation {session_id: $session_id})-[:HAS_MESSAGE]->(:Message)
                -[:MENTIONS]->(customer:Entity)
              MATCH (owner:User {identifier: $preference_namespace + customer.email})
                -[:HAS_PREFERENCE]->(preference:Preference)
              WHERE n = owner OR n = preference
            }
            OR EXISTS {
              MATCH (:Conversation {session_id: $session_id})-[:HAS_MESSAGE]->(:Message)
                -[:MENTIONS]->(e)<-[:ABOUT]-(n:Preference)
              WHERE n.category STARTS WITH $preference_namespace
            })
        WITH n ORDER BY coalesce(n.timestamp, n.created_at, n.started_at) DESC,
                        elementId(n)
        LIMIT $limit
        WITH collect(n) AS candidates
        WITH candidates[..$visible_limit] AS chosen,
             size(candidates) > $visible_limit AS truncated
        UNWIND chosen AS n
        OPTIONAL MATCH (n)-[r]->(m) WHERE m IN chosen
        RETURN {id: elementId(n), labels: labels(n), properties: properties(n)} AS n,
          CASE WHEN m IS NULL THEN null ELSE
            {id: elementId(m), labels: labels(m), properties: properties(m)} END AS m,
          CASE WHEN r IS NULL THEN null ELSE
            {id: elementId(r), from: elementId(startNode(r)),
             to: elementId(endNode(r)), type: type(r), properties: properties(r)} END AS r,
          truncated
        """,
        {
            "labels": labels,
            "session_id": session_id,
            "limit": limit + 1,
            "visible_limit": limit,
            "preference_namespace": (session_id or "").split(":")[0] + ":",
        },
    )
    nodes = {}
    relationships = {}
    for row in rows:
        for key in ("n", "m"):
            node = row.get(key)
            if node:
                nodes[str(node["id"])] = _json_value(node)
        relationship = row.get("r")
        if relationship:
            relationships[str(relationship["id"])] = _json_value(relationship)
    return {
        "nodes": list(nodes.values()),
        "relationships": list(relationships.values()),
        "truncated": any(r.get("truncated", False) for r in rows),
        "session_id": session_id,
    }


# The served skill graph: Skill -> versions -> steps -> the memory each step is
# GROUNDED_IN (entities, agent steps, tool calls). Explicit maps, one row.
NAMS_SKILL_GRAPH = """
MATCH (s:Skill)-[hv:HAS_VERSION]->(v:SkillVersion)
OPTIONAL MATCH (v)-[hs:HAS_STEP]->(st:SkillStep)
OPTIONAL MATCH (st)-[gi:GROUNDED_IN]->(g)
OPTIONAL MATCH (v)-[sup:SUPERSEDES]->(:SkillVersion)
WITH collect(DISTINCT s) + collect(DISTINCT v) + collect(DISTINCT st) + collect(DISTINCT g) AS ns,
     collect(DISTINCT hv) + collect(DISTINCT hs) + collect(DISTINCT gi)
       + collect(DISTINCT sup) AS rs
RETURN [n IN ns[..$limit] | {id: elementId(n), labels: labels(n), properties: properties(n)}]
         AS nodes,
       [r IN rs | {id: elementId(r), from: elementId(startNode(r)), to: elementId(endNode(r)),
                   type: type(r)}] AS relationships,
       size(ns) > $limit AS truncated
"""

# Large documents stored on SkillVersion nodes; the panel shows them elsewhere.
_NAMS_HIDDEN = ("skillMd", "provenanceJson", "referencesJson")


async def nams_graph(s: AppSettings, limit: int = 200) -> dict[str, Any]:
    """The skill graph from the NAMS workspace (module 5), via read-only Cypher REST."""
    if not s.nams_api_key:
        return {"nodes": [], "relationships": [], "unavailable": True}
    try:
        async with httpx.AsyncClient(
            base_url=s.nams_base_url,
            headers={"Authorization": f"Bearer {s.nams_api_key}"},
            timeout=30.0,
        ) as http:
            resp = await http.post(
                "/v1/query", json={"cypher": NAMS_SKILL_GRAPH, "params": {"limit": limit}}
            )
            resp.raise_for_status()
            rows = resp.json().get("rows", [])  # Each row is an object keyed by column.
    except httpx.HTTPError:
        return {"nodes": [], "relationships": [], "unavailable": True}
    if not rows:
        return {"nodes": [], "relationships": []}
    row = rows[0]
    nodes = [
        {
            "id": node["id"],
            "labels": node["labels"],
            "properties": _json_value(
                {k: v for k, v in node["properties"].items() if k not in _NAMS_HIDDEN}
            ),
        }
        for node in row["nodes"]
    ]
    shown = {node["id"] for node in nodes}
    relationships = [
        rel for rel in row["relationships"] if rel["from"] in shown and rel["to"] in shown
    ]
    return {"nodes": nodes, "relationships": relationships, "truncated": row["truncated"]}
