"""Minimal standalone yamcps connector."""

from collections.abc import Iterable
from pathlib import Path

from mcp.server import MCPServer


class DemoConnector:
    id = "demo"

    def register(self, server: MCPServer) -> None:
        @server.tool()
        async def demo_echo(message: str) -> str:
            """Return the message unchanged."""
            return message

    def skill_roots(self) -> Iterable[Path]:
        return [Path(__file__).parent / "skills" / "demo-echo"]
