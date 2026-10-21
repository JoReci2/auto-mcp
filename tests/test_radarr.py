"""Radarr contract tests using its documented API v3 wire shapes."""

import contextlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import httpx
from hmcp_radarr import RadarrConnector
from hmcp_radarr.client import RadarrClient, RadarrError, validate_url
from hmcp_radarr.service import RadarrService
from mcp import Client
from mcp.server import MCPServer
from pydantic import SecretStr

from hmcp import ConnectorSecrets, SecretError
from hmcp.server import create_server
from hmcp.vault import Vault

_KEY = "sentinel-radarr-key-93217"
_URL = "https://radarr.example.test/cinema"
_VALUES = {"HMCP_RADARR_URL": _URL, "HMCP_RADARR_API_KEY": _KEY}
_MOVIE = {
    "id": 42,
    "tmdbId": 77,
    "title": "Example Movie",
    "year": 2024,
    "monitored": True,
    "hasFile": False,
    "genres": ["Drama"],
    "apiKey": _KEY,
}


class RadarrClientTests(unittest.IsolatedAsyncioTestCase):
    def client(self, handler):
        return RadarrClient(_URL, SecretStr(_KEY), transport=httpx.MockTransport(handler))

    async def test_header_prefix_timeout_and_no_credentials_in_url(self):
        requests = []

        def respond(request):
            requests.append(request)
            self.assertEqual(request.headers["X-Api-Key"], _KEY)
            self.assertEqual(str(request.url), _URL + "/api/v3/movie?tmdbId=77")
            self.assertNotIn(_KEY, str(request.url))
            self.assertEqual(request.extensions["timeout"]["connect"], 5.0)
            self.assertEqual(request.extensions["timeout"]["read"], 15.0)
            return httpx.Response(200, json=[_MOVIE])

        self.assertEqual(await self.client(respond).array("movie", params={"tmdbId": 77}), [_MOVIE])
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
                with self.assertRaisesRegex(RadarrError, message) as error:
                    await client.object("system/status")
                self.assertNotIn(_KEY, str(error.exception))

    async def test_redirect_is_not_followed(self):
        seen = []

        def respond(request):
            seen.append(request)
            return httpx.Response(302, headers={"Location": "https://other.example.test/"})

        with self.assertRaisesRegex(RadarrError, "redirect"):
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
                self.assertRaisesRegex(RadarrError, expected) as error,
            ):
                await self.client(fail).object("system/status")
            self.assertNotIn(_KEY, str(error.exception))
        with self.assertRaisesRegex(RadarrError, "invalid JSON"):
            await self.client(lambda request: httpx.Response(200, text="<html>" + _KEY)).object(
                "system/status"
            )

    async def test_unexpected_shapes(self):
        for value, method in [([], "object"), ({}, "array"), ([1], "array")]:
            with self.subTest(value=value, method=method):
                client = self.client(lambda request: httpx.Response(200, json=value))
                with self.assertRaisesRegex(RadarrError, "unexpected"):
                    await getattr(client, method)("movie")

    async def test_no_automatic_retry_on_uncertain_post(self):
        seen = []

        def fail(request):
            seen.append(request)
            raise httpx.ReadTimeout("uncertain", request=request)

        with self.assertRaises(RadarrError):
            await self.client(fail).object("movie", payload={"tmdbId": 77})
        self.assertEqual(len(seen), 1)

    def test_url_and_key_validation(self):
        self.assertEqual(validate_url("http://localhost:7878/"), "http://localhost:7878")
        self.assertEqual(validate_url(_URL + "/"), _URL)
        for url in [
            "file:///tmp/radarr",
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
                RadarrClient(_URL, SecretStr(value))


class RadarrWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.requests = []
        self.existing = []
        self.candidates = [dict(_MOVIE)]
        self.profiles = [{"id": 2, "name": "HD", "apiKey": _KEY}]
        self.roots = [{"id": 3, "path": "/media/movies", "freeSpace": 1000, "apiKey": _KEY}]
        self.queue = {
            "page": 1,
            "pageSize": 20,
            "totalRecords": 1,
            "records": [
                {
                    "id": 5,
                    "movieId": 42,
                    "title": "Example Movie",
                    "status": "downloading",
                    "secret": _KEY,
                }
            ],
        }
        self.client = RadarrClient(
            _URL, SecretStr(_KEY), transport=httpx.MockTransport(self.respond)
        )
        self.service = RadarrService(self.client, ConnectorSecrets("radarr", _VALUES).redact)

    def respond(self, request):
        self.requests.append(request)
        self.assertEqual(request.headers["X-Api-Key"], _KEY)
        route = request.url.path.removeprefix("/cinema/api/v3/")
        if request.method == "POST":
            payload = json.loads(request.content)
            if route == "movie":
                return httpx.Response(201, json={**payload, "id": 55, "apiKey": _KEY})
            if route == "command":
                return httpx.Response(
                    201,
                    json={"id": 9, "name": payload["name"], "status": "queued", "exception": _KEY},
                )
            self.fail(f"Unexpected POST: {route}")
        data = {
            "system/status": {"version": "5.0.0-test", "apiKey": _KEY},
            "movie": self.existing if "tmdbId" in request.url.params else [_MOVIE],
            "movie/42": _MOVIE,
            "movie/lookup": self.candidates,
            "qualityprofile": self.profiles,
            "rootfolder": self.roots,
            "calendar": [_MOVIE],
            "queue": self.queue,
            "command/9": {"id": 9, "status": "completed", "exception": _KEY},
        }
        if route not in data:
            self.fail(f"Unexpected GET: {route}")
        return httpx.Response(200, json=data[route])

    async def test_read_operations_and_projections(self):
        self.assertEqual(await self.service.system_status(), {"version": "5.0.0-test"})
        self.assertEqual(len(await self.service.list_movies()), 1)
        self.assertEqual(len(await self.service.list_movies("example")), 1)
        self.assertEqual(await self.service.list_movies("absent"), [])
        movie = await self.service.get_movie(42)
        self.assertEqual(movie["tmdbId"], 77)
        self.assertFalse(movie["hasFile"])
        self.assertEqual(movie["genres"], ["Drama"])
        self.assertNotIn(_KEY, repr(movie))
        self.assertEqual(await self.service.quality_profiles(), [{"id": 2, "name": "HD"}])
        self.assertEqual((await self.service.root_folders())[0]["path"], "/media/movies")
        self.assertEqual((await self.service.lookup_movies("Example"))[0]["tmdbId"], 77)
        self.assertEqual(self.requests[-1].url.params["term"], "Example")
        with self.assertRaises(RadarrError):
            await self.service.lookup_movies("  ")

    async def test_calendar_and_queue_parameters(self):
        result = await self.service.calendar(date(2026, 1, 1), date(2026, 1, 7), True)
        self.assertEqual(result[0]["id"], 42)
        self.assertEqual(
            dict(self.requests[-1].url.params),
            {"start": "2026-01-01", "end": "2026-01-07", "unmonitored": "true"},
        )
        with self.assertRaises(RadarrError):
            await self.service.calendar(date(2026, 1, 7), date(2026, 1, 1))
        result = await self.service.queue(page=2, page_size=50)
        self.assertEqual(self.requests[-1].url.params["pageSize"], "50")
        self.assertEqual(result["records"][0]["movieId"], 42)
        self.assertNotIn(_KEY, repr(result))
        self.queue["records"] = "invalid"
        with self.assertRaises(RadarrError):
            await self.service.queue()

    async def test_add_uses_tmdb_and_radarr_settings(self):
        result = await self.service.add_movie(77, 2, 3)
        self.assertEqual(result["id"], 55)
        self.assertNotIn(_KEY, repr(result))
        payload = json.loads(self.requests[-1].content)
        self.assertEqual(
            payload,
            {
                "tmdbId": 77,
                "title": "Example Movie",
                "qualityProfileId": 2,
                "rootFolderPath": "/media/movies",
                "monitored": True,
                "minimumAvailability": "released",
                "addOptions": {"monitor": "movieOnly", "searchForMovie": False},
            },
        )
        self.assertEqual(self.requests[1].url.params["term"], "tmdb:77")
        self.assertEqual([r.method for r in self.requests], ["GET", "GET", "GET", "GET", "POST"])

    async def test_add_monitoring_availability_and_initial_search(self):
        await self.service.add_movie(
            77, 2, 3, monitored=False, search_for_movie=True, minimum_availability="inCinemas"
        )
        payload = json.loads(self.requests[-1].content)
        self.assertFalse(payload["monitored"])
        self.assertEqual(payload["minimumAvailability"], "inCinemas")
        self.assertEqual(payload["addOptions"], {"monitor": "none", "searchForMovie": True})

    async def test_add_preflight_failures_do_not_mutate(self):
        for attribute, value, message in [
            ("existing", [_MOVIE], "already exists"),
            ("candidates", [], "not found"),
            ("profiles", [], "Quality profile"),
            ("roots", [], "Root folder"),
        ]:
            original = getattr(self, attribute)
            self.requests.clear()
            setattr(self, attribute, value)
            with self.subTest(attribute=attribute), self.assertRaisesRegex(RadarrError, message):
                await self.service.add_movie(77, 2, 3)
            self.assertFalse(any(request.method == "POST" for request in self.requests))
            setattr(self, attribute, original)

    async def test_active_movie_search_and_command_status(self):
        result = await self.service.search_movies([42, 42, 43])
        self.assertEqual(result["id"], 9)
        self.assertEqual(
            json.loads(self.requests[-1].content), {"name": "MoviesSearch", "movieIds": [42, 43]}
        )
        self.assertEqual(await self.service.command_status(9), {"id": 9, "status": "completed"})

    async def test_metadata_is_projected_and_redacted(self):
        self.candidates = [{**_MOVIE, "overview": [{_KEY: _KEY}], "unexpected": _KEY}]
        result = await self.service.lookup_movies("example")
        self.assertNotIn(_KEY, repr(result))
        self.assertEqual(result[0]["overview"], [{"[REDACTED]": "[REDACTED]"}])
        self.assertNotIn("unexpected", result[0])

    async def test_mcp_schema_annotations_skill_and_validation(self):
        with patch("hmcp_radarr.RadarrClient", return_value=self.client):
            server = create_server(["radarr"], secret_values=_VALUES)
        self.assertEqual(self.requests, [])
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            self.assertEqual(len(tools), 11)
            for tool in tools:
                self.assertNotIn("api-key", repr(tool.input_schema))
                self.assertEqual(
                    tool.annotations.read_only_hint,
                    tool.name not in {"radarr_add_movie", "radarr_search_movies"},
                )
            self.assertIn(
                "radarr_add_movie",
                (await client.read_resource("skill://radarr-manage/SKILL.md")).contents[0].text,
            )
            result = await client.call_tool("radarr_system_status", {})
            self.assertEqual(result.structured_content, {"version": "5.0.0-test"})
            count = len(self.requests)
            for name, args in [
                ("radarr_get_movie", {"movie_id": 0}),
                ("radarr_queue", {"page_size": 101}),
                ("radarr_search_movies", {"movie_ids": []}),
                (
                    "radarr_add_movie",
                    {
                        "tmdb_id": 77,
                        "quality_profile_id": 2,
                        "root_folder_id": 3,
                        "minimum_availability": "invalid",
                    },
                ),
            ]:
                with self.subTest(name=name):
                    self.assertTrue((await client.call_tool(name, args)).is_error)
            self.assertEqual(len(self.requests), count)
            result = await client.call_tool(
                "radarr_add_movie", {"tmdb_id": 77, "quality_profile_id": 2, "root_folder_id": 3}
            )
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content["id"], 55)
            result = await client.call_tool("radarr_search_movies", {"movie_ids": [42]})
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content["status"], "queued")

    async def test_vault_onboarding_and_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Vault(
                Path(directory) / "data/vault.hmcp-vault", Path(directory) / "keys/master.hmcp-key"
            )
            with (
                patch("hmcp_radarr.RadarrClient", return_value=self.client),
                patch("sys.stdin.isatty", return_value=True),
                patch("hmcp.onboarding.getpass.getpass", side_effect=[_URL, _KEY]) as prompt,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                server = create_server(["radarr"], vault=vault, interactive=True)
            self.assertEqual(prompt.call_count, 2)
            self.assertEqual(self.requests, [])
            with (
                patch("hmcp_radarr.RadarrClient", return_value=self.client),
                patch("hmcp.onboarding.getpass.getpass") as prompt,
            ):
                create_server(["radarr"], vault=vault)
            prompt.assert_not_called()
            async with Client(server) as client:
                self.assertFalse((await client.call_tool("radarr_system_status", {})).is_error)

    async def test_sonarr_and_radarr_can_be_loaded_together(self):
        values = {
            **_VALUES,
            "HMCP_SONARR_URL": "http://sonarr.example.test",
            "HMCP_SONARR_API_KEY": "different-sonarr-key",
        }
        with patch("hmcp_radarr.RadarrClient", return_value=self.client):
            server = create_server(["sonarr", "radarr"], secret_values=values)
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            self.assertEqual(len(tools), 24)
            self.assertEqual(len({tool.name for tool in tools}), 24)
            self.assertEqual(len((await client.list_resources()).resources), 2)
            self.assertFalse((await client.call_tool("radarr_system_status", {})).is_error)
        self.assertEqual(self.requests[-1].headers["X-Api-Key"], _KEY)

    async def test_mcp_auth_failure_does_not_expose_body(self):
        failing = RadarrClient(
            _URL,
            SecretStr(_KEY),
            transport=httpx.MockTransport(lambda request: httpx.Response(401, text=_KEY)),
        )
        with patch("hmcp_radarr.RadarrClient", return_value=failing):
            server = create_server(["radarr"], secret_values=_VALUES)
        async with Client(server) as client:
            result = await client.call_tool("radarr_system_status", {})
        self.assertTrue(result.is_error)
        self.assertIn("authentication failed", repr(result))
        self.assertNotIn(_KEY, repr(result))

    def test_registration_requires_configuration(self):
        plugin = RadarrConnector()
        self.assertEqual([spec.name for spec in plugin.required_secrets()], ["url", "api-key"])
        with self.assertRaises(SecretError):
            plugin.register(MCPServer("test"))
        with self.assertRaises(SecretError):
            plugin.configure(ConnectorSecrets("radarr", {}))
        with self.assertRaisesRegex(SecretError, "HMCP_RADARR_API_KEY"):
            plugin.configure(
                ConnectorSecrets("radarr", {"HMCP_RADARR_URL": _URL, "HMCP_SONARR_API_KEY": _KEY})
            )


if __name__ == "__main__":
    unittest.main()
