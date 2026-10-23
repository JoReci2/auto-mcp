"""Core retrieval opt-in, lazy injection and compatibility with existing plugins."""

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from yamcps import RagConfig, RagContext
from yamcps.connectors import ConnectorError
from yamcps.rag import Document
from yamcps.server import create_server


class RetrievalPlugin:
    def __init__(self, identifier):
        self.id = identifier
        self.context = None

    def rag_config(self):
        return RagConfig()

    def configure_rag(self, rag):
        self.context = rag

    def register(self, server):
        pass


class RagCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "rag"
        environment = patch.dict("os.environ", {"YAMCPS_RAG_DIR": str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)

    def test_existing_plugin_needs_no_hooks_or_database(self):
        with patch("yamcps.rag.context.LocalSentenceTransformer") as model:
            create_server(["demo"])
        model.assert_not_called()
        self.assertFalse(self.root.exists())

    def test_two_plugins_receive_separate_lazy_indexes(self):
        alpha, beta = RetrievalPlugin("alpha"), RetrievalPlugin("beta")
        with patch("yamcps.server.load", return_value=[alpha, beta]):
            create_server()
        self.assertFalse(self.root.exists())
        self.assertNotEqual(alpha.context.path, beta.context.path)
        for plugin, text in [(alpha, "alpha requirement"), (beta, "beta requirement")]:
            plugin.context.index.sync(
                "specs",
                [
                    Document(
                        corpus="specs",
                        document_id="SSS",
                        revision="1",
                        text=text,
                    )
                ],
            )
        self.assertEqual(alpha.context.index.search("alpha", "specs")[0].text, "alpha requirement")
        self.assertEqual(beta.context.index.search("alpha", "specs"), [])
        self.assertEqual(alpha.context.path, self.root / "alpha.sqlite3")

    def test_hooks_run_after_secrets_before_skills_and_registration(self):
        calls = []

        class Plugin(RetrievalPlugin):
            def configure(self, secrets):
                calls.append("secrets")

            def rag_config(self):
                calls.append("rag_config")
                return RagConfig()

            def configure_rag(self, rag):
                calls.append("configure_rag")
                super().configure_rag(rag)

            def skill_roots(self):
                calls.append("skills")
                return []

            def register(self, server):
                calls.append("register")
                assert self.context is not None

        plugin = Plugin("example")
        with patch("yamcps.server.load", return_value=[plugin]):
            create_server(secret_values={})
        self.assertEqual(calls, ["secrets", "rag_config", "configure_rag", "skills", "register"])
        self.assertFalse(self.root.exists())

    def test_invalid_hooks_fail_without_leaking_details(self):
        async def async_hook():
            return RagConfig()

        for declaration, consumer in [
            (lambda: {}, lambda context: None),
            (async_hook, lambda context: None),
            (None, lambda context: None),
            (lambda: RagConfig(), None),
            (lambda: RagConfig(), async_hook),
        ]:
            plugin = Mock(
                id="invalid",
                register=Mock(),
                rag_config=declaration,
                configure_rag=consumer,
                spec=["id", "register", "rag_config", "configure_rag"],
            )
            with (
                self.subTest(declaration=declaration),
                patch("yamcps.server.load", return_value=[plugin]),
            ):
                with self.assertRaisesRegex(ConnectorError, "invalid.*RAG configuration"):
                    create_server()
        plugin = RetrievalPlugin("broken")
        plugin.configure_rag = Mock(side_effect=ValueError("/private/path secret-value"))
        with patch("yamcps.server.load", return_value=[plugin]):
            with self.assertRaises(ConnectorError) as error:
                create_server()
        self.assertNotIn("secret-value", str(error.exception))
        self.assertNotIn("/private/path", str(error.exception))

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
        with self.assertRaises(ValueError):
            RagContext("../escape", RagConfig())
        with self.assertRaises(TypeError):
            RagConfig(index_path="invalid")
