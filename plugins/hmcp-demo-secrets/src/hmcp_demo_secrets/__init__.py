"""Demonstrate credential declaration and configuration without an external API."""

from collections.abc import Iterable
from pathlib import Path

from mcp.server import MCPServer

from hmcp import BasicAuth, ConnectorSecrets, SecretError, SecretSpec, TokenAuth


class DemoSecretsConnector:
    """Exercise the local vault with a token and Basic Auth credentials."""

    id = "demo-secrets"

    def __init__(self) -> None:
        """Create an unconfigured connector without reading credentials."""
        self._token: TokenAuth | None = None
        self._basic: BasicAuth | None = None

    def required_secrets(self) -> list[SecretSpec]:
        """Declare the fields requested by the terminal wizard.

        Returns:
            Token, username and password fields in prompt order.
        """
        return [
            SecretSpec("token", "Demo API token (use a fictitious value)"),
            SecretSpec("username", "Demo Basic Auth username (use a fictitious value)"),
            SecretSpec("password", "Demo Basic Auth password (use a fictitious value)"),
        ]

    def configure(self, secrets: ConnectorSecrets) -> None:
        """Load and validate both authentication methods.

        Args:
            secrets: Credentials scoped to demo-secrets by hmcp.
        """
        self._token = secrets.token_auth()
        self._basic = secrets.basic_auth()

    def register(self, server: MCPServer) -> None:
        """Register a local status tool that never returns credential values.

        Args:
            server: MCP server receiving the demo tool.

        Raises:
            SecretError: Configuration has not completed successfully.
        """
        token, basic = self._token, self._basic
        if token is None or basic is None:
            raise SecretError("Configure demo-secrets before registering its tools")

        @server.tool()
        async def demo_secrets_status() -> dict[str, str | bool]:
            """Validate local credentials without contacting an API or returning secrets.

            Returns:
                Configuration status and authentication schemes, without values.
            """
            # A real connector would pass these headers only to its HTTPS client.
            token.authorization_header()
            basic.authorization_header()
            return {"configured": True, "token_auth": token.scheme, "basic_auth": "Basic"}

    def skill_roots(self) -> Iterable[Path]:
        """Locate the packaged instructions for using the demo.

        Returns:
            The directory containing the demo-secrets-check skill.
        """
        return [Path(__file__).parent / "skills" / "demo-secrets-check"]
