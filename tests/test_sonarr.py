"""Sonarr contract tests using its documented API v3 wire shapes."""

import contextlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import httpx
from hmcp_sonarr import SonarrConnector
from hmcp_sonarr.client import SonarrClient, SonarrError, validate_url
from hmcp_sonarr.service import SonarrService
from mcp import Client
from mcp.server import MCPServer
from pydantic import SecretStr

from hmcp import ConnectorSecrets, SecretError
from hmcp.server import create_server
from hmcp.vault import Vault

_KEY = "sentinel-sonarr-key-93217"
_URL = "https://sonarr.example.test/tv"
_VALUES = {"HMCP_SONARR_URL": _URL, "HMCP_SONARR_API_KEY": _KEY}
_SERIES = {
    "id": 42,
    "tvdbId": 77,
    "title": "Example Series",
    "year": 2024,
    "monitored": True,
    "seasons": [{"seasonNumber": 1, "monitored": True}],
    "apiKey": _KEY,
}


class SonarrClientTests(unittest.IsolatedAsyncioTestCase):
    def client(self, handler):
        return SonarrClient(_URL, SecretStr(_KEY), transport=httpx.MockTransport(handler))

    async def test_header_prefix_timeout_and_no_credentials_in_url(self):
        requests = []

        def respond(request):
            requests.append(request)
            self.assertEqual(request.headers["X-Api-Key"], _KEY)
            self.assertEqual(str(request.url), _URL + "/api/v3/series?tvdbId=77")
            self.assertNotIn(_KEY, str(request.url))
            self.assertEqual(request.extensions["timeout"]["connect"], 5.0)
            self.assertEqual(request.extensions["timeout"]["read"], 15.0)
            return httpx.Response(200, json=[_SERIES])

        self.assertEqual(
            await self.client(respond).array("series", params={"tvdbId": 77}), [_SERIES]
        )
        self.assertEqual(len(requests), 1)

    async def test_status_errors_do_not_echo_response_body_or_key(self):
        for status, message in [
            (400, "rejected"),
            (401, "authentication"),
            (403, "denied"),
            (404, "not found"),
            (409, "conflict"),
            (422, "rejected"),
            (429, "rate limit"),
            (503, "HTTP 503"),
        ]:
            with self.subTest(status=status):
                client = self.client(lambda request: httpx.Response(status, text=_KEY))
                with self.assertRaisesRegex(SonarrError, message) as error:
                    await client.object("system/status")
                self.assertNotIn(_KEY, str(error.exception))

    async def test_redirect_is_not_followed(self):
        seen = []

        def respond(request):
            seen.append(request)
            return httpx.Response(302, headers={"Location": "https://other.example.test/"})

        with self.assertRaisesRegex(SonarrError, "redirect"):
            await self.client(respond).object("system/status")
        self.assertEqual(len(seen), 1)

    async def test_timeouts_network_failures_and_invalid_json(self):
        for exception, expected in [
            (httpx.ReadTimeout, "timed out"),
            (httpx.ConnectError, "Cannot reach"),
        ]:

            def fail(request):
                raise exception(_KEY, request=request)

            with (
                self.subTest(exception=exception),
                self.assertRaisesRegex(SonarrError, expected) as error,
            ):
                await self.client(fail).object("system/status")
            self.assertNotIn(_KEY, str(error.exception))
        with self.assertRaisesRegex(SonarrError, "invalid JSON"):
            await self.client(lambda request: httpx.Response(200, text="<html>" + _KEY)).object(
                "system/status"
            )

    async def test_unexpected_shapes(self):
        for value, method in [([], "object"), ({}, "array"), ([1], "array")]:
            with self.subTest(value=value, method=method):
                client = self.client(lambda request: httpx.Response(200, json=value))
                with self.assertRaisesRegex(SonarrError, "unexpected"):
                    await getattr(client, method)("series")

    async def test_no_automatic_retry_on_uncertain_post(self):
        seen = []

        def fail(request):
            seen.append(request)
            raise httpx.ReadTimeout("uncertain", request=request)

        with self.assertRaises(SonarrError):
            await self.client(fail).object("series", payload={"tvdbId": 77})
        self.assertEqual(len(seen), 1)

    def test_url_and_key_validation(self):
        self.assertEqual(validate_url("http://localhost:8989/"), "http://localhost:8989")
        self.assertEqual(validate_url(_URL + "/"), _URL)
        for url in [
            "file:///tmp/sonarr",
            "example.test",
            "https://user:pass@example.test",
            "https://example.test/?apiKey=secret",
            "https://example.test/#fragment",
            "https://example.test/api/v3/",
            "https://example.test/has space",
            "http://example.test:invalid",
            "https://example.test/\\wrong",
        ]:
            with self.subTest(url=url), self.assertRaises(SecretError):
                validate_url(url)
        for value in ["", "bad\r\nheader", "non ascii é"]:
            with self.subTest(value=value), self.assertRaises(SecretError):
                SonarrClient(_URL, SecretStr(value))


class SonarrWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.requests = []
        self.existing = []
        self.candidates = [dict(_SERIES)]
        self.profiles = [{"id": 2, "name": "HD", "apiKey": _KEY}]
        self.roots = [{"id": 3, "path": "/media/tv", "freeSpace": 1000, "apiKey": _KEY}]
        self.episodes = [
            {"id": 10, "seriesId": 42, "seasonNumber": 1, "title": "Pilot", "apiKey": _KEY}
        ]
        self.queue = {
            "page": 1,
            "pageSize": 20,
            "totalRecords": 1,
            "records": [
                {"id": 5, "title": "Example Series", "status": "downloading", "secret": _KEY}
            ],
        }
        self.client = SonarrClient(
            _URL, SecretStr(_KEY), transport=httpx.MockTransport(self.respond)
        )
        self.service = SonarrService(self.client, ConnectorSecrets("sonarr", _VALUES).redact)

    def respond(self, request):
        self.requests.append(request)
        self.assertEqual(request.headers["X-Api-Key"], _KEY)
        route = request.url.path.removeprefix("/tv/api/v3/")
        if request.method == "POST":
            payload = json.loads(request.content)
            if route == "series":
                return httpx.Response(201, json={**payload, "id": 55, "apiKey": _KEY})
            if route == "command":
                return httpx.Response(
                    201,
                    json={"id": 9, "name": payload["name"], "status": "queued", "exception": _KEY},
                )
            self.fail(f"Unexpected POST: {route}")
        data = {
            "system/status": {"version": "4.0.0", "apiKey": _KEY},
            "series": self.existing if "tvdbId" in request.url.params else [_SERIES],
            "series/42": _SERIES,
            "series/lookup": self.candidates,
            "qualityprofile": self.profiles,
            "rootfolder": self.roots,
            "episode": self.episodes,
            "calendar": [{**self.episodes[0], "series": _SERIES}],
            "queue": self.queue,
            "command/9": {"id": 9, "status": "completed", "exception": _KEY},
        }
        if route not in data:
            self.fail(f"Unexpected GET: {route}")
        return httpx.Response(200, json=data[route])

    async def test_read_operations_and_projections(self):
        self.assertEqual(await self.service.system_status(), {"version": "4.0.0"})
        self.assertEqual(len(await self.service.list_series()), 1)
        self.assertEqual(len(await self.service.list_series("example")), 1)
        self.assertEqual(await self.service.list_series("absent"), [])
        self.assertEqual((await self.service.get_series(42))["tvdbId"], 77)
        self.assertEqual((await self.service.list_episodes(42, 0))[0]["id"], 10)
        self.assertEqual(
            dict(self.requests[-1].url.params), {"seriesId": "42", "seasonNumber": "0"}
        )
        await self.service.list_episodes(42)
        self.assertNotIn("seasonNumber", self.requests[-1].url.params)
        self.assertEqual(await self.service.quality_profiles(), [{"id": 2, "name": "HD"}])
        self.assertEqual((await self.service.root_folders())[0]["path"], "/media/tv")
        self.assertEqual((await self.service.lookup_series("Example"))[0]["tvdbId"], 77)
        self.assertEqual(self.requests[-1].url.params["term"], "Example")
        with self.assertRaises(SonarrError):
            await self.service.lookup_series("  ")

    async def test_calendar_and_queue_parameters(self):
        result = await self.service.calendar(date(2026, 1, 1), date(2026, 1, 7), True)
        self.assertEqual(result[0]["series"], {"id": 42, "title": "Example Series"})
        self.assertEqual(self.requests[-1].url.params["start"], "2026-01-01")
        self.assertEqual(self.requests[-1].url.params["unmonitored"], "true")
        with self.assertRaises(SonarrError):
            await self.service.calendar(date(2026, 1, 7), date(2026, 1, 1))
        result = await self.service.queue(page=2, page_size=50)
        self.assertEqual(self.requests[-1].url.params["pageSize"], "50")
        self.assertEqual(result["totalRecords"], 1)
        self.assertNotIn(_KEY, repr(result))
        self.queue["records"] = "invalid"
        with self.assertRaises(SonarrError):
            await self.service.queue()

    async def test_add_uses_catalog_and_existing_settings(self):
        result = await self.service.add_series(77, 2, 3)
        self.assertEqual(result["id"], 55)
        self.assertNotIn(_KEY, repr(result))
        payload = json.loads(self.requests[-1].content)
        self.assertEqual(payload["tvdbId"], 77)
        self.assertEqual(payload["title"], "Example Series")
        self.assertEqual(payload["rootFolderPath"], "/media/tv")
        self.assertEqual(payload["qualityProfileId"], 2)
        self.assertEqual(payload["addOptions"]["monitor"], "all")
        self.assertFalse(payload["addOptions"]["searchForMissingEpisodes"])
        self.assertEqual(payload["seasons"], [{"seasonNumber": 1, "monitored": True}])
        self.assertEqual(self.requests[1].url.params["term"], "tvdb:77")
        self.assertEqual([r.method for r in self.requests], ["GET", "GET", "GET", "GET", "POST"])

    async def test_add_monitoring_and_initial_search(self):
        await self.service.add_series(
            77, 2, 3, monitored=False, search_for_missing_episodes=True, series_type="anime"
        )
        payload = json.loads(self.requests[-1].content)
        self.assertEqual(payload["seriesType"], "anime")
        self.assertEqual(payload["addOptions"]["monitor"], "none")
        self.assertTrue(payload["addOptions"]["searchForMissingEpisodes"])
        self.assertFalse(payload["seasons"][0]["monitored"])

    async def test_add_preflight_failures_do_not_mutate(self):
        cases = [
            ("existing", [_SERIES], "already exists"),
            ("candidates", [], "not found"),
            ("profiles", [], "Quality profile"),
            ("roots", [], "Root folder"),
        ]
        for attribute, value, message in cases:
            original = getattr(self, attribute)
            self.requests.clear()
            setattr(self, attribute, value)
            with self.subTest(attribute=attribute), self.assertRaisesRegex(SonarrError, message):
                await self.service.add_series(77, 2, 3)
            self.assertFalse(any(request.method == "POST" for request in self.requests))
            setattr(self, attribute, original)

    async def test_active_searches_and_command_status(self):
        self.assertEqual((await self.service.search_series(42))["status"], "queued")
        self.assertEqual(
            json.loads(self.requests[-1].content), {"name": "SeriesSearch", "seriesId": 42}
        )
        result = await self.service.search_episodes([10, 10, 11])
        self.assertEqual(result["id"], 9)
        self.assertEqual(
            json.loads(self.requests[-1].content), {"name": "EpisodeSearch", "episodeIds": [10, 11]}
        )
        self.assertEqual(await self.service.command_status(9), {"id": 9, "status": "completed"})

    async def test_known_credentials_are_redacted_even_if_echoed_in_metadata(self):
        self.candidates = [{**_SERIES, "overview": _KEY, "unexpected": {"password": _KEY}}]
        result = await self.service.lookup_series("example")
        self.assertEqual(result[0]["overview"], "[REDACTED]")
        self.assertNotIn("unexpected", result[0])
        self.assertNotIn(_KEY, repr(result))

    async def test_mcp_schema_annotations_skill_and_validation(self):
        with patch("hmcp_sonarr.SonarrClient", return_value=self.client):
            server = create_server(["sonarr"], secret_values=_VALUES)
        self.assertEqual(self.requests, [])
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            self.assertEqual(len(tools), 13)
            for tool in tools:
                self.assertNotIn("api-key", repr(tool.input_schema))
                self.assertEqual(
                    tool.annotations.read_only_hint,
                    tool.name
                    not in {"sonarr_add_series", "sonarr_search_series", "sonarr_search_episodes"},
                )
            skill = await client.read_resource("skill://sonarr-manage/SKILL.md")
            self.assertIn("sonarr_add_series", skill.contents[0].text)
            result = await client.call_tool("sonarr_system_status", {})
            self.assertEqual(result.structured_content, {"version": "4.0.0"})
            count = len(self.requests)
            for name, args in [
                ("sonarr_get_series", {"series_id": 0}),
                ("sonarr_queue", {"page_size": 101}),
                ("sonarr_search_episodes", {"episode_ids": []}),
            ]:
                with self.subTest(name=name):
                    self.assertTrue((await client.call_tool(name, args)).is_error)
            self.assertEqual(len(self.requests), count)

    async def test_vault_onboarding_and_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Vault(
                Path(directory) / "data/vault.hmcp-vault", Path(directory) / "keys/master.hmcp-key"
            )
            with (
                patch("hmcp_sonarr.SonarrClient", return_value=self.client),
                patch("sys.stdin.isatty", return_value=True),
                patch("hmcp.onboarding.getpass.getpass", side_effect=[_URL, _KEY]) as prompt,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                server = create_server(["sonarr"], vault=vault, interactive=True)
            self.assertEqual(prompt.call_count, 2)
            self.assertEqual(self.requests, [])
            with (
                patch("hmcp_sonarr.SonarrClient", return_value=self.client),
                patch("hmcp.onboarding.getpass.getpass") as prompt,
            ):
                create_server(["sonarr"], vault=vault)
            prompt.assert_not_called()
            async with Client(server) as client:
                self.assertFalse((await client.call_tool("sonarr_system_status", {})).is_error)

    async def test_nested_metadata_redaction(self):
        self.candidates = [{**_SERIES, "overview": [{_KEY: _KEY}]}]
        result = await self.service.lookup_series("example")
        self.assertNotIn(_KEY, repr(result))
        self.assertEqual(result[0]["overview"], [{"[REDACTED]": "[REDACTED]"}])

    async def test_mcp_add_and_search_wire_contract(self):
        with patch("hmcp_sonarr.SonarrClient", return_value=self.client):
            server = create_server(["sonarr"], secret_values=_VALUES)
        async with Client(server) as client:
            result = await client.call_tool(
                "sonarr_add_series", {"tvdb_id": 77, "quality_profile_id": 2, "root_folder_id": 3}
            )
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content["id"], 55)
            result = await client.call_tool("sonarr_search_series", {"series_id": 42})
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content["status"], "queued")

    async def test_mcp_auth_error_does_not_expose_upstream_body(self):
        failing = SonarrClient(
            _URL,
            SecretStr(_KEY),
            transport=httpx.MockTransport(lambda request: httpx.Response(401, text=_KEY)),
        )
        with patch("hmcp_sonarr.SonarrClient", return_value=failing):
            server = create_server(["sonarr"], secret_values=_VALUES)
        async with Client(server) as client:
            result = await client.call_tool("sonarr_system_status", {})
        self.assertTrue(result.is_error)
        self.assertIn("authentication failed", repr(result))
        self.assertNotIn(_KEY, repr(result))

    def test_registration_requires_configuration(self):
        plugin = SonarrConnector()
        self.assertEqual([spec.name for spec in plugin.required_secrets()], ["url", "api-key"])
        with self.assertRaises(SecretError):
            plugin.register(MCPServer("test"))
        with self.assertRaises(SecretError):
            plugin.configure(ConnectorSecrets("sonarr", {}))


if __name__ == "__main__":
    unittest.main()
