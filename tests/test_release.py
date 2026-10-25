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

    def test_requested_pep440_release_formats(self):
        versions = (
            "1.2.0",
            "1.2.0.dev1",
            "1.2.0a1",
            "1.2.0b1",
            "1.2.0rc1",
            "1.2.0.post1",
            "23.12",
            "42",
        )
        for version in versions:
            with self.subTest(version=version):
                self.artifacts(version=version)
                verify(self.root, f"v{version}")

    def test_discouraged_release_formats_are_rejected(self):
        for version in ("1!1.0", "1.2.0a1.post1", "1.2.0b1.post1", "1.2.0rc1.post1"):
            with self.subTest(version=version):
                self.artifacts(version=version)
                with self.assertRaisesRegex(ValueError, "epochs or post-releases"):
                    verify(self.root, f"v{version}")

    def test_development_release_tag_is_normalized(self):
        for tag in ("v0.4.0dev1", "v0.4.0.dev1"):
            with self.subTest(tag=tag):
                self.artifacts(version="0.4.0.dev1")
                verify(self.root, tag)

    def test_other_development_or_local_versions_are_rejected(self):
        for tag, version in (
            ("v0.4.0dev1", "0.4.0.dev2"),
            ("v0.4.0dev1", "0.4.0"),
            ("v0.4.0", "0.4.0.dev1"),
            ("v0.4.0dev1", "0.4.0.dev1+g123"),
            ("v0.4.0dev1+g123", "0.4.0.dev1+g123"),
            ("vnot-a-version", "0.4.0.dev1"),
        ):
            with self.subTest(tag=tag, version=version):
                self.artifacts(version=version)
                with self.assertRaises(ValueError):
                    verify(self.root, tag)

    def test_both_archives_must_match_the_normalized_tag(self):
        self.artifacts(version="0.4.0.dev1")
        with zipfile.ZipFile(self.root / "base.whl", "w") as archive:
            archive.writestr(
                "yamcps-0.4.0.dev2.dist-info/METADATA",
                "Name: yamcps\nVersion: 0.4.0.dev2\n",
            )
        with self.assertRaises(ValueError):
            verify(self.root, "v0.4.0dev1")

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
