"""Standalone demo retrieval through the real MCP client."""

import asyncio
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import Client, StdioServerParameters

from yamcps.server import create_server


class DemoRagTests(unittest.IsolatedAsyncioTestCase):
    async def _exercise(self, target):
        async with Client(target) as client:
            await client.call_tool("demo_rag_ingest", {})
            result = await client.call_tool("demo_rag_search", {"query": "horaires"})
            self.assertFalse(result.is_error)
            self.assertIn("demo-rag://source/examples/horaires-bibliotheque/1", str(result))
            resource = await client.read_resource(
                "demo-rag://source/examples/horaires-bibliotheque/1"
            )
            self.assertIn("du mardi au samedi", resource.contents[0].text)
            loans = await client.call_tool("demo_rag_search", {"query": "emprunter"})
            self.assertFalse(loans.is_error)
            self.assertIn("demo-rag://source/examples/emprunt-livres/1", str(loans))
            repeated = await client.call_tool("demo_rag_ingest", {})
            self.assertEqual(repeated.structured_content["unchanged"], 2)

    async def test_memory_and_lazy_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "rag"
            with patch.dict(os.environ, {"YAMCPS_RAG_DIR": str(root)}):
                server = create_server(["demo-rag"])
                self.assertFalse(root.exists())
                await self._exercise(server)
                self.assertTrue((root / "demo-rag.sqlite3").is_file())

    async def test_stdio(self):
        with tempfile.TemporaryDirectory() as temporary:
            await self._exercise(
                StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "yamcps", "serve", "--connector", "demo-rag"],
                    env={**os.environ, "YAMCPS_RAG_DIR": temporary},
                )
            )

    async def test_http(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with tempfile.TemporaryDirectory() as temporary:
            with (Path(temporary) / "server.log").open("wb") as output:
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "yamcps",
                    "serve",
                    "--connector",
                    "demo-rag",
                    "--transport",
                    "http",
                    "--port",
                    str(port),
                    env={**os.environ, "YAMCPS_RAG_DIR": temporary},
                    stdout=output,
                    stderr=output,
                )
                try:
                    async with asyncio.timeout(15):
                        while True:
                            if process.returncode is not None:
                                self.fail("Demo HTTP server exited before accepting connections")
                            try:
                                _, writer = await asyncio.open_connection("127.0.0.1", port)
                                writer.close()
                                await writer.wait_closed()
                                break
                            except OSError:
                                await asyncio.sleep(0.05)
                    await self._exercise(f"http://127.0.0.1:{port}/mcp")
                finally:
                    if process.returncode is None:
                        process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=10)
