"""A tool that refuses a call tells the caller why, through the MCP dispatcher.

The MCP server hands the caller a ``ToolError``'s message and reduces every other
exception to ``Error executing tool <name>``. Scenario executors and the run
browser refuse by raising ``ValueError``, so without ``surface_value_errors`` an
agent told "only the field observer can stabilize" would read a generic failure
and have nothing to correct.
"""

import anyio
from mcp.client.session import ClientSession
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent

from glossogen.mcp_tool_rejection import surface_value_errors
from glossogen.runtime.scenario_mcp_tool import ToolContext, calling_agent_id, resolve_agent_id
from tests.fakes.in_memory_mcp_session import ask

REFUSAL = "Only the field observer can stabilize Veyru entities"
STABILIZE = "stabilize_veyru"
CRASH = "crash"


async def stabilize(ctx: ToolContext, action: str) -> str:
    """Refuse anyone but the field observer, the way a scenario executor does."""
    if resolve_agent_id(ctx=ctx) != "field_observer":
        raise ValueError(REFUSAL)
    return f"stabilized with {action}"


async def crash() -> str:
    """Fail with something no tool raises on purpose."""
    raise KeyError("internal detail")


def build_server(wrap: bool) -> MCPServer:
    """Register both tools, wrapped as production registers them or bare."""
    server = MCPServer(name="rejection-probe")
    if wrap:
        server.tool(name=STABILIZE, description="scenario")(surface_value_errors(tool_fn=stabilize))
        server.tool(name=CRASH, description="scenario")(surface_value_errors(tool_fn=crash))
    else:
        server.tool(name=STABILIZE, description="scenario")(stabilize)
        server.tool(name=CRASH, description="scenario")(crash)
    return server


def call_as(server: MCPServer, agent_id: str, tool_name: str) -> CallToolResult:
    """Call ``tool_name`` as ``agent_id`` and return the result the client receives."""

    async def call(session: ClientSession) -> CallToolResult:
        """Send the call with the one argument ``stabilize`` takes."""
        arguments: dict[str, str] = {}
        if tool_name == STABILIZE:
            arguments = {"action": "gentle"}
        return await session.call_tool(tool_name, arguments)

    async def run() -> CallToolResult:
        """Set the identity for the duration of the exchange."""
        token = calling_agent_id.set(agent_id)
        try:
            return await ask(server, call)
        finally:
            calling_agent_id.reset(token)

    return anyio.run(run)


def text_of(result: CallToolResult) -> str:
    """Return the text the caller was shown."""
    return " ".join(part.text for part in result.content if isinstance(part, TextContent))


def test_a_refusal_reaches_the_caller_in_its_own_words() -> None:
    """The agent reads the sentence the executor wrote, so it can stop retrying."""
    result = call_as(
        server=build_server(wrap=True), agent_id="stabilization_engineer", tool_name=STABILIZE
    )

    assert result.is_error is True
    assert REFUSAL in text_of(result)


def test_the_wrapped_tool_still_runs_and_hides_its_context_parameter() -> None:
    """Wrapping must not change the schema the model sees or what an allowed call does.

    The server finds the context parameter from the function's annotations; a
    wrapper that lost them would publish ``ctx`` as an argument the model has to
    fill in.
    """
    server = build_server(wrap=True)

    async def schema(session: ClientSession) -> list[str]:
        """Return the argument names ``stabilize`` advertises."""
        listed = await session.list_tools()
        tool = next(entry for entry in listed.tools if entry.name == STABILIZE)
        return sorted(tool.input_schema["properties"])

    assert anyio.run(ask, server, schema) == ["action"]
    result = call_as(server=server, agent_id="field_observer", tool_name=STABILIZE)
    assert result.is_error is False
    assert text_of(result) == "stabilized with gentle"


def test_an_unwrapped_refusal_is_reduced_to_a_generic_failure() -> None:
    """The library behaviour the wrapper exists for.

    If this starts failing, the MCP library surfaces ``ValueError`` text again and
    ``surface_value_errors`` can go.
    """
    result = call_as(
        server=build_server(wrap=False), agent_id="stabilization_engineer", tool_name=STABILIZE
    )

    assert result.is_error is True
    assert REFUSAL not in text_of(result)


def test_a_crash_keeps_its_details_on_the_server() -> None:
    """Only ``ValueError`` is translated: a crash's text is internal, not guidance."""
    result = call_as(server=build_server(wrap=True), agent_id="field_observer", tool_name=CRASH)

    assert result.is_error is True
    assert "internal detail" not in text_of(result)
