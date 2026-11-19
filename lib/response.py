"""The JSON envelope every lesson returns from POST /api/chat.

This is transport, not agent behavior: it gives the shared frontend one shape
(docs/frontend-contract.md) no matter which memory layers a lesson uses.
"""

from __future__ import annotations

from typing import Any

REFUND_TOOLS = ("issue_refund", "refund_policy_guard")


def business_status(tool_calls: list[dict[str, Any]]) -> str:
    """The outcome of the latest refund attempt in this turn, or "no_action"."""
    return next(
        (c["output"]["status"] for c in reversed(tool_calls) if c["name"] in REFUND_TOOLS),
        "no_action",
    )


def build_response(
    *,
    reply: str,
    session_id: str,
    request_id: str,
    tool_calls: list[dict[str, Any]],
    execution_ok: bool,
    warnings: list[dict[str, Any]],
    timing: dict[str, Any],
    evidence: list[dict[str, Any]] | None = None,
    hydrated: list[str] | None = None,
    written_layers: list[str] | None = None,
) -> dict[str, Any]:
    evidence = evidence or []
    paths = list(dict.fromkeys(e["path"] for e in evidence))
    if not execution_ok:
        status = "failed"
    elif warnings:
        status = "degraded"
    else:
        status = "completed"
    return {
        "reply": reply,
        "session_id": session_id,
        "request_id": request_id,
        "tool_calls": tool_calls,
        "status": status,
        "execution_status": "succeeded" if execution_ok else "failed",
        "business_status": business_status(tool_calls),
        "warnings": warnings,
        "timing": timing,
        "context": {
            "used_memory": bool(evidence),
            "summary": ", ".join(paths) or None,
            "evidence": evidence,
            "hydrated": hydrated or [],
            "written_layers": written_layers or [],
        },
    }
