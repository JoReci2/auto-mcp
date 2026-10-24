"""Plugin-owned factories and generic source identities."""

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

from yamcps.rag import Document, Index, RagConfig, RagContext


class RagExtensionTests(unittest.TestCase):
    def test_custom_backend_is_lazy_and_created_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            backend = Mock()
            factory = Mock(return_value=backend)
            context = RagContext("external", RagConfig(index_factory=factory), root=Path(temporary))
            factory.assert_not_called()
            with ThreadPoolExecutor(max_workers=4) as pool:
                indexes = list(pool.map(lambda _: context.index, range(8)))
            self.assertTrue(all(index is backend for index in indexes))
            factory.assert_called_once_with(Path(temporary) / "external.sqlite3")
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_factory_failure_can_be_retried(self):
        backend = Mock()
        factory = Mock(side_effect=[RuntimeError("unavailable"), backend])
        context = RagContext("external", RagConfig(index_factory=factory))
        with self.assertRaises(RuntimeError):
            context.index
        self.assertIs(context.index, backend)
        self.assertEqual(factory.call_count, 2)

    def test_factory_configuration_is_unambiguous(self):
        async def asynchronous_factory(path):
            return Mock()

        with self.assertRaises(TypeError):
            RagConfig(index_factory=asynchronous_factory)
        with self.assertRaises(ValueError):
            RagConfig(model_path=Path("model"), index_factory=Mock())
        with self.assertRaises(TypeError):
            RagConfig(index_factory=42)

    def test_source_namespace_survives_storage_and_citation_resolution(self):
        with tempfile.TemporaryDirectory() as temporary:
            index = Index(Path(temporary) / "index.sqlite3", source_namespace="polarion")
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
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "index.sqlite3"
            Index(path, source_namespace="jira").sync("project", [])
            with self.assertRaisesRegex(ValueError, "configuration mismatch"):
                Index(path, source_namespace="polarion").status("project")
