"""Lazy retrieval configuration and plugin-owned backend construction."""

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from yamcps.rag import RagConfig, RagContext


class RagContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "rag"

    def test_explicit_paths_lazy_model_and_concurrent_access(self):
        config = RagConfig(index_path=self.root / "custom.sqlite3", model_path=self.root / "model")
        with patch("yamcps.rag.context.LocalSentenceTransformer") as provider:
            context = RagContext("example", config)
            provider.assert_not_called()
            self.assertFalse(self.root.exists())
            with ThreadPoolExecutor(max_workers=4) as pool:
                indexes = list(pool.map(lambda _: context.index, range(8)))
            provider.assert_called_once_with(config.model_path)
            self.assertTrue(all(index is indexes[0] for index in indexes))
            self.assertEqual(indexes[0].path, config.index_path)
        self.assertFalse(self.root.exists())

    def test_invalid_connector_id_is_rejected(self):
        with self.assertRaises(ValueError):
            RagContext("../escape", RagConfig())

    def test_invalid_path_types_are_rejected(self):
        for field in ("index_path", "model_path"):
            with self.subTest(field=field), self.assertRaises(TypeError):
                RagConfig(**{field: "invalid"})

    def test_custom_backend_is_lazy_and_created_once(self):
        backend = Mock()
        factory = Mock(return_value=backend)
        context = RagContext("external", RagConfig(index_factory=factory), root=self.root)
        factory.assert_not_called()
        with ThreadPoolExecutor(max_workers=4) as pool:
            indexes = list(pool.map(lambda _: context.index, range(8)))
        self.assertTrue(all(index is backend for index in indexes))
        factory.assert_called_once_with(self.root / "external.sqlite3")
        self.assertFalse(self.root.exists())

    def test_factory_failure_can_be_retried(self):
        backend = Mock()
        factory = Mock(side_effect=[RuntimeError("unavailable"), backend])
        context = RagContext("external", RagConfig(index_factory=factory), root=self.root)
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
