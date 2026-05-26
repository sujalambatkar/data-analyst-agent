"""
Seed script: creates products, customers, and sales tables.
~5000 sales rows across 2020-2024 with realistic seasonality and YoY growth.
"""

import os
import random
from datetime import date, timedelta

from dotenv import load_dotenv
from sqlalchemy import (
    Column, Date, Float, ForeignKey, Integer, MetaData,
    String, Table, create_engine, text,
)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/sales_db")

# ── Products ──────────────────────────────────────────────────────────────────
PRODUCTS = [
    # (name, category, unit_price)
    ("Widget Pro",             "Electronics",  49.99),
    ("Widget Ultra",           "Electronics",  99.99),
    ("Widget Lite",            "Electronics",  19.99),
    ("PowerBank 20K",          "Electronics",  39.99),
    ("Webcam HD",              "Electronics",  59.99),
    ("Smart Speaker",          "Electronics",  79.99),
    ("Wireless Charger",       "Electronics",  34.99),
    ("Noise-Cancel Earbuds",   "Electronics", 149.99),
    ("Wireless Mouse",         "Peripherals",  29.99),
    ("Ergonomic Mouse",        "Peripherals",  49.99),
    ("Mechanical Keyboard",    "Peripherals",  89.99),
    ("Compact Keyboard",       "Peripherals",  59.99),
    ("Gaming Headset",         "Peripherals",  79.99),
    ("USB Hub 7-Port",         "Peripherals",  29.99),
    ("DataCable USB-C",        "Accessories",   9.99),
    ("DataCable Lightning",    "Accessories",   9.99),
    ("Laptop Stand",           "Accessories",  24.99),
    ("Cable Organizer",        "Accessories",  14.99),
    ("Screen Cleaner Kit",     "Accessories",   7.99),
    ("Monitor 24in",           "Displays",    199.99),
    ("Monitor 27in",           "Displays",    299.99),
    ("Monitor 32in Ultra",     "Displays",    499.99),
    ("Portable Monitor",       "Displays",    249.99),
    ("Antivirus Pro",          "Software",     29.99),
    ("Productivity Suite",     "Software",     79.99),
    ("Cloud Backup 1TB",       "Software",     49.99),
    ("Password Manager",       "Software",     19.99),
    ("Desk Organizer",         "Office",       19.99),
    ("Document Scanner",       "Office",      149.99),
    ("Label Maker",            "Office",       39.99),
]

REGIONS = ["North", "South", "East", "West", "Central", "Northeast", "Southwest"]
SEGMENTS = ["Consumer", "SMB", "Enterprise"]
CHANNELS = ["Online", "In-Store", "Phone"]

FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Barbara", "David", "Susan", "Richard", "Jessica", "Joseph", "Sarah",
    "Thomas", "Karen", "Charles", "Lisa", "Emma", "Liam", "Olivia", "Noah",
    "Ava", "Sophia", "Ethan", "Isabella", "Mason", "Mia",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Wilson", "Taylor", "Anderson", "Thomas", "Jackson", "White", "Harris", "Martin",
    "Thompson", "Moore", "Young", "Allen", "King", "Wright", "Lopez", "Hill",
    "Scott", "Green", "Adams", "Baker", "Nelson", "Carter",
]

# Monthly seasonal multipliers (1=Jan ... 12=Dec)
MONTHLY_FACTOR = {
    1: 0.70, 2: 0.75, 3: 0.90, 4: 0.95, 5: 1.00, 6: 1.00,
    7: 0.85, 8: 1.05, 9: 1.10, 10: 1.10, 11: 1.40, 12: 1.60,
}

# YoY growth factor applied per year relative to 2020
YEAR_GROWTH = {2020: 1.00, 2021: 1.12, 2022: 1.27, 2023: 1.45, 2024: 1.65}

# Region popularity weight
REGION_WEIGHT = {
    "East": 18, "West": 16, "Northeast": 15, "North": 14,
    "Central": 13, "South": 13, "Southwest": 11,
}

# Segment quantity ranges
SEG_QTY = {"Consumer": (1, 10), "SMB": (5, 40), "Enterprise": (20, 100)}


def quarter_for(d: date) -> int:
    return (d.month - 1) // 3 + 1


