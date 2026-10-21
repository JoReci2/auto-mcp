"""Sonarr connector with vault-backed credentials and an embedded skill."""

from collections.abc import Iterable
from pathlib import Path

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from hmcp import ConnectorSecrets, SecretError, SecretSpec
from hmcp_sonarr.client import SonarrClient
from hmcp_sonarr.service import SonarrService


class SonarrConnector:
    """Expose library browsing, series additions and searches for Sonarr v3/v4."""

    id = "sonarr"

    def __init__(self) -> None:
        """Create an unconfigured instance without network access."""
        self._service: SonarrService | None = None

    def required_secrets(self) -> list[SecretSpec]:
        """Describe instance settings collected by hmcp's terminal wizard.

        Returns:
            Instance URL and API key stored together in the encrypted vault.
        """
        return [
            SecretSpec("url", "Sonarr instance URL, e.g. http://localhost:8989 (without /api/v3)"),
            SecretSpec("api-key", "Sonarr API key (Settings > General > Security)"),
        ]

    def configure(self, secrets: ConnectorSecrets) -> None:
        """Validate settings and create the API service without making a request.

        Args:
            secrets: Values scoped to this Sonarr connector.
        """
        self._service = SonarrService(
            SonarrClient(secrets.require("url").get_secret_value(), secrets.require("api-key")),
            secrets.redact,
        )

    def register(self, server: MCPServer) -> None:
        """Register fixed Sonarr operations with read/write annotations.

        Args:
            server: MCP server receiving the tools.

        Raises:
            SecretError: The connector has not been configured.
        """
        if self._service is None:
            raise SecretError("Configure Sonarr before registering its tools")
        read_only = [
            "system_status",
            "list_series",
            "get_series",
            "list_episodes",
            "calendar",
            "queue",
            "lookup_series",
            "quality_profiles",
            "root_folders",
            "command_status",
        ]
        mutations = ["add_series", "search_series", "search_episodes"]
        for name in read_only + mutations:
            is_read = name in read_only
            server.add_tool(
                getattr(self._service, name),
                name=f"sonarr_{name}",
                annotations=ToolAnnotations(
                    read_only_hint=is_read,
                    destructive_hint=False,
                    idempotent_hint=is_read,
                    open_world_hint=True,
                ),
            )

    def skill_roots(self) -> Iterable[Path]:
        """Locate the packaged Sonarr workflow instructions.

        Returns:
            The sonarr-manage skill directory.
        """
        return [Path(__file__).parent / "skills" / "sonarr-manage"]
