"""Business guardrails around every turn. This is not memory: the file is the same
in every lesson, so you can skip it when comparing modules.

The model proposes and the server decides. Three checks protect refunds:

1. `scope_turn` (before the model runs): the billing case the operator selected
   scopes the turn, and the server itself rejects an over-limit case.
2. `tools.issue_refund`: every refund is re-checked against current SQLite policy.
3. `checked_reply` (after the model runs): the reply cannot claim an action that
   no tool receipt supports.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from lib import db as dbx

from .tools import ToolDeps

FAILURE_REPLY = (
    "The request failed before a complete answer. Check the operation receipt before retrying."
)


@dataclass
class TurnScope:
    """What the operator selected for this turn, as extra model instructions."""

    instructions: str
    case: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    case_refund: dict[str, Any] | None = None  # An existing refund for the selected case.


def scope_turn(deps: ToolDeps, policy_plan: str | None) -> TurnScope:
    """Load the selected billing case and plan, then run the server-side refund guard."""
    lines = []
    with dbx.connect(deps.db_path) as db:
        case = dbx.case_details(db, deps.incident_id) if deps.incident_id else None
        refund = (
            db.execute(
                "SELECT id AS refund_id, amount, status FROM refunds WHERE incident_id=?",
                (deps.incident_id,),
            ).fetchone()
            if case
            else None
        )
        row = (
            db.execute(
                "SELECT name,refund_limit FROM plans WHERE name=?", (policy_plan,)
            ).fetchone()
            if policy_plan
            else None
        )
    plan = dict(row) if row else None
    case_refund = dict(refund) if refund else None
    if case:
        lines.append("Confirmed operator-selected billing case: " + json.dumps(case))
    if case_refund:
        lines.append(
            f"This case was already refunded (refund #{case_refund['refund_id']}, "
            f"${case_refund['amount']:.2f}). It cannot be refunded again."
        )
    if plan:
        lines.append(
            f"This question concerns the {plan['name']} plan only. Its current "
            f"no-approval limit is ${plan['refund_limit']:.2f}. The previous speaker's "
            "plan does not apply. Do not act on another person's account."
        )
        if case and case["plan"] != plan["name"]:
            deps.authorize_refund = False
    _reject_over_limit_case(deps)
    lines.append(f"Refund execution authorized for this turn: {deps.authorize_refund}.")
    return TurnScope("\n".join(lines), case, plan, case_refund)


def _reject_over_limit_case(deps: ToolDeps) -> None:
    """Record a server-side rejection when the authorized case exceeds the plan limit.

    The rejection appears in the tool trace with origin=server_validation, so it is
    never confused with a tool the model chose to call.
    """
    if not deps.authorize_refund or not deps.incident_id:
        return
    statements: list[str] = []
    started = time.monotonic()
    with dbx.connect(deps.db_path, audit=statements) as db:
        case = dbx.case_details(db, deps.incident_id)
        if not case or case["amount"] <= case["refund_limit"]:
            return
        result = dbx.issue_refund(
            db,
            case["email"],
            case["amount"],
            "Confirmed case policy check",
            incident_id=deps.incident_id,
            authorized_email=deps.account_email,
            authorized=True,
        )
    deps.collector.append(
        {
            "name": "refund_policy_guard",
            "origin": "server_validation",
            "input": {"incident_id": deps.incident_id},
            "output": result,
            "sql": "\n".join(statements),
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
        }
    )


def checked_reply(message: str, model_reply: str, deps: ToolDeps, scope: TurnScope) -> str:
    """The model's reply, unless a receipt or the selected plan says otherwise."""
    reply = verified_reply(message, model_reply, deps.collector)
    receipts = [c for c in deps.collector if c["name"] in ("issue_refund", "refund_policy_guard")]
    if reply != model_reply and not receipts and scope.case_refund:
        # The guard blocked an action claim; report the selected case's real state.
        refund = scope.case_refund
        reply = (
            f"Billing case {scope.case['id']} was already refunded: refund "
            f"#{refund['refund_id']}, ${refund['amount']:.2f} ({refund['status']}, SQLite "
            "refunds). No new refund was performed; a case can be refunded only once."
        )
    if scope.plan is not None and not deps.authorize_refund:
        plan = scope.plan
        reply = (
            f"{plan['name']} plan: current no-approval refund limit "
            f"${plan['refund_limit']:.2f} per request (source: SQLite plans). "
            "Larger requests require manager approval. No refund or escalation "
            "was authorized or performed for this policy question."
        )
    return reply


