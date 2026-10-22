"""Discover installed plugins without importing unselected connectors."""

import inspect
import re
from collections.abc import Iterable
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Protocol

from mcp.server import MCPServer

from yamcps.rag import RagConfig, RagContext
from yamcps.secrets import ConnectorSecrets, SecretSpec


class Connector(Protocol):
    id: str

    def register(self, server: MCPServer) -> None: ...


class SecretConsumer(Protocol):
    """Optional connector capability for receiving scoped API credentials."""

    def configure(self, secrets: ConnectorSecrets) -> None:
        """Validate and retain credentials before registering MCP handlers.

        Args:
            secrets: Credential view scoped to this connector.
        """
        ...


class SecretRequirements(Protocol):
    """Optional declaration used by interactive secret configuration."""

    def required_secrets(self) -> Iterable[SecretSpec]:
        """Describe the credentials required by this connector.

        Returns:
            Required fields in the order they should be prompted.
        """
        ...


class SkillProvider(Protocol):
    def skill_roots(self) -> Iterable[Path]: ...


class RagProvider(Protocol):
    """Optional paired hooks for receiving core-managed retrieval."""

    def rag_config(self) -> RagConfig:
        """Declare retrieval options without loading models or reading sources.

        Returns:
            Configuration for the connector's index and optional local embeddings.
        """
        ...

    def configure_rag(self, rag: RagContext) -> None:
        """Receive a lazy retrieval context before skills and handlers are registered.

        Args:
            rag: Context scoped by the connector's identifier.
        """
        ...


class ConnectorError(ValueError):
    """A plugin cannot safely be loaded."""


def discover() -> dict[str, EntryPoint]:
    plugins: dict[str, EntryPoint] = {}
    for entry in entry_points(group="yamcps.connectors"):
        if entry.name in plugins:
            raise ConnectorError(f"Duplicate connector entry point: {entry.name}")
        plugins[entry.name] = entry
    return plugins


def load(names: list[str] | None = None) -> list[Connector]:
    """Load selected connectors, or every installed connector when omitted.

    Args:
        names: Explicit selection; None selects all entry points in name order.

    Returns:
        Validated connector instances.

    Raises:
        ConnectorError: Discovery/loading fails or automatic selection is empty.
    """
    available = discover()
    if names is None:
        names = sorted(available)
        if not names:
            raise ConnectorError("No connectors installed; install an yamcps plugin first")
    selected: list[Connector] = []
    seen: set[str] = set()
    for name in names:
        try:
            entry = available[name]
            connector = entry.load()()
            identifier = connector.id
            if not isinstance(identifier, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", identifier):
                raise ValueError("id must be a lowercase kebab-case identifier")
            if identifier != name:
                raise ValueError(f"id {identifier!r} must match entry point {name!r}")
            if identifier in seen:
                raise ValueError(f"duplicate connector id: {identifier}")
            register = getattr(connector, "register", None)
            if not callable(register) or inspect.iscoroutinefunction(register):
                raise ValueError("register must be a synchronous callable")
            seen.add(identifier)
            selected.append(connector)
        except Exception as exc:
            raise ConnectorError(f"Connector {name!r}: {exc}") from exc
    return selected
