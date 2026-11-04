
import time

from .common import event
from db.models import Customer, Order, Ticket


def find_matching_orders(message, orders):
    """Find orders whose product names match words in the message."""
    import re

    words = {
        word.lower()
        for word in re.findall(r"[a-zA-Z0-9]+", message or "")
        if len(word) > 2
    }
    if not words:
        return []

    matches = []
    for order in orders:
        name_words = {
            word.lower()
            for word in re.findall(r"[a-zA-Z0-9]+", order.item)
            if len(word) > 2
        }
        if name_words and len(words & name_words) / len(name_words) >= 0.4:
            matches.append(order)
    return matches


def _order_data(order):
    return {
        "id": order.id,
        "item": order.item,
        "delivered_item": order.delivered_item,
        "status": order.status,
        "amount": order.amount,
        "payment_status": order.payment_status,
        "courier": order.courier,
        "eta": order.eta,
        "purchase_date": (
            order.purchase_date.isoformat()
            if getattr(order, "purchase_date", None)
            else None
        ),
    }


def run(db, customer_id, order_id=None, message=""):
    started = time.perf_counter()
    customer = db.get(Customer, customer_id)

    if not customer:
        return {
            "customer_found": False,
            "customer_id": customer_id,
            "order": None,
            "orders": [],
            "matching_orders": [],
            "ownership_verified": False,
        }, event(
            "Context Agent",
            "Look up customer and validate ownership",
            "Customer not found",
            started,
            "warning",
        )

    # Always retrieve only this customer's orders.
    customer_orders = (
        db.query(Order)
        .filter(Order.customer_id == customer_id)
        .order_by(Order.id.asc())
        .all()
    )
    orders_data = [_order_data(order) for order in customer_orders]

    selected_order = None
    ownership_verified = True

    if order_id:
        candidate = db.get(Order, order_id)

        if candidate and candidate.customer_id == customer_id:
            selected_order = candidate
        else:
            ownership_verified = False

    ticket_count = (
        db.query(Ticket)
        .filter(Ticket.customer_id == customer_id)
        .count()
    )

    context = {
        "customer_found": True,
        "customer_id": customer.id,
        "name": customer.name,
        "tier": customer.tier,
        "city": customer.city,
        "account_status": customer.account_status,
        "past_ticket_count": ticket_count,
        "order": (
            _order_data(selected_order)
            if selected_order else None
        ),
        "orders": orders_data,
        "matching_orders": [
            _order_data(order)
            for order in find_matching_orders(message, customer_orders)
        ],
        "ownership_verified": ownership_verified,
    }

    if order_id and not ownership_verified:
        output = (
            "Requested order not found for this customer; "
            "no order details disclosed."
        )
        status = "warning"
    else:
        output = (
            f"Verified customer {customer.id}; "
            f"retrieved {len(customer_orders)} owned order(s); "
            + (
                f"verified order {order_id}"
                if selected_order
                else "no specific order selected"
            )
        )
        status = "success"

    return context, event(
        "Context Agent",
        "Retrieve customer profile, full order history and verify ownership",
        output,
        started,
        status,
    )
