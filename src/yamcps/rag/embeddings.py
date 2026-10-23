"""Optional local embedding providers, never downloaded automatically."""

import hashlib
import importlib
import math
from pathlib import Path
from typing import Protocol


class Embedder(Protocol):
    """Provider identity must change whenever the model or preprocessing changes."""

    identity: str

    def embed(self, text: str) -> list[float]:
        """Encode text into a finite, nonempty vector.

        Args:
            text: Source passage or query.

        Returns:
            Dense vector in the provider's shared embedding space.
        """
        ...


def validate_vector(vector: list[float]) -> None:
    """Reject empty, zero or non-finite vectors.

    Args:
        vector: Provider output.

    Raises:
        ValueError: The vector cannot be used for cosine retrieval.
    """
    if not vector or not all(math.isfinite(x) for x in vector) or not any(vector):
        raise ValueError("Embedding must be nonempty, finite and nonzero")


class LocalSentenceTransformer:
    """Load a trusted local model directory with a content-based identity."""

    def __init__(self, model_path: Path) -> None:
        """Load local weights without network access or remote Python code.

        Args:
            model_path: Preinstalled Sentence Transformers model directory.

        Raises:
            ValueError: No model files exist or a symlink is found.
        """
        root = model_path.resolve(strict=True)
        files = sorted(root.rglob("*"))
        if not root.is_dir() or not any(p.is_file() for p in files):
            raise ValueError("Expected a nonempty local model directory")
        digest = hashlib.sha256()
        for path in files:
            if path.is_symlink():
                raise ValueError("Model symlinks are not supported")
            if path.is_file():
                digest.update(path.relative_to(root).as_posix().encode())
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
        self.identity = "sentence-transformers:normalized:v1:" + digest.hexdigest()
        module = importlib.import_module("sentence_transformers")
        self._model = module.SentenceTransformer(
            str(root), local_files_only=True, trust_remote_code=False
        )

    def embed(self, text: str) -> list[float]:
        """Encode text using the local model.

        Args:
            text: Passage or query.

        Returns:
            Normalized embedding vector.
        """
        return [float(x) for x in self._model.encode(text, normalize_embeddings=True)]
