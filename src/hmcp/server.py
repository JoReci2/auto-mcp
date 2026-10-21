"""Compose selected connectors before starting either transport."""

from mcp.server import MCPServer

from hmcp.connectors import ConnectorError, load
from hmcp.registry import StrictServer
from hmcp.skills import SkillCatalog


def create_server(names: list[str]) -> MCPServer:
    catalog = SkillCatalog()
    connectors = load(names)
    for connector in connectors:
        try:
            roots = getattr(connector, "skill_roots", None)
            if roots is not None:
                catalog.add_roots(connector.id, roots())
        except Exception as exc:
            raise ConnectorError(f"Connector {connector.id!r} skills: {exc}") from exc
    server = StrictServer(name="hmcp", version="0.1.0", extensions=[catalog])
    for connector in connectors:
        try:
            connector.register(server)
        except Exception as exc:
            raise ConnectorError(f"Connector {connector.id!r} registration: {exc}") from exc
    catalog.register_resources(server)
    return server