def seed() -> None:
    engine = create_engine(DATABASE_URL)
    meta = MetaData()

    products_tbl = Table(
        "products", meta,
        Column("id",         Integer, primary_key=True, autoincrement=True),
        Column("name",       String(100), nullable=False),
        Column("category",   String(50),  nullable=False),
        Column("unit_price", Float,       nullable=False),
    )

    customers_tbl = Table(
        "customers", meta,
        Column("id",               Integer, primary_key=True, autoincrement=True),
        Column("first_name",       String(50),  nullable=False),
        Column("last_name",        String(50),  nullable=False),
        Column("email",            String(120), nullable=False, unique=True),
        Column("region",           String(30),  nullable=False),
        Column("segment",          String(20),  nullable=False),
        Column("acquisition_date", Date,        nullable=False),
    )

    sales_tbl = Table(
        "sales", meta,
        Column("id",          Integer, primary_key=True, autoincrement=True),
        Column("product_id",  Integer, ForeignKey("products.id"),  nullable=False),
        Column("customer_id", Integer, ForeignKey("customers.id"), nullable=False),
        Column("quantity",    Integer, nullable=False),
        Column("unit_price",  Float,   nullable=False),
        Column("revenue",     Float,   nullable=False),
        Column("sale_date",   Date,    nullable=False),
        Column("quarter",     Integer, nullable=False),
        Column("year",        Integer, nullable=False),
        Column("region",      String(30), nullable=False),
        Column("channel",     String(20), nullable=False),
        Column("segment",     String(20), nullable=False),
    )

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS sales"))
        conn.execute(text("DROP TABLE IF EXISTS customers"))
        conn.execute(text("DROP TABLE IF EXISTS products"))

    meta.create_all(engine)

    random.seed(42)

    with engine.begin() as conn:
        # ── Insert products ───────────────────────────────────────────────────
        product_ids = []
        for name, category, price in PRODUCTS:
            row = conn.execute(
                products_tbl.insert()
                .values(name=name, category=category, unit_price=price)
                .returning(products_tbl.c.id)
            ).fetchone()
            product_ids.append((row[0], price))

        # ── Insert customers ──────────────────────────────────────────────────
        region_pool = [r for r, w in REGION_WEIGHT.items() for _ in range(w)]
        customer_ids = []
        used_emails: set[str] = set()

        for i in range(300):
            fn = random.choice(FIRST_NAMES)
            ln = random.choice(LAST_NAMES)
            base_email = f"{fn.lower()}.{ln.lower()}{i}@example.com"
            # guarantee uniqueness
            email = base_email
            suffix = 0
            while email in used_emails:
                suffix += 1
                email = f"{fn.lower()}.{ln.lower()}{i}_{suffix}@example.com"
            used_emails.add(email)

            region = random.choice(region_pool)
            # segment distribution: 50% Consumer, 35% SMB, 15% Enterprise
            segment = random.choices(SEGMENTS, weights=[50, 35, 15])[0]
            acq_date = date(2019, 1, 1) + timedelta(days=random.randint(0, 365 * 5))

            row = conn.execute(
                customers_tbl.insert()
                .values(
                    first_name=fn, last_name=ln, email=email,
                    region=region, segment=segment, acquisition_date=acq_date,
                )
                .returning(customers_tbl.c.id)
            ).fetchone()
            customer_ids.append((row[0], region, segment))

        # ── Insert sales ──────────────────────────────────────────────────────
        start_date = date(2020, 1, 1)
        end_date   = date(2024, 12, 31)
        date_range = (end_date - start_date).days

        sales_rows = []
        for _ in range(5000):
            sale_date = start_date + timedelta(days=random.randint(0, date_range))
            pid, unit_price = random.choice(product_ids)
            cid, cust_region, segment = random.choice(customer_ids)

            lo, hi = SEG_QTY[segment]
            qty = random.randint(lo, hi)

            seasonal  = MONTHLY_FACTOR[sale_date.month]
            growth    = YEAR_GROWTH[sale_date.year]
            # small per-sale noise ±5%
            noise     = random.uniform(0.95, 1.05)
            revenue   = round(qty * unit_price * seasonal * growth * noise, 2)

            channel = random.choices(CHANNELS, weights=[60, 30, 10])[0]

            sales_rows.append({
                "product_id":  pid,
                "customer_id": cid,
                "quantity":    qty,
                "unit_price":  unit_price,
                "revenue":     revenue,
                "sale_date":   sale_date,
                "quarter":     quarter_for(sale_date),
                "year":        sale_date.year,
                "region":      cust_region,
                "channel":     channel,
                "segment":     segment,
            })

        conn.execute(sales_tbl.insert(), sales_rows)

    print(
        f"Seeded {len(PRODUCTS)} products, 300 customers, "
        f"and {len(sales_rows)} sales rows (2020-2024)."
    )


if __name__ == "__main__":
    seed()
