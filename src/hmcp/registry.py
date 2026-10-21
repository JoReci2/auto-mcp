"""Reject duplicate registrations instead of the SDK's default replacement."""

from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.prompts import Prompt
from mcp.server.mcpserver.resources import Resource


class StrictServer(MCPServer):
    def __init__(self, **kwargs: Any) -> None:
        self._hmcp_names: dict[str, set[str]] = {"tool": set(), "prompt": set(), "resource": set()}
        super().__init__(**kwargs)

    def _claim(self, kind: str, name: str) -> None:
        if name in self._hmcp_names[kind]:
            raise ValueError(f"Duplicate {kind}: {name}")
        self._hmcp_names[kind].add(name)

    def add_tool(
        self, fn: Callable[..., Any], name: str | None = None, *args: Any, **kwargs: Any
    ) -> None:
        self._claim("tool", name or fn.__name__)
        super().add_tool(fn, name, *args, **kwargs)

    def add_prompt(self, prompt: Prompt) -> None:
        self._claim("prompt", prompt.name)
        super().add_prompt(prompt)

    def add_resource(self, resource: Resource) -> None:
        self._claim("resource", str(resource.uri))
        super().add_resource(resource)
