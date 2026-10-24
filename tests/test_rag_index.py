"""SQLite snapshots, retrieval, citations and backend compatibility."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from yamcps.rag import Document, Index


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

    def test_snapshot_is_idempotent_and_preserves_citations(self):
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

    def test_search_respects_corpus_and_metadata_filters(self):
        self.index.sync(self.source.corpus, [self.source])
        self.assertEqual(self.index.search("server", "another"), [])
        self.assertEqual(
            self.index.search("server", self.source.corpus, filters={"status": "draft"}), []
        )
        self.assertEqual(
            len(
                self.index.search(
                    "server", self.source.corpus, filters={"baseline": "v1", "status": "approved"}
                )
            ),
            1,
        )
        self.assertEqual(
            self.index.search(
                "server", self.source.corpus, filters={"baseline": "v1", "status": "draft"}
            ),
            [],
        )
        self.assertEqual(self.index.search("nonexistent", self.source.corpus), [])

    def test_status_reports_counts_mode_and_change_timestamp(self):
        self.index.sync(self.source.corpus, [self.source])
        self.assertEqual(self.index.status(self.source.corpus)["documents"], 1)
        self.assertEqual(self.index.status(self.source.corpus)["passages"], 1)
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

    def test_reads_of_missing_index_do_not_create_database(self):
        for action in [lambda: self.index.status("c"), lambda: self.index.get_passage("id")]:
            with self.assertRaisesRegex(ValueError, "Index missing"):
                action()
        self.assertFalse(self.path.exists())

    def test_invalid_search_does_not_create_database(self):
        for query, corpus, limit in [
            ("", "c", 5),
            ("?", "c", 5),
            ("x", "", 5),
            ("x", "c", 21),
            ("x" * 4001, "c", 1),
        ]:
            with self.subTest(query=query[:10]), self.assertRaises(ValueError):
                self.index.search(query, corpus, limit=limit)
        self.assertFalse(self.path.exists())

    def test_invalid_snapshot_does_not_create_database(self):
        for args in [
            ("", [], 64),
            ("x", [self.source], 64),
            (self.source.corpus, [self.source] * 2, 64),
            ("x", [], 1),
        ]:
            with self.subTest(corpus=args[0], chunk_size=args[2]), self.assertRaises(ValueError):
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

    def test_embedding_failure_rolls_back_the_entire_snapshot(self):
        provider = ToyEmbedder()
        index = Index(self.path, provider)
        originals = [
            self.source.model_copy(update={"document_id": name})
            for name in ("first", "second", "stale")
        ]
        index.sync(self.source.corpus, originals)
        before = index.search("server", self.source.corpus)
        replacements = [
            document.model_copy(update={"text": "changed"}) for document in originals[:2]
        ]
        with patch.object(provider, "embed", side_effect=[[1.0, 0.0], RuntimeError("offline")]):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                index.sync(self.source.corpus, replacements)
        for document in originals:
            with self.subTest(document_id=document.document_id):
                self.assertEqual(
                    index.get_document(document.corpus, document.document_id, document.revision),
                    document,
                )
        self.assertEqual(index.search("server", self.source.corpus), before)

    def test_source_namespace_survives_storage_and_citation_resolution(self):
        index = Index(self.path, source_namespace="polarion")
        document = Document(
            corpus="project",
            document_id="REQ/1",
            revision="1",
            text="requirement backup",
            source_namespace="polarion",
        )
        other = document.model_copy(update={"source_namespace": "jira"})
        self.assertNotEqual(document.key, other.key)
        index.sync("project", [document])
        hits = index.search("backup", "project")
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual(index.get_document("project", "REQ/1", "1"), document)
        with self.assertRaises(ValueError):
            index.sync("project", [other])
        self.assertEqual(hit.source_uri, "polarion://source/project/REQ%2F1/1")
        self.assertEqual(index.get_passage(hit.passage_id).source_uri, document.source_uri)

    def test_wrong_index_namespace_is_rejected(self):
        Index(self.path, source_namespace="jira").sync("project", [])
        with self.assertRaisesRegex(ValueError, "configuration mismatch"):
            Index(self.path, source_namespace="polarion").status("project")
