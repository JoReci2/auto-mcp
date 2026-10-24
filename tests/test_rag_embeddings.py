"""Embedding validation, offline loading and model identity."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from yamcps.rag import LocalSentenceTransformer
from yamcps.rag.embeddings import validate_vector


class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_invalid_vectors_are_rejected(self):
        for value in [[], [0, 0], [float("nan")], [float("inf")]]:
            with self.assertRaises(ValueError):
                validate_vector(value)

    def test_local_model_is_offline_and_identity_tracks_weights(self):
        root = self.root / "model"
        root.mkdir()
        with self.assertRaises(ValueError):
            LocalSentenceTransformer(root)
        (root / "weights").write_bytes(b"model")
        model = Mock()
        model.encode.return_value = [1, 0]
        module = Mock()
        module.SentenceTransformer.return_value = model
        with patch("yamcps.rag.embeddings.importlib.import_module", return_value=module):
            provider = LocalSentenceTransformer(root)
            identity = provider.identity
            self.assertEqual(provider.embed("hello"), [1, 0])
            module.SentenceTransformer.assert_called_once_with(
                str(root.resolve()), local_files_only=True, trust_remote_code=False
            )
            (root / "weights").write_bytes(b"different")
            self.assertNotEqual(LocalSentenceTransformer(root).identity, identity)
        (root / "link").symlink_to(root / "weights")
        with self.assertRaisesRegex(ValueError, "symlinks"):
            LocalSentenceTransformer(root)
