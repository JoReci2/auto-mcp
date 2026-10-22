"""Validate the exact base-package artifacts before uploading them to PyPI."""

import argparse
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path


def _wheel_metadata(path: Path) -> bytes:
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
        metadata_paths = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_paths) != 1 or any(name.startswith(("hmcp", "yamcps_")) for name in names):
            raise ValueError("Wheel must contain only the renamed base package")
        return wheel.read(metadata_paths[0])


def _source_metadata(path: Path) -> bytes:
    with tarfile.open(path, "r:gz") as archive:
        members = [
            m
            for m in archive.getmembers()
            if m.name.count("/") == 1 and m.name.endswith("/PKG-INFO")
        ]
        if len(members) != 1:
            raise ValueError("Expected one root source metadata file")
        stream = archive.extractfile(members[0])
        if stream is None:
            raise ValueError("Missing source metadata")
        with stream:
            return stream.read()


def verify(directory: Path, tag: str) -> None:
    """Require exactly one yamcps wheel and sdist matching a v-prefixed tag.

    Args:
        directory: Dedicated output directory for the root package build.
        tag: GitHub release tag, such as v0.1.0.

    Raises:
        ValueError: Unexpected artifacts, distribution name or version.
    """
    files = sorted(directory.iterdir())
    wheels = [p for p in files if p.name.endswith(".whl")]
    sources = [p for p in files if p.name.endswith(".tar.gz")]
    if len(files) != 2 or len(wheels) != 1 or len(sources) != 1:
        raise ValueError("Expected exactly one base wheel and one source archive")
    if not tag.startswith("v") or not tag[1:]:
        raise ValueError("Release tag must have the form v<package-version>")
    metadata = [_wheel_metadata(wheels[0]), _source_metadata(sources[0])]
    for raw in metadata:
        message = BytesParser().parsebytes(raw)
        if message["Name"] != "yamcps" or message["Version"] != tag[1:]:
            raise ValueError("Only yamcps matching the release tag may be published")


def main() -> None:
    """Validate a build directory against its release tag."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    verify(args.directory, args.tag)


if __name__ == "__main__":
    main()
