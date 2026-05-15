import logging
from datetime import date
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class ImmichError(Exception):
    pass


class ImmichClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        verify_tls: bool = True,
        timeout: float = 15.0,
    ):
        if not base_url:
            raise ValueError("immich.base_url is required")
        if not api_key:
            raise ValueError("immich.api_key is required")

        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=f"{self.base_url}/api",
            headers={"x-api-key": api_key, "Accept": "application/json"},
            verify=verify_tls,
            timeout=timeout,
        )

    def close(self):
        self._client.close()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            r = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as e:
            raise ImmichError(f"{method} {path} failed: {e}") from e
        if r.status_code >= 400:
            raise ImmichError(f"{method} {path} -> {r.status_code}: {r.text[:200]}")
        return r

    def search_random(self, size: int, with_exif: bool = True) -> list[dict]:
        body = {"size": size, "withExif": with_exif, "type": "IMAGE"}
        return self._request("POST", "/search/random", json=body).json()

    def get_memories(self, for_date: Optional[date] = None) -> list[dict]:
        params = {"for": (for_date or date.today()).isoformat()}
        return self._request("GET", "/memories", params=params).json()

    def list_albums(self) -> list[dict]:
        return self._request("GET", "/albums").json()

    def get_album(self, album_id: str) -> dict:
        return self._request("GET", f"/albums/{album_id}").json()

    def fetch_image(self, asset_id: str, size: str = "preview") -> bytes:
        if size == "original":
            path = f"/assets/{asset_id}/original"
            params = None
        else:
            path = f"/assets/{asset_id}/thumbnail"
            params = {"size": "preview"}
        return self._request("GET", path, params=params).content