def failure_reply(message: str, deps: ToolDeps) -> str:
    """A safe reply when the turn failed; receipts recorded before the failure still win."""
    return verified_reply(message, FAILURE_REPLY, deps.collector)


def verified_reply(message: str, reply: str, calls: list[dict]) -> str:
    """Business receipts override unsupported action claims in model prose."""
    refunds = [c["output"] for c in calls if c["name"] in ("issue_refund", "refund_policy_guard")]
    if refunds:
        result = refunds[-1]
        if result["status"] in ("issued", "already_issued"):
            verb = "Issued" if result["status"] == "issued" else "Previously issued"
            return (
                f"{verb} refund #{result['refund_id']}: ${result['amount']:.2f} "
                f"for {result['customer']} ({result['customer_email']}, {result['plan']}). "
                f"Incident: {result['incident_id']}. This incident cannot be refunded twice."
            )
        return "No refund was issued. " + result["reason"]
    statuses = [c["output"] for c in calls if c["name"] == "check_service_status"]
    if statuses and statuses[-1].get("status") == "known":
        rows = statuses[-1]["services"]
        return "Workshop snapshot (not live monitoring): " + "; ".join(
            f"{row['service']}: {row['status']} as of {row['updated_at']} (SQLite service_status)"
            for row in rows
        )
    if statuses and statuses[-1].get("status") == "unknown":
        return (
            "Current service status is unknown: this workshop has no verified "
            "status source for that service."
        )
    lower = message.lower()
    status_question = any(
        p in lower
        for p in ("status", "outage", "operational", "having issues", "showing any issues")
    )
    if status_question and not statuses:
        return (
            "No current service status was verified in this turn. Please name "
            "an Acme Cloud service so I can check it."
        )
    escalation = "escalat" in lower or "escalat" in reply.lower()
    refund_claim = re.search(
        r"\brefunded\b|\brefund\b.{0,60}\b(issued|processed|sent|completed|approved)\b"
        r"|\b(issue[ds]?|process(?:ed)?|sent|completed)\b.{0,60}\brefund\b",
        reply,
        re.I,
    )
    if escalation or refund_claim:
        policies = [
            c["output"].get("body", "")
            for c in calls
            if c["name"] == "fetch_policy" and isinstance(c["output"], dict)
        ]
        accounts = [
            c["output"]
            for c in calls
            if c["name"] == "lookup_account"
            and isinstance(c["output"], dict)
            and "email" in c["output"]
        ]
        detail = ""
        if accounts:
            # Keep the facts the tools actually returned; only the claim is dropped.
            account = accounts[-1]
            history = account.get("refunds", [])
            detail += (
                f"Account: {account['name']} ({account['email']}), {account['plan']} plan, "
                f"no-approval refund limit ${account['refund_limit']:.2f}. "
                "Recorded SQL refund history: "
                + (
                    ", ".join(
                        f"#{r['refund_id']} ${r['amount']:.2f} ({r['status']})" for r in history
                    )
                    or "none"
                )
                + ". "
            )
        if policies:
            detail += "Current SQL policy: " + policies[-1] + " "
        return detail + (
            "No new refund or escalation was performed in this turn. "
            "Confirm a billing case for a refund; ask a manager for approval above the plan limit."
        )
    return reply
