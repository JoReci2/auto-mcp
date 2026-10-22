"""Shared retrieval library; deliberately declares no MCP entry point."""

from yamcps_rag_core.embeddings import Embedder, LocalSentenceTransformer
from yamcps_rag_core.index import Index
from yamcps_rag_core.models import Document, Passage, SearchHit

__all__ = ["Document", "Embedder", "Index", "LocalSentenceTransformer", "Passage", "SearchHit"]
