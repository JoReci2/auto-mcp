"""Read-only indexer workflows with credential-bearing fields omitted."""

from collections.abc import Callable
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import Field

from hmcp_prowlarr.client import JsonObject, Params, ProwlarrClient, ProwlarrError

PositiveId = Annotated[int, Field(gt=0)]
PageSize = Annotated[int, Field(ge=1, le=100)]
Offset = Annotated[int, Field(ge=0)]
IdList = Annotated[list[PositiveId], Field(min_length=1, max_length=100)]
SearchTerm = Annotated[str, Field(min_length=1, max_length=300)]
_INDEXER_FIELDS = "id name enable priority protocol privacy supportsRss supportsSearch supportsPagination appProfileId tags"
_RELEASE_FIELDS = "title indexerId indexer size age ageHours publishDate protocol seeders leechers grabs files imdbId tmdbId tvdbId"
_STATS_FIELDS = "indexerId indexerName averageResponseTime averageGrabResponseTime numberOfQueries numberOfGrabs numberOfRssQueries numberOfAuthQueries numberOfFailedQueries numberOfFailedGrabs numberOfFailedRssQueries numberOfFailedAuthQueries"


class ProwlarrService:
    """Expose public metadata and searches without indexer credentials or grab URLs."""

    def __init__(self, client: ProwlarrClient, redact: Callable[[str], str]) -> None:
        """Bind the API and connector credential redactor.

        Args:
            client: API client for one Prowlarr instance.
            redact: Redactor for known credential values.
        """
        self._client = client
        self._redact = redact

    def _clean(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._redact(value)
        if isinstance(value, list):
            return [self._clean(item) for item in value]
        if isinstance(value, dict):
            return {self._redact(key): self._clean(item) for key, item in value.items()}
        return value

    def _view(self, value: JsonObject, fields: str) -> JsonObject:
        return {name: self._clean(value[name]) for name in fields.split() if name in value}

    def _records(self, value: Any, resource: str) -> list[JsonObject]:
        if value is None:
            return []
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ProwlarrError(f"Prowlarr returned an unexpected {resource} format")
        return value

    def _categories(self, values: Any) -> list[JsonObject]:
        if not isinstance(values, list):
            return []
        return [
            {
                **self._view(item, "id name"),
                "subCategories": self._categories(item.get("subCategories")),
            }
            for item in values
            if isinstance(item, dict)
        ]

    def _indexer(self, value: JsonObject) -> JsonObject:
        result = self._view(value, _INDEXER_FIELDS)
        capabilities = value.get("capabilities")
        if isinstance(capabilities, dict):
            result["capabilities"] = self._view(
                capabilities,
                "limitsMax limitsDefault supportsRawSearch searchParams tvSearchParams movieSearchParams musicSearchParams bookSearchParams",
            )
            result["capabilities"]["categories"] = self._categories(capabilities.get("categories"))
        return result

    async def system_status(self) -> JsonObject:
        """Check connectivity and report the Prowlarr version.

        Returns:
            Public version and runtime information without server configuration.
        """
        return self._view(
            await self._client.object("system/status"),
            "version appName instanceName startTime osName isDocker runtimeVersion branch",
        )

    async def list_indexers(self) -> list[JsonObject]:
        """List configured indexers without their credentials or connection fields.

        Returns:
            Public indexer metadata and search capabilities.
        """
        return [self._indexer(item) for item in await self._client.array("indexer")]

    async def get_indexer(self, indexer_id: PositiveId) -> JsonObject:
        """Read one indexer's public metadata.

        Args:
            indexer_id: Positive Prowlarr indexer identifier.

        Returns:
            Indexer metadata and capabilities without configuration fields.
        """
        return self._indexer(await self._client.object(f"indexer/{indexer_id}"))

    async def indexer_status(self) -> list[JsonObject]:
        """Read indexer failure and temporary-disable timestamps.

        Returns:
            Indexer identifiers and recorded status timestamps.
        """
        return [
            self._view(item, "id indexerId disabledTill mostRecentFailure initialFailure")
            for item in await self._client.array("indexerstatus")
        ]

    async def categories(self) -> list[JsonObject]:
        """List the category hierarchy used to filter searches.

        Returns:
            Category identifiers, names and nested subcategories.
        """
        return self._categories(await self._client.array("indexer/categories"))

    async def search(
        self,
        query: SearchTerm,
        indexer_ids: IdList | None = None,
        category_ids: IdList | None = None,
        search_type: Literal["search", "tvsearch", "movie", "music", "book"] = "search",
        limit: PageSize = 100,
        offset: Offset = 0,
    ) -> list[JsonObject]:
        """Search indexers without downloading; searches consume provider quotas.

        Args:
            query: Nonempty title or search terms.
            indexer_ids: Optional configured indexer identifiers; omitted means Prowlarr's selection.
            category_ids: Optional category identifiers from prowlarr_categories.
            search_type: Newznab search mode supported by the selected indexers.
            limit: Result limit forwarded to Prowlarr, between 1 and 100.
            offset: Nonnegative result offset forwarded to Prowlarr.

        Returns:
            Release summaries without GUIDs, download links, magnets or passkeys.
        """
        if not query.strip():
            raise ProwlarrError("A nonempty search query is required")
        params: Params = {"query": query, "type": search_type, "limit": limit, "offset": offset}
        if indexer_ids is not None:
            params["indexerIds"] = list(dict.fromkeys(indexer_ids))
        if category_ids is not None:
            params["categories"] = list(dict.fromkeys(category_ids))
        results = await self._client.array("search", params=params)
        return [
            {
                **self._view(item, _RELEASE_FIELDS),
                "categories": self._categories(item.get("categories")),
            }
            for item in results
        ]

    async def history(
        self, page: PositiveId = 1, page_size: PageSize = 20, indexer_ids: IdList | None = None
    ) -> JsonObject:
        """Read a page of indexer history without raw request or download data.

        Args:
            page: One-based page number.
            page_size: Page size between 1 and 100.
            indexer_ids: Optional indexer filter.

        Returns:
            Pagination metadata and event identifiers, dates, types and success flags.
        """
        params: Params = {"page": page, "pageSize": page_size}
        if indexer_ids is not None:
            params["indexerIds"] = list(dict.fromkeys(indexer_ids))
        value = await self._client.object("history", params=params)
        records = self._records(value.get("records"), "history")
        return {
            **self._view(value, "page pageSize totalRecords"),
            "records": [
                self._view(item, "id indexerId date eventType successful") for item in records
            ],
        }

    async def health(self) -> list[JsonObject]:
        """Read health check sources and severity without credential-bearing messages.

        Returns:
            Health identifiers, sources and severity types; raw messages are omitted.
        """
        return [self._view(item, "id source type") for item in await self._client.array("health")]

    async def statistics(self, start: date | None = None, end: date | None = None) -> JsonObject:
        """Read indexer statistics without host or user-agent information.

        Args:
            start: Optional ISO start date; omitted uses the server's default range.
            end: Optional ISO end date, not earlier than start when both are given.

        Returns:
            Per-indexer query, failure, grab and response-time statistics.

        Raises:
            ProwlarrError: The interval or upstream response is invalid.
        """
        if start is not None and end is not None and end < start:
            raise ProwlarrError("Statistics end must not precede start")
        params: Params = {}
        if start is not None:
            params["startDate"] = start.isoformat()
        if end is not None:
            params["endDate"] = end.isoformat()
        value = await self._client.object("indexerstats", params=params)
        indexers = self._records(value.get("indexers"), "statistics")
        return {"indexers": [self._view(item, _STATS_FIELDS) for item in indexers]}

    async def applications(self) -> list[JsonObject]:
        """List connected application names without their settings or credentials.

        Returns:
            Application identifiers, names, implementation and synchronization level.
        """
        return [
            self._view(item, "id name implementation implementationName syncLevel tags")
            for item in await self._client.array("applications")
        ]
