"""Shared retrieval library; deliberately declares no MCP entry point."""

from hmcp_rag_core.embeddings import Embedder, LocalSentenceTransformer
from hmcp_rag_core.index import Index
from hmcp_rag_core.models import Document, Passage, SearchHit

__all__ = ["Document", "Embedder", "Index", "LocalSentenceTransformer", "Passage", "SearchHit"]
