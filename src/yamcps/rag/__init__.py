"""Optional retrieval capability bundled with the yamcps core."""

from yamcps.rag.context import RagConfig, RagContext
from yamcps.rag.embeddings import Embedder, LocalSentenceTransformer
from yamcps.rag.index import Index
from yamcps.rag.models import Document, Passage, SearchHit

__all__ = [
    "Document",
    "Embedder",
    "Index",
    "LocalSentenceTransformer",
    "Passage",
    "RagConfig",
    "RagContext",
    "SearchHit",
]
