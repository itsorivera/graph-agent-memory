#!/usr/bin/env python3
"""Seed the Acme Cloud SQLite system of record.

Creates data/acme_cloud.db with deterministic seed data so every agent tool
returns meaningful results from the very first message (Module 1 design note).
Setup preserves existing workshop data. An explicit reseed replaces it.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.db import ensure_case_schema
from lib.settings import AppSettings

DB_PATH = AppSettings().db_path

SCHEMA = """
CREATE TABLE organizations (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, industry TEXT
);
CREATE TABLE plans (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, tier TEXT NOT NULL,
    monthly_price REAL NOT NULL, refund_limit REAL NOT NULL
);
CREATE TABLE customers (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
    organization_id INTEGER REFERENCES organizations(id),
    plan_id INTEGER REFERENCES plans(id), signup_date TEXT NOT NULL,
    preferred_contact TEXT DEFAULT 'email'
);
CREATE TABLE products (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, sku TEXT NOT NULL,
    description TEXT NOT NULL, category TEXT NOT NULL
);
CREATE TABLE features (
    id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products(id),
    name TEXT NOT NULL, description TEXT
);
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id),
    product_id INTEGER REFERENCES products(id), status TEXT NOT NULL,
    started_at TEXT NOT NULL
);
CREATE TABLE policies (
    id INTEGER PRIMARY KEY, topic TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
    body TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE service_status (
    id INTEGER PRIMARY KEY, service TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
    detail TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE refunds (
    id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id),
    amount REAL NOT NULL, reason TEXT, status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

ORGANIZATIONS = [
    ("Northwind Robotics", "robotics"),
    ("Contoso Ltd", "logistics"),
]

PLANS = [
    # name, tier, monthly_price, refund_limit (no-approval ceiling)
    ("Free", "free", 0.0, 0.0),
    ("Pro", "pro", 49.0, 250.0),
    ("Enterprise", "enterprise", 999.0, 500.0),
]

CUSTOMERS = [
    # name, email, org, plan, signup_date
    ("Maya Chen", "maya.chen@northwind.example", "Northwind Robotics", "Pro", "2025-03-14"),
    ("Dana Whitfield", "dana.w@contoso.example", "Contoso Ltd", "Enterprise", "2024-11-02"),
    ("Ravi Shah", "ravi.shah@northwind.example", "Northwind Robotics", "Pro", "2025-06-30"),
]

PRODUCTS = [
    (
        "Acme Cloud Compute",
        "ACC-100",
        "Autoscaling container compute for production workloads.",
        "compute",
    ),
    (
        "Acme Cloud Storage",
        "ACS-200",
        "Object storage with lifecycle policies and CDN edge caching.",
        "storage",
    ),
    (
        "Acme Cloud Functions",
        "ACF-300",
        "Event-driven serverless functions with sub-second cold starts.",
        "compute",
    ),
    (
        "Acme Cloud Billing API",
        "ACB-400",
        "Usage metering, invoicing, and payment-webhook APIs.",
        "platform",
    ),
]

FEATURES = [
    ("Acme Cloud Compute", "Autoscaling", "Horizontal autoscaling based on CPU/RPS targets."),
    ("Acme Cloud Compute", "Spot Capacity", "Discounted preemptible capacity for batch jobs."),
    (
        "Acme Cloud Billing API",
        "Payment Webhooks",
        "Outbound webhooks for invoice and payment events.",
    ),
    (
        "Acme Cloud Billing API",
        "Usage Metering",
        "Per-minute usage metering with export to CSV/JSON.",
    ),
    ("Acme Cloud Storage", "Lifecycle Policies", "Automatic archival and expiry rules per bucket."),
]

SUBSCRIPTIONS = [
    ("maya.chen@northwind.example", "Acme Cloud Compute", "active", "2025-03-14"),
    ("maya.chen@northwind.example", "Acme Cloud Billing API", "active", "2025-04-02"),
    ("dana.w@contoso.example", "Acme Cloud Storage", "active", "2024-11-02"),
    ("dana.w@contoso.example", "Acme Cloud Functions", "active", "2025-01-19"),
    ("ravi.shah@northwind.example", "Acme Cloud Compute", "trialing", "2025-06-30"),
]

POLICIES = [
    (
        "refund",
        "Refund Policy",
        "Refunds up to the plan's no-approval limit (Free $0, Pro $250, Enterprise $500) "
        "are granted immediately for charges within the last 30 days. Amounts above the "
        "limit require engineering-manager approval via ticket escalation. Duplicate "
        "charges are always refundable regardless of amount.",
        "2026-01-15",
    ),
    (
        "sla",
        "Service Level Agreement",
        "Pro plans carry a 99.9% monthly uptime SLA; Enterprise 99.95% with service "
        "credits of 10% per 0.1% below target. Credits are applied automatically.",
        "2025-12-01",
    ),
    (
        "api_key_rotation",
        "API Key Rotation",
        "API keys must be rotated every 90 days. Keys older than 90 days are flagged in "
        "the dashboard; keys older than 180 days are deactivated automatically.",
        "2026-02-10",
    ),
    (
        "data_export",
        "Data Export & Deletion",
        "Customers may export all workspace data as JSON from Settings → Export. "
        "Deletion requests are honored within 30 days per the privacy policy.",
        "2025-10-20",
    ),
]

SERVICE_STATUS = [
    ("Acme Cloud Compute", "operational", "All regions nominal.", "2026-10-27T08:00:00Z"),
    ("Acme Cloud Storage", "operational", "All regions nominal.", "2026-10-27T08:00:00Z"),
    (
        "Acme Cloud Functions",
        "degraded",
        "Elevated cold-start latency in us-east-1.",
        "2026-10-27T07:42:00Z",
    ),
    ("Acme Cloud Billing API", "operational", "Webhook delivery nominal.", "2026-10-27T08:00:00Z"),
    ("Stripe", "operational", "Third-party payments integration nominal.", "2026-10-27T08:00:00Z"),
]


def seed(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO organizations (name, industry) VALUES (?, ?)", ORGANIZATIONS)
        conn.executemany(
            "INSERT INTO plans (name, tier, monthly_price, refund_limit) VALUES (?, ?, ?, ?)",
            PLANS,
        )
        for name, email, org, plan, signup in CUSTOMERS:
            conn.execute(
                "INSERT INTO customers (name, email, organization_id, plan_id, signup_date) "
                "VALUES (?, ?, (SELECT id FROM organizations WHERE name = ?), "
                "(SELECT id FROM plans WHERE name = ?), ?)",
                (name, email, org, plan, signup),
            )
        conn.executemany(
            "INSERT INTO products (name, sku, description, category) VALUES (?, ?, ?, ?)",
            PRODUCTS,
        )
        for product, fname, fdesc in FEATURES:
            conn.execute(
                "INSERT INTO features (product_id, name, description) "
                "VALUES ((SELECT id FROM products WHERE name = ?), ?, ?)",
                (product, fname, fdesc),
            )
        for email, product, status, started in SUBSCRIPTIONS:
            conn.execute(
                "INSERT INTO subscriptions (customer_id, product_id, status, started_at) "
                "VALUES ((SELECT id FROM customers WHERE email = ?), "
                "(SELECT id FROM products WHERE name = ?), ?, ?)",
                (email, product, status, started),
            )
        conn.executemany(
            "INSERT INTO policies (topic, title, body, updated_at) VALUES (?, ?, ?, ?)",
            POLICIES,
        )
        conn.executemany(
            "INSERT INTO service_status (service, status, detail, updated_at) VALUES (?, ?, ?, ?)",
            SERVICE_STATUS,
        )
        conn.commit()
    finally:
        conn.close()
    with sqlite3.connect(path) as migration:
        ensure_case_schema(migration)


def main(*, if_missing: bool = False) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if if_missing and DB_PATH.exists():
        print(f"Using existing workshop SQLite database at {DB_PATH}")
        return
    # Build a complete seed before replacing a database or exposing a new one.
    with tempfile.TemporaryDirectory(dir=DB_PATH.parent) as folder:
        staged = Path(folder) / "seed.db"
        seed(staged)
        if if_missing:
            try:
                os.link(staged, DB_PATH)
            except FileExistsError:
                print(f"Using existing workshop SQLite database at {DB_PATH}")
                return
        else:
            staged.replace(DB_PATH)
    counts = sqlite3.connect(DB_PATH)
    summary = {
        t: counts.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in (
            "customers",
            "organizations",
            "products",
            "features",
            "plans",
            "subscriptions",
            "policies",
            "service_status",
        )
    }
    counts.close()
    print(f"Seeded {DB_PATH}")
    for table, count in summary.items():
        print(f"  {table}: {count} rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--if-missing", action="store_true", help="Keep an existing workshop database")
    main(if_missing=parser.parse_args().if_missing)
