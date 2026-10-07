"""Describe the MCP tools a simulation offers, without serving them.

Registers every tool on a throwaway server and reads back the schemas the server
would send an agent on ``tools/list``. The per-agent trimming that server applies
is middleware on the request path, so callers filter by the agent's tool names.
"""

from mcp.server.mcpserver import MCPServer

from glossogen.models.tool_definition import RecordedToolDefinition
from glossogen.runtime.mcp_tools import register_tools
from glossogen.runtime.simulation_state import SimulationRuntime


async def list_tool_definitions(runtime: SimulationRuntime) -> list[RecordedToolDefinition]:
    """Every base and scenario tool the runtime's scenario registers, with its schema."""
    server = MCPServer(name="tool-definitions")
    register_tools(mcp=server, runtime=runtime)
    definitions: list[RecordedToolDefinition] = []
    for tool in await server.list_tools():
        description = ""
        if tool.description is not None:
            description = tool.description
        definitions.append(
            RecordedToolDefinition(
                name=tool.name,
                description=description,
                input_schema=tool.input_schema,
            )
        )
    return definitions


def select_tool_definitions(
    definitions: list[RecordedToolDefinition],
    tool_names: list[str],
) -> list[RecordedToolDefinition]:
    """The definitions of ``tool_names``, in that order, once each.

    A name with no definition is skipped. Runs recorded before registration
    deduplicated its tool list name a tool twice, so repeats are dropped.
    """
    by_name = {definition.name: definition for definition in definitions}
    return [by_name[name] for name in dict.fromkeys(tool_names) if name in by_name]
