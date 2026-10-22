"""Prowlarr connector with vault-backed credentials and an embedded skill."""

from collections.abc import Iterable
from pathlib import Path

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from yamcps import ConnectorSecrets, SecretError, SecretSpec
from yamcps_prowlarr.client import ProwlarrClient
from yamcps_prowlarr.service import ProwlarrService


class ProwlarrConnector:
    """Expose indexer browsing and release searches through Prowlarr API v1."""

    id = "prowlarr"

    def __init__(self) -> None:
        """Create an unconfigured instance without network access."""
        self._service: ProwlarrService | None = None

    def required_secrets(self) -> list[SecretSpec]:
        """Describe instance settings collected by yamcps's terminal wizard.

        Returns:
            Instance URL and API key stored together in the encrypted vault.
        """
        return [
            SecretSpec(
                "url", "Prowlarr instance URL, e.g. http://localhost:9696 (without /api/v1)"
            ),
            SecretSpec("api-key", "Prowlarr API key (Settings > General > Security)"),
        ]

    def configure(self, secrets: ConnectorSecrets) -> None:
        """Validate settings and create the API service without making a request.

        Args:
            secrets: Values scoped to this Prowlarr connector.
        """
        self._service = ProwlarrService(
            ProwlarrClient(secrets.require("url").get_secret_value(), secrets.require("api-key")),
            secrets.redact,
        )

    def register(self, server: MCPServer) -> None:
        """Register read-only Prowlarr operations without configuration or download tools.

        Args:
            server: MCP server receiving the tools.

        Raises:
            SecretError: The connector has not been configured.
        """
        if self._service is None:
            raise SecretError("Configure Prowlarr before registering its tools")
        tools = [
            "system_status",
            "list_indexers",
            "get_indexer",
            "indexer_status",
            "categories",
            "search",
            "history",
            "health",
            "statistics",
            "applications",
        ]
        for name in tools:
            server.add_tool(
                getattr(self._service, name),
                name=f"prowlarr_{name}",
                annotations=ToolAnnotations(
                    read_only_hint=True,
                    destructive_hint=False,
                    idempotent_hint=name != "search",
                    open_world_hint=True,
                ),
            )

    def skill_roots(self) -> Iterable[Path]:
        """Locate the packaged Prowlarr workflow instructions.

        Returns:
            The prowlarr-search skill directory.
        """
        return [Path(__file__).parent / "skills" / "prowlarr-search"]
