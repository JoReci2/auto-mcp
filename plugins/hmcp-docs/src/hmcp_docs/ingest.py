"""Explicit offline ingestion from a complete JSON manifest."""

import importlib
import json
from pathlib import Path

from hmcp_rag_core import Document, Index
from pydantic import BaseModel, ConfigDict, Field


class Source(BaseModel):
    """One source revision under the manifest directory."""

    model_config = ConfigDict(extra="forbid")
    path: str
    document_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    metadata: dict[str, str] = Field(default_factory=dict)


class Manifest(BaseModel):
    """Complete desired snapshot of exactly one corpus."""

    model_config = ConfigDict(extra="forbid")
    corpus: str = Field(min_length=1)
    sources: list[Source]


def _source_path(root: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Source paths must stay below the manifest directory")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Source symlinks are not supported")
    path = current.resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Source must be a file below the manifest directory")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Source exceeds the 20 MiB limit")
    return path


def _extract(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        reader = importlib.import_module("pypdf").PdfReader(str(path))
        return "\n\f\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        document = importlib.import_module("docx").Document(str(path))
        paragraphs = [p.text for p in document.paragraphs]
        tables = [
            " | ".join(c.text for c in row.cells) for table in document.tables for row in table.rows
        ]
        return "\n".join(paragraphs + tables)
    raise ValueError("Supported source formats: .txt, .md, .pdf, .docx")


def ingest(index: Index, manifest_path: Path, *, chunk_size: int = 1200) -> dict[str, int]:
    """Extract all sources before atomically synchronizing a corpus.

    Args:
        index: Configured retrieval index.
        manifest_path: JSON manifest, relative paths resolved against its directory.
        chunk_size: Maximum extracted characters per passage.

    Returns:
        Updated, unchanged and deleted document counts.

    Raises:
        ValueError: Manifest, source path, format or extracted content is invalid.
    """
    manifest = Manifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
    root = manifest_path.resolve(strict=True).parent
    documents = []
    for source in manifest.sources:
        path = _source_path(root, source.path)
        text = _extract(path)
        if not text.strip() or len(text) > 4_000_000:
            raise ValueError(
                "Source is empty or exceeds 4 million extracted characters; OCR is not included"
            )
        documents.append(
            Document(
                corpus=manifest.corpus,
                document_id=source.document_id,
                revision=source.revision,
                text=text,
                metadata=source.metadata,
            )
        )
    return index.sync(manifest.corpus, documents, chunk_size=chunk_size)
