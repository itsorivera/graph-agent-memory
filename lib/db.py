"""SQLite access for the Acme Cloud system of record (stdlib sqlite3 only).

Every query is parameterized — the tools are agent-facing, so injection safety
and typed results are part of the workshop's teaching surface.
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any


def connect(db_path: Path, *, audit: list[str] | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='refunds'").fetchone():
        ensure_case_schema(conn)
    if audit is not None:
        conn.set_trace_callback(audit.append)
    return conn


def rows_as_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


# ── Query helpers backing the agent tools ─────────────────────────────────────

LOOKUP_ACCOUNT_SQL = (
    "SELECT c.id, c.name, c.email, c.signup_date, c.preferred_contact, "
    "o.name AS organization, p.name AS plan, p.tier AS plan_tier, "
    "p.monthly_price, p.refund_limit "
    "FROM customers c "
    "LEFT JOIN organizations o ON c.organization_id = o.id "
    "LEFT JOIN plans p ON c.plan_id = p.id "
    "WHERE c.email = ?"
)

SEARCH_PRODUCTS_SQL = (
    "SELECT p.id, p.name, p.sku, p.description, p.category, "
    "GROUP_CONCAT(f.name, '; ') AS features "
    "FROM products p LEFT JOIN features f ON f.product_id = p.id "
    "WHERE p.name LIKE ? OR p.description LIKE ? OR p.category LIKE ? "
    "GROUP BY p.id"
)

FETCH_POLICY_SQL = "SELECT topic, title, body, updated_at FROM policies WHERE topic = ?"

SERVICE_STATUS_SQL = (
    "SELECT service, status, detail, updated_at FROM service_status "
    "WHERE service LIKE ? AND service LIKE 'Acme Cloud %'"
)

INSERT_REFUND_SQL = (
    "INSERT INTO refunds (customer_id, amount, reason, status, created_at) "
    "VALUES (?, ?, ?, ?, datetime('now'))"
)

CUSTOMER_PLAN_SQL = (
    "SELECT c.id, c.name, p.name AS plan, p.refund_limit FROM customers c "
    "JOIN plans p ON c.plan_id = p.id WHERE c.email = ?"
)


def lookup_account(db: sqlite3.Connection, email: str) -> dict[str, Any] | None:
    row = db.execute(LOOKUP_ACCOUNT_SQL, (email,)).fetchone()
    if row is None:
        return None
    account = dict(row)
    account["refunds"] = refund_history(db, email)
    return account


def search_products(db: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    like = f"%{query}%"
    return rows_as_dicts(db.execute(SEARCH_PRODUCTS_SQL, (like, like, like)).fetchall())


def fetch_policy(db: sqlite3.Connection, topic: str) -> dict[str, Any] | None:
    row = db.execute(FETCH_POLICY_SQL, (topic,)).fetchone()
    return dict(row) if row else None


def service_status(db: sqlite3.Connection, service: str) -> list[dict[str, Any]]:
    return rows_as_dicts(db.execute(SERVICE_STATUS_SQL, (f"%{service}%",)).fetchall())


CASES = [
    ("ravi-duplicate-compute", "ravi.shah@northwind.example", 49, "Duplicate Compute charge"),
    ("maya-duplicate-compute", "maya.chen@northwind.example", 49, "Duplicate Compute charge"),
    ("maya-spot-capacity", "maya.chen@northwind.example", 400, "Unused spot capacity"),
    ("ravi-spot-capacity", "ravi.shah@northwind.example", 400, "Ops lead Pro spot capacity"),
    ("dana-duplicate-storage", "dana.w@contoso.example", 129, "Duplicate Storage charge"),
]


def ensure_case_schema(db):
    """Add incident identifiers without removing any existing business records."""
    columns = {r[1] for r in db.execute("PRAGMA table_info(refunds)")}
    if "incident_id" not in columns:
        db.execute("ALTER TABLE refunds ADD COLUMN incident_id TEXT")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS refund_incident ON refunds(incident_id)")
    db.execute("""CREATE TABLE IF NOT EXISTS billing_cases (
        id TEXT PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),
        amount REAL NOT NULL, description TEXT NOT NULL)""")
    for case_id, email, amount, description in CASES:
        db.execute(
            """INSERT OR IGNORE INTO billing_cases
            SELECT ?, id, ?, ? FROM customers WHERE email=?""",
            (case_id, amount, description, email),
        )
    db.commit()


def billing_cases(db):
    return rows_as_dicts(
        db.execute("""SELECT b.id, b.amount, b.description,
        c.email, c.name AS customer, p.name AS plan, p.refund_limit
        FROM billing_cases b JOIN customers c ON c.id=b.customer_id
        JOIN plans p ON p.id=c.plan_id ORDER BY b.id""").fetchall()
    )


def case_details(db, incident_id):
    return next((c for c in billing_cases(db) if c["id"] == incident_id), None)


def refund_history(db, email):
    return rows_as_dicts(
        db.execute(
            """SELECT r.id AS refund_id,r.incident_id,r.amount,
        r.status,r.created_at FROM refunds r JOIN customers c ON c.id=r.customer_id
        WHERE c.email=? ORDER BY r.id DESC""",
            (email,),
        ).fetchall()
    )


def issue_refund(
    db,
    email: str,
    amount: float,
    reason: str,
    *,
    incident_id: str | None = None,
    authorized_email: str | None = None,
    authorized: bool = False,
) -> dict[str, Any]:
    """Apply a confirmed incident once; the caller, never the model, binds identity."""
    if not math.isfinite(amount) or amount <= 0:
        return {"status": "rejected_invalid_amount", "reason": "Amount must be finite and positive"}
    if not authorized or not incident_id or not authorized_email:
        return {
            "status": "requires_confirmation",
            "reason": "Select and confirm a billing case for this turn",
        }
    case = case_details(db, incident_id)
    if case is None:
        return {"status": "rejected_unknown_case", "reason": "Unknown billing case"}
    if email != authorized_email or case["email"] != authorized_email:
        return {
            "status": "rejected_wrong_account",
            "reason": "The requested account does not match the confirmed case",
        }
    if amount != case["amount"]:
        return {
            "status": "rejected_case_amount",
            "reason": "Amount differs from the confirmed charge",
        }
    evidence = {
        "customer": case["customer"],
        "customer_email": case["email"],
        "plan": case["plan"],
        "no_approval_limit": case["refund_limit"],
        "incident_id": incident_id,
        "amount": amount,
        "source": "sqlite:plans",
    }
    if amount > case["refund_limit"]:
        return {
            **evidence,
            "status": "rejected_over_limit",
            "reason": (
                f"${amount:.2f} exceeds the {case['plan']} no-approval limit of "
                f"${case['refund_limit']:.2f}; manager approval is required. "
                "No escalation has been created."
            ),
        }
    db.execute(
        """INSERT OR IGNORE INTO refunds
        (customer_id,amount,reason,status,created_at,incident_id)
        SELECT customer_id,?,?, 'issued',datetime('now'),id FROM billing_cases WHERE id=?""",
        (amount, reason, incident_id),
    )
    inserted = db.execute("SELECT changes()").fetchone()[0] == 1
    row = db.execute("SELECT id FROM refunds WHERE incident_id=?", (incident_id,)).fetchone()
    db.commit()
    return {**evidence, "status": "issued" if inserted else "already_issued", "refund_id": row[0]}
