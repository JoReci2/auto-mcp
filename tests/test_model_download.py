"""Explicit local model downloads, pinned revisions and failure cleanup."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from yamcps.cli import main
from yamcps.rag.download import ModelDownloadError, _load_hub, download_model

COMMIT = "a" * 40


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hub = Mock()
        self.hub.HfApi.return_value.model_info.return_value.sha = COMMIT
        self.hub.HfApi.return_value.model_info.return_value.siblings = [
            Mock(rfilename="model.safetensors")
        ]
        self.hub.snapshot_download.side_effect = self.snapshot
        provider = patch("yamcps.rag.download._load_hub", return_value=self.hub)
        provider.start()
        self.addCleanup(provider.stop)
        environment = patch.dict(os.environ, {"YAMCPS_MODELS_DIR": str(self.root)}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def snapshot(self, **kwargs):
        root = Path(kwargs["local_dir"])
        root.mkdir(parents=True)
        (root / "modules.json").write_text(
            json.dumps(
                [
                    {
                        "idx": 0,
                        "name": "0",
                        "path": "",
                        "type": "sentence_transformers.models.Transformer",
                    }
                ]
            )
        )
        (root / "config.json").write_text("{}")
        (root / "model.safetensors").write_bytes(b"fake weights for downloader tests")
        (root / ".cache/huggingface").mkdir(parents=True)
        (root / ".cache/huggingface/metadata").write_text("temporary download metadata")
        return str(root)

    def test_download_is_pinned_and_materialized_without_metadata_cache(self):
        result = download_model("organization/model", revision="v1")
        self.assertEqual(result, self.root / "organization--model" / COMMIT)
        self.assertTrue((result / "model.safetensors").is_file())
        self.assertFalse((result / ".cache").exists())
        self.assertEqual(
            json.loads((result / "yamcps-model.json").read_text()),
            {
                "repo_id": "organization/model",
                "revision": "v1",
                "commit": COMMIT,
            },
        )
        kwargs = self.hub.snapshot_download.call_args.kwargs
        self.assertEqual(kwargs["revision"], COMMIT)
        self.assertFalse(kwargs["token"])
        self.assertIn("*.py", kwargs["ignore_patterns"])
        self.assertIn("*.safetensors", kwargs["allow_patterns"])
        self.assertNotIn("*.bin", kwargs["allow_patterns"])
        self.assertFalse(any(result.parent.glob("*.download.lock")))

    def test_binary_weights_fallback(self):
        self.hub.HfApi.return_value.model_info.return_value.siblings = []
        download_model("org/model")
        patterns = self.hub.snapshot_download.call_args.kwargs["allow_patterns"]
        self.assertIn("*.bin", patterns)
        self.assertNotIn("*.safetensors", patterns)

    def test_stateless_normalize_module_needs_no_files(self):
        def snapshot(**kwargs):
            self.snapshot(**kwargs)
            root = Path(kwargs["local_dir"])
            modules = json.loads((root / "modules.json").read_text())
            modules.append(
                {"path": "2_Normalize", "type": "sentence_transformers.models.Normalize"}
            )
            (root / "modules.json").write_text(json.dumps(modules))

        self.hub.snapshot_download.side_effect = snapshot
        result = download_model("org/model")
        self.assertTrue((result / "modules.json").is_file())

    def test_existing_destination_is_never_overwritten(self):
        destination = self.root / "existing"
        destination.mkdir()
        (destination / "keep").write_text("original")
        with self.assertRaisesRegex(ModelDownloadError, "already exists"):
            download_model("organization/model", destination=destination)
        self.assertEqual((destination / "keep").read_text(), "original")
        self.hub.snapshot_download.assert_not_called()

    def test_failure_leaves_no_model_and_hides_token(self):
        destination = self.root / "broken"
        self.hub.snapshot_download.side_effect = RuntimeError("private HF_TOKEN=secret")
        with self.assertRaises(ModelDownloadError) as error:
            download_model("organization/model", destination=destination)
        self.assertNotIn("secret", str(error.exception))
        self.assertFalse(destination.exists())
        self.assertFalse(list(self.root.glob(".yamcps-model-*")))
        self.assertFalse(list(self.root.glob("*.download.lock")))

    def test_invalid_layout_and_symlinks_are_not_published(self):
        for variant in ["missing", "empty", "traversal", "not-directory", "no-weights", "symlink"]:

            def snapshot(**kwargs):
                self.snapshot(**kwargs)
                root = Path(kwargs["local_dir"])
                if variant == "missing":
                    (root / "modules.json").unlink()
                elif variant == "empty":
                    (root / "modules.json").write_text("[]")
                elif variant == "traversal":
                    (root / "modules.json").write_text('[{"path":"../outside"}]')
                elif variant == "not-directory":
                    (root / "modules.json").write_text('[{"path":"absent"}]')
                elif variant == "no-weights":
                    (root / "model.safetensors").unlink()
                else:
                    (root / "linked").symlink_to(root / "config.json")

            self.hub.snapshot_download.side_effect = snapshot
            with self.subTest(variant=variant), self.assertRaises(ModelDownloadError):
                download_model("organization/model", destination=self.root / variant)
            self.assertFalse((self.root / variant).exists())

    def test_invalid_inputs_dependency_and_commit(self):
        for repo in [
            "../escape",
            "https://host/repo",
            "org/../x",
            "org/a--b",
            "org/a..b",
            "single",
        ]:
            with self.subTest(repo=repo), self.assertRaises(ModelDownloadError):
                download_model(repo)
        with self.assertRaises(ModelDownloadError):
            download_model("org/model", revision="")
        with patch("yamcps.rag.download.importlib.import_module", side_effect=ImportError):
            with self.assertRaisesRegex(ModelDownloadError, r"yamcps\[models\]"):
                _load_hub()
        self.hub.HfApi.return_value.model_info.return_value.sha = None
        with self.assertRaisesRegex(ModelDownloadError, "immutable"):
            download_model("org/model")

    def test_auth_and_lock_are_explicit(self):
        destination = self.root / "locked"
        lock = self.root / "locked.download.lock"
        lock.write_text("another operation")
        with self.assertRaises(ModelDownloadError):
            download_model("org/model", destination=destination)
        self.assertTrue(lock.exists())
        lock.unlink()
        with patch.dict(os.environ, {"HF_TOKEN": "private-token"}):
            result = download_model("org/model", destination=destination)
        self.assertEqual(self.hub.snapshot_download.call_args.kwargs["token"], "private-token")
        self.assertNotIn("private-token", (result / "yamcps-model.json").read_text())

    def test_cli_outputs_the_model_path_without_starting_server(self):
        destination = self.root / "cli-model"
        with patch(
            "sys.argv",
            [
                "yamcps",
                "models",
                "download",
                "org/model",
                "--revision",
                "v1",
                "--destination",
                str(destination),
            ],
        ):
            with (
                patch("yamcps.cli.create_server") as server,
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                main()
        self.assertEqual(output.getvalue().strip(), str(destination))
        server.assert_not_called()
        with patch("sys.argv", ["yamcps", "models", "download", "invalid"]):
            with (
                contextlib.redirect_stderr(io.StringIO()) as output,
                self.assertRaises(SystemExit) as error,
            ):
                main()
        self.assertEqual(error.exception.code, 2)
        self.assertIn("organization/model", output.getvalue())
