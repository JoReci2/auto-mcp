"""Independent retrieval connector with a plugin-owned backend factory."""

import asyncio
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from yamcps import RagConfig, RagContext
from yamcps.rag import Document, Index, RetrievalIndex


def create_index(path: Path) -> RetrievalIndex:
    """Build a local lexical backend without downloading or loading a model.

    Args:
        path: Database path resolved by the host for this connector.

    Returns:
        Backend implementing the public retrieval contract.
    """
    return Index(path, source_namespace="demo-rag")


class DemoRagConnector:
    """Demonstrate explicit ingestion and retrieval without external services."""

    id = "demo-rag"

    def __init__(self) -> None:
        """Create an unconfigured connector without touching storage."""
        self._rag: RagContext | None = None

    def rag_config(self) -> RagConfig:
        """Return lazy plugin-owned backend configuration.

        Returns:
            Configuration selecting this plugin's backend factory.
        """
        return RagConfig(index_factory=create_index)

    def configure_rag(self, rag: RagContext) -> None:
        """Retain the injected context without constructing its backend.

        Args:
            rag: Context scoped to this connector.
        """
        self._rag = rag

    def _index(self) -> RetrievalIndex:
        if self._rag is None:
            raise RuntimeError("RAG context has not been configured")
        return self._rag.index

    def _ingest(self) -> dict[str, int]:
        return self._index().sync(
            "examples",
            [
                Document(
                    corpus="examples",
                    document_id="horaires-bibliotheque",
                    revision="1",
                    text=(
                        "Horaires : la bibliothèque du quartier ouvre du mardi au samedi, de 10 h à 18 h. "
                        "Elle est fermée le dimanche et le lundi."
                    ),
                    source_namespace="demo-rag",
                    metadata={"type": "information", "theme": "horaires"},
                ),
                Document(
                    corpus="examples",
                    document_id="emprunt-livres",
                    revision="1",
                    text=(
                        "Une carte de bibliothèque permet d’emprunter cinq livres pendant "
                        "trois semaines. Le prêt peut être renouvelé une fois si aucun autre "
                        "lecteur n’a réservé le livre."
                    ),
                    source_namespace="demo-rag",
                    metadata={"type": "guide", "theme": "emprunts"},
                ),
            ],
        )

    def register(self, server: MCPServer) -> None:
        """Register explicit ingestion, search and citation handlers.

        Args:
            server: MCP server receiving the demo handlers.
        """

        @server.tool()
        async def demo_rag_ingest() -> dict[str, int]:
            """Replace the examples corpus with two bundled fictional documents.

            Returns:
                Updated, unchanged and deleted document counts.
            """
            return await asyncio.to_thread(self._ingest)

        @server.tool()
        async def demo_rag_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
            """Search the examples corpus after calling demo_rag_ingest.

            Args:
                query: Text or identifier to search for.
                limit: Maximum number of passages, between 1 and 20.

            Returns:
                Ranked passages with source references and offsets.

            Raises:
                ValueError: Ingestion is missing or the query is invalid.
            """

            def run() -> list[dict[str, Any]]:
                return [
                    hit.model_dump() for hit in self._index().search(query, "examples", limit=limit)
                ]

            return await asyncio.to_thread(run)

        @server.resource("demo-rag://source/{corpus}/{document_id}/{revision}")
        async def source(corpus: str, document_id: str, revision: str) -> str:
            """Read the exact indexed revision referenced by a search result.

            Args:
                corpus: Corpus containing the source.
                document_id: Exact source identifier.
                revision: Exact indexed revision.

            Returns:
                Complete extracted source text.

            Raises:
                ValueError: The requested revision is unavailable.
            """
            return await asyncio.to_thread(
                lambda: self._index().get_document(corpus, document_id, revision).text
            )
