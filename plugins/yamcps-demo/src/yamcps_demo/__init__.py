"""Minimal standalone yamcps connector."""

import logging
from collections.abc import Iterable
from pathlib import Path

from mcp.server import MCPServer

logger = logging.getLogger("yamcps.connectors.demo")


class DemoConnector:
    id = "demo"

    def register(self, server: MCPServer) -> None:
        @server.tool()
        async def demo_echo(message: str) -> str:
            """Return the message unchanged."""
            logger.debug("Handling demo_echo")
            return message

    def skill_roots(self) -> Iterable[Path]:
        return [Path(__file__).parent / "skills" / "demo-echo"]
