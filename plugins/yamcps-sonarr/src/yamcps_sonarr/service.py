"""Sonarr workflows and bounded public response projections."""

from collections.abc import Callable
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import Field

from yamcps_sonarr.client import JsonObject, Params, SonarrClient, SonarrError

PositiveId = Annotated[int, Field(gt=0)]
SeasonNumber = Annotated[int, Field(ge=0)]
PageSize = Annotated[int, Field(ge=1, le=100)]
EpisodeIds = Annotated[list[PositiveId], Field(min_length=1, max_length=100)]
SearchTerm = Annotated[str, Field(min_length=1, max_length=200)]
_SERIES_FIELDS = "id title tvdbId year status monitored qualityProfileId path rootFolderPath titleSlug seriesType overview network"
_EPISODE_FIELDS = (
    "id seriesId seasonNumber episodeNumber title airDate airDateUtc hasFile monitored overview"
)
_COMMAND_FIELDS = "id name status queued started ended"


class SonarrService:
    """Implement the connector's read and mutation tools."""

    def __init__(self, client: SonarrClient, redact: Callable[[str], str]) -> None:
        """Bind the API and credential redactor.

        Args:
            client: API client configured for one instance.
            redact: Redactor for known connector credential values.
        """
        self._client = client
        self._redact = redact

    def _clean(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._redact(value)
        if isinstance(value, list):
            return [self._clean(item) for item in value]
        if isinstance(value, dict):
            return {self._redact(name): self._clean(item) for name, item in value.items()}
        return value

    def _view(self, value: JsonObject, fields: str) -> JsonObject:
        return {name: self._clean(value[name]) for name in fields.split() if name in value}

    def _series(self, value: JsonObject) -> JsonObject:
        result = self._view(value, _SERIES_FIELDS)
        result["seasons"] = [
            self._view(season, "seasonNumber monitored")
            for season in value.get("seasons") or []
            if isinstance(season, dict)
        ]
        return result

    def _episode(self, value: JsonObject) -> JsonObject:
        result = self._view(value, _EPISODE_FIELDS)
        series = value.get("series")
        if isinstance(series, dict):
            result["series"] = self._view(series, "id title")
        return result

    async def system_status(self) -> JsonObject:
        """Check connectivity and report Sonarr version and instance status.

        Returns:
            Public version and runtime information, without server configuration.
        """
        return self._view(
            await self._client.object("system/status"),
            "version appName instanceName startTime osName isDocker runtimeVersion branch",
        )

    async def list_series(self, query: str | None = None) -> list[JsonObject]:
        """List the existing Sonarr library, optionally filtering by title.

        Args:
            query: Optional case-insensitive title substring.

        Returns:
            Series summaries with Sonarr identifiers and TVDB identifiers.
        """
        series = await self._client.array("series")
        return [
            self._series(item)
            for item in series
            if not query or query.casefold() in str(item.get("title", "")).casefold()
        ]

    async def get_series(self, series_id: PositiveId) -> JsonObject:
        """Read details of an existing series.

        Args:
            series_id: Positive Sonarr series identifier, not a TVDB identifier.

        Returns:
            Series details and monitored seasons.
        """
        return self._series(await self._client.object(f"series/{series_id}"))

    async def list_episodes(
        self, series_id: PositiveId, season_number: SeasonNumber | None = None
    ) -> list[JsonObject]:
        """List episodes for an existing series, optionally within one season.

        Args:
            series_id: Sonarr series identifier.
            season_number: Optional season; zero selects specials.

        Returns:
            Episode details and local-file availability.
        """
        params: Params = {"seriesId": series_id}
        if season_number is not None:
            params["seasonNumber"] = season_number
        return [self._episode(item) for item in await self._client.array("episode", params=params)]

    async def calendar(
        self, start: date, end: date, include_unmonitored: bool = False
    ) -> list[JsonObject]:
        """Read the broadcast calendar for an explicit date interval.

        Args:
            start: ISO start date sent to Sonarr.
            end: ISO end date sent to Sonarr; must not precede start.
            include_unmonitored: Include episodes that are not monitored.

        Returns:
            Episodes and their series summaries in Sonarr's calendar interval.

        Raises:
            SonarrError: The interval is reversed.
        """
        if end < start:
            raise SonarrError("Calendar end must not precede start")
        values = await self._client.array(
            "calendar",
            params={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "unmonitored": include_unmonitored,
                "includeSeries": True,
            },
        )
        return [self._episode(item) for item in values]

    async def queue(self, page: PositiveId = 1, page_size: PageSize = 20) -> JsonObject:
        """Read one page of the download queue.

        Args:
            page: One-based page number.
            page_size: Page size between 1 and 100.

        Returns:
            Pagination metadata and bounded queue records.
        """
        value = await self._client.object("queue", params={"page": page, "pageSize": page_size})
        result = self._view(value, "page pageSize totalRecords")
        records = value.get("records")
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise SonarrError("Sonarr returned an unexpected queue format")
        result["records"] = [
            self._view(
                item,
                "id seriesId episodeId title size sizeleft status trackedDownloadStatus trackedDownloadState estimatedCompletionTime timeleft",
            )
            for item in records
        ]
        return result

    async def lookup_series(self, term: SearchTerm) -> list[JsonObject]:
        """Search Sonarr's external series catalog without adding anything.

        Args:
            term: Series title or tvdb:<id> query.

        Returns:
            Candidate series with TVDB identifiers for a later add operation.
        """
        if not term.strip():
            raise SonarrError("A nonempty catalog search term is required")
        return [
            self._series(item)
            for item in await self._client.array("series/lookup", params={"term": term})
        ]

    async def quality_profiles(self) -> list[JsonObject]:
        """List quality profiles available for adding a series.

        Returns:
            Profile identifiers and display names.
        """
        return [self._view(item, "id name") for item in await self._client.array("qualityprofile")]

    async def root_folders(self) -> list[JsonObject]:
        """List configured library roots available for adding a series.

        Returns:
            Root identifiers, paths, available space and accessibility.
        """
        return [
            self._view(item, "id path freeSpace accessible")
            for item in await self._client.array("rootfolder")
        ]

    async def _catalog_entry(self, tvdb_id: int) -> JsonObject:
        if await self._client.array("series", params={"tvdbId": tvdb_id}):
            raise SonarrError("This TVDB series already exists in Sonarr")
        candidates = await self._client.array("series/lookup", params={"term": f"tvdb:{tvdb_id}"})
        candidate = next((item for item in candidates if item.get("tvdbId") == tvdb_id), None)
        if candidate is None or not candidate.get("title"):
            raise SonarrError("TVDB series not found in the Sonarr catalog")
        return candidate

    async def _add_root(self, quality_profile_id: int, root_folder_id: int) -> JsonObject:
        profiles = await self._client.array("qualityprofile")
        if not any(item.get("id") == quality_profile_id for item in profiles):
            raise SonarrError("Quality profile does not exist; use sonarr_quality_profiles")
        roots = await self._client.array("rootfolder")
        root = next((item for item in roots if item.get("id") == root_folder_id), None)
        if root is None or not root.get("path"):
            raise SonarrError("Root folder does not exist; use sonarr_root_folders")
        return root

    async def add_series(
        self,
        tvdb_id: PositiveId,
        quality_profile_id: PositiveId,
        root_folder_id: PositiveId,
        monitored: bool = True,
        search_for_missing_episodes: bool = False,
        series_type: Literal["standard", "daily", "anime"] = "standard",
    ) -> JsonObject:
        """Add a catalog series to Sonarr; optional initial search may download episodes.

        Args:
            tvdb_id: TVDB identifier obtained from sonarr_lookup_series.
            quality_profile_id: Existing profile from sonarr_quality_profiles.
            root_folder_id: Existing root from sonarr_root_folders.
            monitored: Monitor the series and all its seasons.
            search_for_missing_episodes: Start an active episode search after adding.
            series_type: Sonarr episode naming and numbering mode.

        Returns:
            The created series; this does not confirm any download has completed.

        Raises:
            SonarrError: The series exists or required catalog/profile/root data is absent.
        """
        candidate = await self._catalog_entry(tvdb_id)
        root = await self._add_root(quality_profile_id, root_folder_id)
        payload = {
            "tvdbId": tvdb_id,
            "title": candidate["title"],
            "qualityProfileId": quality_profile_id,
            "rootFolderPath": root["path"],
            "monitored": monitored,
            "seasonFolder": True,
            "seriesType": series_type,
            "seasons": [
                {"seasonNumber": season["seasonNumber"], "monitored": monitored}
                for season in candidate.get("seasons") or []
                if isinstance(season, dict) and "seasonNumber" in season
            ],
            "addOptions": {
                "monitor": "all" if monitored else "none",
                "searchForMissingEpisodes": search_for_missing_episodes,
                "searchForCutoffUnmetEpisodes": False,
            },
        }
        return self._series(await self._client.object("series", payload=payload))

    async def search_series(self, series_id: PositiveId) -> JsonObject:
        """Queue an active episode search for a series, potentially starting downloads.

        Args:
            series_id: Existing Sonarr series identifier.

        Returns:
            Asynchronous command identifier and current state.
        """
        await self._client.object(f"series/{series_id}")
        return self._view(
            await self._client.object(
                "command", payload={"name": "SeriesSearch", "seriesId": series_id}
            ),
            _COMMAND_FIELDS,
        )

    async def search_episodes(self, episode_ids: EpisodeIds) -> JsonObject:
        """Queue an active search for episodes, potentially starting downloads.

        Args:
            episode_ids: Between 1 and 100 positive Sonarr episode identifiers.

        Returns:
            Asynchronous command identifier and current state.
        """
        return self._view(
            await self._client.object(
                "command",
                payload={"name": "EpisodeSearch", "episodeIds": list(dict.fromkeys(episode_ids))},
            ),
            _COMMAND_FIELDS,
        )

    async def command_status(self, command_id: PositiveId) -> JsonObject:
        """Read the status of a previously queued search command.

        Args:
            command_id: Command identifier returned by a search operation.

        Returns:
            Command status and timestamps without internal exceptions or payloads.
        """
        return self._view(await self._client.object(f"command/{command_id}"), _COMMAND_FIELDS)
