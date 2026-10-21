import hashlib

import pytest
import yaml

from hmcp.skills import SkillCatalog


def skill_root(tmp_path, frontmatter="name: demo-test\ndescription: A test"):
    root = tmp_path / "demo-test"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(f"---\n{frontmatter}\n---\nInstructions\n")
    return root


@pytest.mark.parametrize(
    "frontmatter",
    [
        "name: other\ndescription: test",
        "name: demo-test",
        "[invalid",
        "[]",
        "name: demo-test\ndescription: 42",
    ],
)
def test_invalid_frontmatter(tmp_path, frontmatter):
    root = skill_root(tmp_path, frontmatter)
    with pytest.raises((ValueError, yaml.YAMLError)):
        SkillCatalog().add_roots("demo", [root])


def test_missing_frontmatter(tmp_path):
    root = skill_root(tmp_path)
    (root / "SKILL.md").write_text("No frontmatter")
    with pytest.raises(ValueError, match="frontmatter"):
        SkillCatalog().add_roots("demo", [root])


def test_manifest_and_snapshot(tmp_path):
    root = skill_root(tmp_path)
    (root / "asset.bin").write_bytes(b"\xff\x00")
    catalog = SkillCatalog()
    catalog.add_roots("demo", [root])
    for resource in catalog.skills["skill://demo-test/SKILL.md"]["resources"]:
        data = catalog.files[resource["uri"]]
        assert resource["size"] == len(data)
        assert resource["digest"] == "sha256:" + hashlib.sha256(data).hexdigest()
    (root / "SKILL.md").write_text("changed")
    assert b"Instructions" in catalog.files["skill://demo-test/SKILL.md"]
    with pytest.raises(ValueError, match="Duplicate"):
        catalog.add_roots("demo", [skill_root(tmp_path / "second")])


def test_symlink_escape(tmp_path):
    root = skill_root(tmp_path)
    outside = tmp_path / "secret"
    outside.write_text("private")
    (root / "escape").symlink_to(outside)
    with pytest.raises(ValueError, match="symbolic"):
        SkillCatalog().add_roots("demo", [root])


async def test_binary_resource(tmp_path):
    import base64

    from mcp import Client

    from hmcp.registry import StrictServer

    root = skill_root(tmp_path)
    (root / "asset.bin").write_bytes(b"\xff\x00")
    catalog = SkillCatalog()
    catalog.add_roots("demo", [root])
    server = StrictServer(name="binary-test", extensions=[catalog])
    catalog.register_resources(server)
    async with Client(server) as client:
        result = await client.read_resource("skill://demo-test/asset.bin")
        assert base64.b64decode(result.contents[0].blob) == b"\xff\x00"
