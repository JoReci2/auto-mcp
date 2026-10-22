"""Prowlarr contract tests using its documented API v1 wire shapes."""

import contextlib
import io
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import httpx
from mcp import Client
from mcp.server import MCPServer
from pydantic import SecretStr
from yamcps_prowlarr import ProwlarrConnector
from yamcps_prowlarr.client import ProwlarrClient, ProwlarrError, validate_url
from yamcps_prowlarr.service import ProwlarrService

from yamcps import ConnectorSecrets, SecretError
from yamcps.server import create_server
from yamcps.vault import Vault

_KEY = "sentinel-prowlarr-key-93217"
_URL = "https://prowlarr.example.test/indexers"
_VALUES = {"YAMCPS_PROWLARR_URL": _URL, "YAMCPS_PROWLARR_API_KEY": _KEY}
_INDEXER = {"id": 1, "name": "Example Indexer", "enable": True}


class ProwlarrClientTests(unittest.IsolatedAsyncioTestCase):
    def client(self, handler):
        return ProwlarrClient(_URL, SecretStr(_KEY), transport=httpx.MockTransport(handler))

    async def test_header_prefix_timeout_and_no_credentials_in_url(self):
        requests = []

        def respond(request):
            requests.append(request)
            self.assertEqual(request.headers["X-Api-Key"], _KEY)
            self.assertEqual(str(request.url), _URL + "/api/v1/indexer")
            self.assertNotIn(_KEY, str(request.url))
            self.assertEqual(request.extensions["timeout"]["connect"], 5.0)
            self.assertEqual(request.extensions["timeout"]["read"], 15.0)
            return httpx.Response(200, json=[_INDEXER])

        self.assertEqual(await self.client(respond).array("indexer"), [_INDEXER])
        self.assertEqual(len(requests), 1)

    async def test_status_errors_do_not_echo_response_body_or_key(self):
        for status, message in [
            (400, "rejected"),
            (401, "authentication"),
            (403, "denied"),
            (404, "not found"),
            (409, "HTTP 409"),
            (422, "rejected"),
            (429, "rate limit"),
            (503, "HTTP 503"),
        ]:
            with self.subTest(status=status):
                client = self.client(lambda request: httpx.Response(status, text=_KEY))
                with self.assertRaisesRegex(ProwlarrError, message) as error:
                    await client.object("system/status")
                self.assertNotIn(_KEY, str(error.exception))

    async def test_redirect_is_not_followed(self):
        seen = []

        def respond(request):
            seen.append(request)
            return httpx.Response(302, headers={"Location": "https://other.example.test/"})

        with self.assertRaisesRegex(ProwlarrError, "redirect"):
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
                self.assertRaisesRegex(ProwlarrError, expected) as error,
            ):
                await self.client(fail).object("system/status")
            self.assertNotIn(_KEY, str(error.exception))
        with self.assertRaisesRegex(ProwlarrError, "invalid JSON"):
            await self.client(lambda request: httpx.Response(200, text="<html>" + _KEY)).object(
                "system/status"
            )

    async def test_unexpected_shapes(self):
        for value, method in [([], "object"), ({}, "array"), ([1], "array")]:
            with self.subTest(value=value, method=method):
                client = self.client(lambda request: httpx.Response(200, json=value))
                with self.assertRaisesRegex(ProwlarrError, "unexpected"):
                    await getattr(client, method)("indexer")

    async def test_no_automatic_retry_on_timeout(self):
        seen = []

        def fail(request):
            seen.append(request)
            raise httpx.ReadTimeout("uncertain", request=request)

        with self.assertRaises(ProwlarrError):
            await self.client(fail).array("search", params={"query": "Example"})
        self.assertEqual(len(seen), 1)

    def test_url_and_key_validation(self):
        self.assertEqual(validate_url("http://localhost:9696/"), "http://localhost:9696")
        self.assertEqual(validate_url(_URL + "/"), _URL)
        for url in [
            "file:///tmp/prowlarr",
            "example.test",
            "https://user:pass@example.test",
            "https://example.test/?apiKey=secret",
            "https://example.test/#fragment",
            "https://example.test/api/v1/",
            "https://example.test/has space",
            "http://example.test:invalid",
            "https://example.test/\\wrong",
        ]:
            with self.subTest(url=url), self.assertRaises(SecretError):
                validate_url(url)
        for value in ["", "bad\r\nheader", "non ascii é"]:
            with self.subTest(value=value), self.assertRaises(SecretError):
                ProwlarrClient(_URL, SecretStr(value))


class ProwlarrWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.requests = []
        self.tracker_secret = "unrelated-tracker-passkey-481"
        secret_url = "https://tracker.example.test/?passkey=" + self.tracker_secret
        self.category = {
            "id": 2000,
            "name": "Movies",
            "subCategories": [{"id": 2040, "name": "HD", "secret": self.tracker_secret}],
        }
        self.indexer = {
            **_INDEXER,
            "protocol": "torrent",
            "fields": [{"value": self.tracker_secret}],
            "presets": [{"secret": self.tracker_secret}],
            "indexerUrls": [secret_url],
            "capabilities": {
                "searchParams": ["q"],
                "categories": [self.category],
                "secret": self.tracker_secret,
            },
        }
        self.release = {
            "title": "Example.Release",
            "indexerId": 1,
            "indexer": "Example Indexer",
            "size": 100,
            "protocol": "torrent",
            "seeders": 5,
            "categories": [self.category],
            "guid": secret_url,
            "downloadUrl": secret_url,
            "magnetUrl": secret_url,
            "infoUrl": secret_url,
        }
        self.history = {
            "page": 1,
            "pageSize": 20,
            "totalRecords": 1,
            "records": [
                {
                    "id": 2,
                    "indexerId": 1,
                    "successful": True,
                    "eventType": "indexerQuery",
                    "data": {"url": secret_url},
                }
            ],
        }
        self.stats = {
            "indexers": [
                {
                    "indexerId": 1,
                    "indexerName": "Example Indexer",
                    "numberOfQueries": 4,
                    "numberOfFailedQueries": 1,
                    "averageResponseTime": 100,
                    "secret": self.tracker_secret,
                }
            ],
            "hosts": [{"host": self.tracker_secret}],
            "userAgents": [self.tracker_secret],
        }
        self.client = ProwlarrClient(
            _URL, SecretStr(_KEY), transport=httpx.MockTransport(self.respond)
        )
        self.service = ProwlarrService(self.client, ConnectorSecrets("prowlarr", _VALUES).redact)

    def respond(self, request):
        self.requests.append(request)
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.headers["X-Api-Key"], _KEY)
        self.assertNotIn(_KEY, str(request.url))
        route = request.url.path.removeprefix("/indexers/api/v1/")
        data = {
            "system/status": {"version": "2.0.0-test", "apiKey": _KEY},
            "indexer": [self.indexer],
            "indexer/1": self.indexer,
            "indexer/categories": [self.category],
            "indexerstatus": [
                {"id": 1, "indexerId": 1, "disabledTill": "2026-01-01", "raw": self.tracker_secret}
            ],
            "search": [self.release],
            "history": self.history,
            "indexerstats": self.stats,
            "health": [
                {"source": "IndexerStatusCheck", "type": "warning", "message": self.tracker_secret}
            ],
            "applications": [
                {
                    "id": 3,
                    "name": "Sonarr",
                    "syncLevel": "fullSync",
                    "fields": [{"value": self.tracker_secret}],
                }
            ],
        }
        if route not in data:
            self.fail(f"Unexpected route: {route}")
        return httpx.Response(200, json=data[route])

    def assert_safe(self, result):
        self.assertNotIn(_KEY, repr(result))
        self.assertNotIn(self.tracker_secret, repr(result))

    async def test_public_metadata_does_not_expose_configurations(self):
        self.assertEqual(await self.service.system_status(), {"version": "2.0.0-test"})
        indexers = await self.service.list_indexers()
        self.assertEqual(indexers[0]["id"], 1)
        self.assertEqual(indexers[0]["capabilities"]["searchParams"], ["q"])
        self.assertEqual(await self.service.get_indexer(1), indexers[0])
        self.assert_safe(indexers)
        categories = await self.service.categories()
        self.assertEqual(categories[0]["subCategories"][0]["id"], 2040)
        self.assert_safe(categories)
        self.assert_safe(await self.service.indexer_status())
        self.assertEqual(
            await self.service.health(), [{"source": "IndexerStatusCheck", "type": "warning"}]
        )
        self.assertEqual(
            await self.service.applications(),
            [{"id": 3, "name": "Sonarr", "syncLevel": "fullSync"}],
        )

    async def test_search_filters_repeated_parameters_and_safe_results(self):
        result = await self.service.search(
            "Example",
            indexer_ids=[1, 2, 1],
            category_ids=[2000, 2040],
            search_type="movie",
            limit=20,
            offset=40,
        )
        params = self.requests[-1].url.params
        self.assertEqual(params.get_list("indexerIds"), ["1", "2"])
        self.assertEqual(params.get_list("categories"), ["2000", "2040"])
        self.assertEqual(params["type"], "movie")
        self.assertEqual(params["query"], "Example")
        self.assertEqual(params["limit"], "20")
        self.assertEqual(params["offset"], "40")
        self.assertEqual(self.requests[-1].extensions["timeout"]["read"], 60.0)
        self.assertEqual(result[0]["title"], "Example.Release")
        self.assertEqual(result[0]["seeders"], 5)
        self.assert_safe(result)
        self.assertFalse({"guid", "downloadUrl", "magnetUrl", "infoUrl"} & result[0].keys())
        await self.service.search("Example")
        self.assertNotIn("indexerIds", self.requests[-1].url.params)
        self.assertNotIn("categories", self.requests[-1].url.params)
        with self.assertRaises(ProwlarrError):
            await self.service.search("  ")

    async def test_optional_capabilities_and_category_shapes(self):
        self.indexer.pop("capabilities")
        self.assertNotIn("capabilities", (await self.service.list_indexers())[0])
        self.category["subCategories"] = None
        self.assertEqual((await self.service.categories())[0]["subCategories"], [])

    async def test_history_pagination_filter_and_invalid_response(self):
        result = await self.service.history(page=2, page_size=50, indexer_ids=[1, 2])
        self.assertEqual(self.requests[-1].url.params["pageSize"], "50")
        self.assertEqual(self.requests[-1].url.params.get_list("indexerIds"), ["1", "2"])
        self.assertTrue(result["records"][0]["successful"])
        self.assert_safe(result)
        self.history["records"] = None
        self.assertEqual((await self.service.history())["records"], [])
        self.history["records"] = "invalid"
        with self.assertRaises(ProwlarrError):
            await self.service.history()

    async def test_statistics_dates_and_omitted_host_information(self):
        result = await self.service.statistics(date(2026, 1, 1), date(2026, 1, 7))
        self.assertEqual(
            dict(self.requests[-1].url.params), {"startDate": "2026-01-01", "endDate": "2026-01-07"}
        )
        self.assertEqual(result["indexers"][0]["numberOfQueries"], 4)
        self.assertEqual(set(result), {"indexers"})
        self.assert_safe(result)
        await self.service.statistics()
        self.assertEqual(dict(self.requests[-1].url.params), {})
        with self.assertRaises(ProwlarrError):
            await self.service.statistics(date(2026, 1, 7), date(2026, 1, 1))
        self.stats["indexers"] = None
        self.assertEqual(await self.service.statistics(), {"indexers": []})
        self.stats["indexers"] = "invalid"
        with self.assertRaises(ProwlarrError):
            await self.service.statistics()

    async def test_known_credentials_redacted_even_in_nested_metadata(self):
        self.indexer["tags"] = [{_KEY: _KEY}]
        self.indexer["name"] = _KEY
        result = await self.service.get_indexer(1)
        self.assertEqual(result["name"], "[REDACTED]")
        self.assert_safe(result)

    async def test_mcp_schema_annotations_skill_and_no_mutation_tools(self):
        with patch("yamcps_prowlarr.ProwlarrClient", return_value=self.client):
            server = create_server(["prowlarr"], secret_values=_VALUES)
        self.assertEqual(self.requests, [])
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            self.assertEqual(len(tools), 10)
            for tool in tools:
                self.assertTrue(tool.annotations.read_only_hint)
                self.assertNotIn("api-key", repr(tool.input_schema))
                self.assertFalse(
                    any(
                        action in tool.name
                        for action in ["grab", "download", "delete", "add", "update"]
                    )
                )
            self.assertIn(
                "prowlarr_search",
                (await client.read_resource("skill://prowlarr-search/SKILL.md")).contents[0].text,
            )
            result = await client.call_tool(
                "prowlarr_search", {"query": "Example", "indexer_ids": [1], "category_ids": [2000]}
            )
            self.assertFalse(result.is_error)
            self.assert_safe(result)
            count = len(self.requests)
            for name, args in [
                ("prowlarr_get_indexer", {"indexer_id": 0}),
                ("prowlarr_search", {"query": "Example", "limit": 101}),
                ("prowlarr_search", {"query": "Example", "offset": -1}),
                ("prowlarr_search", {"query": "Example", "indexer_ids": []}),
                ("prowlarr_history", {"page": 0}),
            ]:
                with self.subTest(name=name, args=args):
                    self.assertTrue((await client.call_tool(name, args)).is_error)
            self.assertEqual(len(self.requests), count)

    async def test_onboarding_and_headless_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Vault(
                Path(directory) / "data/vault.yamcps-vault",
                Path(directory) / "keys/master.yamcps-key",
            )
            with (
                patch("yamcps_prowlarr.ProwlarrClient", return_value=self.client),
                patch("sys.stdin.isatty", return_value=True),
                patch("yamcps.onboarding.getpass.getpass", side_effect=[_URL, _KEY]) as prompt,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                server = create_server(["prowlarr"], vault=vault, interactive=True)
            self.assertEqual(prompt.call_count, 2)
            self.assertEqual(self.requests, [])
            with (
                patch("yamcps_prowlarr.ProwlarrClient", return_value=self.client),
                patch("yamcps.onboarding.getpass.getpass") as prompt,
            ):
                create_server(["prowlarr"], vault=vault)
            prompt.assert_not_called()
            async with Client(server) as client:
                self.assertFalse((await client.call_tool("prowlarr_system_status", {})).is_error)

    async def test_coexistence_with_sonarr_and_radarr(self):
        values = {
            **_VALUES,
            "YAMCPS_SONARR_URL": "http://sonarr.example.test",
            "YAMCPS_SONARR_API_KEY": "sonarr-only-key",
            "YAMCPS_RADARR_URL": "http://radarr.example.test",
            "YAMCPS_RADARR_API_KEY": "radarr-only-key",
        }
        with patch("yamcps_prowlarr.ProwlarrClient", return_value=self.client):
            server = create_server(["sonarr", "radarr", "prowlarr"], secret_values=values)
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            self.assertEqual(len(tools), 34)
            self.assertEqual(len({tool.name for tool in tools}), 34)
            self.assertEqual(len((await client.list_resources()).resources), 3)
            self.assertFalse((await client.call_tool("prowlarr_system_status", {})).is_error)

    async def test_auth_failure_is_safe_through_mcp(self):
        failing = ProwlarrClient(
            _URL,
            SecretStr(_KEY),
            transport=httpx.MockTransport(lambda request: httpx.Response(401, text=_KEY)),
        )
        with patch("yamcps_prowlarr.ProwlarrClient", return_value=failing):
            server = create_server(["prowlarr"], secret_values=_VALUES)
        async with Client(server) as client:
            result = await client.call_tool("prowlarr_system_status", {})
        self.assertTrue(result.is_error)
        self.assertIn("authentication failed", repr(result))
        self.assertNotIn(_KEY, repr(result))

    def test_configuration_required_and_scoped_to_prowlarr(self):
        plugin = ProwlarrConnector()
        self.assertEqual([spec.name for spec in plugin.required_secrets()], ["url", "api-key"])
        with self.assertRaises(SecretError):
            plugin.register(MCPServer("test"))
        with self.assertRaisesRegex(SecretError, "YAMCPS_PROWLARR_API_KEY"):
            plugin.configure(
                ConnectorSecrets(
                    "prowlarr", {"YAMCPS_PROWLARR_URL": _URL, "YAMCPS_RADARR_API_KEY": _KEY}
                )
            )


if __name__ == "__main__":
    unittest.main()
