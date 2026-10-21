"""Immutable startup skill catalog and SDK extension compatibility adapter.

The published mcp 2.3 SDK has Extension but not mcp.server.skills.
Keep this adapter separate so the native implementation can replace it later.
"""

import hashlib
import mimetypes
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml
from mcp.server import MCPServer
from mcp.server.context import ServerRequestContext
from mcp.server.extension import Extension, MethodBinding
from mcp.server.mcpserver.resources import BinaryResource, TextResource
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS, RequestParams


class GetSkillParams(RequestParams):
    uri: str


class SkillCatalog(Extension):
    identifier = "io.modelcontextprotocol/skills"

    def __init__(self) -> None:
        self.skills: dict[str, dict[str, Any]] = {}
        self.files: dict[str, bytes] = {}

    def add_roots(self, connector_id: str, roots: Iterable[Path]) -> None:
        """Each root is one skill directory, named like its frontmatter name."""
        for root in roots:
            root = Path(root)
            if root.is_symlink():
                raise ValueError(f"Skill {root}: symbolic links are not supported")
            root = root.resolve(strict=True)
            paths = sorted(root.rglob("*"))
            if any(path.is_symlink() for path in paths):
                raise ValueError(f"Skill {root}: symbolic links are not supported")
            contents = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in paths
                if path.is_file() and path.resolve().is_relative_to(root)
            }
            raw = contents.get("SKILL.md", b"").decode("utf-8")
            match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", raw, re.DOTALL)
            if not match:
                raise ValueError(f"Skill {root}: missing YAML frontmatter")
            metadata = yaml.safe_load(match.group(1))
            if not isinstance(metadata, dict):
                raise ValueError(f"Skill {root}: frontmatter must be a mapping")
            name = metadata.get("name")
            description = metadata.get("description")
            if (
                not isinstance(name, str)
                or len(name) > 64
                or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
                or not name.startswith(f"{connector_id}-")
                or root.name != name
            ):
                raise ValueError(
                    f"Skill {root}: name must match directory and start with {connector_id}-"
                )
            if not isinstance(description, str) or not description.strip():
                raise ValueError(f"Skill {root}: description is required")
            base = f"skill://{name}/"
            uri = base + "SKILL.md"
            if uri in self.skills:
                raise ValueError(f"Duplicate skill: {name}")
            resources = []
            for relative, data in contents.items():
                file_uri = base + quote(relative, safe="/")
                self.files[file_uri] = data
                resources.append(
                    {
                        "uri": file_uri,
                        "size": len(data),
                        "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                    }
                )
            self.skills[uri] = {"uri": uri, "frontmatter": metadata, "resources": resources}

    async def list_skills(self, ctx: ServerRequestContext[Any, Any], params: RequestParams) -> Any:
        return {"skills": list(self.skills.values())}

    async def get_skill(self, ctx: ServerRequestContext[Any, Any], params: GetSkillParams) -> Any:
        if params.uri not in self.skills:
            raise MCPError(code=INVALID_PARAMS, message=f"Unknown skill: {params.uri}")
        return {"skill": self.skills[params.uri]}

    def methods(self) -> Sequence[MethodBinding]:
        return [
            MethodBinding("skills/list", RequestParams, self.list_skills),
            MethodBinding("skills/get", GetSkillParams, self.get_skill),
        ]

    def register_resources(self, server: MCPServer) -> None:
        for uri, data in self.files.items():
            mime = mimetypes.guess_type(uri)[0] or "application/octet-stream"
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                server.add_resource(BinaryResource(uri=uri, data=data, mime_type=mime))
            else:
                server.add_resource(TextResource(uri=uri, text=text, mime_type=mime))
