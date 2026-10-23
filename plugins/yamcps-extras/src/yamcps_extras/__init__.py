"""Skills-only development connector for yamcps."""

from collections.abc import Iterable
from pathlib import Path

from mcp.server import MCPServer

_SKILLS = (
    "extras-configure-agents",
    "extras-develop-plugin",
)


class ExtrasConnector:
    """Supply static skills through the existing yamcps catalog."""

    id = "extras"

    def register(self, server: MCPServer) -> None:
        """Leave tool and prompt registration empty; the core serves skill resources.

        Args:
            server: MCP server receiving no additional handlers from this plugin.
        """

    def skill_roots(self) -> Iterable[Path]:
        """Locate the two bundled skill folders independently of the working directory.

        Returns:
            Skill roots resolved relative to the installed Python module.
        """
        root = Path(__file__).parent / "skills"
        return [root / name for name in _SKILLS]
