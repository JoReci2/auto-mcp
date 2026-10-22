"""Optional per-connector retrieval capability managed by the core."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from yamcps.rag.embeddings import Embedder, LocalSentenceTransformer
from yamcps.rag.index import Index


@dataclass(frozen=True)
class RagConfig:
    """Retrieval options; omitted paths use the core's per-connector index default."""

    index_path: Path | None = None
    model_path: Path | None = None

    def __post_init__(self) -> None:
        """Validate path types without reading files or loading a model."""
        if any(
            p is not None and not isinstance(p, Path) for p in (self.index_path, self.model_path)
        ):
            raise TypeError("RAG paths must be Path objects or None")


class RagContext:
    """Lazy retrieval context injected only into connectors opting into RAG."""

    def __init__(self, connector_id: str, config: RagConfig, *, root: Path | None = None) -> None:
        """Resolve configuration without creating files or loading embeddings.

        Args:
            connector_id: Connector identifier used for the default database name.
            config: Explicit index and optional local model configuration.
            root: Optional base directory; otherwise YAMCPS_RAG_DIR or the local default.

        Raises:
            ValueError: The connector identifier is invalid.
        """
        if not re.fullmatch(r"[a-z][a-z0-9-]*", connector_id):
            raise ValueError("Invalid RAG connector identifier")
        base = (
            root
            if root is not None
            else Path(os.environ.get("YAMCPS_RAG_DIR", "~/.local/share/yamcps/rag"))
        )
        self.connector_id = connector_id
        self.config = config
        self.path = (
            (
                config.index_path
                if config.index_path is not None
                else base / f"{connector_id}.sqlite3"
            )
            .expanduser()
            .absolute()
        )
        self._index: Index | None = None
        self._lock = Lock()

    @property
    def index(self) -> Index:
        """Get the index once, loading a local model only on first access.

        Returns:
            Index using this connector's database and optional embeddings.
        """
        with self._lock:
            if self._index is None:
                embedder: Embedder | None = None
                if self.config.model_path is not None:
                    embedder = LocalSentenceTransformer(self.config.model_path.expanduser())
                self._index = Index(self.path, embedder)
            return self._index
