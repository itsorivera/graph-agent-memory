"""Hydration: extracted entities get their facts from SQLite, never from the LLM.

The extractor finds *who and what* a message mentions ("Maya Chen", "Pro"). This
file looks each name up in the Acme Cloud system of record and copies the
grounded facts (email, plan, refund limit, ...) onto the entity node. When the
SQL record changes, the next mention refreshes the node.

Two writes per entity (verified in spike 0.5, docs/verification-log.md):
  1. `long_term.add_entity` is the public upsert. On an existing node it
     refreshes `description` but not its attributes, which is an upstream
     limitation.
  2. So `PropertyWriter` sets the facts as flat node properties with its own
     driver. The memory client's Cypher surface is read-only.
"""

from __future__ import annotations

from contextlib import closing
from typing import Any

from lib import db as dbx

MENTIONED_ENTITIES_CYPHER = """
MATCH (c:Conversation {session_id: $session_id})-[:HAS_MESSAGE]->(m:Message)
WHERE $message_id IS NULL OR m.id=$message_id
MATCH (m)-[:MENTIONS]->(e:Entity)
RETURN DISTINCT e.name AS name, e.type AS type, e.subtype AS subtype, e.aliases AS aliases
"""

SET_FLAT_ATTRIBUTES_CYPHER = """
MATCH (e:Entity {name: $name, type: $type})
SET e += $attributes
"""

# The POLE+O type an entity must have to receive facts from each table. A product
# name extracted as an ORGANIZATION never gets product facts.
EXPECTED_TYPE = {
    "sqlite:customers": "PERSON",
    "sqlite:products": "OBJECT",
    "sqlite:plans": "OBJECT",
    "sqlite:organizations": "ORGANIZATION",
}


class PropertyWriter:
    """Sets flat properties on entity nodes. Opens one short session per write, so
    concurrent chat turns never share a driver session."""

    def __init__(self, driver, database: str):
        self.driver = driver
        self.database = database

    async def set_properties(self, name: str, etype: str, attributes: dict) -> None:
        async with self.driver.session(database=self.database) as session:
            await session.execute_write(
                lambda tx: _run(tx, {"name": name, "type": etype, "attributes": attributes})
            )


async def _run(tx, parameters):
    await (await tx.run(SET_FLAT_ATTRIBUTES_CYPHER, parameters)).consume()


def lookup_facts(conn, name: str) -> dict[str, Any] | None:
    """Find a customer, product, plan or organization with exactly this name."""
    lname = name.lower()
    row = conn.execute(
        "SELECT c.name, c.email, c.signup_date, c.preferred_contact, "
        "o.name AS organization, p.name AS plan, p.tier AS plan_tier "
        "FROM customers c LEFT JOIN organizations o ON c.organization_id = o.id "
        "LEFT JOIN plans p ON c.plan_id = p.id WHERE lower(c.name) = ?",
        (lname,),
    ).fetchone()
    if row:
        r = dict(row)
        return {
            "description": (
                f"{r['name']} — {r['plan']} plan customer at "
                f"{r['organization']}, signed up {r['signup_date']}."
            ),
            "attributes": {
                "email": r["email"],
                "plan": r["plan"],
                "plan_tier": r["plan_tier"],
                "signup_date": r["signup_date"],
                "preferred_contact": r["preferred_contact"],
                "organization": r["organization"],
                "hydrated_from": "sqlite:customers",
            },
        }
    row = conn.execute(
        "SELECT name, sku, description, category FROM products WHERE lower(name) = ?",
        (lname,),
    ).fetchone()
    if row:
        r = dict(row)
        return {
            "description": r["description"],
            "attributes": {
                "sku": r["sku"],
                "category": r["category"],
                "hydrated_from": "sqlite:products",
            },
        }
    row = conn.execute(
        "SELECT name, tier, monthly_price, refund_limit FROM plans WHERE lower(name) = ?",
        (lname,),
    ).fetchone()
    if row:
        r = dict(row)
        return {
            "description": (
                f"{r['name']} plan — ${r['monthly_price']:.2f}/mo, "
                f"no-approval refund limit ${r['refund_limit']:.2f}."
            ),
            "attributes": {
                "tier": r["tier"],
                "monthly_price": r["monthly_price"],
                "refund_limit": r["refund_limit"],
                "hydrated_from": "sqlite:plans",
            },
        }
    row = conn.execute(
        "SELECT name, industry FROM organizations WHERE lower(name) = ?", (lname,)
    ).fetchone()
    if row:
        r = dict(row)
        return {
            "description": f"{r['name']} ({r['industry']}) — Acme Cloud customer organization.",
            "attributes": {"industry": r["industry"], "hydrated_from": "sqlite:organizations"},
        }
    return None


def grounded_facts(conn, entity: dict) -> dict[str, Any] | None:
    """Facts for one extracted entity, or None when SQL has no single safe answer.

    Entity resolution may keep a short name ("Maya") and record the full name
    ("Maya Chen") as an alias, so both are checked. Conflicting matches, or a
    match with the wrong entity type, hydrate nothing rather than guess.
    """
    names = {entity["name"], *(entity.get("aliases") or [])}
    matches = [facts for name in names if (facts := lookup_facts(conn, name)) is not None]
    if not matches:
        return None
    if any(EXPECTED_TYPE[m["attributes"]["hydrated_from"]] != entity["type"] for m in matches):
        return None
    if any(m != matches[0] for m in matches):
        return None
    return matches[0]


async def hydrate_session_entities(
    memory, session_id: str, db_path, *, message_id=None, writer: PropertyWriter | None = None
) -> list[str]:
    """Copy SQLite facts onto the entities this message (or session) mentions.

    Unknown names, such as an external company, stay unhydrated. Returns the
    names of the hydrated entities.
    """
    mentioned = await memory.query.cypher(
        MENTIONED_ENTITIES_CYPHER,
        {"session_id": session_id, "message_id": str(message_id) if message_id else None},
    )
    hydrated: list[str] = []
    # closing() matters on Windows: the context manager commits but does not
    # close, and a lingering handle blocks removing or replacing the database.
    with closing(dbx.connect(db_path)) as conn, conn:
        grounded = [(entity, grounded_facts(conn, entity)) for entity in mentioned]
    for entity, facts in grounded:
        if facts is None:
            continue
        # 1. Public upsert: creates the node if needed and refreshes its description.
        await memory.long_term.add_entity(
            entity["name"],
            entity["type"],
            subtype=entity.get("subtype"),
            description=facts["description"],
            attributes=facts["attributes"],
            resolve=False,  # Keep the resolved node's name; never merge into another.
            deduplicate=False,
            generate_embedding=False,
            enrich=False,
        )
        # 2. Flat properties, visible in the graph panel (see module docstring).
        if writer is not None:
            await writer.set_properties(entity["name"], entity["type"], facts["attributes"])
        hydrated.append(entity["name"])
    return hydrated
