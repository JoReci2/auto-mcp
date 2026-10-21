"""Radarr connector with vault-backed credentials and an embedded skill."""

from collections.abc import Iterable
from pathlib import Path

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from hmcp import ConnectorSecrets, SecretError, SecretSpec
from hmcp_radarr.client import RadarrClient
from hmcp_radarr.service import RadarrService


class RadarrConnector:
    """Expose library browsing, movie additions and searches through Radarr API v3."""

    id = "radarr"

    def __init__(self) -> None:
        """Create an unconfigured instance without network access."""
        self._service: RadarrService | None = None

    def required_secrets(self) -> list[SecretSpec]:
        """Describe instance settings collected by hmcp's terminal wizard.

        Returns:
            Instance URL and API key stored together in the encrypted vault.
        """
        return [
            SecretSpec("url", "Radarr instance URL, e.g. http://localhost:7878 (without /api/v3)"),
            SecretSpec("api-key", "Radarr API key (Settings > General > Security)"),
        ]

    def configure(self, secrets: ConnectorSecrets) -> None:
        """Validate settings and create the API service without making a request.

        Args:
            secrets: Values scoped to this Radarr connector.
        """
        self._service = RadarrService(
            RadarrClient(secrets.require("url").get_secret_value(), secrets.require("api-key")),
            secrets.redact,
        )

    def register(self, server: MCPServer) -> None:
        """Register fixed Radarr operations with read/write annotations.

        Args:
            server: MCP server receiving the tools.

        Raises:
            SecretError: The connector has not been configured.
        """
        if self._service is None:
            raise SecretError("Configure Radarr before registering its tools")
        read_only = [
            "system_status",
            "list_movies",
            "get_movie",
            "calendar",
            "queue",
            "lookup_movies",
            "quality_profiles",
            "root_folders",
            "command_status",
        ]
        mutations = ["add_movie", "search_movies"]
        for name in read_only + mutations:
            is_read = name in read_only
            server.add_tool(
                getattr(self._service, name),
                name=f"radarr_{name}",
                annotations=ToolAnnotations(
                    read_only_hint=is_read,
                    destructive_hint=False,
                    idempotent_hint=is_read,
                    open_world_hint=True,
                ),
            )

    def skill_roots(self) -> Iterable[Path]:
        """Locate the packaged Radarr workflow instructions.

        Returns:
            The radarr-manage skill directory.
        """
        return [Path(__file__).parent / "skills" / "radarr-manage"]
