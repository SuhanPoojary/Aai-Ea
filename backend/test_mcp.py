
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server = StdioServerParameters(
        command="python",
        args=["-m", "mcp_server.server"],
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("=== ORDER LOOKUP ===")
            lookup = await session.call_tool(
                "lookup_order",
                {
                    "customer_id": "C001",
                    "order_id": "ORD12345",
                },
            )
            print(lookup)

            if lookup.isError:
                print("Order lookup failed.")
                return

            print("\n=== REFUND ELIGIBILITY ===")
            eligibility = await session.call_tool(
                "refund_eligibility",
                {
                    "customer_id": "C001",
                    "order_id": "ORD12345",
                },
            )
            print(eligibility)


if __name__ == "__main__":
    asyncio.run(main())
 