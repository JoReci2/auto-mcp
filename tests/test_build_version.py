"""Exercise tag-derived versions and rebuilding the source distribution without Git."""

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.verify_release import verify
from yamcps.server import create_server


class BuildVersionTests(unittest.TestCase):
    def test_server_announces_installed_version(self):
        """Use package metadata instead of a fixed MCP server version."""
        with patch("yamcps.server.version", return_value="0.2.0") as metadata:
            server = create_server([], secret_values={}, config_values={})
        metadata.assert_called_once_with("yamcps")
        self.assertEqual(server.version, "0.2.0")

    def test_tag_sets_both_archives_and_sdist_rebuild(self):
        """Build successive release tags without changing project metadata."""
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            root.mkdir()
            for name in ("pyproject.toml", "README.md", "LICENSE"):
                shutil.copy2(project / name, root / name)
            shutil.copytree(
                project / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__")
            )
            env = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith("SETUPTOOLS_SCM_")
            }
            env.update(
                GIT_AUTHOR_NAME="Test",
                GIT_AUTHOR_EMAIL="test@example.com",
                GIT_COMMITTER_NAME="Test",
                GIT_COMMITTER_EMAIL="test@example.com",
            )

            def run(*args):
                subprocess.run(args, cwd=root, env=env, check=True, capture_output=True, text=True)

            run("git", "init")
            run("git", "add", ".")
            run("git", "commit", "-m", "Initial package")
            original = (root / "pyproject.toml").read_bytes()
            for tag in ("v0.2.0", "v0.3.0"):
                if tag == "v0.3.0":
                    run("git", "commit", "--allow-empty", "-m", "Next release")
                run("git", "tag", tag)
                output = root / "dist" / tag
                run(sys.executable, "-m", "build", "--no-isolation", "--outdir", str(output))
                verify(output, tag)
                self.assertEqual(original, (root / "pyproject.toml").read_bytes())

            unpacked = Path(temporary) / "unpacked"
            with tarfile.open(next(output.glob("*.tar.gz"))) as archive:
                archive.extractall(unpacked, filter="data")
            source = next(unpacked.iterdir())
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "build",
                    "--wheel",
                    "--no-isolation",
                    "--outdir",
                    str(output),
                    str(source),
                ],
                cwd=unpacked,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            verify(output, "v0.3.0")
