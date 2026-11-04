"""Standalone MCP server exposing the same guarded demo business operations.
Run from backend/: python -m mcp_server.server
Pinned to MCP SDK v1.x so FastMCP imports remain consistent.
"""
from mcp.server.fastmcp import FastMCP
from db.database import Base, engine, SessionLocal
from db.seed import seed_demo
from .business_tools import get_order, check_refund_eligibility, initiate_return, cancel_order, check_account
mcp = FastMCP("AegisSupport Business Tools")
Base.metadata.create_all(bind=engine)
with SessionLocal() as _db: seed_demo(_db)
@mcp.tool()
def lookup_order(customer_id: str, order_id: str) -> dict:
    """Look up an order only when it belongs to the supplied authenticated demo customer ID."""
    with SessionLocal() as db: return get_order(db,customer_id,order_id)
@mcp.tool()
def refund_eligibility(customer_id: str, order_id: str) -> dict:
    """Check refund eligibility; this tool does not send money."""
    with SessionLocal() as db: return check_refund_eligibility(db,customer_id,order_id)
@mcp.tool()
def request_return(customer_id: str, order_id: str) -> dict:
    """Create a demo return request only for an eligible delivered item mismatch."""
    with SessionLocal() as db: return initiate_return(db,customer_id,order_id)
@mcp.tool()
def cancel_eligible_order(customer_id: str, order_id: str) -> dict:
    """Cancel an order only when its status is processing and ownership is verified."""
    with SessionLocal() as db: return cancel_order(db,customer_id,order_id)
@mcp.tool()
def account_status(customer_id: str) -> dict:
    """Retrieve a customer's account status and tier."""
    with SessionLocal() as db: return check_account(db,customer_id)
if __name__ == "__main__": mcp.run()
