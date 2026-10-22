"""Read-only MCP document retrieval; ingestion is a separate CLI."""

import asyncio
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from yamcps.rag import Index, RagConfig, RagContext


def _rag_config() -> RagConfig:
    path = os.environ.get("YAMCPS_DOCS_INDEX")
    model = os.environ.get("YAMCPS_DOCS_MODEL")
    return RagConfig(
        index_path=Path(path) if path else None,
        model_path=Path(model) if model else None,
    )


def configured_index() -> Index:
    """Create an offline ingestion index using the same core settings as the plugin.

    Returns:
        Core-managed index configured for the docs connector.
    """
    return RagContext("docs", _rag_config()).index


class DocsConnector:
    """Expose indexed evidence without source filesystem access from MCP inputs."""

    id = "docs"

    def __init__(self) -> None:
        """Prepare for core injection without accessing sources or loading a model."""
        self._rag: RagContext | None = None

    def rag_config(self) -> RagConfig:
        """Declare optional docs paths, otherwise use the core defaults.

        Returns:
            Configuration shared with offline ingestion.
        """
        return _rag_config()

    def configure_rag(self, rag: RagContext) -> None:
        """Receive the lazy context supplied by the yamcps core.

        Args:
            rag: Core retrieval context for this connector.
        """
        self._rag = rag

    @property
    def index(self) -> Index:
        """Return the injected index on first use, outside server registration."""
        if self._rag is None:
            raise ValueError("The core has not configured the docs RAG context")
        return self._rag.index

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
                "filters and limits; run yamcps-docs ingest with matching index/model configuration."
            ) from None

    def register(self, server: MCPServer) -> None:
        """Register read-only tools and citation resource templates.

        Args:
            server: Selected yamcps server instance.
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
