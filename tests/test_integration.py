import asyncio
import hashlib
import socket
import sys

import pytest
from mcp import Client, StdioServerParameters
from mcp.client.extension import advertise
from mcp.types import Request, RequestParams, Result

from hmcp.server import create_server
from hmcp.skills import GetSkillParams


class ListResult(Result):
    skills: list[dict]


class GetResult(Result):
    skill: dict


async def exercise(target):
    async with Client(target, extensions=[advertise("io.modelcontextprotocol/skills")]) as client:
        result = await client.call_tool("demo_echo", {"message": "Bonjour MCP"})
        assert result.structured_content == {"result": "Bonjour MCP"}
        listed = await client.session.send_request(
            Request(method="skills/list", params=RequestParams()), ListResult
        )
        assert len(listed.skills) == 1
        uri = listed.skills[0]["uri"]
        fetched = await client.session.send_request(
            Request(method="skills/get", params=GetSkillParams(uri=uri)), GetResult
        )
        assert fetched.skill == listed.skills[0]
        resource = fetched.skill["resources"][0]
        content = await client.read_resource(uri)
        data = content.contents[0].text.encode()
        assert hashlib.sha256(data).hexdigest() == resource["digest"].removeprefix("sha256:")
        assert len(data) == resource["size"]
        for bad_uri in ["skill://demo-echo/missing", "skill://demo-echo/../secret"]:
            with pytest.raises(Exception):
                await client.read_resource(bad_uri)
        with pytest.raises(Exception):
            await client.session.send_request(
                Request(method="skills/get", params=GetSkillParams(uri="skill://unknown/SKILL.md")),
                GetResult,
            )


async def test_memory():
    await exercise(create_server(["demo"]))


async def test_stdio():
    await exercise(
        StdioServerParameters(
            command=sys.executable, args=["-m", "hmcp", "serve", "--connector", "demo"]
        )
    )


async def test_http(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log = tmp_path / "server.log"
    with log.open("wb") as output:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "hmcp",
            "serve",
            "--connector",
            "demo",
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
                        pytest.fail(log.read_text())
                    try:
                        reader, writer = await asyncio.open_connection("127.0.0.1", port)
                        writer.close()
                        await writer.wait_closed()
                        break
                    except OSError:
                        await asyncio.sleep(0.05)
            await exercise(f"http://127.0.0.1:{port}/mcp")
        finally:
            if process.returncode is None:
                process.terminate()
            await asyncio.wait_for(process.wait(), timeout=10)
