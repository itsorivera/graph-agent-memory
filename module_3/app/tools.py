"""SupportBot's five business tools, backed by the Acme Cloud SQLite database.

These are ordinary PydanticAI tools: async functions whose first argument is
`RunContext[ToolDeps]`. The docstring and type hints become the tool schema the
model sees. Each tool also records its input, executed SQL, output and duration
in `deps.collector`, which the UI's trace panel shows.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext, Tool, ToolDefinition

from lib import db as dbx


@dataclass
class ToolDeps:
    """Per-turn dependencies passed to every tool through `RunContext.deps`."""

    db_path: Path
    collector: list[dict[str, Any]] = field(default_factory=list)
    # Selected by the operator in the UI, never inferred by the model:
    account_email: str | None = None
    incident_id: str | None = None
    authorize_refund: bool = False
    # Used by the memory tools (memory_tools.py), new in module 3:
    namespace: str = "workshop"
    current_message_id: str | None = None
    embedder: Any = None


def _json_safe(value):
    """Render NaN/inf as strings so a rejected refund attempt stays valid JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _record(
    ctx: RunContext[ToolDeps],
    name: str,
    tool_input: dict,
    sql: str | None,
    started: float,
    output: Any,
) -> Any:
    """Append one tool call to the trace collector and return its output unchanged."""
    ctx.deps.collector.append(
        {
            "name": name,
            "input": _json_safe(tool_input),
            "sql": sql,
            "output": _json_safe(output),
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
        }
    )
    return output


async def lookup_account(ctx: RunContext[ToolDeps], customer_email: str) -> dict[str, Any]:
    """Read a customer's plan, organization, refund limit and refund history by email."""
    started = time.monotonic()
    statements: list[str] = []
    with dbx.connect(ctx.deps.db_path, audit=statements) as conn:
        out = dbx.lookup_account(conn, customer_email)
    return _record(
        ctx,
        "lookup_account",
        {"customer_email": customer_email},
        "\n".join(statements),
        started,
        out or {"error": f"no account for {customer_email}"},
    )


async def search_product_catalog(ctx: RunContext[ToolDeps], query: str) -> dict[str, Any]:
    """Search the Acme Cloud product catalog by name, description, or category."""
    started = time.monotonic()
    statements: list[str] = []
    with dbx.connect(ctx.deps.db_path, audit=statements) as conn:
        out = dbx.search_products(conn, query)
    return _record(
        ctx,
        "search_product_catalog",
        {"query": query},
        "\n".join(statements),
        started,
        {"matches": out, "count": len(out)},
    )


async def fetch_policy(ctx: RunContext[ToolDeps], topic: str) -> dict[str, Any]:
    """Fetch an Acme Cloud policy by topic (refund, sla, api_key_rotation, data_export)."""
    started = time.monotonic()
    statements: list[str] = []
    with dbx.connect(ctx.deps.db_path, audit=statements) as conn:
        out = dbx.fetch_policy(conn, topic)
    return _record(
        ctx,
        "fetch_policy",
        {"topic": topic},
        "\n".join(statements),
        started,
        out or {"error": f"no policy for topic '{topic}'"},
    )


async def check_service_status(ctx: RunContext[ToolDeps], service: str) -> dict[str, Any]:
    """Read an Acme Cloud status snapshot with its observation timestamp."""
    started = time.monotonic()
    statements: list[str] = []
    with dbx.connect(ctx.deps.db_path, audit=statements) as conn:
        out = dbx.service_status(conn, service)
    return _record(
        ctx,
        "check_service_status",
        {"service": service},
        "\n".join(statements),
        started,
        {
            "services": out,
            "status": "known" if out else "unknown",
            "source": "sqlite:service_status",
            "notice": None
            if out
            else "No status source for this service; do not infer health from memory or Wikipedia.",
        },
    )


async def issue_refund(
    ctx: RunContext[ToolDeps], customer_email: str, amount: float, reason: str
) -> dict[str, Any]:
    """Issue a refund, validated against the plan's no-approval limit from policy."""
    started = time.monotonic()
    statements: list[str] = []
    with dbx.connect(ctx.deps.db_path, audit=statements) as conn:
        out = dbx.issue_refund(
            conn,
            customer_email,
            amount,
            reason,
            incident_id=ctx.deps.incident_id,
            authorized_email=ctx.deps.account_email,
            authorized=ctx.deps.authorize_refund,
        )
    return _record(
        ctx,
        "issue_refund",
        {"customer_email": customer_email, "amount": amount, "reason": reason},
        "\n".join(statements),
        started,
        out,
    )


async def prepare_refund(
    ctx: RunContext[ToolDeps], definition: ToolDefinition
) -> ToolDefinition | None:
    """Offer the write tool only for an explicitly selected and authorized case."""
    if ctx.deps.authorize_refund and ctx.deps.account_email and ctx.deps.incident_id:
        return definition
    return None


SQLITE_TOOLS = [
    lookup_account,
    search_product_catalog,
    fetch_policy,
    check_service_status,
    Tool(issue_refund, prepare=prepare_refund),
]
