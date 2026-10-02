"""Puts one question to an ``MCPServer`` over a real client session, without a socket.

The client and server are joined by in-memory streams, so the exchange goes
through the server's dispatcher and middleware and is as deterministic as a
function call.
"""

from collections.abc import Awaitable, Callable
from typing import TypeVar

import anyio
from mcp.client.session import ClientSession
from mcp.server.mcpserver import MCPServer
from mcp.shared.memory import create_client_server_memory_streams

Answer = TypeVar("Answer")


async def ask(server: MCPServer, question: Callable[[ClientSession], Awaitable[Answer]]) -> Answer:
    """Put one question to ``server`` over an initialized in-memory session.

    The answer is collected into a list because it is produced inside a task
    group, and a plain local would be unbound on any path that leaves early.
    """
    answers: list[Answer] = []
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        client_read, client_write = client_streams
        server_read, server_write = server_streams
        lowlevel = server._lowlevel_server  # pyright: ignore[reportPrivateUsage]

        async with anyio.create_task_group() as group:

            async def serve() -> None:
                """Serve until the session closes and the group is cancelled."""
                await lowlevel.run(
                    server_read,
                    server_write,
                    lowlevel.create_initialization_options(),
                    raise_exceptions=True,
                )

            group.start_soon(serve)
            async with ClientSession(client_read, client_write) as session:
                await session.initialize()
                answers.append(await question(session))
            group.cancel_scope.cancel()
        return answers[0]
