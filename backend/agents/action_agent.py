
import asyncio
import json
import os
import sys
import time
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .common import event


# Map the orchestrator's action names to registered MCP tool names.
MCP_TOOL_MAP = {
    "get_order": "lookup_order",
    "check_refund_eligibility": "refund_eligibility",
    "initiate_return": "request_return",
    "cancel_order": "cancel_eligible_order",
    "check_account": "account_status",
}


def _parse_tool_result(result):
    """Convert an MCP tool response into a Python dictionary."""
    if result.isError:
        return {
            "ok": False,
            "message": "MCP tool execution failed.",
        }

    # Prefer structured content when the server supplies it.
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    for item in result.content:
        text = getattr(item, "text", None)
        if text:
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, TypeError):
                continue

    return {
        "ok": False,
        "message": "MCP returned no valid structured result.",
    }


async def _execute_mcp_actions(customer_id, order_id, actions, correlation_id):
    """Connect to the MCP server and execute approved actions."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=backend_dir,
    )

    results = []

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            available = await session.list_tools()
            available_names = {tool.name for tool in available.tools}

            for name in actions[:3]:
                mcp_name = MCP_TOOL_MAP.get(name)

                if not mcp_name:
                    results.append({
                        "tool": name,
                        "ok": False,
                        "message": "Action is not registered for MCP execution.",
                    })
                    break

                if mcp_name not in available_names:
                    results.append({
                        "tool": name,
                        "ok": False,
                        "message": f"MCP tool '{mcp_name}' is unavailable.",
                    })
                    break

                if name == "check_account":
                    arguments = {"customer_id": customer_id}
                elif order_id:
                    arguments = {
                        "customer_id": customer_id,
                        "order_id": order_id,
                    }
                else:
                    results.append({
                        "tool": name,
                        "ok": False,
                        "message": (
                            "Required order ID is missing; "
                            "ask the customer for it."
                        ),
                    })
                    break

                attempts = 2 if name in {"get_order", "check_refund_eligibility", "check_account"} else 1
                response = None
                for attempt in range(attempts):
                    try:
                        response = await asyncio.wait_for(
                            session.call_tool(mcp_name, arguments),
                            timeout=10,
                        )
                        break
                    except (TimeoutError, asyncio.TimeoutError):
                        if attempt + 1 == attempts:
                            results.append({"tool": name, "ok": False, "message": "MCP tool timed out.", "correlation_id": correlation_id})
                if response is None:
                    break
                data = _parse_tool_result(response)

                results.append({
                    "tool": name,
                    "correlation_id": correlation_id,
                    **data,
                })

                if not data.get("ok", False):
                    break

    return results


def run(db, customer_id, order_id, plan, correlation_id=None):
    """Execute planned actions through the actual MCP server.

    The db argument is retained for compatibility with the existing
    orchestrator. Business operations are executed by the MCP server,
    which manages its own database sessions.
    """
    started = time.perf_counter()
    results = []
    actions = plan.get("actions", [])[:3]
    correlation_id = correlation_id or uuid.uuid4().hex

    try:
        if actions:
            results = asyncio.run(
                _execute_mcp_actions(
                    customer_id,
                    order_id,
                    actions,
                    correlation_id,
                )
            )

    except Exception as exc:
        # Avoid returning internal exception details to the customer.
        print(
            f"[MCP Action Agent Error] "
            f"{type(exc).__name__}: {exc}"
        )
        results.append({
            "tool": "mcp_connection",
            "ok": False,
            "message": "Could not connect to or execute the MCP server.",
            "correlation_id": correlation_id,
        })

    summary = "; ".join(
        f"{item['tool']}: "
        f"{item.get('message', 'completed' if item.get('ok') else 'failed')}"
        for item in results
    ) or "No business action executed"

    if not results:
        status = "skipped"
    elif all(item.get("ok", False) for item in results):
        status = "success"
    else:
        status = "warning"

    trace = event(
        "Action / MCP Tools Agent",
        "Execute approved business tools through the MCP client",
        summary,
        started,
        status,
    )
    trace["correlation_id"] = correlation_id
    return results, trace
