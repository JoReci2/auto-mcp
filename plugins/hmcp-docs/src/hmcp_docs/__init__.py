"""Read-only MCP document retrieval; ingestion is a separate CLI."""

import asyncio
import os
from collections.abc import Iterable
from pathlib import Path
from threading import Lock
from typing import Any

from hmcp_rag_core import Index, LocalSentenceTransformer
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations


def configured_index() -> Index:
    """Open configuration and optionally load a preinstalled embedding model.

    Returns:
        Index configured from HMCP_DOCS_INDEX and optional HMCP_DOCS_MODEL.
    """
    path = Path(os.environ.get("HMCP_DOCS_INDEX", "~/.local/share/hmcp/docs.sqlite3"))
    model = os.environ.get("HMCP_DOCS_MODEL")
    return Index(path, LocalSentenceTransformer(Path(model)) if model else None)


class DocsConnector:
    """Expose indexed evidence without source filesystem access from MCP inputs."""

    id = "docs"

    def __init__(self) -> None:
        """Prepare lazy configuration without accessing files or loading a model."""
        self._index: Index | None = None
        self._index_lock = Lock()

    @property
    def index(self) -> Index:
        """Initialize the index once, including under concurrent handler calls."""
        with self._index_lock:
            if self._index is None:
                self._index = configured_index()
            return self._index

    def skill_roots(self) -> Iterable[Path]:
        """Return the bundled document research skill."""
        return [Path(__file__).parent / "skills" / "docs-research"]

    async def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        def run() -> Any:
            return getattr(self.index, method)(*args, **kwargs)

        try:
            return await asyncio.to_thread(run)
        except Exception:
            # Source paths and parser/provider diagnostics must not cross MCP.
            raise ToolError(
                "Document index unavailable or request invalid. Check corpus, identifiers, "
                "filters and limits; run hmcp-docs ingest with matching index/model configuration."
            ) from None

    def register(self, server: MCPServer) -> None:
        """Register read-only tools and citation resource templates.

        Args:
            server: Selected hmcp server instance.
        """
        readonly = ToolAnnotations(
            read_only_hint=True, destructive_hint=False, idempotent_hint=True
        )

        @server.tool(annotations=readonly)
        async def docs_search(
            query: str, corpus: str, filters: dict[str, str] | None = None, limit: int = 5
        ) -> list[dict[str, Any]]:
            """Search a corpus; filters match metadata exactly. Cite returned revisions and offsets."""
            hits = await self._call("search", query, corpus, filters=filters, limit=limit)
            return [hit.model_dump() for hit in hits]

        @server.tool(annotations=readonly)
        async def docs_get_document(corpus: str, document_id: str, revision: str) -> dict[str, Any]:
            """Read a specific indexed revision, which may differ from the live source."""
            document = await self._call("get_document", corpus, document_id, revision)
            return {**document.model_dump(), "source_uri": document.source_uri}

        @server.tool(annotations=readonly)
        async def docs_get_passage(passage_id: str) -> dict[str, Any]:
            """Read a passage by its opaque search result identifier."""
            passage = await self._call("get_passage", passage_id)
            result: dict[str, Any] = passage.model_dump()
            return result

        @server.tool(annotations=readonly)
        async def docs_index_status(corpus: str) -> dict[str, Any]:
            """Report lexical/hybrid mode, counts and last changed passage timestamp."""
            result: dict[str, Any] = await self._call("status", corpus)
            return result

        @server.resource("docs://source/{corpus}/{document_id}/{revision}")
        async def source(corpus: str, document_id: str, revision: str) -> str:
            """Read the extracted text of an exact indexed document revision."""
            document = await self._call("get_document", corpus, document_id, revision)
            return str(document.text)

        @server.resource("docs://passage/{passage_id}")
        async def passage(passage_id: str) -> str:
            """Read a cited passage with its provenance."""
            result = await self._call("get_passage", passage_id)
            return str(result.model_dump_json())
