"""Snapshot, citation, filtering and embedding invariants."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from yamcps_rag_core import Document, Index, LocalSentenceTransformer
from yamcps_rag_core.embeddings import validate_vector


class ToyEmbedder:
    identity = "toy-v1"

    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0] if any(t in text for t in ("server", "machine")) else [0.0, 1.0]


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "index.sqlite3"
        self.index = Index(self.path)
        self.source = Document(
            corpus="project/specs",
            document_id="SSS",
            revision="1.2",
            text="SSS-REQ-0042 requires a server.\nBackup every evening.",
            metadata={"status": "approved", "baseline": "v1"},
        )

    def test_incremental_snapshot_citations_and_filtering(self):
        self.assertEqual(self.index.sync(self.source.corpus, [self.source])["updated"], 1)
        hit = self.index.search("SSS-REQ-0042", self.source.corpus)[0]
        self.assertEqual(hit.source_uri, "docs://source/project%2Fspecs/SSS/1.2")
        self.assertEqual(hit.text, self.source.text[hit.start : hit.end])
        self.assertEqual(self.index.get_passage(hit.passage_id).text, hit.text)
        self.assertEqual(self.index.get_document("project/specs", "SSS", "1.2"), self.source)
        self.assertEqual(self.index.sync(self.source.corpus, [self.source])["unchanged"], 1)
        self.assertEqual(
            self.index.search("server", self.source.corpus)[0].passage_id, hit.passage_id
        )
        self.assertEqual(self.index.search("server", "another"), [])
        self.assertEqual(
            self.index.search("server", self.source.corpus, filters={"status": "draft"}), []
        )
        self.assertEqual(
            len(self.index.search("server", self.source.corpus, filters={"baseline": "v1"})), 1
        )
        self.assertEqual(self.index.search("nonexistent", self.source.corpus), [])
        self.assertEqual(self.index.status(self.source.corpus)["mode"], "lexical")
        self.assertIsNotNone(self.index.status(self.source.corpus)["last_changed_at"])

    def test_changes_deletions_and_corpus_isolation(self):
        self.index.sync(self.source.corpus, [self.source])
        old = self.index.search("server", self.source.corpus)[0].passage_id
        other = self.source.model_copy(update={"corpus": "other"})
        self.index.sync("other", [other])
        updated = self.source.model_copy(update={"text": "New server specification"})
        self.assertEqual(self.index.sync(self.source.corpus, [updated])["updated"], 1)
        with self.assertRaisesRegex(ValueError, "Passage not found"):
            self.index.get_passage(old)
        new_revision = updated.model_copy(update={"revision": "2"})
        result = self.index.sync(self.source.corpus, [new_revision])
        self.assertEqual(result, {"updated": 1, "unchanged": 0, "deleted": 1})
        with self.assertRaisesRegex(ValueError, "Document revision not found"):
            self.index.get_document(self.source.corpus, "SSS", "1.2")
        self.index.sync(self.source.corpus, [])
        self.assertEqual(self.index.status(self.source.corpus)["documents"], 0)
        self.assertIsNone(self.index.status(self.source.corpus)["last_changed_at"])
        self.assertEqual(self.index.status("other")["documents"], 1)

    def test_chunking_and_empty_text(self):
        source = self.source.model_copy(update={"text": "x" * 150})
        self.index.sync(source.corpus, [source], chunk_size=64)
        hits = self.index.search("x" * 64, source.corpus)
        self.assertEqual(len(hits), 2)
        self.assertEqual(self.index.status(source.corpus)["passages"], 3)
        self.index.sync(source.corpus, [source], chunk_size=100)
        self.assertEqual(self.index.status(source.corpus)["passages"], 2)
        empty = source.model_copy(update={"text": ""})
        self.index.sync(source.corpus, [empty])
        self.assertEqual(self.index.status(source.corpus)["passages"], 0)

    def test_validation_and_missing_index_do_not_create_database(self):
        for action in [lambda: self.index.status("c"), lambda: self.index.get_passage("id")]:
            with self.assertRaisesRegex(ValueError, "Index missing"):
                action()
        self.assertFalse(self.path.exists())
        for query, corpus, limit in [
            ("", "c", 5),
            ("?", "c", 5),
            ("x", "", 5),
            ("x", "c", 21),
            ("x" * 4001, "c", 1),
        ]:
            with self.subTest(query=query[:10]), self.assertRaises(ValueError):
                self.index.search(query, corpus, limit=limit)
        for args in [
            ("", [], 64),
            ("x", [self.source], 64),
            (self.source.corpus, [self.source] * 2, 64),
            ("x", [], 1),
        ]:
            with self.assertRaises(ValueError):
                self.index.sync(args[0], args[1], chunk_size=args[2])
        self.assertFalse(self.path.exists())

    def test_hybrid_synonym_provider_and_mismatch(self):
        index = Index(self.path, ToyEmbedder())
        index.sync(self.source.corpus, [self.source])
        self.assertEqual(index.search("machine", self.source.corpus)[0].document_id, "SSS")
        self.assertEqual(index.status(self.source.corpus)["mode"], "hybrid")
        with self.assertRaisesRegex(ValueError, "configuration mismatch"):
            self.index.search("server", self.source.corpus)
        bad = Mock(identity="toy-v1")
        bad.embed.return_value = [1, 2, 3]
        with self.assertRaisesRegex(ValueError, "dimension mismatch"):
            Index(self.path, bad).search("server", self.source.corpus)
        with self.assertRaisesRegex(ValueError, "dimension mismatch"):
            Index(self.path, bad).sync(
                self.source.corpus, [self.source.model_copy(update={"text": "changed"})]
            )
        self.assertEqual(index.get_document(self.source.corpus, "SSS", "1.2"), self.source)

    def test_provider_failure_rolls_back_deletions_and_replacements(self):
        provider = ToyEmbedder()
        index = Index(self.path, provider)
        index.sync(self.source.corpus, [self.source])
        with patch.object(provider, "embed", side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):
                index.sync(self.source.corpus, [self.source.model_copy(update={"text": "changed"})])
        self.assertEqual(index.get_document(self.source.corpus, "SSS", "1.2"), self.source)

    def test_vectors_and_local_provider_never_download(self):
        for value in [[], [0, 0], [float("nan")], [float("inf")]]:
            with self.assertRaises(ValueError):
                validate_vector(value)
        root = self.path.parent / "model"
        root.mkdir()
        with self.assertRaises(ValueError):
            LocalSentenceTransformer(root)
        (root / "weights").write_bytes(b"model")
        model = Mock()
        model.encode.return_value = [1, 0]
        module = Mock()
        module.SentenceTransformer.return_value = model
        with patch("yamcps_rag_core.embeddings.importlib.import_module", return_value=module):
            provider = LocalSentenceTransformer(root)
            identity = provider.identity
            self.assertEqual(provider.embed("hello"), [1, 0])
            module.SentenceTransformer.assert_called_once_with(
                str(root), local_files_only=True, trust_remote_code=False
            )
            (root / "weights").write_bytes(b"different")
            self.assertNotEqual(LocalSentenceTransformer(root).identity, identity)
        (root / "link").symlink_to(root / "weights")
        with self.assertRaisesRegex(ValueError, "symlinks"):
            LocalSentenceTransformer(root)
