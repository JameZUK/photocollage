import logging
import os
import random
import time
from datetime import date
from typing import Callable, Optional

from immich_client import ImmichClient, ImmichError

logger = logging.getLogger(__name__)


class _TTLCache:
    def __init__(self, ttl_seconds: int):
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[float, object]] = {}

    def get_or_set(self, key: str, producer: Callable[[], object]):
        if self.ttl <= 0:
            return producer()
        now = time.monotonic()
        hit = self._store.get(key)
        if hit and (now - hit[0]) < self.ttl:
            return hit[1]
        value = producer()
        self._store[key] = (now, value)
        return value


class AssetSource:
    """Picks Immich assets according to weighted strategies."""

    def __init__(self, client: ImmichClient, selection_cfg: dict, cache_cfg: dict):
        self.client = client
        self.weights: dict[str, int] = selection_cfg.get('weights', {})
        self.album_ids: list[str] = selection_cfg.get('album_ids', []) or []
        self.min_assets: int = selection_cfg.get('min_assets_per_collage', 4)
        self._cache = _TTLCache(cache_cfg.get('asset_list_ttl_seconds', 0))

    def pick_assets(self, max_count: int) -> tuple[list[dict], str]:
        strategy = self._pick_strategy()
        logger.info(f"Asset selection strategy: {strategy}")

        assets = self._run_strategy(strategy, max_count)

        if len(assets) < self.min_assets and strategy != 'random':
            logger.info(
                f"Strategy '{strategy}' returned {len(assets)} assets "
                f"(< {self.min_assets}). Falling back to random."
            )
            strategy = 'random'
            assets = self._run_strategy(strategy, max_count)

        return assets, strategy

    def _pick_strategy(self) -> str:
        active = [(k, v) for k, v in self.weights.items() if v > 0]
        if not active:
            return 'random'
        names, weights = zip(*active)
        return random.choices(names, weights=weights, k=1)[0]

    def _run_strategy(self, strategy: str, max_count: int) -> list[dict]:
        try:
            if strategy == 'random':
                return self.client.search_random(size=max_count, with_exif=True)
            if strategy == 'memories':
                return self._memories(max_count)
            if strategy == 'album':
                return self._album(max_count)
        except ImmichError as e:
            logger.error(f"Strategy '{strategy}' failed: {e}")
        return []

    def _memories(self, max_count: int) -> list[dict]:
        memories = self._cache.get_or_set(
            f"memories:{date.today().isoformat()}",
            lambda: self.client.get_memories(),
        )
        if not memories:
            return []
        # Each memory has an 'assets' list. Pick one memory at random, then sample.
        candidates = [m for m in memories if m.get('assets')]
        if not candidates:
            return []
        chosen = random.choice(candidates)
        assets = chosen['assets']
        logger.info(
            f"Memory '{chosen.get('type', '?')}' from "
            f"{chosen.get('data', {}).get('year', '?')} with {len(assets)} assets"
        )
        return random.sample(assets, min(len(assets), max_count))

    def _album(self, max_count: int) -> list[dict]:
        if self.album_ids:
            album_id = random.choice(self.album_ids)
        else:
            albums = self._cache.get_or_set('albums', lambda: self.client.list_albums())
            viable = [a for a in albums if a.get('assetCount', 0) >= self.min_assets]
            if not viable:
                return []
            album_id = random.choice(viable)['id']

        album = self.client.get_album(album_id)
        assets = album.get('assets', [])
        logger.info(f"Album '{album.get('albumName', album_id)}' with {len(assets)} assets")
        if len(assets) > max_count:
            assets = random.sample(assets, max_count)
        return assets


class ImageFetcher:
    """Fetches image bytes from Immich, with an optional on-disk LRU cache."""

    def __init__(self, client: ImmichClient, size: str, cache_cfg: dict):
        self.client = client
        self.size = size if size in ('preview', 'original') else 'preview'
        self.cache_dir = cache_cfg.get('image_dir') or ''
        self.cache_max_bytes = int(cache_cfg.get('image_max_bytes', 0) or 0)
        if self.cache_dir:
            os.makedirs(self.cache_dir, exist_ok=True)

    def fetch(self, asset_id: str) -> Optional[bytes]:
        cache_path = self._cache_path(asset_id)
        if cache_path and os.path.exists(cache_path):
            try:
                with open(cache_path, 'rb') as f:
                    data = f.read()
                os.utime(cache_path)  # bump mtime for LRU
                return data
            except OSError as e:
                logger.warning(f"Cache read failed for {asset_id}: {e}")

        try:
            data = self.client.fetch_image(asset_id, size=self.size)
        except ImmichError as e:
            logger.error(f"Failed to fetch asset {asset_id}: {e}")
            return None

        if cache_path:
            try:
                with open(cache_path, 'wb') as f:
                    f.write(data)
                self._evict_if_needed()
            except OSError as e:
                logger.warning(f"Cache write failed for {asset_id}: {e}")
        return data

    def _cache_path(self, asset_id: str) -> Optional[str]:
        if not self.cache_dir:
            return None
        safe_id = asset_id.replace('/', '_')
        return os.path.join(self.cache_dir, f"{safe_id}_{self.size}.bin")

    def _evict_if_needed(self):
        if self.cache_max_bytes <= 0:
            return
        try:
            entries = []
            total = 0
            for name in os.listdir(self.cache_dir):
                p = os.path.join(self.cache_dir, name)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                entries.append((st.st_mtime, st.st_size, p))
                total += st.st_size
            if total <= self.cache_max_bytes:
                return
            entries.sort()  # oldest first
            for _, size, path in entries:
                if total <= self.cache_max_bytes:
                    break
                try:
                    os.remove(path)
                    total -= size
                except OSError:
                    pass
        except OSError as e:
            logger.warning(f"Cache eviction failed: {e}")
