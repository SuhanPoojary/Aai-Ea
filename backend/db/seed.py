"""Idempotent synthetic seed data for AegisSupport.

All people, email addresses, orders, and transaction references are fictional.
The seed keeps existing demo customers/orders and adds related catalog,
payment, shipment, and order-item records.
"""
from sqlalchemy.orm import Session
from .models import (
    Customer, Order, Product, OrderItem, Payment, Shipment, UserAccount
)
import base64
import hashlib
import os


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256."""
    salt = os.urandom(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        600_000,
    )
    return (
        "pbkdf2_sha256$600000$"
        + base64.b64encode(salt).decode("ascii")
        + "$"
        + base64.b64encode(password_hash).decode("ascii")
    )

PRODUCTS = [
    ("PRD001", "Noise-Cancelling Headphones X2", "Audio", "Wireless over-ear headphones", 8999, 120),
    ("PRD002", "Wired Earbuds E1", "Audio", "Wired stereo earbuds", 799, 250),
    ("PRD003", "Yoga Mat Pro", "Fitness", "Non-slip exercise mat", 1499, 90),
    ("PRD004", "Smart Watch S5", "Wearables", "Smart watch with activity tracking", 12499, 65),
    ("PRD005", "Premium Plan Annual", "Subscription", "Annual digital premium plan", 4999, 999),
    ("PRD006", "Mechanical Keyboard", "Computers", "Mechanical keyboard", 4299, 75),
    ("PRD007", "USB-C Hub", "Accessories", "Multiport USB-C hub", 2199, 100),
    ("PRD008", "USB-A Hub H1", "Accessories", "USB-A hub", 999, 140),
    ("PRD009", "Desk Lamp D2", "Home", "Adjustable LED desk lamp", 1899, 80),
    ("PRD010", "Wireless Charger W1", "Accessories", "Qi wireless charging pad", 1299, 150),
]

CUSTOMERS = [
    ("C001", "Aarav Mehta", "Premium", "aarav@example.test", "Mumbai"),
    ("C002", "Diya Shah", "Standard", "diya@example.test", "Pune"),
    ("C003", "Kabir Rao", "Premium", "kabir@example.test", "Thane"),
    ("C004", "Mira Iyer", "Standard", "mira@example.test", "Navi Mumbai"),
    ("C005", "Ishaan Patel", "Gold", "ishaan@example.test", "Mumbai"),
    ("C006", "Anaya Kulkarni", "Standard", "anaya@example.test", "Pune"),
    ("C007", "Reyansh Nair", "Premium", "reyansh@example.test", "Bengaluru"),
    ("C008", "Sara Khan", "Standard", "sara@example.test", "Hyderabad"),
    ("C009", "Vivaan Joshi", "Gold", "vivaan@example.test", "Delhi"),
    ("C010", "Myra Desai", "Standard", "myra@example.test", "Ahmedabad"),
    ("C011", "Arjun Menon", "Premium", "arjun@example.test", "Kochi"),
    ("C012", "Aditi Rao", "Standard", "aditi@example.test", "Chennai"),
]

ORDERS = [
    ("ORD12345", "C001", "Noise-Cancelling Headphones X2", "Wired Earbuds E1", "delivered", 8999, "success", "BlueDart", "Delivered"),
    ("ORD33410", "C001", "Yoga Mat Pro", "", "processing", 1499, "success", "Aegis Express", "Ships in 1–2 days"),
    ("ORD22001", "C004", "Smart Watch S5", "", "payment_failed", 12499, "debited_not_confirmed", "—", "Order confirmation pending"),
    ("ORD44100", "C003", "Premium Plan Annual", "", "paid", 4999, "success", "Digital", "Active"),
    ("ORD12006", "C002", "Mechanical Keyboard", "", "shipped", 4299, "success", "BlueDart", "Expected in 2 days"),
    ("ORD12007", "C005", "USB-C Hub", "USB-A Hub H1", "delivered", 2199, "success", "Delhivery", "Delivered"),
    ("ORD12008", "C006", "Desk Lamp D2", "", "delivered", 1899, "success", "Delhivery", "Delivered"),
    ("ORD12009", "C007", "Wireless Charger W1", "", "processing", 1299, "success", "Aegis Express", "Ships in 1–2 days"),
    ("ORD12010", "C008", "Premium Plan Annual", "", "paid", 4999, "success", "Digital", "Active"),
    ("ORD12011", "C009", "Mechanical Keyboard", "", "payment_failed", 4299, "debited_not_confirmed", "—", "Order confirmation pending"),
    ("ORD12012", "C010", "Noise-Cancelling Headphones X2", "", "shipped", 8999, "success", "BlueDart", "Expected in 3 days"),
    ("ORD12013", "C011", "USB-C Hub", "", "cancelled", 2199, "refunded", "Delhivery", "Cancelled and refunded"),
    ("ORD12014", "C012", "Smart Watch S5", "", "processing", 12499, "success", "Aegis Express", "Ships in 1–2 days"),
]


def seed_demo(db: Session):
    # Add missing customers without overwriting user changes.
    for cid, name, tier, email, city in CUSTOMERS:
        if not db.get(Customer, cid):
            db.add(Customer(
                id=cid, name=name, tier=tier, email=email, city=city,
                account_status="Active"
            ))
    db.flush()

    # Product catalog.
    for pid, name, category, description, price, stock in PRODUCTS:
        if not db.get(Product, pid):
            db.add(Product(
                id=pid, name=name, category=category,
                description=description, price=price, stock=stock
            ))
    db.flush()

    # Existing orders are preserved; add only missing order records.
    for row in ORDERS:
        oid, cid, item, delivered, status, amount, pay_status, courier, eta = row
        if not db.get(Order, oid):
            db.add(Order(
                id=oid, customer_id=cid, item=item, delivered_item=delivered,
                status=status, amount=amount, payment_status=pay_status,
                courier=courier, eta=eta
            ))
    db.flush()

    # Seed related rows for all known orders.
    product_by_name = {p.name: p for p in db.query(Product).all()}
    for order in db.query(Order).all():
        product = product_by_name.get(order.item)
        if product and not db.query(OrderItem).filter_by(order_id=order.id).first():
            db.add(OrderItem(
                order_id=order.id, product_id=product.id,
                product_name=order.item, quantity=1, unit_price=order.amount
            ))

        if not db.query(Payment).filter_by(order_id=order.id).first():
            db.add(Payment(
                id=f"PAY-{order.id}",
                order_id=order.id,
                customer_id=order.customer_id,
                amount=order.amount,
                status=order.payment_status,
                method="UPI" if int(order.id[-1], 36) % 2 else "Card",
                transaction_ref=f"TXN-{order.id}",
            ))

        if order.courier not in ("—", "Digital") and not db.query(Shipment).filter_by(order_id=order.id).first():
            db.add(Shipment(
                id=f"SHP-{order.id}",
                order_id=order.id,
                courier=order.courier,
                tracking_code=f"AEG-{order.id[-5:]}",
                status=order.status,
                estimated_delivery=order.eta,
            ))

    # Demo login accounts use a documented demo-only password.
    # Change these before deploying anywhere public.
    demo_password = "Demo@12345"
    for cid, name, tier, email, city in CUSTOMERS:
        account = db.query(UserAccount).filter_by(customer_id=cid).first()
        if not account:
            db.add(UserAccount(
                customer_id=cid,
                email=email,
                password_hash=hash_password(demo_password),
                role="customer",
                is_active=True,
            ))

    db.commit()
