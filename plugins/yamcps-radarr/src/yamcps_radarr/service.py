"""Radarr movie workflows and bounded public response projections."""

from collections.abc import Callable
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import Field

from yamcps_radarr.client import JsonObject, RadarrClient, RadarrError

PositiveId = Annotated[int, Field(gt=0)]
PageSize = Annotated[int, Field(ge=1, le=100)]
MovieIds = Annotated[list[PositiveId], Field(min_length=1, max_length=100)]
SearchTerm = Annotated[str, Field(min_length=1, max_length=200)]
_MOVIE_FIELDS = "id title originalTitle tmdbId imdbId year status monitored qualityProfileId path rootFolderPath titleSlug overview studio runtime hasFile isAvailable minimumAvailability inCinemas digitalRelease physicalRelease genres"
_COMMAND_FIELDS = "id name status queued started ended"


class RadarrService:
    """Implement read and mutation tools for one configured movie library."""

    def __init__(self, client: RadarrClient, redact: Callable[[str], str]) -> None:
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

    async def system_status(self) -> JsonObject:
        """Check connectivity and report the Radarr version and instance status.

        Returns:
            Public version and runtime information without server configuration.
        """
        return self._view(
            await self._client.object("system/status"),
            "version appName instanceName startTime osName isDocker runtimeVersion branch",
        )

    async def list_movies(self, query: str | None = None) -> list[JsonObject]:
        """List existing movies, optionally filtering their titles.

        Args:
            query: Optional case-insensitive title substring.

        Returns:
            Movie summaries with Radarr and TMDB identifiers.
        """
        values = await self._client.array("movie")
        return [
            self._view(item, _MOVIE_FIELDS)
            for item in values
            if not query or query.casefold() in str(item.get("title", "")).casefold()
        ]

    async def get_movie(self, movie_id: PositiveId) -> JsonObject:
        """Read one existing movie.

        Args:
            movie_id: Positive Radarr movie identifier, not a TMDB identifier.

        Returns:
            Movie metadata, availability and local-file presence.
        """
        return self._view(await self._client.object(f"movie/{movie_id}"), _MOVIE_FIELDS)

    async def calendar(
        self, start: date, end: date, include_unmonitored: bool = False
    ) -> list[JsonObject]:
        """Read the movie release calendar for an explicit date interval.

        Args:
            start: ISO start date sent to Radarr.
            end: ISO end date sent to Radarr; must not precede start.
            include_unmonitored: Include movies that are not monitored.

        Returns:
            Movie summaries with cinema, digital and physical release dates.

        Raises:
            RadarrError: The interval is reversed.
        """
        if end < start:
            raise RadarrError("Calendar end must not precede start")
        values = await self._client.array(
            "calendar",
            params={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "unmonitored": include_unmonitored,
            },
        )
        return [self._view(item, _MOVIE_FIELDS) for item in values]

    async def queue(self, page: PositiveId = 1, page_size: PageSize = 20) -> JsonObject:
        """Read one page of the download queue.

        Args:
            page: One-based page number.
            page_size: Page size between 1 and 100.

        Returns:
            Pagination metadata and bounded movie download records.
        """
        value = await self._client.object("queue", params={"page": page, "pageSize": page_size})
        result = self._view(value, "page pageSize totalRecords")
        records = value.get("records")
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise RadarrError("Radarr returned an unexpected queue format")
        result["records"] = [
            self._view(
                item,
                "id movieId title size sizeleft status trackedDownloadStatus trackedDownloadState estimatedCompletionTime timeleft",
            )
            for item in records
        ]
        return result

    async def lookup_movies(self, term: SearchTerm) -> list[JsonObject]:
        """Search the external movie catalog without adding anything.

        Args:
            term: Movie title or tmdb:<id> query.

        Returns:
            Candidate movies with TMDB identifiers for a later add operation.
        """
        if not term.strip():
            raise RadarrError("A nonempty catalog search term is required")
        return [
            self._view(item, _MOVIE_FIELDS)
            for item in await self._client.array("movie/lookup", params={"term": term})
        ]

    async def quality_profiles(self) -> list[JsonObject]:
        """List quality profiles available for adding a movie.

        Returns:
            Profile identifiers and display names.
        """
        return [self._view(item, "id name") for item in await self._client.array("qualityprofile")]

    async def root_folders(self) -> list[JsonObject]:
        """List configured library roots available for adding a movie.

        Returns:
            Root identifiers, paths, available space and accessibility.
        """
        return [
            self._view(item, "id path freeSpace accessible")
            for item in await self._client.array("rootfolder")
        ]

    async def _catalog_entry(self, tmdb_id: int) -> JsonObject:
        if await self._client.array("movie", params={"tmdbId": tmdb_id}):
            raise RadarrError("This TMDB movie already exists in Radarr")
        candidates = await self._client.array("movie/lookup", params={"term": f"tmdb:{tmdb_id}"})
        candidate = next((item for item in candidates if item.get("tmdbId") == tmdb_id), None)
        if candidate is None or not candidate.get("title"):
            raise RadarrError("TMDB movie not found in the Radarr catalog")
        return candidate

    async def _add_root(self, quality_profile_id: int, root_folder_id: int) -> JsonObject:
        profiles = await self._client.array("qualityprofile")
        if not any(item.get("id") == quality_profile_id for item in profiles):
            raise RadarrError("Quality profile does not exist; use radarr_quality_profiles")
        roots = await self._client.array("rootfolder")
        root = next((item for item in roots if item.get("id") == root_folder_id), None)
        if root is None or not root.get("path"):
            raise RadarrError("Root folder does not exist; use radarr_root_folders")
        return root

    async def add_movie(
        self,
        tmdb_id: PositiveId,
        quality_profile_id: PositiveId,
        root_folder_id: PositiveId,
        monitored: bool = True,
        search_for_movie: bool = False,
        minimum_availability: Literal["announced", "inCinemas", "released"] = "released",
    ) -> JsonObject:
        """Add a catalog movie to Radarr; an optional search may start a download.

        Args:
            tmdb_id: TMDB identifier obtained from radarr_lookup_movies.
            quality_profile_id: Existing profile from radarr_quality_profiles.
            root_folder_id: Existing root from radarr_root_folders.
            monitored: Monitor only this movie, without adding its collection.
            search_for_movie: Start an active download search after adding.
            minimum_availability: Release stage at which the movie becomes available.

        Returns:
            The created movie; this does not confirm a download has completed.

        Raises:
            RadarrError: The movie exists or required catalog/profile/root data is absent.
        """
        candidate = await self._catalog_entry(tmdb_id)
        root = await self._add_root(quality_profile_id, root_folder_id)
        payload = {
            "tmdbId": tmdb_id,
            "title": candidate["title"],
            "qualityProfileId": quality_profile_id,
            "rootFolderPath": root["path"],
            "monitored": monitored,
            "minimumAvailability": minimum_availability,
            "addOptions": {
                "monitor": "movieOnly" if monitored else "none",
                "searchForMovie": search_for_movie,
            },
        }
        return self._view(await self._client.object("movie", payload=payload), _MOVIE_FIELDS)

    async def search_movies(self, movie_ids: MovieIds) -> JsonObject:
        """Queue an active movie search that may start downloads.

        Args:
            movie_ids: Between 1 and 100 positive existing Radarr movie identifiers.

        Returns:
            Asynchronous command identifier and current state.
        """
        return self._view(
            await self._client.object(
                "command",
                payload={
                    "name": "MoviesSearch",
                    "movieIds": list(dict.fromkeys(movie_ids)),
                },
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
