"""Reject plugin distributions and mismatched versions before publication."""

import io
import runpy
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

verify = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / ".github/workflows/verify_release.py")
)["verify"]


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.artifacts()

    def artifacts(self, name="yamcps", version="0.1.0", extra_module=None):
        metadata = f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n".encode()
        with zipfile.ZipFile(self.root / "base.whl", "w") as archive:
            archive.writestr(f"{name}-{version}.dist-info/METADATA", metadata)
            archive.writestr("yamcps/__init__.py", "")
            if extra_module:
                archive.writestr(extra_module + "/__init__.py", "")
        with tarfile.open(self.root / "base.tar.gz", "w:gz") as archive:
            member = tarfile.TarInfo(f"{name}-{version}/PKG-INFO")
            member.size = len(metadata)
            archive.addfile(member, io.BytesIO(metadata))

    def test_base_artifacts_match_release(self):
        verify(self.root, "v0.1.0")

    def test_plugin_or_wrong_version_cannot_be_uploaded(self):
        for name, version in [("yamcps-demo", "0.1.0"), ("hmcp", "0.1.0"), ("yamcps", "0.2.0")]:
            with self.subTest(name=name, version=version):
                self.artifacts(name, version)
                with self.assertRaises(ValueError):
                    verify(self.root, "v0.1.0")

    def test_extra_artifact_or_missing_sdist_rejected(self):
        (self.root / "plugin.whl").touch()
        with self.assertRaises(ValueError):
            verify(self.root, "v0.1.0")
        (self.root / "plugin.whl").unlink()
        (self.root / "base.tar.gz").unlink()
        with self.assertRaises(ValueError):
            verify(self.root, "v0.1.0")

    def test_tag_format_and_embedded_plugin_rejected(self):
        for tag in ["0.1.0", "v", "v0.2.0"]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                verify(self.root, tag)
        for module in ["yamcps_demo", "hmcp"]:
            self.artifacts(extra_module=module)
            with self.assertRaises(ValueError):
                verify(self.root, "v0.1.0")

    def test_archive_metadata_is_required(self):
        with zipfile.ZipFile(self.root / "base.whl", "w") as archive:
            archive.writestr("yamcps/__init__.py", "")
        with self.assertRaises(ValueError):
            verify(self.root, "v0.1.0")
        self.artifacts()
        with tarfile.open(self.root / "base.tar.gz", "w:gz") as archive:
            member = tarfile.TarInfo("base/NOT-METADATA")
            archive.addfile(member, io.BytesIO())
        with self.assertRaises(ValueError):
            verify(self.root, "v0.1.0")
