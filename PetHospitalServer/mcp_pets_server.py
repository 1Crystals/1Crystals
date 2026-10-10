from mcp.server.mcpserver import MCPServer
from mcp.types import Tool, TextContent
import httpx
import json


PET_HOSPITAL_BASE = "http://127.0.0.1:8080"


async def list_pets_tool() -> dict:
    """Call GET /api/v1/pets from PetHospitalServer and return the pet data."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{PET_HOSPITAL_BASE}/api/v1/pets", timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        return data


def list_pets_tool_def() -> Tool:
    """Create the list_pets tool definition."""
    return Tool(
        name="list_pets",
        description="List pets from the pet hospital API with filtering, sorting, and pagination",
        inputSchema={
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "name": {"type": "string"},
                "ownerName": {"type": "string"},
                "ownerPhone": {"type": "string"},
                "species": {"type": "string"},
                "doctor": {"type": "string"},
                "disease": {"type": "string"},
                "status": {"type": "string"},
                "min": {"type": "number"},
                "max": {"type": "number"},
                "sortBy": {"type": "string"},
                "order": {"type": "string"},
                "page": {"type": "integer"},
                "pageSize": {"type": "integer"},
            },
        },
    )


async def list_pets_call(tool_name: str, arguments: dict | None) -> list[TextContent]:
    """Call the list_pets tool and return results."""
    if tool_name == "list_pets":
        data = await list_pets_tool()
        items = data.get("data", {}).get("items", [])
        total = data.get("data", {}).get("total", len(items))
        page = data.get("data", {}).get("page", 1)
        pageSize = data.get("data", {}).get("pageSize", len(items))

        result_text = f"Pet list (page {page}, pageSize {pageSize}, total {total}):\n"
        for pet in items:
            pname = pet.get('name', 'Unknown')
            species = pet.get('species', '?')
            owner = pet.get('ownerName', '?')
            status = pet.get('status', '?')
            result_text += f"- {pname}({species}) - Owner: {owner} - Status: {status}\n"
        result_text += f"\nRaw: {json.dumps(data, ensure_ascii=False, indent=2)}"
        return [TextContent(type="text", text=result_text)]
    raise ValueError(f"Unknown tool: {tool_name}")


def create_mcp_server() -> MCPServer:
    """Create an MCP server instance with the list_pets tool registered."""
    # Initialize MCPServer with the tool added via add_tool
    s = MCPServer(
        name="pet-hospital-mcp",
        version="1.0.0",
        tools=[list_pets_tool_def()],
    )

    return s


async def main():
    mcp_server = create_mcp_server()

    # Run the MCP server using StreamableHTTP transport
    # This handles both old protocol (with handshake) and new protocol (2026-07-28, stateless)
    await mcp_server.run_streamable_http_async(
        host="127.0.0.1",
        port=8081,
        streamable_http_path="/mcp",
        json_response=False,
        stateless_http=True,  # No session tracking - each request independent (no handshake, no long links)
    )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())