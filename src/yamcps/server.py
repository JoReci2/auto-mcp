"""Compose selected connectors before starting either transport."""

import inspect
from collections.abc import Mapping

from mcp.server import MCPServer

from yamcps.connectors import ConnectorError, load
from yamcps.onboarding import prepare_secrets
from yamcps.registry import StrictServer
from yamcps.secrets import ConnectorSecrets, SecretError
from yamcps.skills import SkillCatalog
from yamcps.vault import Vault


def create_server(
    names: list[str] | None = None,
    *,
    secret_values: Mapping[str, str] | None = None,
    vault: Vault | None = None,
    interactive: bool = False,
) -> MCPServer:
    """Compose a server with optional connector-scoped secrets.

    Args:
        names: Selected connector identifiers; None loads all installed plugins.
        secret_values: Explicit values; None uses environment when no vault is given.
        vault: Optional store to resolve declared secret requirements from.
        interactive: Allow hidden prompts for missing vault credentials.

    Returns:
        A configured MCP server, ready to run.

    Raises:
        ConnectorError: Connector configuration or registration fails.
    """
    if vault is not None and secret_values is not None:
        raise SecretError("Supply either vault or secret_values, not both")
    catalog = SkillCatalog()
    connectors = load(names)
    if vault is not None:
        secret_values = prepare_secrets(connectors, vault, interactive=interactive)
    for connector in connectors:
        configure = getattr(connector, "configure", None)
        if configure is not None:
            try:
                if not callable(configure) or inspect.iscoroutinefunction(configure):
                    raise TypeError("configure must be synchronous")
                configure(ConnectorSecrets(connector.id, secret_values))
            except SecretError as exc:
                message = ConnectorSecrets(connector.id, secret_values).redact(str(exc))
                raise ConnectorError(
                    f"Connector {connector.id!r} configuration: {message}"
                ) from None
            except Exception:
                raise ConnectorError(f"Connector {connector.id!r} configuration failed") from None
        try:
            roots = getattr(connector, "skill_roots", None)
            if roots is not None:
                catalog.add_roots(connector.id, roots())
        except Exception as exc:
            message = ConnectorSecrets(connector.id, secret_values).redact(str(exc))
            raise ConnectorError(f"Connector {connector.id!r} skills: {message}") from None
    server = StrictServer(name="yamcps", version="0.1.0", extensions=[catalog])
    for connector in connectors:
        try:
            connector.register(server)
        except Exception as exc:
            message = ConnectorSecrets(connector.id, secret_values).redact(str(exc))
            raise ConnectorError(f"Connector {connector.id!r} registration: {message}") from None
    catalog.register_resources(server)
    return server
