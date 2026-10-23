"""Skills-only connector discovery and MCP resource delivery."""

import asyncio
import hashlib
import re
import socket
import sys
import tempfile
import unittest
from pathlib import Path

from mcp import Client, StdioServerParameters
from mcp.client.extension import advertise
from mcp.types import Request, RequestParams, Result
from yamcps_extras import ExtrasConnector

from yamcps.connectors import load
from yamcps.rag import Document, Index
from yamcps.server import create_server
from yamcps.skills import GetSkillParams


class SkillsResult(Result):
    skills: list[dict]


class SkillResult(Result):
    skill: dict


class ExtrasTests(unittest.TestCase):
    def test_entry_point_and_bundled_references(self):
        connector = load(["extras"])[0]
        self.assertIsInstance(connector, ExtrasConnector)
        roots = list(connector.skill_roots())
        self.assertEqual(len(roots), 4)
        for root in roots:
            text = (root / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(root.name.startswith("extras-"))
            self.assertNotIn("TODO", text)
            for target in re.findall(r"\]\((assets/[^)]+)\)", text):
                self.assertTrue((root / target).is_file(), target)
        self.assertFalse(hasattr(connector, "required_secrets"))
        self.assertFalse(hasattr(connector, "configure"))


class ExtrasIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, target):
        expected = {root.name for root in ExtrasConnector().skill_roots()}
        async with Client(
            target, extensions=[advertise("io.modelcontextprotocol/skills")]
        ) as client:
            self.assertEqual((await client.list_tools()).tools, [])
            self.assertEqual((await client.list_prompts()).prompts, [])
            listed = await client.session.send_request(
                Request(method="skills/list", params=RequestParams()), SkillsResult
            )
            self.assertEqual({s["frontmatter"]["name"] for s in listed.skills}, expected)
            resources = (await client.list_resources()).resources
            self.assertEqual(len(resources), 6)
            self.assertTrue(all(str(r.uri).startswith("skill://extras-") for r in resources))
            for skill in listed.skills:
                fetched = await client.session.send_request(
                    Request(method="skills/get", params=GetSkillParams(uri=skill["uri"])),
                    SkillResult,
                )
                self.assertEqual(fetched.skill, skill)
                for resource in skill["resources"]:
                    response = await client.read_resource(resource["uri"])
                    data = response.contents[0].text.encode()
                    self.assertEqual(len(data), resource["size"])
                    self.assertEqual(
                        "sha256:" + hashlib.sha256(data).hexdigest(), resource["digest"]
                    )
            with self.assertRaises(Exception):
                await client.read_resource("skill://extras-configure-agents/../private")

    async def test_memory(self):
        await self.exercise(create_server(["extras"]))

    async def test_stdio(self):
        await self.exercise(
            StdioServerParameters(
                command=sys.executable, args=["-m", "yamcps", "serve", "--connector", "extras"]
            )
        )

    async def test_http(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with tempfile.TemporaryFile() as output:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "yamcps",
                "serve",
                "--connector",
                "extras",
                "--transport",
                "http",
                "--port",
                str(port),
                stdout=output,
                stderr=output,
            )
            try:
                async with asyncio.timeout(15):
                    while True:
                        if process.returncode is not None:
                            self.fail("Extras HTTP process exited")
                        try:
                            _, writer = await asyncio.open_connection("127.0.0.1", port)
                            writer.close()
                            await writer.wait_closed()
                            break
                        except OSError:
                            await asyncio.sleep(0.05)
                await self.exercise(f"http://127.0.0.1:{port}/mcp")
            finally:
                if process.returncode is None:
                    process.terminate()
                await asyncio.wait_for(process.wait(), timeout=10)

    async def test_coexists_with_demo(self):
        async with Client(create_server(["extras", "demo"])) as client:
            self.assertEqual({t.name for t in (await client.list_tools()).tools}, {"demo_echo"})
            self.assertEqual(len((await client.list_resources()).resources), 7)
            response = await client.call_tool("demo_echo", {"message": "extras coexist"})
            self.assertEqual(response.structured_content["result"], "extras coexist")

    async def test_coexists_with_configured_docs_and_lazy_rag(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "docs.sqlite3"
            server = create_server(
                ["extras", "docs"],
                config_values={"YAMCPS_DOCS_INDEX": str(path), "YAMCPS_DOCS_MODEL": ""},
            )
            async with Client(server) as client:
                self.assertEqual(
                    {tool.name for tool in (await client.list_tools()).tools},
                    {"docs_search", "docs_get_document", "docs_get_passage", "docs_index_status"},
                )
                self.assertEqual((await client.list_prompts()).prompts, [])
                self.assertEqual(len((await client.list_resources()).resources), 7)
                skill = await client.read_resource("skill://extras-develop-plugin/SKILL.md")
                self.assertIn("required_configs()", skill.contents[0].text)
                self.assertIn("yamcps.rag", skill.contents[0].text)
                self.assertFalse(path.exists())
                Index(path).sync(
                    "example",
                    [Document(corpus="example", document_id="SSS", revision="1", text="evidence")],
                )
                response = await client.call_tool(
                    "docs_search", {"query": "evidence", "corpus": "example"}
                )
                self.assertFalse(response.is_error)
                self.assertIn("evidence", str(response.structured_content))


if __name__ == "__main__":
    unittest.main()
